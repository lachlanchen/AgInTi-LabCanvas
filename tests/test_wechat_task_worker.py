from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_worker():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_task_worker.py"
    spec = importlib.util.spec_from_file_location("wechat_task_worker_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatTaskWorkerTests(unittest.TestCase):
    def test_idle_queue_gate_scans_changes_and_periodic_maintenance_only(self) -> None:
        worker = load_worker()
        signature = (1, 2, 100, 200)

        self.assertTrue(
            worker.idle_queue_scan_due(
                loop=True,
                signature=signature,
                last_idle_signature=None,
                now=10.0,
                next_maintenance_at=70.0,
            )
        )
        self.assertFalse(
            worker.idle_queue_scan_due(
                loop=True,
                signature=signature,
                last_idle_signature=signature,
                now=20.0,
                next_maintenance_at=70.0,
            )
        )
        self.assertTrue(
            worker.idle_queue_scan_due(
                loop=True,
                signature=(1, 2, 101, 201),
                last_idle_signature=signature,
                now=20.0,
                next_maintenance_at=70.0,
            )
        )
        self.assertTrue(
            worker.idle_queue_scan_due(
                loop=True,
                signature=signature,
                last_idle_signature=signature,
                now=70.0,
                next_maintenance_at=70.0,
            )
        )

    def test_queue_activity_signature_changes_after_append(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            self.assertEqual(worker.queue_activity_signature(queue), (0, 0, 0, 0))
            worker.append_jsonl(queue, {"id": "one", "status": "pending"})
            first = worker.queue_activity_signature(queue)
            worker.append_jsonl(queue, {"id": "two", "status": "pending"})
            second = worker.queue_activity_signature(queue)

        self.assertNotEqual(first, (0, 0, 0, 0))
        self.assertNotEqual(first, second)
        self.assertGreater(second[2], first[2])

    def test_compact_worker_stdout_omits_prompt_context_and_result_text(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-compact",
            "chat": "LabAgent",
            "status": "done",
            "request": "private full prompt",
            "context": [{"text": "private chat history"}],
            "result": {
                "message": "reader-facing answer",
                "confirmation": "",
                "files": ["/tmp/report.pdf"],
            },
            "scheduled_recovery_count": 1,
        }
        output = io.StringIO()
        with (
            mock.patch.dict(
                worker.os.environ,
                {"WECHAT_WORKER_COMPACT_STDOUT": "1"},
                clear=False,
            ),
            contextlib.redirect_stdout(output),
        ):
            worker.print_worker_task_result(task)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["worker_task"], "task-compact")
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["file_count"], 1)
        self.assertTrue(payload["has_message"])
        self.assertEqual(payload["scheduled_recovery_count"], 1)
        self.assertNotIn("private full prompt", output.getvalue())
        self.assertNotIn("private chat history", output.getvalue())
        self.assertNotIn("reader-facing answer", output.getvalue())

    def test_idle_loop_wakes_immediately_after_queue_append(self) -> None:
        worker = load_worker()

        class StopLoop(Exception):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text("", encoding="utf-8")
            sleeps = 0

            def sleep_and_append(_seconds: float) -> None:
                nonlocal sleeps
                sleeps += 1
                if sleeps == 1:
                    worker.append_jsonl(queue, {"id": "new", "status": "pending"})
                    return
                raise StopLoop

            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "wechat_task_worker.py",
                        "--queue",
                        str(queue),
                        "--loop",
                        "--poll-seconds",
                        "0.1",
                        "--idle-maintenance-seconds",
                        "60",
                    ],
                ),
                mock.patch.object(worker, "process_one", return_value=False) as process_one,
                mock.patch.object(worker.time, "sleep", side_effect=sleep_and_append),
                self.assertRaises(StopLoop),
            ):
                worker.main()

        self.assertEqual(process_one.call_count, 2)

    def test_completion_audit_repairs_missing_pdf_in_same_worker_session(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "report.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            task = {
                "id": "parent-1",
                "chat": "LabAgent",
                "original_request": "请直接回答。",
                "source": {"local_id": 1, "sender_display": "Prof Ma"},
                "interruptions": [
                    {
                        "incoming_task_id": "child-2",
                        "request": "请同时提供 PDF 报告。",
                        "source": {"local_id": 2, "sender_display": "Prof Ma"},
                    }
                ],
                "worker_policy": {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "medium",
                    "sandbox": "danger-full-access",
                    "timeout_seconds": 300,
                },
            }
            first = {
                "status": "checked",
                "coverage_complete": False,
                "expected_item_ids": ["task:parent-1", "task:child-2"],
                "covered_item_ids": ["task:parent-1"],
                "missing": [
                    {
                        "item_id": "task:child-2",
                        "requirement": "Create and return the requested PDF.",
                        "kind": "artifact",
                    }
                ],
                "repair_recommended": True,
                "complexity": "medium",
            }
            second = {
                "status": "checked",
                "coverage_complete": True,
                "expected_item_ids": ["task:parent-1", "task:child-2"],
                "covered_item_ids": ["task:parent-1", "task:child-2"],
                "missing": [],
                "repair_recommended": False,
                "complexity": "low",
            }
            policies: list[dict[str, object]] = []

            def repair(_task: dict, policy: dict) -> str:
                policies.append(dict(policy))
                return json.dumps(
                    {
                        "message": "直接回答，并附上详细报告。",
                        "files": [str(pdf)],
                        "confirmation": "",
                    },
                    ensure_ascii=False,
                )

            with (
                mock.patch.object(
                    worker,
                    "run_completion_audit",
                    side_effect=[first, second],
                ),
                mock.patch.object(
                    worker,
                    "run_worker_agent_session",
                    side_effect=repair,
                ),
                mock.patch.object(
                    worker,
                    "enforce_reader_facing_pdf_quality",
                    side_effect=lambda _task, candidate: candidate,
                ),
            ):
                result = worker.audit_and_repair_worker_completion(
                    task,
                    {"message": "直接回答。", "confirmation": "", "files": []},
                )

        self.assertEqual(result["files"], [str(pdf)])
        self.assertEqual(policies[0]["model"], "gpt-5.6-sol")
        self.assertEqual(policies[0]["reasoning_effort"], "medium")
        self.assertEqual(task["message_coverage"]["status"], "covered")
        self.assertEqual(
            task["message_coverage"]["covered_item_ids"],
            ["task:parent-1", "task:child-2"],
        )

    def test_completion_audit_recovers_exact_task_pdf_before_agent_repair(self) -> None:
        worker = load_worker()
        first = {
            "status": "unavailable",
            "coverage_complete": False,
            "expected_item_ids": ["task:daily-1"],
            "covered_item_ids": [],
            "missing": [
                {
                    "item_id": "task:daily-1",
                    "requirement": "Create and return the explicitly requested PDF artifact.",
                    "kind": "artifact",
                }
            ],
            "repair_recommended": True,
            "complexity": "medium",
        }
        recovered_audit = {
            "status": "unavailable",
            "coverage_complete": True,
            "expected_item_ids": ["task:daily-1"],
            "covered_item_ids": ["task:daily-1"],
            "missing": [],
            "repair_recommended": False,
            "complexity": "low",
        }
        task = {
            "id": "daily-1",
            "chat": "LabAgent",
            "original_request": "请提供今日研究 PDF。",
            "source": {"local_id": 1, "sender_display": "Researcher"},
            "routine": {"id": "research_summary"},
            "daily_research": {"date": "2026-08-23"},
            "worker_policy": {
                "model": "gpt-5.6-sol",
                "reasoning_effort": "medium",
                "sandbox": "danger-full-access",
                "timeout_seconds": 300,
            },
        }
        recovered = {
            "message": "今日研究简报已完成，PDF 已附上。",
            "confirmation": "",
            "files": ["/tmp/daily-report.pdf"],
            "data": {"artifact_recovery": True},
        }

        with (
            mock.patch.object(
                worker,
                "run_completion_audit",
                side_effect=[first, recovered_audit],
            ),
            mock.patch.object(
                worker,
                "run_worker_agent_session",
                return_value='{"message":"unable","files":[],"no_reply":true}',
            ) as repair_agent,
            mock.patch.object(
                worker,
                "completion_repair_result_usable",
                return_value=False,
            ),
            mock.patch.object(
                worker,
                "recover_completed_research_artifacts",
                return_value=recovered,
            ) as recover,
            mock.patch.object(
                worker,
                "enforce_reader_facing_pdf_quality",
                return_value=recovered,
            ) as quality_gate,
        ):
            result = worker.audit_and_repair_worker_completion(
                task,
                {"message": "正文已完成，但没有 PDF。", "confirmation": "", "files": []},
            )

        self.assertEqual(result["files"], ["/tmp/daily-report.pdf"])
        self.assertEqual(task["message_coverage"]["status"], "covered")
        self.assertTrue(task["completion_audit"]["repair_succeeded"])
        self.assertEqual(
            task["completion_audit"]["attempts"][-1]["stage"],
            "deterministic_artifact_recovery_pre_repair",
        )
        recover.assert_called_once_with(
            task,
            "completion audit requires an exact-task PDF artifact",
            force=True,
        )
        repair_agent.assert_not_called()
        self.assertEqual(quality_gate.call_count, 1)
        quality_gate.assert_any_call(task, recovered)

    def test_completion_audit_repair_names_rejected_source_and_host_recovers_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "organoid-evidence-review.md"
            report.write_text(
                "# Draft\n\nInternal task record.\n\n## Evidence\n\n10.1000/example\n",
                encoding="utf-8",
            )
            rejected_pdf = root / "organoid-evidence-review.pdf"
            rejected_pdf.write_bytes(b"%PDF-1.4\nrejected")
            corrected_pdf = root / "organoid-evidence-review-reader.pdf"
            corrected_pdf.write_bytes(b"%PDF-1.4\ncorrected")
            task = {
                "id": "daily-reader-repair",
                "chat": "LabAgent",
                "artifact_dir": str(root),
                "request": "Prepare and send the daily organoid research PDF.",
                "daily_research": {
                    "report_date": "2026-08-27",
                    "topics": ["organoid evidence"],
                },
                "routine": {"id": "research_summary"},
                "execution_contract": {
                    "required_artifacts": ["compiled_pdf"],
                    "research_evidence": {"required": True},
                    "report_quality": {
                        "required_dimensions": [
                            "source_level_methods_results_and_limitations",
                            "complete_traceable_references",
                        ]
                    },
                },
                "worker_policy": {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "medium",
                    "sandbox": "danger-full-access",
                    "timeout_seconds": 300,
                },
            }
            first = {
                "status": "checked",
                "coverage_complete": False,
                "expected_item_ids": ["task:daily-reader-repair"],
                "covered_item_ids": [],
                "missing": [
                    {
                        "item_id": "task:daily-reader-repair",
                        "requirement": "Rebuild and return the requested PDF.",
                        "kind": "artifact",
                    }
                ],
                "repair_recommended": True,
                "complexity": "medium",
            }
            still_missing = dict(first)
            complete = {
                "status": "checked",
                "coverage_complete": True,
                "expected_item_ids": ["task:daily-reader-repair"],
                "covered_item_ids": ["task:daily-reader-repair"],
                "missing": [],
                "repair_recommended": False,
                "complexity": "low",
            }
            candidate = {
                "message": "The substantive briefing is ready.",
                "confirmation": "",
                "files": [],
                "data": {
                    "report_path": str(report),
                    "pdf_quality_rejections": [
                        {
                            "path": str(rejected_pdf),
                            "issues": [
                                "internal_task_identity",
                                "missing_complete_reference_section",
                            ],
                        }
                    ],
                },
            }
            recovered = {
                "message": "The repaired evidence briefing is attached.",
                "confirmation": "",
                "files": [str(corrected_pdf)],
                "data": {
                    "report_path": str(report),
                    "pdf_quality_rejections": [],
                },
            }
            repair_packets: list[dict[str, object]] = []

            def repair(current_task: dict, _policy: dict) -> str:
                repair_packets.append(dict(current_task["completion_audit_repair"]))
                report.write_text(
                    "# Reader report\n\n## Evidence and sources\n\n"
                    "Method, result, and limitation. DOI: 10.1000/example.\n\n"
                    "## References\n\n1. Example. https://doi.org/10.1000/example\n",
                    encoding="utf-8",
                )
                return json.dumps(
                    {
                        "message": "I revised the reader-facing source.",
                        "files": [str(report)],
                        "confirmation": "",
                    }
                )

            with (
                mock.patch.object(
                    worker,
                    "run_completion_audit",
                    side_effect=[first, still_missing, complete],
                ),
                mock.patch.object(
                    worker,
                    "recover_completed_research_artifacts",
                    side_effect=[None, recovered],
                ),
                mock.patch.object(
                    worker,
                    "run_worker_agent_session",
                    side_effect=repair,
                ),
                mock.patch.object(
                    worker,
                    "enforce_reader_facing_pdf_quality",
                    side_effect=lambda _task, value: value,
                ),
            ):
                result = worker.audit_and_repair_worker_completion(task, candidate)

        artifact_repair = repair_packets[0]["artifact_repair"]
        self.assertIn(
            "internal_task_identity",
            artifact_repair["rejected_artifacts"][0]["issues"],
        )
        self.assertEqual(
            artifact_repair["source_candidates"][0]["path"],
            str(report.resolve()),
        )
        self.assertEqual(result["files"], [str(corrected_pdf)])
        self.assertEqual(task["message_coverage"]["status"], "covered")
        self.assertTrue(task["completion_audit"]["repair_succeeded"])

    def test_completion_audit_does_not_redeliver_recovered_low_quality_pdf(self) -> None:
        worker = load_worker()
        first = {
            "status": "checked",
            "coverage_complete": False,
            "expected_item_ids": ["task:research-1"],
            "covered_item_ids": [],
            "missing": [
                {
                    "item_id": "task:research-1",
                    "requirement": "Create and return the requested PDF artifact.",
                    "kind": "artifact",
                }
            ],
            "repair_recommended": False,
            "complexity": "medium",
        }
        task = {
            "id": "research-1",
            "chat": "LabAgent",
            "original_request": "请提供有证据的研究 PDF。",
            "source": {"local_id": 2, "sender_display": "Researcher"},
            "routine": {"id": "research_summary"},
        }
        recovered = {
            "message": "PDF 已附上。",
            "confirmation": "",
            "files": ["/tmp/internal-work-record.pdf"],
            "data": {"artifact_recovery": True},
        }
        rejected = {
            **recovered,
            "files": [],
            "data": {
                "artifact_recovery": True,
                "pdf_quality_rejections": [
                    {
                        "filename": "internal-work-record.pdf",
                        "issues": ["agent_output_contract"],
                    }
                ],
            },
        }

        with (
            mock.patch.object(worker, "run_completion_audit", return_value=first),
            mock.patch.object(
                worker,
                "recover_completed_research_artifacts",
                return_value=recovered,
            ),
            mock.patch.object(
                worker,
                "enforce_reader_facing_pdf_quality",
                return_value=rejected,
            ),
        ):
            result = worker.audit_and_repair_worker_completion(
                task,
                {"message": "正文已完成，但没有 PDF。", "confirmation": "", "files": []},
            )

        self.assertEqual(result["files"], [])
        self.assertEqual(task["message_coverage"]["status"], "supplement_required")
        self.assertEqual(
            task["completion_audit"]["attempts"][-1]["status"],
            "recovered_pdf_failed_reader_quality",
        )

    def test_research_report_evidence_accepts_verified_facts_heading(self) -> None:
        worker = load_worker()
        evidence = worker.research_report_evidence_summary(
            """# Briefing

## 已核实事实

- https://example.org/source-one
- https://example.net/source-two

## 局限

This hypothesis still needs validation.
"""
        )

        self.assertTrue(evidence["has_evidence_section"])
        self.assertTrue(evidence["has_uncertainty"])
        self.assertEqual(evidence["traceable_source_count"], 2)

    def test_completion_repair_replaces_rejected_candidate_artifacts(self) -> None:
        worker = load_worker()
        original = {
            "message": "I found a candidate paper.",
            "confirmation": "",
            "files": ["/tmp/topic-similar-paper.pdf"],
            "data": {"source_identity": "unverified"},
        }
        correction = {
            "message": "The source is a podcast, not that paper.",
            "confirmation": "",
            "files": ["/tmp/source-verification.pdf"],
            "data": {"source_identity": "verified"},
        }

        merged = worker.merge_completion_results(original, correction)

        self.assertEqual(merged["files"], ["/tmp/source-verification.pdf"])
        self.assertNotIn("/tmp/topic-similar-paper.pdf", merged["files"])
        self.assertEqual(merged["data"]["source_identity"], "verified")

    def test_numbered_uncovered_child_is_requeued_once_as_supplement(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "parent-1",
                    "chat": "LabAgent",
                    "status": "done",
                    "result": {"message": "只回答了第一条。", "files": []},
                    "message_coverage": {
                        "status": "supplement_required",
                        "covered_item_ids": ["task:parent-1"],
                        "unresolved_item_ids": ["task:child-2"],
                        "missing": [
                            {
                                "item_id": "task:child-2",
                                "requirement": "提供 PDF。",
                                "kind": "artifact",
                            }
                        ],
                    },
                },
                {
                    "id": "child-2",
                    "chat": "LabAgent",
                    "status": "canceled_superseded",
                    "request": "请提供 PDF。",
                    "original_request": "请提供 PDF。",
                    "superseded_by": "parent-1",
                    "superseded_reason": "merged_as_same_chat_interruption",
                },
            ]
            queue.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 1)
            updated = worker.read_tasks(queue)
            child = next(row for row in updated if row["id"] == "child-2")
            self.assertEqual(child["status"], "pending")
            self.assertEqual(child["coverage_requeue_count"], 1)
            self.assertEqual(child["coverage_status"], "supplement_pending")
            self.assertEqual(
                child["coverage_followup"]["item_id"],
                "task:child-2",
            )
            self.assertNotIn("superseded_by", child)
            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 0)

    def test_numbered_covered_child_stays_superseded_with_receipt(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "parent-1",
                    "status": "done",
                    "message_coverage": {
                        "status": "covered",
                        "covered_item_ids": ["task:parent-1", "task:child-2"],
                        "unresolved_item_ids": [],
                        "missing": [],
                    },
                },
                {
                    "id": "child-2",
                    "status": "canceled_superseded",
                    "superseded_by": "parent-1",
                },
            ]
            queue.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 0)
            child = worker.read_tasks(queue)[1]

        self.assertEqual(child["status"], "canceled_superseded")
        self.assertEqual(child["coverage_status"], "covered")

    def test_reconcile_repairs_pdf_requirement_inferred_from_transport_policy(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "finder-780",
                        "chat": "Shares",
                        "status": "done",
                        "request": (
                            "Worker policy.\n\n"
                            "Current coalesced request:\n"
                            "Chen: New WeChat file/link item received; inspect its "
                            "message metadata, card/link fields, and recent synced "
                            "files/media, then summarize or process it.\n"
                            "metadata: [WeChat video channel]\n"
                            "title: Example\n\n"
                            "Link/read-later inbox source received. Do not include "
                            "PDF unless explicitly requested.\n"
                            "Structured source text:\nExample"
                        ),
                        "message_coverage": {
                            "status": "supplement_required",
                            "expected_item_ids": ["task:finder-780"],
                            "covered_item_ids": [],
                            "unresolved_item_ids": ["task:finder-780"],
                            "missing": [
                                {
                                    "item_id": "task:finder-780",
                                    "requirement": "Create the explicitly requested PDF.",
                                    "kind": "artifact",
                                }
                            ],
                        },
                    }
                ],
            )

            requeued = worker.reconcile_numbered_message_coverage(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertEqual(requeued, 0)
        self.assertEqual(stored["status"], "done")
        self.assertEqual(stored["coverage_status"], "covered")
        self.assertEqual(stored["message_coverage"]["missing"], [])
        self.assertEqual(
            stored["message_coverage"]["covered_item_ids"],
            ["task:finder-780"],
        )
        self.assertEqual(stored["message_coverage"]["unresolved_item_ids"], [])

    def test_legacy_child_absent_from_parent_ledger_is_requeued(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "parent-1",
                        "status": "done",
                        "message_coverage": {
                            "status": "covered",
                            "covered_item_ids": ["task:parent-1"],
                            "unresolved_item_ids": [],
                            "missing": [],
                        },
                    },
                    {
                        "id": "legacy-child",
                        "status": "canceled_superseded",
                        "request": "A row truncated by an older merge cap.",
                        "original_request": "A row truncated by an older merge cap.",
                        "superseded_by": "parent-1",
                    },
                ],
            )

            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 1)
            child = worker.read_tasks(queue)[1]

        self.assertEqual(child["status"], "pending")
        self.assertEqual(child["coverage_status"], "supplement_pending")
        self.assertEqual(
            child["coverage_followup"]["item_id"],
            "task:legacy-child",
        )

    def test_coverage_followup_cannot_be_merged_again(self) -> None:
        worker = load_worker()
        parent = {
            "id": "parent-1",
            "chat": "LabAgent",
            "request": "先回答原问题。",
            "status": "in_progress",
        }
        supplement = {
            "id": "child-2",
            "chat": "LabAgent",
            "request": "补充被遗漏的 PDF。",
            "status": "pending",
            "coverage_followup": {
                "item_id": "task:child-2",
                "parent_task_id": "parent-1",
            },
        }

        self.assertFalse(worker.same_chat_interruption_target(parent, supplement))
        self.assertFalse(worker.same_chat_interruption_target(supplement, parent))

    def test_cross_sender_update_interrupts_only_agent_selected_active_task(self) -> None:
        worker = load_worker()
        parent = {
            "id": "active-report",
            "chat": "wecom:group:labagent",
            "status": "in_progress",
            "source": {
                "local_id": 10,
                "sender": "member-a",
                "message_table": "messages",
            },
            "route_decision": {"route_kind": "research_or_summary"},
        }
        related = {
            "id": "related-update",
            "chat": "wecom:group:labagent",
            "status": "pending",
            "source": {
                "local_id": 11,
                "sender": "member-b",
                "message_table": "messages",
            },
            "route_decision": {
                "route_kind": "paper_figure",
                "active_task_relation": "interrupt",
                "active_task_id": "active-report",
            },
        }
        independent = {
            **related,
            "id": "independent",
            "route_decision": {
                "route_kind": "paper_figure",
                "active_task_relation": "independent",
                "active_task_id": "",
            },
        }

        self.assertTrue(worker.same_chat_interruption_target(parent, related))
        self.assertFalse(worker.same_chat_interruption_target(parent, independent))

    def test_file_intake_never_absorbs_later_video_generation(self) -> None:
        worker = load_worker()
        intake = {
            "id": "file-46",
            "chat": "MEMO",
            "status": "in_progress",
            "source": {"local_id": 46, "message_table": "messages"},
            "route_decision": {"route_kind": "file_intake"},
            "routine": {"id": "file_intake"},
        }
        generation = {
            "id": "video-48",
            "chat": "MEMO",
            "status": "pending",
            "source": {"local_id": 48, "message_table": "messages"},
            "route_decision": {"route_kind": "generate_video", "project": "lalachan"},
            "routine": {"id": "generated_video"},
        }

        self.assertFalse(worker.same_chat_interruption_target(intake, generation))

    def test_backend_diagnostics_are_private_no_reply_results(self) -> None:
        worker = load_worker()
        raw = (
            "Worker failed via codex: open error [Errno -3] "
            "Temporary failure in name resolution; transport channel closed"
        )

        result = worker.parse_worker_result(raw)

        self.assertTrue(result["no_reply"])
        self.assertEqual(result["message"], "")
        self.assertEqual(result["files"], [])
        self.assertEqual(
            result["private_failure"]["kind"],
            "transient_backend_unavailable",
        )
        self.assertIn("Temporary failure", result["raw"])

    def test_process_one_never_sends_private_backend_failure(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "failed-backend",
                        "chat": "wecom:group:labagent",
                        "request": "Continue the current discussion.",
                        "status": "pending",
                        "route_decision": {"route_kind": "other_worker"},
                    }
                ],
            )
            raw = (
                "Worker failed via codex: open error [Errno -3] "
                "Temporary failure in name resolution"
            )
            passthrough = lambda _task, result, *_args, **_kwargs: result
            with (
                mock.patch.object(worker, "run_worker_codex", return_value=raw),
                mock.patch.object(
                    worker,
                    "enforce_worker_result_contract",
                    side_effect=passthrough,
                ),
                mock.patch.object(
                    worker,
                    "attach_audio_transcript_reference",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(
                    worker,
                    "prepare_result_files",
                    side_effect=lambda result, *_args, **_kwargs: result,
                ),
                mock.patch.object(
                    worker,
                    "audit_and_repair_worker_completion",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(worker, "record_event"),
                mock.patch.object(worker, "send_result_with_retries") as sender,
            ):
                self.assertTrue(
                    worker.process_one(
                        queue,
                        "wecom:group:labagent",
                        send=True,
                        send_targets=Path(tmp) / "targets.json",
                        log_idle=False,
                    )
                )
            stored = worker.find_task(queue, "failed-backend")

        sender.assert_not_called()
        self.assertEqual(stored["status"], "worker_failed")
        self.assertTrue(stored["result"]["no_reply"])
        self.assertEqual(
            stored["worker_error"]["type"],
            "transient_backend_unavailable",
        )

    def test_process_one_sends_one_safe_terminal_feedback_for_interactive_failure(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "interactive-failed-backend",
                        "chat": "wecom:group:labagent",
                        "request": "请继续处理这个研究任务。",
                        "status": "pending",
                        "source": {
                            "message_table": "messages",
                            "local_id": 42,
                            "server_id": "server-42",
                        },
                        "route_decision": {"route_kind": "other_worker"},
                    }
                ],
            )
            raw = (
                "Worker failed via codex: open error [Errno -3] "
                "Temporary failure in name resolution"
            )
            passthrough = lambda _task, result, *_args, **_kwargs: result
            with (
                mock.patch.object(worker, "run_worker_codex", return_value=raw),
                mock.patch.object(
                    worker,
                    "enforce_worker_result_contract",
                    side_effect=passthrough,
                ),
                mock.patch.object(
                    worker,
                    "attach_audio_transcript_reference",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(
                    worker,
                    "prepare_result_files",
                    side_effect=lambda result, *_args, **_kwargs: result,
                ),
                mock.patch.object(
                    worker,
                    "audit_and_repair_worker_completion",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(worker, "record_event"),
                mock.patch.object(
                    worker,
                    "send_result_with_retries",
                    return_value=[],
                ) as sender,
            ):
                self.assertTrue(
                    worker.process_one(
                        queue,
                        "wecom:group:labagent",
                        send=True,
                        send_targets=Path(tmp) / "targets.json",
                        log_idle=False,
                    )
                )
            stored = worker.find_task(queue, "interactive-failed-backend")

        sender.assert_called_once()
        delivered = sender.call_args.args[0]
        self.assertEqual(
            delivered["message"],
            "这次任务没有完成，已停止重试，不会重复发送。",
        )
        self.assertNotIn("codex", delivered["message"].lower())
        self.assertNotIn("name resolution", delivered["message"].lower())
        self.assertEqual(stored["status"], "worker_failed")
        self.assertEqual(stored["terminal_failure_feedback"]["status"], "sent")
        self.assertEqual(
            stored["worker_error"]["type"],
            "transient_backend_unavailable",
        )

    def test_merge_keeps_more_than_twenty_numbered_interruptions(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "parent",
                    "chat": "LabAgent",
                    "request": "message 0",
                    "status": "in_progress",
                    "source": {
                        "message_table": "messages",
                        "local_id": 1,
                        "sender": "member-a",
                    },
                    "route_decision": {
                        "route_kind": "research_or_summary",
                        "worker_needed": True,
                    },
                }
            ]
            rows.extend(
                {
                    "id": f"child-{index}",
                    "chat": "LabAgent",
                    "request": f"message {index}",
                    "original_request": f"message {index}",
                    "status": "pending",
                    "source": {
                        "message_table": "messages",
                        "local_id": index + 1,
                        "sender": "member-a",
                    },
                    "route_decision": {
                        "route_kind": "research_or_summary",
                        "worker_needed": True,
                    },
                }
                for index in range(1, 26)
            )
            worker.write_tasks(queue, rows)

            merged = worker.merge_existing_pending_interruptions(queue)
            stored = worker.read_tasks(queue)
            parent = stored[0]

        self.assertEqual(merged, 25)
        self.assertEqual(len(parent["interruptions"]), 25)
        self.assertEqual(
            [item["incoming_task_id"] for item in parent["interruptions"]],
            [f"child-{index}" for index in range(1, 26)],
        )

    def test_task_interruption_keeps_complete_focused_request(self) -> None:
        worker = load_worker()
        policy_prefix = "Reusable worker policy. " * 500
        focused = (
            "Chen: summarize the first source carefully.\n"
            "Chen: compare it with the second source and answer both requests."
        )
        incoming = {
            "id": "child-focused",
            "request": (
                f"{policy_prefix}\n\n"
                "Current coalesced request:\n"
                f"{focused}\n\n"
                "Recent history:\n"
                "Old unrelated chat history."
            ),
            "original_request": "fallback text",
            "source": {
                "message_table": "messages",
                "local_id": 27,
                "sender": "member-a",
            },
        }

        interruption = worker.build_task_interruption({"id": "parent"}, incoming)

        self.assertEqual(interruption["request"], focused)
        self.assertEqual(
            interruption["request_excerpt"],
            "Chen: summarize the first source carefully. "
            "Chen: compare it with the second source and answer both requests.",
        )
        self.assertNotIn("Reusable worker policy", interruption["request"])
        self.assertNotIn("Old unrelated chat history", interruption["request"])

    def test_worker_response_policy_is_exact_chat_and_transport_scoped(self) -> None:
        worker = load_worker()
        echomind = worker.worker_response_policy({"chat": "EchoMind", "route": {"transport": "wechat"}})
        labagent = worker.worker_response_policy(
            {
                "chat": "wecom:external:group:abc",
                "route": {"transport": "wecom"},
                "response_policy": {
                    "profile_id": "labagent",
                    "chat_purpose": "labagent_research_drawing_and_design",
                    "automatic_multilingual": False,
                    "language_mode": "match_requester_language",
                },
            }
        )

        self.assertTrue(echomind["automatic_multilingual"])
        self.assertFalse(labagent["automatic_multilingual"])
        self.assertFalse(labagent["cross_chat_context_allowed"])
        self.assertEqual(labagent["sender_attribution"], "preserve_each_message_author")
        self.assertEqual(labagent["capability_profile"]["id"], "labagent")
        self.assertTrue(labagent["capability_profile"]["template_profile"])
        self.assertEqual(labagent["chat"], "wecom:external:group:abc")

    def test_worker_prompt_preserves_authors_without_labagent_language_tail(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        task = {
            "id": "wecom-attribution",
            "chat": "wecom:external:group:abc",
            "request": "请根据两位成员的反馈修改图。",
            "route": {"transport": "wecom"},
            "response_policy": {
                "scope": "exact_chat_only",
                "automatic_multilingual": False,
                "language_mode": "match_requester_language",
            },
            "source": {
                "sender": "member-a",
                "sender_display": "megamonster",
                "sender_mention": "megamonster@微信",
                "sender_identity_confidence": "visible_row_label",
            },
            "context": [
                {
                    "sender_display": "megamonster",
                    "sender_identity_confidence": "visible_row_label",
                    "content": "思想上还不够高级",
                },
                {
                    "sender_display": "sunnyyty",
                    "sender_identity_confidence": "visible_row_label",
                    "content": "字太多",
                },
            ],
        }

        def fake_run(prompt: str, **kwargs: object) -> dict[str, object]:
            calls.append({"prompt": prompt, **kwargs})
            return {"ok": True, "message": "done", "thread_id": "worker-thread"}

        with mock.patch.object(worker, "run_codex_session", side_effect=fake_run):
            self.assertEqual(
                worker.run_worker_agent_session(
                    task,
                    {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "low",
                        "sandbox": "danger-full-access",
                        "timeout_seconds": 300,
                    },
                ),
                "done",
            )

        prompt = str(calls[0]["prompt"])
        self.assertIn("Never transfer one person's statement", prompt)
        self.assertIn("Do not append English/Japanese translations", prompt)
        self.assertIn("Name every artifact intended for delivery", prompt)
        self.assertIn("Do not expose task IDs, checksums, UUIDs", prompt)
        self.assertIn("verify that premise before extending it", prompt)
        self.assertIn("Do not replace factual identification", prompt)
        self.assertIn('"sender_display": "megamonster"', prompt)
        self.assertIn('"sender_display": "sunnyyty"', prompt)
        self.assertNotIn("This exact chat is a multilingual language-teaching chat", prompt)
        self.assertEqual(calls[0]["chat_name"], "wecom:external:group:abc")
        self.assertTrue(calls[0]["reuse"])

    def test_wecom_delivery_guard_removes_only_unsolicited_language_tail(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:external:group:abc",
            "request": "请把论文图发回来。",
            "route": {"transport": "wecom"},
            "response_policy": {"automatic_multilingual": False},
        }
        result = {
            "message": "图和可编辑源文件已经完成。\n\nEnglish: Figure completed.\n日本語：図が完成しました。",
            "confirmation": "",
            "files": [],
            "data": {"message": "图和可编辑源文件已经完成。\n\nEnglish: Figure completed.\n日本語：図が完成しました。"},
        }

        worker.enforce_worker_result_response_policy(task, result)

        self.assertEqual(result["message"], "图和可编辑源文件已经完成。")
        self.assertEqual(result["data"]["message"], result["message"])
        self.assertEqual(
            task["response_policy_adjustments"][0]["kind"],
            "removed_unsolicited_multilingual_tail",
        )

    def test_response_guard_preserves_explicit_translation_request(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:external:group:abc",
            "request": "请翻译成中英日三语。",
            "route": {"transport": "wecom"},
            "response_policy": {"automatic_multilingual": False},
        }
        message = "中文内容。\n\nEnglish: English text.\n日本語：日本語。"
        result = {"message": message, "confirmation": "", "files": []}

        worker.enforce_worker_result_response_policy(task, result)

        self.assertEqual(result["message"], message)
        self.assertNotIn("response_policy_adjustments", task)

    def test_response_guard_removes_transport_internal_confirmation(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:external:group:abc",
            "request": "给群里一个研究灵感。",
            "route": {"transport": "wecom"},
            "response_policy": {"automatic_multilingual": False},
        }
        result = {
            "message": "今天的灵感：把血管接入周龄作为独立实验变量。",
            "confirmation": (
                "未在本轮发送；请由 queue_orchestrator 的 "
                "send_result_with_retries 交付并补齐发送证据。"
            ),
            "files": [],
            "data": {
                "confirmation": (
                    "请由 queue_orchestrator 的 send_result_with_retries 交付。"
                )
            },
        }

        worker.enforce_worker_result_response_policy(task, result)

        self.assertEqual(result["confirmation"], "")
        self.assertEqual(result["data"]["confirmation"], "")
        self.assertEqual(
            task["response_policy_adjustments"][0]["kind"],
            "removed_transport_internal_confirmation",
        )

    def test_response_guard_preserves_real_human_confirmation(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:external:group:abc",
            "request": "准备公开视频。",
            "route": {"transport": "wecom"},
            "response_policy": {"automatic_multilingual": False},
        }
        result = {
            "message": "视频和字幕已经准备完成。",
            "confirmation": "是否现在发布到 YouTube？",
            "files": [],
        }

        worker.enforce_worker_result_response_policy(task, result)

        self.assertEqual(result["confirmation"], "是否现在发布到 YouTube？")
        self.assertNotIn("response_policy_adjustments", task)

    def test_research_timeout_recovers_exact_task_report_and_latex_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "weekly_research_briefing.md"
            report.write_text(
                "# Weekly Research Briefing\n\n"
                "> No exact seven-day match was found; three verified open-access papers are reviewed.\n\n"
                "## Evidence\n\nDOI: 10.1000/example. DOI: 10.1000/example-two.\n\n"
                "## Methods\n\nResearch evidence and conclusions.\n" + ("Grounded analysis. " * 50),
                encoding="utf-8",
            )
            source_pdf = root / "source-paper.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nsource")
            compiled_pdf = root / "weekly_research_briefing.en.pdf"

            def fake_compile(_source: Path, _language: str) -> Path:
                compiled_pdf.write_bytes(b"%PDF-1.4\nreport")
                return compiled_pdf

            task = {
                "id": "daily-recovery",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "route_decision": {"route_kind": "research_or_summary"},
                "request": "Prepare and send the research briefing PDF.",
            }
            with mock.patch.object(worker, "ensure_markdown_pdf_companion_for_language", side_effect=fake_compile):
                result = worker.recover_completed_research_artifacts(task, "Worker failed via codex: timeout")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["data"]["require_file_delivery"])
        self.assertEqual(result["data"]["latex_style"], "nature_research_report")
        self.assertEqual(result["files"], [str(compiled_pdf)])
        self.assertFalse(task["worker_result_exhausted"])
        self.assertIn("Weekly Research Briefing", result["message"])

    def test_research_artifact_recovery_rejects_routine_notes_and_nonresearch(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "routine_contract.md").write_text(
                "# Contract\n\n## Research\n\nDOI https://example.org\n" + ("instructions " * 100),
                encoding="utf-8",
            )
            research = {
                "id": "notes-only",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
            }
            nonresearch = {
                "id": "cad-task",
                "artifact_dir": str(root),
                "routine": {"id": "cad_design"},
            }

            self.assertIsNone(worker.recover_completed_research_artifacts(research, "timeout"))
            self.assertIsNone(worker.recover_completed_research_artifacts(nonresearch, "timeout", force=True))

    def test_message_only_research_never_recovers_an_unsolicited_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "inspiration.md"
            report.write_text(
                "# Useful inspiration\n\n## Evidence\n\n"
                "DOI: 10.1000/one. DOI: 10.1000/two.\n\n"
                + ("Reader-facing evidence and analysis. " * 40),
                encoding="utf-8",
            )
            task = {
                "id": "message-only-inspiration",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "message_only": True,
                    "artifact_delivery": "forbidden",
                },
                "request": "Return exactly one natural chat message. Create no files or attachments.",
            }

            result = worker.recover_completed_research_artifacts(
                task,
                "Worker failed via aginti: model_timeout",
                force=True,
            )

        self.assertIsNone(result)

    def test_research_recovery_rejects_internal_worker_record_as_report(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "research-report.md"
            report.write_text(
                "# Organoid research brief\n\n"
                "Task: wecom-inspiration-202608241923-abcdef\n"
                "Chat: wecom:external-gui:group:private\n\n"
                "## Final group message\n\n"
                + ("A useful but chat-sized evidence summary. " * 30)
                + "\n\n## Evidence\n\n"
                "DOI: 10.1000/one. DOI: 10.1000/two.\n\n"
                "## Output contract\n\n"
                '{"message": "", "files": []}\n',
                encoding="utf-8",
            )
            task = {
                "id": "internal-record",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
                "request": "Prepare and send a substantive organoid research PDF.",
            }

            result = worker.recover_completed_research_artifacts(
                task,
                "Worker failed via aginti: model_timeout",
                force=True,
            )

        self.assertIsNone(result)

    def test_research_artifact_recovery_finds_nested_report_directory(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "report"
            report_dir.mkdir()
            report = report_dir / "vascular_integration_report.md"
            report.write_text(
                "# Vascular Integration Report\n\n"
                "## Evidence\n\nDOI: 10.1000/example. DOI: 10.1000/example-two.\n\n"
                "## Experiments\n\n" + ("Direct evidence and limitations. " * 40),
                encoding="utf-8",
            )
            compiled_pdf = report_dir / "vascular_integration_report.en.pdf"

            def fake_compile(_source: Path, _language: str) -> Path:
                compiled_pdf.write_bytes(b"%PDF-1.4\nreport")
                return compiled_pdf

            task = {
                "id": "nested-report",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "artifact_recovery_only": True,
                "request": "Generate Markdown and a polished PDF; send the PDF to the group.",
            }
            with mock.patch.object(worker, "ensure_markdown_pdf_companion_for_language", side_effect=fake_compile):
                result = worker.recover_completed_research_artifacts(task, force=True)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["files"], [str(compiled_pdf)])
        self.assertEqual(result["message"], "研究报告已完成，PDF 已附上。")

    def test_research_recovery_sends_markdown_only_when_delivery_is_explicit(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "evidence_report.md"
            report.write_text(
                "# Evidence Report\n\n## Evidence\n\n"
                "DOI: 10.1000/one. DOI: 10.1000/two.\n\n"
                + ("Evidence and limitations. " * 40),
                encoding="utf-8",
            )
            pdf = report.with_suffix(".pdf")
            pdf.write_bytes(b"%PDF-1.4\nreport")
            task = {
                "id": "source-delivery",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "request": "Please send the Markdown source files too.",
            }

            result = worker.recover_completed_research_artifacts(task, force=True)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["files"], [str(pdf), str(report)])

    def test_research_recovery_prefers_existing_typeset_sibling_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "evidence_report.md"
            report.write_text(
                "# Evidence Report\n\n"
                "## Evidence\n\nDOI: 10.1000/one. DOI: 10.1000/two.\n\n"
                "## Limitations\n\n" + ("Evidence and uncertainty. " * 40),
                encoding="utf-8",
            )
            polished_pdf = report.with_suffix(".pdf")
            polished_pdf.write_bytes(b"%PDF-1.4\npolished")
            task = {
                "id": "polished-report",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "artifact_recovery_only": True,
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
            }
            with mock.patch.object(
                worker,
                "ensure_markdown_pdf_companion_for_language",
                side_effect=AssertionError("generic compiler must not replace a typeset report"),
            ):
                result = worker.recover_completed_research_artifacts(task, force=True)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["data"]["report_pdf"], str(polished_pdf))
        self.assertEqual(result["files"], [str(polished_pdf)])

    def test_artifact_only_recovery_accepts_one_exact_task_pdf_without_markdown(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "compiled-report.pdf"
            pdf.write_bytes(b"%PDF-1.4\ncompiled")
            task = {
                "id": "compiled-only",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "artifact_recovery_only": True,
                "request": "Prepare an organoid imaging evidence review PDF.",
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
            }

            result = worker.recover_completed_research_artifacts(task, force=True)
            repeated = worker.recover_completed_research_artifacts(task, force=True)
            delivered_pdf = Path(result["files"][0])
            delivery_exists = delivered_pdf.is_file()

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(delivery_exists)
        self.assertNotEqual(delivered_pdf, pdf.resolve())
        self.assertIn("organoid-imaging-evidence-review", delivered_pdf.name)
        self.assertEqual(repeated["files"], result["files"])
        self.assertEqual(result["data"]["recovery_source"], "exact_task_single_pdf")
        self.assertEqual(result["message"], "研究报告已完成，PDF 已附上。")

    def test_automatic_recovery_accepts_one_quality_checked_descriptive_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "2026-08-27-organoid-replay-dataset-briefing.pdf"
            pdf.write_bytes(b"%PDF-1.4\ncompiled")
            task = {
                "id": "descriptive-compiled-only",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "request": "Prepare and send today's organoid research briefing PDF.",
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
            }

            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=[],
            ):
                result = worker.recover_completed_research_artifacts(
                    task,
                    "Worker failed via aginti: max_steps_reached",
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["data"]["recovery_source"], "exact_task_single_pdf")
        self.assertEqual(result["files"], [str(pdf)])

    def test_automatic_recovery_rejects_one_invalid_descriptive_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "daily-research-briefing.pdf").write_bytes(b"%PDF-1.4\ninvalid")
            task = {
                "id": "invalid-compiled-only",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "request": "Prepare and send today's research briefing PDF.",
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
            }

            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=["internal_task_identity"],
            ):
                result = worker.recover_completed_research_artifacts(
                    task,
                    "Worker failed via aginti: max_steps_reached",
                )

        self.assertIsNone(result)

    def test_research_recovery_rejects_report_without_traceable_sources(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "unsupported_report.md"
            report.write_text(
                "# Unsupported Report\n\n## Evidence\n\n"
                + ("This report makes an unsupported claim. " * 60),
                encoding="utf-8",
            )
            task = {
                "id": "unsupported-report",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
            }

            result = worker.recover_completed_research_artifacts(task, force=True)

        self.assertIsNone(result)

    def test_android_group_reply_does_not_mention_local_owner(self) -> None:
        worker = load_worker()
        task = {
            "source": {
                "transport": "wecom",
                "wecom_transport_channel": "wecom_android",
                "wecom_chat_type": "group",
                "sender": "local-owner:lachlan",
                "reply_mentions": ["Lachlan"],
            }
        }
        with mock.patch.object(worker, "ready_wecom_android_transport", return_value=("http://127.0.0.1:19581", "token")):
            self.assertEqual(
                worker.wecom_native_reply_mentions(task, "http://127.0.0.1:19581"),
                [],
            )

    def test_unique_paths_keeps_each_delivery_artifact_once(self) -> None:
        worker = load_worker()
        paths = [Path("/tmp/report.zh.pdf"), Path("/tmp/report.en.pdf"), Path("/tmp/report.zh.pdf")]

        result = worker.unique_paths(paths)

        self.assertEqual(result, [Path("/tmp/report.zh.pdf"), Path("/tmp/report.en.pdf")])

    def test_no_reply_worker_output_is_silent_even_with_explanation(self) -> None:
        worker = load_worker()
        result = worker.parse_worker_result(
            '{"message":"NO_REPLY：这是机器人上一轮消息的回声，不要再次发送。","files":[]}'
        )

        self.assertTrue(result["no_reply"])
        self.assertEqual(result["message"], "")
        self.assertFalse(worker.should_send_worker_result({}, result))

    def test_worker_send_boundary_drops_no_reply_text(self) -> None:
        worker = load_worker()
        sent: list[str] = []
        original_guard = worker.guarded_send_target
        original_send = worker.send_message
        try:
            worker.guarded_send_target = lambda *_args, **_kwargs: {"name": "EchoMind"}
            worker.send_message = lambda message, *_args, **_kwargs: sent.append(message)
            worker.send_result_once(
                {"message": "noreply: internal", "confirmation": "", "files": [], "no_reply": True},
                "EchoMind",
                Path("/tmp/no-targets.json"),
            )
        finally:
            worker.guarded_send_target = original_guard
            worker.send_message = original_send

        self.assertEqual(sent, [])

    def test_parse_worker_result_extracts_json_from_aginti_logs(self) -> None:
        worker = load_worker()
        raw = """AgInTi: starting fallback backend
stdout: preparing tool context
```json
{"message": "完成：我已经把结果整理好了。", "files": ["/tmp/result.pdf"], "confirmation": ""}
```
stderr: noisy internal trace
"""

        result = worker.parse_worker_result(raw)

        self.assertEqual(result["message"], "完成：我已经把结果整理好了。")
        self.assertEqual(result["files"], ["/tmp/result.pdf"])
        self.assertNotIn("AgInTi: starting", result["message"])

    def test_parse_worker_result_does_not_treat_message_prose_as_file_path(self) -> None:
        worker = load_worker()
        raw = json.dumps(
            {
                "message": "Evidence note saved to output/task/evidence-note.md",
                "file": "output/task/evidence-note.md",
            }
        )

        result = worker.parse_worker_result(raw)

        self.assertEqual(result["files"], ["output/task/evidence-note.md"])

    def test_parse_worker_result_sanitizes_unstructured_backend_logs(self) -> None:
        worker = load_worker()
        raw = "aginti: startup\nstdout: hidden details\nUseful result line\nbackend: aginti"

        result = worker.parse_worker_result(raw)

        self.assertEqual(result["message"], "Useful result line")

    def test_parse_worker_result_sanitizes_structured_message_logs(self) -> None:
        worker = load_worker()
        raw = json.dumps(
            {
                "message": "backend: codex\nstdout: internal details\n报告已经完成。",
                "confirmation": "sandbox: read-only\n请确认是否公开发布。",
                "files": [],
            },
            ensure_ascii=False,
        )

        result = worker.parse_worker_result(raw)

        self.assertEqual(result["message"], "报告已经完成。")
        self.assertEqual(result["confirmation"], "请确认是否公开发布。")

    def test_parse_worker_result_drops_log_only_output(self) -> None:
        worker = load_worker()

        result = worker.parse_worker_result("backend: aginti\nstdout: internal\nstderr: trace")

        self.assertEqual(result["message"], "")
        self.assertFalse(result["files"])

    def test_supervisor_worker_uses_guarded_selftest_entrypoint(self) -> None:
        supervisor = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_supervisor_tmux.sh"
        wrapper = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_worker_guarded_loop.sh"

        self.assertTrue(wrapper.exists())
        self.assertTrue(wrapper.stat().st_mode & 0o111)
        supervisor_text = supervisor.read_text(encoding="utf-8")
        wrapper_text = wrapper.read_text(encoding="utf-8")
        self.assertIn("wechat_worker_guarded_loop.sh", supervisor_text)
        self.assertIn('WORKER_COUNT="${WECHAT_WORKER_COUNT:-2}"', supervisor_text)
        self.assertIn("worker_window_name", supervisor_text)
        self.assertIn("direct_monitor_command", supervisor_text)
        self.assertIn('source %q', supervisor_text)
        self.assertIn("wechat selftest --suite all", wrapper_text)
        self.assertIn("wechat_supervisor.local.env", wrapper_text)
        self.assertIn("WECHAT_WORKER_ENV_FILE", wrapper_text)
        self.assertIn('source "$PRIVATE_ENV"', wrapper_text)
        self.assertIn("SELFTEST_SIGNATURE", wrapper_text)
        self.assertIn("worker-selftest.lock", wrapper_text)
        self.assertIn("flock 9", wrapper_text)
        self.assertIn("WECHAT_WORKER_COMPACT_STDOUT", wrapper_text)
        self.assertIn("--extra-root", supervisor_text)
        self.assertIn("output/wecom", supervisor_text)
        self.assertIn("-u WECHAT_AGENT_FORCE_BACKEND", wrapper_text)
        self.assertIn("-u WECHAT_AGENT_FORCE_DISABLE_AGINTI", wrapper_text)
        self.assertIn("-u WECHAT_WORKER_DISABLE_GUI_FILE_DOWNLOAD", wrapper_text)

        wecom_wrapper = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_worker_loop.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("wechat_worker_guarded_loop.sh", wecom_wrapper)
        self.assertNotIn("agenticapp wechat selftest", wecom_wrapper)
        self.assertNotIn("export WECHAT_WORKER_SKIP_SELFTEST=1", wecom_wrapper)

    def test_deterministic_lazyedit_fallback_submits_without_holding_worker(self) -> None:
        worker = load_worker()
        with mock.patch.object(
            worker,
            "run_lazyedit_publish_subprocess",
            return_value={"ok": True, "status": "submitted"},
        ) as run:
            worker.run_lazyedit_publish_command(
                video_id=495,
                platforms=["shipinhao", "youtube"],
                correction_prompt="/tmp/correction.md",
                metadata_prompt="/tmp/metadata.md",
                target=Path("/tmp/video_COMPLETED.mp4"),
            )

        command = run.call_args.args[0]
        shell_command = command[-1]
        self.assertIn("--no-wait", shell_command)
        self.assertNotIn("--wait", shell_command)
        self.assertNotIn("--guided-monitor", shell_command)

    def test_worker_policy_uses_high_for_cad_or_pcb_tasks(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "design a PCB and render the CAD in Blender"})

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "high")
        self.assertEqual(policy["sandbox"], "danger-full-access")
        self.assertEqual(policy["timeout_seconds"], 600)

    def test_worker_policy_uses_xhigh_for_full_autonomous_tasks(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "fully implement this WeChat automation, commit and push"})

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "xhigh")
        self.assertEqual(policy["timeout_seconds"], 1200)

    def test_worker_policy_respects_explicit_high_ceiling_for_protein_structure_tasks(self) -> None:
        worker = load_worker()
        with mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_CODEX_MODEL": "gpt-5.5",
                "WECHAT_WORKER_MIN_EFFORT": "high",
                "WECHAT_WORKER_MAX_EFFORT": "high",
                "WECHAT_WORKER_TIMEOUT_ULTRA_SECONDS": "86400",
            },
            clear=False,
        ):
            policy = worker.choose_worker_policy(
                {"request": "用 AlphaFold 算出 COL1A1 的蛋白结构，并查找靶向这个分子的抑制剂"}
            )

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "high")
        self.assertEqual(policy["timeout_seconds"], 600)

    def test_worker_tool_context_reuses_protein_structure_pipeline(self) -> None:
        worker = load_worker()

        context = worker.build_worker_tool_context(
            {"id": "protein-task", "chat": "LabAgent", "request": "Predict a protein structure"}
        )

        self.assertIn("external/ProteinStructure", context)
        self.assertIn("python -m agenticapp protein start", context)
        self.assertIn("Do not recreate its browser or analysis pipeline", context)

    def test_worker_tool_context_reuses_musia_and_separates_mv_publication(self) -> None:
        worker = load_worker()

        context = worker.build_worker_tool_context(
            {
                "id": "music-task",
                "chat": "LazyResearch",
                "request": "Generate a song and then create an MV.",
                "route_decision": {
                    "route_kind": "music_to_mv",
                    "project": "musia",
                    "public_publish_allowed": False,
                },
                "routine": {"id": "musia_music_to_mv"},
            }
        )

        self.assertIn("python -m agenticapp music submit", context)
        self.assertIn("python -m agenticapp music mv-pack", context)
        self.assertIn("reviewed Musia master", context)
        self.assertIn("independent permissions", context)
        self.assertIn("current request explicitly authorizes", context)

    def test_worker_tool_context_reuses_books_and_pocketpolyglot(self) -> None:
        worker = load_worker()

        context = worker.build_worker_tool_context(
            {
                "id": "polyglot-task",
                "chat": "My devices",
                "request": "Continue this quadrilingual PocketPolyglot book.",
                "route_decision": {
                    "route_kind": "multilingual_book",
                    "project": "zhjpbook",
                },
                "routine": {
                    "id": "multilingual_book",
                    "default_effort": "high",
                },
            }
        )
        policy = worker.choose_worker_policy(
            {
                "request": "Continue this quadrilingual PocketPolyglot book.",
                "routine": {
                    "id": "multilingual_book",
                    "default_effort": "high",
                },
            }
        )

        self.assertIn("python -m agenticapp books search", context)
        self.assertIn("python -m agenticapp books polyglot", context)
        self.assertIn("one durable project per book", context)
        self.assertIn("never download copyrighted material", context)
        self.assertEqual(policy["reasoning_effort"], "high")

    def test_worker_materializes_verified_feedback_without_chat_attachment(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "id": "feedback-task-1",
                "chat": "My devices",
                "request": "Write a bug report for LazyEdit about the missing QR artifact.",
                "source": {"local_id": 11, "server_id": "private-source"},
            }
            result = {
                "message": "I verified the gap and recorded it for LazyEdit.",
                "files": [],
                "data": {
                    "upstream_feedback": [
                        {
                            "target": "lazyedit",
                            "kind": "bug",
                            "title": "Job-scoped QR artifact is unavailable",
                            "summary": "The integration cannot retrieve the current login QR.",
                            "expected": "Expose the current job-scoped QR artifact.",
                            "observed": "Only the login blocker state is exposed.",
                            "evidence": ["Inspected the current local publish status response."],
                            "acceptance": ["Return one current QR image for the blocked job."],
                            "verified": True,
                            "transient": False,
                            "deliver_report": False,
                        }
                    ]
                },
            }
            with mock.patch.dict(
                os.environ,
                {"LABCANVAS_FEEDBACK_LAZYEDIT_ROOT": tmp},
            ):
                prepared = worker.prepare_result_files(
                    result,
                    json.dumps(result),
                    task=task,
                )

            reports = task["upstream_feedback_reports"]
            report_path = Path(reports[0]["path"])
            self.assertTrue(report_path.is_file())
            self.assertEqual(prepared["files"], [])
            self.assertIn("handoff/labcanvas", report_path.as_posix())
            report = report_path.read_text(encoding="utf-8")
            self.assertNotIn("feedback-task-1", report)
            self.assertNotIn("private-source", report)

    def test_worker_skips_unverified_or_transient_feedback(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "id": "feedback-task-2",
                "chat": "My devices",
                "request": "Inspect a temporary LazyEdit timeout.",
            }
            result = {
                "message": "The temporary failure was not recorded as a product bug.",
                "files": [],
                "data": {
                    "upstream_feedback": [
                        {
                            "target": "lazyedit",
                            "kind": "bug",
                            "title": "Temporary timeout",
                            "summary": "A temporary timeout occurred.",
                            "observed": "The network was unavailable.",
                            "evidence": ["One transient attempt."],
                            "acceptance": ["No requirement."],
                            "verified": True,
                            "transient": True,
                        },
                        {
                            "target": "lazyedit",
                            "kind": "bug",
                            "title": "Unverified behavior",
                            "summary": "This was not reproduced.",
                            "observed": "Unknown.",
                            "evidence": ["None."],
                            "acceptance": ["Reproduce first."],
                            "verified": False,
                            "transient": False,
                        },
                    ]
                },
            }
            with mock.patch.dict(
                os.environ,
                {"LABCANVAS_FEEDBACK_LAZYEDIT_ROOT": tmp},
            ):
                prepared = worker.prepare_result_files(
                    result,
                    json.dumps(result),
                    task=task,
                )

            self.assertEqual(prepared["files"], [])
            self.assertNotIn("upstream_feedback_reports", task)
            self.assertEqual(
                {item["reason"] for item in task["upstream_feedback_report_errors"]},
                {"transient", "unverified"},
            )
            self.assertFalse((Path(tmp) / "handoff" / "labcanvas").exists())

    def test_worker_tool_context_exposes_feedback_control_plane(self) -> None:
        worker = load_worker()

        context = worker.build_worker_tool_context(
            {
                "id": "feedback-task",
                "chat": "My devices",
                "request": "Write a feature request for Musia.",
                "route_decision": {
                    "route_kind": "cross_repo_feedback",
                    "project": "musia",
                },
                "routine": {"id": "cross_repo_feedback"},
            }
        )

        self.assertIn("python -m agenticapp feedback targets", context)
        self.assertIn("upstream_feedback", context)
        self.assertIn("remains local by default", context)

    def test_worker_policy_uses_medium_for_literature_summary(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "summarize this PDF paper"})

        self.assertEqual(policy["reasoning_effort"], "medium")

    def test_existing_video_publish_policy_uses_gpt_5_6_sol(self) -> None:
        worker = load_worker()
        task = {
            "request": "Publish this exact video.",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "routine": {
                "id": "video_publish_existing",
                "default_effort": "low",
            },
        }

        policy = worker.choose_worker_policy(task)

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "low")

    def test_existing_video_publish_tool_context_pins_exact_platform_allowlist(self) -> None:
        worker = load_worker()
        task = {
            "request": (
                "Current coalesced request:\n"
                "Publish this video to Shipinhao, YouTube, and Instagram."
            ),
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "routine": {"id": "video_publish_existing"},
        }

        context = worker.build_worker_tool_context(task)

        self.assertIn(
            "--platforms shipinhao,youtube,instagram",
            context,
        )
        self.assertIn("must not broaden the platform allowlist", context)
        self.assertIn("Do not use repeated `--platform` flags", context)
        self.assertNotIn("--platforms douyin,", context)

    def test_detect_publish_platforms_supports_explicit_douyin(self) -> None:
        worker = load_worker()
        task = {
            "request": (
                "Current coalesced request:\n"
                "发布到抖音、视频号、YouTube 和 Instagram"
            )
        }

        self.assertEqual(
            worker.detect_publish_platforms(task, current_only=True),
            ["douyin", "shipinhao", "youtube", "instagram"],
        )

    def test_publish_preflight_exposes_exact_target_and_prompt_paths_to_agent(self) -> None:
        worker = load_worker()
        preflight = {
            "autopublish_video": {
                "ok": True,
                "status": "copied",
                "target": "/tmp/exact_COMPLETED.mp4",
            },
            "lazyedit_context": {
                "correction_prompt_file": "/tmp/correction.md",
                "metadata_prompt_file": "/tmp/metadata.md",
            },
        }

        compact = worker.compact_worker_preflight_for_agent(preflight)

        self.assertEqual(
            compact["autopublish_video"]["target"],
            "/tmp/exact_COMPLETED.mp4",
        )
        self.assertIn(
            "/tmp/correction.md",
            compact["lazyedit_context"]["context_paths"],
        )
        self.assertIn(
            "/tmp/metadata.md",
            compact["lazyedit_context"]["context_paths"],
        )

    def test_pending_manual_xyq_lazyedit_handoff_merges_and_closes_target(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            target = {
                "id": "task-xyq",
                "chat": "懒人科研",
                "status": "generation_waiting",
                "request": "Current coalesced request:\nGenerate the approved LALACHAN story video.",
                "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
                "source": {"chat": "懒人科研", "config_id": "lazy.json", "message_table": "MSG", "server_id": "srv-201", "local_id": 201},
                "routine": {"id": "generated_video"},
                "next_poll_at": 999999,
            }
            incoming = {
                "id": "task-202",
                "chat": "懒人科研",
                "status": "pending",
                "request": (
                    "Current coalesced request:\n"
                    "There are two videos in the XYQ session. I already downloaded both to Downloads "
                    "and handed them to LazyEdit for publishing, so do nothing."
                ),
                "route_decision": {
                    "route_kind": "generate_video",
                    "project": "lalachan",
                    "manual_handoff_update": True,
                    "public_publish_allowed": False,
                },
                "source": {"chat": "懒人科研", "config_id": "lazy.json", "message_table": "MSG", "server_id": "srv-202", "local_id": 202},
                "routine": {"id": "generated_video"},
            }
            queue.write_text(
                json.dumps(target, ensure_ascii=False) + "\n" + json.dumps(incoming, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 1)
        self.assertEqual(tasks[0]["status"], "done")
        self.assertEqual(tasks[0]["manual_generated_video_handoff"]["reported_video_count"], 2)
        self.assertTrue(tasks[0]["route_decision"]["manual_handoff_update"])
        self.assertTrue(tasks[0]["route_decision"]["no_new_xyq_submit"])
        self.assertNotIn("next_poll_at", tasks[0])
        self.assertEqual(tasks[1]["status"], "canceled_superseded")
        self.assertEqual(tasks[1]["superseded_reason"], "manual_generated_video_handoff_recorded")

    def test_research_route_blocks_video_publish_preflight_fallback(self) -> None:
        worker = load_worker()
        task = {
            "id": "research-with-boilerplate-video-words",
            "chat": "鏈接",
            "route_decision": {
                "route_kind": "research_or_summary",
                "needs_recent_media": True,
                "public_publish_allowed": False,
            },
            "request": (
                "Handle this WeChat request as backend work. Generic tool playbook mentions "
                "video, subtitle, caption, LazyEdit, AutoPublish, and publish folder.\n\n"
                "Current coalesced request:\n"
                "Summarize this WeChat article card about Michael Jordan and economics."
            ),
        }

        with tempfile.TemporaryDirectory() as tmp:
            preflight = worker.prepare_worker_preflight(task, Path(tmp))

        self.assertEqual(preflight, {})
        self.assertFalse(worker.is_video_publish_task(task))
        self.assertFalse(worker.should_preflight_autopublish(task))

    def test_shipinhao_comment_preflight_reads_exported_json(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            comments = tmp_path / "comment_data" / "shipinhao-comments.json"
            comments.parent.mkdir(parents=True)
            comments.write_text(
                json.dumps(
                    {
                        "objectId": "oid-123",
                        "objectNonceId": "nonce-456",
                        "title": "demo video",
                        "author": "demo author",
                        "source": "finderGetCommentList",
                        "commentInfo": [
                            {
                                "nickname": "A",
                                "content": "@元宝 这个视频的英文全文",
                                "likeCount": 5,
                                "levelTwoComment": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = {
                "id": "shipinhao-preflight",
                "chat": "鏈接",
                "routine": {"id": "research_summary"},
                "route_decision": {"route_kind": "research_or_summary"},
                "request": f"Current coalesced request:\n总结这个视频号，并检查评论 {comments}\n\nRecent history:\n",
            }

            preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")
            manifest_exists = Path(preflight["shipinhao_comment_intel"]["manifest_json"]).is_file()

        intel = preflight["shipinhao_comment_intel"]
        self.assertEqual(intel["status"], "ok")
        self.assertEqual(intel["source_quality"], "comment_hits")
        self.assertTrue(manifest_exists)
        summary = intel["results"][0]["summary"]
        self.assertEqual(summary["comment_count"], 1)
        self.assertIn("@元宝", json.dumps(summary["keyword_hits"], ensure_ascii=False))

    def test_shipinhao_media_manifest_is_not_treated_as_comment_export(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "verified-capture.json"
            manifest.write_text(
                json.dumps(
                    {
                        "object_id": "oid-123",
                        "title": "demo video",
                        "author": "demo author",
                        "status": "verified",
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(worker.shipinhao_comment_json_looks_relevant(manifest))

    def test_mp_weixin_research_runs_read_only_source_recovery_preflight(self) -> None:
        worker = load_worker()
        task = {
            "id": "article-recovery",
            "chat": "鏈接",
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Current coalesced request:\nread https://mp.weixin.qq.com/s/demo\n\nRecent history:\n",
        }
        recovered = {
            "status": "ok",
            "read_only": True,
            "articles": [{"source_quality": "full_article", "markdown_path": "/tmp/article.md"}],
        }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(worker, "recover_task_sources", return_value=recovered) as recover:
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

        self.assertEqual(preflight["wechat_source_recovery"], recovered)
        recover.assert_called_once()

    def test_shipinhao_comment_preflight_auto_discovers_only_exact_export(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_dir = root / "comment_data" / "2026-07-15"
            export_dir.mkdir(parents=True)
            exact = export_dir / "exact.json"
            wrong = export_dir / "wrong.json"
            exact.write_text(
                json.dumps(
                    {
                        "objectId": "1234567890",
                        "objectNonceId": "nonce-exact-123456",
                        "title": "Exact video",
                        "author": "Creator",
                        "commentInfo": [{"content": "useful summary", "nickname": "Reader"}],
                    }
                ),
                encoding="utf-8",
            )
            wrong.write_text(
                json.dumps(
                    {
                        "objectId": "9999999999",
                        "objectNonceId": "nonce-wrong-123456",
                        "title": "Wrong video",
                        "author": "Other",
                        "commentInfo": [{"content": "wrong source"}],
                    }
                ),
                encoding="utf-8",
            )
            task = {
                "id": "shipinhao-auto-discovery",
                "chat": "鏈接",
                "routine": {"id": "research_summary"},
                "route_decision": {"route_kind": "research_or_summary"},
                "request": (
                    "Current coalesced request:\n<finderFeed>"
                    "<objectId><![CDATA[1234567890]]></objectId>"
                    "<objectNonceId><![CDATA[nonce-exact-123456]]></objectNonceId>"
                    "<nickname><![CDATA[Creator]]></nickname>"
                    "<desc><![CDATA[Exact video]]></desc></finderFeed>\n\nRecent history:\n"
                ),
            }
            env = {
                "WECHAT_SHIPINHAO_COMMENT_DIRS": str(root / "comment_data"),
                "WECHAT_WX_CHANNEL_API_URL": "",
                "WECHAT_SHIPINHAO_AUTO_DISCOVER_API": "0",
                "WECHAT_SHIPINHAO_PUBLIC_MIRROR_RECOVERY": "0",
                "WECHAT_SHIPINHAO_AUTO_GUI_CAPTURE": "0",
            }
            with mock.patch.dict(worker.os.environ, env, clear=False):
                preflight = worker.prepare_worker_preflight(task, root / "artifact")

        results = preflight["shipinhao_comment_intel"]["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(Path(results[0]["source_path"]).name, "exact.json")
        self.assertEqual(results[0]["summary"]["title"], "Exact video")

    def test_shipinhao_comment_preflight_marks_missing_source(self) -> None:
        worker = load_worker()
        task = {
            "id": "shipinhao-missing-source",
            "chat": "鏈接",
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Current coalesced request:\n总结这个视频号并看评论里有没有元宝总结。\n\nRecent history:\n",
        }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(worker.os.environ, {"WECHAT_WX_CHANNEL_API_URL": ""}, clear=False):
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

        intel = preflight["shipinhao_comment_intel"]
        self.assertEqual(intel["status"], "not_available")
        self.assertIn("No exported Shipinhao comment JSON", intel["reason"])
        self.assertIn("Do not ask the user to verify", intel["recommended_next"])
        self.assertIn("access_ladder", intel)
        self.assertIn("native_capture", intel)
        self.assertTrue(intel["native_capture"]["read_only"])
        self.assertFalse(intel["native_capture"]["public_actions"])
        self.assertIn("shipinhao_native_capture.py", intel["native_capture"]["command"])

    def test_shipinhao_yuanbao_public_prompt_needs_confirmation(self) -> None:
        worker = load_worker()
        task = {
            "id": "shipinhao-yuanbao",
            "chat": "鏈接",
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Current coalesced request:\n打开这个视频号，@元宝 这个视频的英文全文。\n\nRecent history:\n",
        }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(worker.os.environ, {"WECHAT_WX_CHANNEL_API_URL": ""}, clear=False):
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

        action = preflight["shipinhao_comment_intel"]["yuanbao_public_action"]
        self.assertTrue(action["requested"])
        self.assertFalse(action["allowed_by_default"])
        self.assertEqual(action["status"], "needs_current_per_video_confirmation")

    def test_shipinhao_comment_profile_extracts_wechat_xml_cdata_ids(self) -> None:
        worker = load_worker()
        task = {
            "id": "shipinhao-xml-profile",
            "chat": "鏈接",
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": (
                "Current coalesced request:\n"
                "<finderFeed>"
                "<objectId><![CDATA[14792814475849631952]]></objectId>"
                "<nickname><![CDATA[Roy价值知行荟]]></nickname>"
                "<desc><![CDATA[巴菲特与芒格谈消费品]]></desc>"
                "<objectNonceId><![CDATA[7860797635834206573_4_20_13_1_1782694936919416_bd6fb930-7364-11f1-bc60-fb1d69ad351a]]></objectNonceId>"
                "<megaVideo><objectId><![CDATA[]]></objectId><objectNonceId><![CDATA[]]></objectNonceId></megaVideo>"
                "</finderFeed>\n\nRecent history:\n"
            ),
        }

        profile = worker.extract_shipinhao_comment_profile(task)

        self.assertEqual(profile["object_id"], "14792814475849631952")
        self.assertEqual(
            profile["nonce_id"],
            "7860797635834206573_4_20_13_1_1782694936919416_bd6fb930-7364-11f1-bc60-fb1d69ad351a",
        )

    def test_shipinhao_media_transcript_preflight_uses_exact_card_context(self) -> None:
        worker = load_worker()
        exact_url = "http://wxapp.tc.qq.com/video?id=exact-source"
        wrong_url = "http://wxapp.tc.qq.com/video?id=old-history"
        exact_card = (
            "<finderFeed><objectId><![CDATA[exact-object-123]]></objectId>"
            "<nickname><![CDATA[Exact Creator]]></nickname><desc><![CDATA[Exact subject]]></desc>"
            "<mediaList><media><videoPlayDuration><![CDATA[42]]></videoPlayDuration>"
            f"<url><![CDATA[{exact_url}]]></url></media></mediaList></finderFeed>"
        )
        task = {
            "id": "shipinhao-exact-media",
            "chat": "鏈接",
            "source": {"local_id": 77, "kind": "file/link", "local_type": 219043332145},
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary", "needs_recent_media": True},
            "request": f"Current coalesced request:\nsummarize this video\n\nRecent history:\n{wrong_url}",
            "context": [
                {"local_id": 76, "content": wrong_url},
                {"local_id": 77, "content": exact_card},
            ],
        }
        captured: dict[str, object] = {}

        def fake_transcriber(command, *, output_dir, timeout, profile):
            source_path = Path(command[command.index("--source-text-file") + 1])
            captured["source_text"] = source_path.read_text(encoding="utf-8")
            captured["profile"] = profile
            return {
                "status": "transcribed",
                "agent_context_path": str(output_dir / "shipinhao-audio-transcript.md"),
                "read_only": True,
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(worker, "run_shipinhao_media_transcriber", side_effect=fake_transcriber):
                result = worker.prepare_shipinhao_media_transcript_preflight(task, Path(tmp))

        self.assertEqual(result["status"], "transcribed")
        self.assertIn(exact_url, str(captured["source_text"]))
        self.assertNotIn(wrong_url, str(captured["source_text"]))
        self.assertEqual(captured["profile"]["object_id"], "exact-object-123")

    def test_shipinhao_download_route_promotes_exact_card_video_for_delivery(self) -> None:
        worker = load_worker()
        exact_card = (
            "<finderFeed><objectId><![CDATA[14947210711380400704]]></objectId>"
            "<nickname><![CDATA[Hui世界]]></nickname>"
            "<desc><![CDATA[徒步天堂马德拉群岛]]></desc>"
            "<mediaList><media><videoPlayDuration><![CDATA[63]]></videoPlayDuration>"
            "<url><![CDATA[http://wxapp.tc.qq.com/video?id=exact-download]]></url>"
            "</media></mediaList></finderFeed>"
        )
        task = {
            "id": "shipinhao-download",
            "chat": "🍓My devices",
            "source": {"local_id": 146, "kind": "text", "local_type": 1},
            "routine": {"id": "file_download_save"},
            "route_decision": {
                "route_kind": "file_download_or_save",
                "delivery_mode": "agent_decide",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nCan you download this Shipinhao for me?",
            "context": [{"local_id": 145, "content": exact_card}],
        }

        def fake_transcriber(command, *, output_dir, timeout, profile):
            media = output_dir / "private-cache-source.mp4"
            media.write_bytes(b"verified-video")
            return {
                "status": "transcribed",
                "input_kind": "card_media_url",
                "media_path": str(media),
                "profile": profile,
                "agent_context_path": str(output_dir / "shipinhao-audio-transcript.md"),
                "read_only": True,
            }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "shipinhao_media_transcript"
            with mock.patch.object(worker, "run_shipinhao_media_transcriber", side_effect=fake_transcriber):
                result = worker.prepare_shipinhao_media_transcript_preflight(task, Path(tmp))
            task["preflight"] = {"shipinhao_media_transcript": result}
            delivery_files = worker.shipinhao_auto_delivery_files(task)

        self.assertTrue(worker.should_prepare_shipinhao_media_transcript(task))
        self.assertEqual(result["download_delivery"]["status"], "ready")
        self.assertEqual(len(delivery_files), 1)
        self.assertIn("Hui世界-徒步天堂马德拉群岛", Path(delivery_files[0]).name)
        self.assertFalse(task["route_decision"]["public_publish_allowed"])

    def test_shipinhao_research_summary_promotes_video_and_transcript_by_default(self) -> None:
        worker = load_worker()
        exact_card = (
            "<finderFeed><objectId><![CDATA[14947210711380400704]]></objectId>"
            "<nickname><![CDATA[Hui世界]]></nickname>"
            "<desc><![CDATA[徒步天堂马德拉群岛]]></desc>"
            "<mediaList><media><videoPlayDuration><![CDATA[63]]></videoPlayDuration>"
            "<url><![CDATA[http://wxapp.tc.qq.com/video?id=exact-download]]></url>"
            "</media></mediaList></finderFeed>"
        )
        task = {
            "id": "shipinhao-summary-default-delivery",
            "chat": "Shares鏈接",
            "source": {"local_id": 146, "kind": "file/link"},
            "routine": {"id": "research_summary"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nSummarize this source.",
            "context": [{"local_id": 146, "kind": "file/link", "content": exact_card}],
        }

        def fake_transcriber(command, *, output_dir, timeout, profile):
            media = output_dir / "private-cache-source.mp4"
            media.write_bytes(b"verified-video")
            context = output_dir / "shipinhao-audio-transcript.md"
            context.write_text(
                "## Timestamped Transcript\n\n[00:00.00-00:02.00] 马德拉群岛\n",
                encoding="utf-8",
            )
            return {
                "status": "transcribed",
                "input_kind": "card_media_url",
                "media_path": str(media),
                "profile": profile,
                "agent_context_path": str(context),
                "content_identity_verified": True,
                "read_only": True,
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(worker, "run_shipinhao_media_transcriber", side_effect=fake_transcriber):
                result = worker.prepare_shipinhao_media_transcript_preflight(task, Path(tmp))
            task["preflight"] = {"shipinhao_media_transcript": result}
            files = worker.shipinhao_auto_delivery_files(task)

        self.assertTrue(worker.should_prepare_shipinhao_media_transcript(task))
        self.assertEqual(result["download_delivery"]["status"], "ready")
        self.assertEqual({Path(path).suffix for path in files}, {".mp4", ".txt"})
        self.assertFalse(task["route_decision"]["public_publish_allowed"])

    def test_shipinhao_transcriber_is_pinned_to_configured_gpu(self) -> None:
        worker = load_worker()
        completed = mock.Mock(returncode=1, stdout="", stderr="failed")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                worker.os.environ,
                {"CUDA_VISIBLE_DEVICES": "0", "WECHAT_SHIPINHAO_CUDA_DEVICE": "1"},
                clear=False,
            ), mock.patch.object(worker.subprocess, "run", return_value=completed) as run:
                worker.run_shipinhao_media_transcriber(
                    ["python", "transcribe.py"],
                    output_dir=Path(tmp),
                    timeout=30,
                    profile={"object_id": "exact-object"},
                )

        self.assertEqual(run.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "1")

    def test_shipinhao_delivery_adds_recipient_safe_timestamped_transcript(self) -> None:
        worker = load_worker()
        task = {
            "request": "Current coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr",
            "route_decision": {
                "route_kind": "file_download_or_save",
                "delivery_mode": "chat_attachment",
                "public_publish_allowed": False,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "shipinhao_media_transcript"
            output_dir.mkdir(parents=True)
            media = output_dir / "source.mp4"
            media.write_bytes(b"verified-video")
            context = output_dir / "shipinhao-audio-transcript.md"
            context.write_text(
                "# Shipinhao Audio Transcript\n\n"
                "- Model: `large-v2`\n"
                "- Input: `exact_sph_share_link`\n\n"
                "## Timestamped Transcript\n\n"
                "[00:00.00-00:02.00] 阿拉斯加是美国面积最大的州\n",
                encoding="utf-8",
            )
            result = worker.promote_shipinhao_download_for_delivery(
                task,
                output_dir,
                {
                    "status": "transcribed",
                    "input_kind": "exact_sph_share_link",
                    "media_path": str(media),
                    "agent_context_path": str(context),
                    "duration_seconds": 80.13,
                    "content_identity_verified": True,
                    "profile": {
                        "object_id": "sph-Ae2UMH6gqr",
                        "title": "美国最后的边疆阿拉斯加",
                        "author": "Hui世界",
                    },
                },
            )
            task["preflight"] = {"shipinhao_media_transcript": result}
            files = worker.shipinhao_auto_delivery_files(task)
            transcript_path = Path(result["delivery_transcript_path"])
            transcript = transcript_path.read_text(encoding="utf-8")

        self.assertEqual(len(files), 2)
        self.assertTrue(any(Path(path).suffix == ".mp4" for path in files))
        self.assertTrue(any(Path(path).suffix == ".txt" for path in files))
        self.assertIn("时间戳转写", transcript)
        self.assertIn("阿拉斯加是美国面积最大的州", transcript)
        self.assertNotIn("large-v2", transcript)
        self.assertNotIn("exact_sph_share_link", transcript)

    def test_verified_shipinhao_delivery_uses_bounded_agent_and_survives_backend_failure(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "alaska.mp4"
            transcript = root / "alaska-transcript.txt"
            context = root / "context.md"
            media.write_bytes(b"verified-video")
            transcript.write_text("时间戳转写\n[00:00] 阿拉斯加是美国面积最大的州\n", encoding="utf-8")
            context.write_text(
                "## Timestamped Transcript\n\n[00:00] 阿拉斯加是美国面积最大的州。\n",
                encoding="utf-8",
            )
            task = {
                "id": "shipinhao-bounded-delivery",
                "chat": "🍓My devices",
                "request": (
                    "stale publish instructions " * 300
                    + "\nCurrent coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr"
                ),
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "delivery_mode": "chat_attachment",
                    "public_publish_allowed": False,
                },
                "preflight": {
                    "shipinhao_media_transcript": {
                        "status": "cached",
                        "input_kind": "exact_sph_share_link",
                        "content_identity_verified": True,
                        "duration_seconds": 80.13,
                        "agent_context_path": str(context),
                        "delivery_media_path": str(media),
                        "delivery_transcript_path": str(transcript),
                        "download_delivery": {"verified": True},
                        "profile": {
                            "object_id": "sph-Ae2UMH6gqr",
                            "title": "美国最后的边疆阿拉斯加",
                            "author": "Hui世界",
                        },
                    }
                },
            }
            calls: list[dict[str, object]] = []

            def unavailable(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                return {"ok": False, "message": "timeout", "backend": "aginti"}

            with mock.patch.object(worker, "run_codex_session", side_effect=unavailable):
                raw = worker.run_verified_shipinhao_delivery_synthesis(
                    task,
                    {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "medium",
                        "sandbox": "danger-full-access",
                    },
                )

        self.assertIsNotNone(raw)
        payload = json.loads(raw or "{}")
        self.assertEqual(calls[0]["role"], "chat-shipinhao-summary")
        self.assertLess(len(str(calls[0]["prompt"])), 5000)
        self.assertNotIn("stale publish instructions", str(calls[0]["prompt"]))
        self.assertIn("阿拉斯加", payload["message"])
        self.assertIn("没有公开发布", payload["message"])
        self.assertEqual(set(payload["files"]), {str(media), str(transcript)})
        self.assertTrue(payload["data"]["require_file_delivery"])
        self.assertTrue(worker.result_requires_file_delivery(task, payload))
        self.assertFalse(payload["no_reply"])
        self.assertFalse(task["worker_result_exhausted"])
        self.assertEqual([call["backend"] for call in calls], ["aginti"])

    def test_verified_shipinhao_delivery_falls_back_from_codex_to_aginti(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "alaska.mp4"
            transcript = root / "alaska-transcript.txt"
            media.write_bytes(b"verified-video")
            transcript.write_text("时间戳转写\n[00:00] 阿拉斯加\n", encoding="utf-8")
            task = {
                "id": "shipinhao-backend-handoff",
                "chat": "Shares鏈接",
                "agent_backend": "codex",
                "request": "Current coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "delivery_mode": "chat_attachment",
                    "public_publish_allowed": False,
                },
                "preflight": {
                    "shipinhao_media_transcript": {
                        "status": "cached",
                        "input_kind": "exact_sph_share_link",
                        "content_identity_verified": True,
                        "duration_seconds": 80.13,
                        "text_preview": "阿拉斯加是美国面积最大的州。",
                        "delivery_media_path": str(media),
                        "delivery_transcript_path": str(transcript),
                        "download_delivery": {"verified": True},
                        "profile": {
                            "object_id": "sph-Ae2UMH6gqr",
                            "title": "美国最后的边疆阿拉斯加",
                            "author": "Hui世界",
                        },
                    }
                },
            }
            calls: list[str] = []

            def backend_handoff(prompt: str, **kwargs: object) -> dict[str, object]:
                requested = str(kwargs.get("backend") or "")
                calls.append(requested)
                if requested == "codex":
                    return {"ok": False, "message": "quota unavailable", "backend": "codex"}
                return {
                    "ok": True,
                    "message": json.dumps(
                        {
                            "message": "这段视频介绍阿拉斯加的地理、历史和自然景观；视频与时间戳转写已附上。",
                            "files": [],
                            "confirmation": "",
                        },
                        ensure_ascii=False,
                    ),
                    "backend": "aginti",
                }

            with mock.patch.object(worker, "run_codex_session", side_effect=backend_handoff):
                raw = worker.run_verified_shipinhao_delivery_synthesis(
                    task,
                    {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "medium",
                        "sandbox": "danger-full-access",
                    },
                )

        payload = json.loads(raw or "{}")
        self.assertEqual(calls, ["codex", "aginti"])
        self.assertIn("地理、历史和自然景观", payload["message"])
        self.assertEqual(
            [item["backend"] for item in task["shipinhao_delivery_synthesis"]["backend_attempts"]],
            ["codex", "aginti"],
        )
        self.assertEqual(task["shipinhao_delivery_synthesis"]["status"], "agent_completed")

    def test_verified_shipinhao_artifact_recovers_from_generic_worker_no_reply(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "alaska.mp4"
            media.write_bytes(b"verified-video")
            task = {
                "request": "Current coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "delivery_mode": "chat_attachment",
                    "public_publish_allowed": False,
                },
                "preflight": {
                    "shipinhao_media_transcript": {
                        "status": "cached",
                        "input_kind": "exact_sph_share_link",
                        "content_identity_verified": True,
                        "text_preview": "阿拉斯加是美国面积最大的州。",
                        "delivery_media_path": str(media),
                        "download_delivery": {"verified": True},
                        "profile": {
                            "object_id": "sph-Ae2UMH6gqr",
                            "title": "美国最后的边疆阿拉斯加",
                            "author": "Hui世界",
                        },
                    }
                },
                "worker_result_exhausted": True,
            }
            recovered = worker.recover_verified_shipinhao_delivery_result(
                task,
                {
                    "message": "",
                    "confirmation": "",
                    "files": [],
                    "no_reply": True,
                    "private_failure": {"kind": "backend_execution_failed"},
                },
            )

        self.assertFalse(recovered["no_reply"])
        self.assertNotIn("private_failure", recovered)
        self.assertEqual(recovered["files"], [str(media)])
        self.assertIn("没有公开发布", recovered["message"])
        self.assertTrue(recovered["data"]["require_file_delivery"])
        self.assertFalse(task["worker_result_exhausted"])

    def test_shipinhao_short_link_runs_resolver_pipeline_with_whisper_environment(self) -> None:
        worker = load_worker()
        task = {
            "id": "shipinhao-short-link",
            "chat": "Shares鏈接",
            "source": {"local_id": 152, "kind": "text", "local_type": 1},
            "routine": {"id": "file_download_save"},
            "route_decision": {
                "route_kind": "file_download_or_save",
                "delivery_mode": "chat_attachment",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr",
            "context": [],
        }
        captured = {}

        def fake_transcriber(command, *, output_dir, timeout, profile):
            captured["command"] = command
            media = output_dir / "source.mp4"
            media.write_bytes(b"verified-video")
            return {
                "status": "transcribed",
                "input_kind": "exact_sph_share_link",
                "media_path": str(media),
                "profile": {
                    "object_id": "sph-Ae2UMH6gqr",
                    "author": "Hui世界",
                    "title": "美国最后的边疆阿拉斯加",
                },
                "agent_context_path": str(output_dir / "shipinhao-audio-transcript.md"),
                "content_identity_verified": True,
                "read_only": True,
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {"WECHAT_SHIPINHAO_TRANSCRIBE_PYTHON": "/opt/miniconda3/envs/whisper/bin/python"},
                clear=False,
            ), mock.patch.object(worker, "run_shipinhao_media_transcriber", side_effect=fake_transcriber):
                result = worker.prepare_shipinhao_media_transcript_preflight(task, Path(tmp))

        self.assertTrue(worker.should_prepare_shipinhao_media_transcript(task))
        self.assertTrue(str(captured["command"][0]).endswith("/envs/whisper/bin/python"))
        self.assertEqual(result["download_delivery"]["status"], "ready")
        self.assertTrue(result["content_identity_verified"])

    def test_worker_repairs_stale_publish_route_for_bare_shipinhao_link(self) -> None:
        worker = load_worker()
        task = {
            "id": "stale-route",
            "request": "Current coalesced request:\nhttps://weixin.qq.com/sph/Ae2UMH6gqr",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_intent": True,
                "public_publish_allowed": True,
            },
            "routine": {"id": "video_publish_existing"},
        }

        changed = worker.enforce_current_task_route_safety(task)

        self.assertTrue(changed)
        self.assertEqual(task["route_decision"]["route_kind"], "file_download_or_save")
        self.assertEqual(task["route_decision"]["delivery_mode"], "chat_attachment")
        self.assertFalse(task["route_decision"]["needs_recent_media"])
        self.assertFalse(task["route_decision"]["public_publish_allowed"])
        self.assertNotIn("routine", task)
        self.assertFalse(worker.has_public_publish_intent("https://weixin.qq.com/sph/Ae2UMH6gqr"))
        self.assertTrue(worker.has_public_publish_intent("Publish this video to Shipinhao"))

    def test_worker_repairs_native_shipinhao_card_to_download_delivery(self) -> None:
        worker = load_worker()
        exact_card = (
            "<finderFeed><objectId><![CDATA[exact-object-123]]></objectId>"
            "<nickname><![CDATA[Exact Creator]]></nickname>"
            "<desc><![CDATA[Exact subject]]></desc>"
            "<mediaList><media><url><![CDATA[http://wxapp.tc.qq.com/video?id=fresh]]>"
            "</url></media></mediaList></finderFeed>"
        )
        task = {
            "id": "native-finder-route",
            "request": f"Current coalesced request:\n{exact_card}",
            "source": {"local_id": 77, "kind": "file/link"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "public_publish_intent": False,
                "public_publish_allowed": False,
            },
            "routine": {"id": "research_summary"},
        }

        changed = worker.enforce_current_task_route_safety(task)

        self.assertTrue(changed)
        self.assertEqual(task["route_decision"]["route_kind"], "file_download_or_save")
        self.assertEqual(task["route_decision"]["delivery_mode"], "chat_attachment")
        self.assertFalse(task["route_decision"]["public_publish_allowed"])
        self.assertNotIn("routine", task)

    def test_shipinhao_media_preflight_automatically_captures_after_signed_url_failure(self) -> None:
        worker = load_worker()
        exact_card = (
            "<finderFeed><objectId><![CDATA[exact-object-123]]></objectId>"
            "<nickname><![CDATA[Exact Creator]]></nickname><desc><![CDATA[Exact subject]]></desc>"
            "<mediaList><media><videoPlayDuration><![CDATA[42]]></videoPlayDuration>"
            "<url><![CDATA[http://wxapp.tc.qq.com/video?id=expired]]></url></media></mediaList></finderFeed>"
        )
        task = {
            "id": "shipinhao-native-fallback",
            "chat": "鏈接",
            "source": {"local_id": 77, "kind": "file/link", "local_type": 219043332145},
            "routine": {"id": "research_summary"},
            "request": f"Current coalesced request:\nsummarize this video\n\nRecent history:\n{exact_card}",
            "context": [{"local_id": 77, "content": exact_card}],
        }
        calls: list[list[str]] = []

        def fake_transcriber(command, *, output_dir, timeout, profile):
            calls.append(list(command))
            if len(calls) == 1:
                return {
                    "status": "failed",
                    "failure_stage": "download",
                    "read_only": True,
                    "profile": profile,
                }
            return {
                "status": "transcribed",
                "agent_context_path": str(output_dir / "shipinhao-audio-transcript.md"),
                "read_only": True,
            }

        with tempfile.TemporaryDirectory() as tmp:
            capture_manifest = Path(tmp) / "verified-capture.json"
            with mock.patch.object(worker, "run_shipinhao_media_transcriber", side_effect=fake_transcriber), mock.patch.object(
                worker,
                "run_automatic_shipinhao_gui_capture",
                return_value={"status": "verified", "visual_identity_verified": True, "source_chat": "鏈接"},
            ) as capture, mock.patch.object(
                worker,
                "discover_verified_shipinhao_capture",
                side_effect=[None, capture_manifest],
            ):
                result = worker.prepare_shipinhao_media_transcript_preflight(task, Path(tmp))

        self.assertEqual(result["status"], "transcribed")
        self.assertEqual(len(calls), 2)
        self.assertIn("--capture-manifest", calls[1])
        self.assertEqual(calls[1][calls[1].index("--capture-manifest") + 1], str(capture_manifest))
        capture.assert_called_once()
        self.assertTrue(result["native_capture_fallback"]["visual_identity_verified"])

    def test_automatic_shipinhao_capture_passes_card_duration(self) -> None:
        worker = load_worker()
        task = {"chat": "鏈接"}
        profile = {
            "object_id": "exact-object-123",
            "title": "Exact subject",
            "author": "Exact Creator",
            "duration_seconds": 42.5,
        }
        completed = mock.Mock(
            returncode=2,
            stdout=json.dumps(
                {
                    "status": "failed",
                    "error_code": "finder_player_unavailable",
                    "failure_stage": "player_open",
                    "source_card_found": True,
                }
            ),
            stderr="",
        )

        with mock.patch.object(worker.subprocess, "run", return_value=completed) as run:
            result = worker.run_automatic_shipinhao_gui_capture(task, profile)

        command = run.call_args.args[0]
        self.assertIn("--expected-duration-seconds", command)
        self.assertEqual(command[command.index("--expected-duration-seconds") + 1], "42.500")
        self.assertEqual(result["error_code"], "finder_player_unavailable")
        self.assertTrue(result["source_card_found"])

    def test_failed_shipinhao_acquisition_creates_not_silent_agent_context(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            stale_context = Path(tmp) / "stale-transcript.md"
            stale_context.write_text("# stale transcript\n", encoding="utf-8")
            result = worker.finalize_shipinhao_media_transcript_preflight(
                Path(tmp),
                {
                    "status": "failed",
                    "failure_stage": "media_resolution",
                    "verified_silent_media": True,
                    "agent_context_path": str(stale_context),
                    "profile": {"title": "Exact source", "author": "Exact creator"},
                },
            )
            context = Path(result["agent_context_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["audio_evidence_status"], "media_unavailable_not_silent")
        self.assertFalse(result["verified_silent_media"])
        self.assertNotEqual(Path(result["agent_context_path"]), stale_context)
        self.assertIn("Media acquisition failure is not evidence that the source is silent", context)
        self.assertIn("Do not say the video has no audio", context)

    def test_finder_audio_alias_cannot_turn_failed_download_into_silence(self) -> None:
        worker = load_worker()

        result = worker.finder_audio_intake_alias(
            {"source": {"local_id": 91}},
            {
                "status": "failed",
                "verified_silent_media": True,
                "audio_evidence_status": "verified_silent_media",
                "failure_stage": "download",
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["verified_silent_media"])
        self.assertEqual(result["audio_evidence_status"], "media_unavailable_not_silent")

    def test_shipinhao_preflight_prefers_matching_verified_capture_manifest(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            object_dir = cache_root / "exact-object-123"
            object_dir.mkdir(parents=True)
            audio = object_dir / "source.wav"
            audio.write_bytes(b"source-scoped-audio")
            manifest = object_dir / "verified-capture.json"
            manifest.write_text(
                json.dumps(
                    {
                        "status": "verified",
                        "visual_identity_verified": True,
                        "object_id": "exact-object-123",
                        "title": "Exact subject",
                        "author": "Exact Creator",
                        "identity_terms": ["Exact subject"],
                        "audio_path": str(audio),
                        "audio_sha256": worker.sha256_file(audio),
                    }
                ),
                encoding="utf-8",
            )
            profile = {
                "object_id": "exact-object-123",
                "title": "Exact subject",
                "author": "Exact Creator",
            }

            with mock.patch.object(worker, "SHIPINHAO_MEDIA_CACHE_ROOT", cache_root):
                discovered = worker.discover_verified_shipinhao_capture(profile)

        self.assertEqual(discovered, manifest)

    def test_matching_lazyedit_publish_jobs_deduplicates_numeric_string_ids(self) -> None:
        worker = load_worker()
        with mock.patch.object(
            worker,
            "lazyedit_api_get",
            return_value={"jobs": [{"id": "210", "video_id": 404, "status": "done"}]},
        ):
            jobs = worker.matching_lazyedit_publish_jobs(
                404,
                {"payload": {"publish_job": {"job": {"id": 210, "video_id": 404, "status": "done"}}}},
            )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "210")

    def test_worker_policy_uses_routine_default_for_long_research_summary(self) -> None:
        worker = load_worker()
        request = (
            "Handle this WeChat request as backend work. "
            "Use available local tools and return artifacts. "
        ) * 160
        request += (
            "\n\nCurrent coalesced request:\n"
            "New WeChat link: EventDrive 把事件相机接进驾驶大模型, summarize the article.\n\n"
            "Recent history:\n"
            "A long source-limited WeChat XML card and synced thumbnail context."
        )
        policy = worker.choose_worker_policy(
            {
                "request": request,
                "routine": {"id": "research_summary", "default_effort": "medium"},
                "route_decision": {"route_kind": "research_or_summary"},
            }
        )

        self.assertEqual(policy["reasoning_effort"], "medium")

    def test_scheduled_daily_research_uses_xhigh_despite_unrelated_protein_context(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy(
            {
                "request": (
                    "Prepare today's organoid literature briefing. Recent group context also "
                    "mentions AlphaFold and COL1A1, but that is not this member's daily topic."
                ),
                "daily_research": {"topics": ["recent organoid papers"]},
                "route_decision": {"scheduled_daily_research": True},
                "routine": {"id": "research_summary", "default_effort": "xhigh"},
            }
        )

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "xhigh")

    def test_worker_policy_ignores_boilerplate_length_for_story_edit(self) -> None:
        worker = load_worker()
        boilerplate = (
            "Handle this WeChat request as backend work. "
            "Use LabCanvas, GitHub, MCP, install, publish, submit order, fully control, and robust automation. "
        ) * 80
        request = (
            f"{boilerplate}\n\n"
            "Current coalesced request:\n"
            "陈苗: Could you optimize the story? The words and sentences are strange. "
            "Please show me here and make each sentence understandable.\n\n"
            "Recent history:\n"
            "陈喵瞄秒妙: 《餐厅地板下的金光》..."
        )
        policy = worker.choose_worker_policy({"chat": "🍓我的设备", "request": request})

        self.assertEqual(policy["reasoning_effort"], "medium")

    def test_worker_policy_uses_current_request_for_complex_followup(self) -> None:
        worker = load_worker()
        request = (
            "Reusable execution instructions mentioning only generic files.\n\n"
            "Current coalesced request:\n"
            "陈苗: fully implement the WeChat automation, commit and push\n\n"
            "Recent history:\n"
            "陈喵瞄秒妙: previous short answer"
        )
        policy = worker.choose_worker_policy({"request": request})

        self.assertEqual(policy["reasoning_effort"], "xhigh")

    def test_worker_policy_escalates_weak_low_result(self) -> None:
        worker = load_worker()
        next_policy = worker.escalated_policy(
            {"model": "gpt-5.5", "reasoning_effort": "low", "sandbox": "workspace-write", "timeout_seconds": 120},
            "Worker failed: timed out before completing the task.",
        )

        self.assertIsNotNone(next_policy)
        self.assertEqual(next_policy["reasoning_effort"], "medium")

    def test_worker_policy_does_not_escalate_codex_launcher_failure(self) -> None:
        worker = load_worker()
        self.assertIsNone(
            worker.escalated_policy(
                {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "danger-full-access", "timeout_seconds": 300},
                "Worker failed via codex: codex wrapper error: could not find real codex binary in PATH",
            )
        )
        self.assertFalse(worker.worker_result_needs_escalation("Codex failed: codex executable was not found in PATH."))

    def test_worker_policy_escalates_failed_high_result_to_xhigh(self) -> None:
        worker = load_worker()
        next_policy = worker.escalated_policy(
            {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "danger-full-access", "timeout_seconds": 600},
            "Worker failed: cannot complete the CAD export.",
        )

        self.assertIsNotNone(next_policy)
        assert next_policy is not None
        self.assertEqual(next_policy["model"], "gpt-5.6-sol")
        self.assertEqual(next_policy["reasoning_effort"], "xhigh")
        self.assertEqual(next_policy["timeout_seconds"], 1200)

    def test_worker_policy_stops_gpt56_escalation_at_xhigh(self) -> None:
        worker = load_worker()
        with mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_CODEX_MODEL": "gpt-5.6-sol",
                "WECHAT_WORKER_MIN_EFFORT": "low",
                "WECHAT_WORKER_MAX_EFFORT": "ultra",
            },
            clear=False,
        ):
            maximum = worker.escalated_policy(
                {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "xhigh",
                    "sandbox": "danger-full-access",
                    "timeout_seconds": 1200,
                },
                "Worker failed: incomplete research task.",
            )
        self.assertIsNone(maximum)

    def test_worker_policy_uses_sol_xhigh_for_presentation_routine(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy(
            {
                "request": "Create a polished PowerPoint presentation with editable slides.",
                "routine": {"id": "presentation_deck", "default_effort": "xhigh"},
            }
        )

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "xhigh")
        self.assertEqual(policy["timeout_seconds"], 1200)

    def test_worker_policy_does_not_use_spark_unless_allowed(self) -> None:
        worker = load_worker()
        original = worker.os.environ.get("WECHAT_WORKER_CODEX_MODEL")
        original_allow = worker.os.environ.get("WECHAT_ALLOW_SPARK_WORKER")
        try:
            worker.os.environ["WECHAT_WORKER_CODEX_MODEL"] = "gpt-5.3-codex-spark"
            worker.os.environ.pop("WECHAT_ALLOW_SPARK_WORKER", None)
            self.assertEqual(worker.choose_worker_policy({"request": "summarize"}), {
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "sandbox": "danger-full-access",
                "timeout_seconds": 300,
            })
            worker.os.environ["WECHAT_ALLOW_SPARK_WORKER"] = "1"
            self.assertEqual(worker.worker_model(), "gpt-5.3-codex-spark")
        finally:
            if original is None:
                worker.os.environ.pop("WECHAT_WORKER_CODEX_MODEL", None)
            else:
                worker.os.environ["WECHAT_WORKER_CODEX_MODEL"] = original
            if original_allow is None:
                worker.os.environ.pop("WECHAT_ALLOW_SPARK_WORKER", None)
            else:
                worker.os.environ["WECHAT_ALLOW_SPARK_WORKER"] = original_allow

    def test_blank_title_guard_detects_short_ascii_ocr_noise(self) -> None:
        worker = load_worker()
        errors = [
            "RuntimeError: Opened chat title guard failed for EchoMind: OCR='3 - oO\\n|'.",
        ]

        self.assertTrue(worker.send_errors_indicate_blank_title_guard(errors))
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), "title_guard_blank")

    def test_wrong_chat_title_remains_distinct_and_bounded_retryable(self) -> None:
        worker = load_worker()
        errors = [
            "RuntimeError: Opened chat title guard failed for EchoMind: OCR='鏈接'.",
        ]

        self.assertFalse(worker.send_errors_indicate_blank_title_guard(errors))
        self.assertTrue(worker.send_errors_indicate_title_guard_failure(errors))
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), "title_guard_failed")

    def test_worker_policy_does_not_escalate_missing_source_or_manual_blocker(self) -> None:
        worker = load_worker()

        self.assertIsNone(
            worker.escalated_policy(
                {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "danger-full-access", "timeout_seconds": 600},
                "Source-limited: please resend the exact file/source.",
            )
        )
        self.assertIsNone(
            worker.escalated_policy(
                {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "danger-full-access", "timeout_seconds": 600},
                "This needs login/CAPTCHA, waiting for approval.",
            )
        )

    def test_worker_policy_does_not_misread_source_timeout_inside_useful_json(self) -> None:
        worker = load_worker()
        result = json.dumps(
            {
                "message": (
                    "原始公众号页面读取超时，但卡片标题、作者和同一聊天中的正文摘录足以确认主题。"
                    "文章主张先验证用户是否愿意为重复劳动的自动化付费，再决定是否扩展产品；"
                    "当前最值得保留的是这个验证顺序，而不是页面中的宣传措辞。"
                ),
                "files": [],
            },
            ensure_ascii=False,
        )

        self.assertFalse(worker.worker_result_needs_escalation(result))

    def test_run_worker_codex_keeps_best_earlier_result_when_retries_are_empty(self) -> None:
        worker = load_worker()
        responses = [
            "Partial answer with the source title.",
            "",
            "Worker failed: cannot complete with current effort.",
        ]
        original = worker.run_worker_codex_once
        try:
            worker.run_worker_codex_once = lambda _task, _policy: responses.pop(0)
            task = {"chat": "demo", "request": "summarize this PDF paper"}
            result = worker.run_worker_codex(task)
        finally:
            worker.run_worker_codex_once = original

        self.assertIn("Partial answer", result)
        self.assertEqual(task["worker_policy_selected_attempt"], 1)
        self.assertTrue(task["worker_policy_attempts"][0]["selected"])
        self.assertEqual(
            [item["reasoning_effort"] for item in task["worker_policy_attempts"]],
            ["medium", "high", "xhigh"],
        )

    def test_run_worker_codex_retries_through_xhigh(self) -> None:
        worker = load_worker()
        calls: list[str] = []
        original = worker.run_worker_codex_once
        try:
            def fake_run_worker_codex_once(task: dict[str, object], policy: dict[str, object]) -> str:
                calls.append(str(policy["reasoning_effort"]))
                if policy["reasoning_effort"] == "xhigh":
                    return "Finished the task with enough detail to be accepted by the worker pipeline."
                return "Worker failed: cannot complete with current effort."

            worker.run_worker_codex_once = fake_run_worker_codex_once
            task = {"chat": "demo", "request": "summarize this PDF paper"}
            result = worker.run_worker_codex(task)
        finally:
            worker.run_worker_codex_once = original

        self.assertEqual(calls, ["medium", "high", "xhigh"])
        self.assertIn("Finished the task", result)
        self.assertEqual(task["worker_policy"]["reasoning_effort"], "xhigh")
        self.assertEqual(len(task["worker_policy_attempts"]), 3)

    def test_worker_detects_repairable_tool_failure_without_bypassing_policy(self) -> None:
        worker = load_worker()

        self.assertTrue(
            worker.worker_result_is_repairable_tool_failure(
                "Worker failed via codex: codex_core::tools::router: "
                "exec_command failed: CreateProcess { message: \"Rejected(malformed quoting)\" }"
            )
        )
        self.assertFalse(
            worker.worker_result_is_repairable_tool_failure(
                "Worker failed via codex: exec_command failed: approval required by policy"
            )
        )
        self.assertFalse(
            worker.worker_result_is_repairable_tool_failure(
                "Worker failed via codex: codex executable was not found in PATH"
            )
        )

    def test_run_worker_codex_repairs_tool_failure_at_ultra_once(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run_worker_codex_once(task: dict[str, object], policy: dict[str, object]) -> str:
            calls.append(
                {
                    "effort": policy["reasoning_effort"],
                    "repair": bool(policy.get("tool_repair_retry")),
                    "retry_context": dict(task.get("worker_retry_context") or {}),
                }
            )
            if len(calls) == 1:
                return (
                    "Worker failed via codex: codex_core::tools::router: exec_command failed "
                    "for a malformed shell command: CreateProcess { message: \"Rejected\" }"
                )
            return "Finished the exact research report and compiled its PDF from existing evidence."

        task = {"chat": "wecom:group:labagent", "request": "prepare report"}
        ultra_policy = {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "ultra",
            "sandbox": "danger-full-access",
            "timeout_seconds": 86400,
        }
        with mock.patch.object(worker, "choose_worker_policy", return_value=ultra_policy), mock.patch.object(
            worker, "run_worker_codex_once", side_effect=fake_run_worker_codex_once
        ), mock.patch.object(worker, "recover_completed_research_artifacts", return_value=None):
            result = worker.run_worker_codex(task)

        self.assertIn("Finished the exact research report", result)
        self.assertEqual([call["effort"] for call in calls], ["ultra", "ultra"])
        self.assertEqual([call["repair"] for call in calls], [False, True])
        self.assertEqual(calls[1]["retry_context"]["kind"], "repairable_tool_invocation_failure")
        self.assertNotIn("worker_retry_context", task)
        self.assertTrue(task["worker_policy_attempts"][1]["tool_repair_retry"])

    def test_run_worker_codex_bounds_repeated_tool_repair_failure(self) -> None:
        worker = load_worker()
        failure = (
            "Worker failed via codex: codex_core::tools::router: exec_command failed: "
            "CreateProcess { message: \"Rejected\" }"
        )
        task = {"chat": "wecom:group:labagent", "request": "prepare report"}
        ultra_policy = {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "ultra",
            "sandbox": "danger-full-access",
            "timeout_seconds": 86400,
        }
        with mock.patch.object(worker, "choose_worker_policy", return_value=ultra_policy), mock.patch.object(
            worker, "run_worker_codex_once", return_value=failure
        ) as run, mock.patch.object(worker, "recover_completed_research_artifacts", return_value=None):
            result = worker.run_worker_codex(task)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(result, failure)
        self.assertTrue(task["worker_result_exhausted"])
        self.assertEqual(
            sum(bool(item["tool_repair_retry"]) for item in task["worker_policy_attempts"]),
            1,
        )

    def test_worker_recovers_one_aginti_permission_pause_without_more_authority(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run_worker_codex_once(task: dict[str, object], policy: dict[str, object]) -> str:
            backend_config = worker.worker_backend_config(task, "aginti")
            calls.append(
                {
                    "permission_retry": bool(policy.get("permission_recovery_retry")),
                    "reuse_session": bool(policy.get("reuse_session", True)),
                    "retry_context": dict(task.get("worker_retry_context") or {}),
                    "sandbox_mode": backend_config.get("sandbox_mode"),
                    "allow_host_workspace": backend_config.get("allow_host_workspace"),
                }
            )
            if len(calls) == 1:
                return "Worker failed via aginti: permission_required"
            return "Finished the exact task using the existing safe worker policy."

        task = {"chat": "wecom:group:labagent", "request": "prepare report"}
        xhigh_policy = {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "xhigh",
            "sandbox": "danger-full-access",
            "timeout_seconds": 43200,
        }
        with mock.patch.object(worker, "choose_worker_policy", return_value=xhigh_policy), mock.patch.object(
            worker, "run_worker_codex_once", side_effect=fake_run_worker_codex_once
        ), mock.patch.object(worker, "recover_completed_research_artifacts", return_value=None):
            result = worker.run_worker_codex(task)

        self.assertIn("Finished the exact task", result)
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[0]["permission_retry"])
        self.assertTrue(calls[1]["permission_retry"])
        self.assertTrue(calls[1]["reuse_session"])
        self.assertEqual(
            calls[1]["retry_context"]["kind"],
            "recoverable_aginti_permission_pause",
        )
        self.assertIn("grants no new permission", calls[1]["retry_context"]["instruction"])
        self.assertEqual(calls[0]["sandbox_mode"], "docker-workspace")
        self.assertEqual(calls[1]["sandbox_mode"], "docker-workspace")
        self.assertFalse(calls[1]["allow_host_workspace"])
        self.assertNotIn("worker_retry_context", task)

    def test_worker_bounds_repeated_aginti_permission_pause(self) -> None:
        worker = load_worker()
        failure = "Worker failed via aginti: permission_required"
        task = {"chat": "wecom:group:labagent", "request": "prepare report"}
        xhigh_policy = {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "xhigh",
            "sandbox": "danger-full-access",
            "timeout_seconds": 43200,
        }
        with mock.patch.object(worker, "choose_worker_policy", return_value=xhigh_policy), mock.patch.object(
            worker, "run_worker_codex_once", return_value=failure
        ) as run, mock.patch.object(worker, "recover_completed_research_artifacts", return_value=None):
            result = worker.run_worker_codex(task)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(result, failure)
        self.assertTrue(task["worker_result_exhausted"])
        self.assertEqual(
            sum(
                bool(item["permission_recovery_retry"])
                for item in task["worker_policy_attempts"]
            ),
            1,
        )

    def test_permission_recovery_classifier_is_aginti_specific(self) -> None:
        worker = load_worker()

        self.assertTrue(
            worker.worker_result_is_recoverable_aginti_permission_pause(
                "Worker failed via aginti: permission_required"
            )
        )
        self.assertFalse(
            worker.worker_result_is_recoverable_aginti_permission_pause(
                "Worker failed via codex: permission_required"
            )
        )
        self.assertFalse(
            worker.worker_result_is_recoverable_aginti_permission_pause(
                "Worker failed via aginti: unsafe command"
            )
        )

    def test_worker_backend_config_bounds_aginti_evidence_scope(self) -> None:
        worker = load_worker()
        task = {
            "id": "scope-test",
            "request": (
                "Current coalesced request:\n"
                "Create permission-smoke.txt and verify it.\n\n"
                "Recent history:\n"
                "An unrelated browser discussion."
            ),
        }

        config = worker.worker_backend_config(task, "aginti")

        self.assertEqual(
            config["evidence_scope_request"],
            "Create permission-smoke.txt and verify it.",
        )
        self.assertEqual(
            config["evidence_scope_artifact_root"],
            "output/wechat_worker/scope-test",
        )
        self.assertEqual(config["permission_mode"], "normal")
        self.assertEqual(config["sandbox_mode"], "docker-workspace")
        self.assertEqual(config["package_install_policy"], "allow")
        self.assertFalse(config["allow_host_workspace"])

    def test_worker_backend_config_can_explicitly_enable_aginti_host_workspace(self) -> None:
        worker = load_worker()
        with mock.patch.dict(os.environ, {"WECHAT_AGINTI_HOST_WORKSPACE": "1"}):
            config = worker.worker_backend_config(
                {"id": "scope-test", "request": "Inspect only."},
                "aginti",
            )
        self.assertEqual(config["sandbox_mode"], "host")
        self.assertTrue(config["allow_host_workspace"])

    def test_worker_backend_config_contains_permission_recovery_in_docker(self) -> None:
        worker = load_worker()
        task = {
            "id": "scope-test",
            "request": "Compile the report from existing task evidence.",
            "agent_backend_config": {
                "permission_mode": "normal",
                "sandbox_mode": "host",
                "allow_host_workspace": True,
            },
            "worker_retry_context": {
                "kind": "recoverable_aginti_permission_pause",
            },
        }

        config = worker.worker_backend_config(task, "aginti")

        self.assertEqual(config["permission_mode"], "normal")
        self.assertEqual(config["sandbox_mode"], "docker-workspace")
        self.assertEqual(config["package_install_policy"], "allow")
        self.assertFalse(config["allow_host_workspace"])

    def test_worker_backend_config_preserves_explicit_evidence_scope(self) -> None:
        worker = load_worker()
        task = {
            "id": "scope-test",
            "request": "Create another file.",
            "agent_backend_config": {
                "evidence_scope_request": "Explicit bounded request.",
                "evidence_scope_artifact_root": "output/custom",
            },
        }

        config = worker.worker_backend_config(task, "aginti")

        self.assertEqual(config["evidence_scope_request"], "Explicit bounded request.")
        self.assertEqual(config["evidence_scope_artifact_root"], "output/custom")

    def test_failed_worker_records_safe_backend_attribution(self) -> None:
        worker = load_worker()
        task = {"id": "failed-worker", "chat": "LabAgent", "request": "Create report."}
        failed = {
            "ok": False,
            "backend": "aginti",
            "thread_id": "private-session-identifier",
            "stderr_tail": "permission_required with private diagnostic text",
            "message_source": "session.stopped",
            "provider": "deepseek",
            "backend_attempts": [
                {
                    "backend": "aginti",
                    "model": "aginti",
                    "reasoning_effort": "medium",
                    "ok": False,
                    "failure_kind": "other",
                    "returncode": 1,
                    "stderr_tail": "must not persist",
                }
            ],
            "provider_attempts": [
                {
                    "provider": "deepseek",
                    "ok": False,
                    "returncode": 1,
                    "failure_kind": "permission_required",
                    "retry_safe": False,
                    "private_prompt": "must not persist",
                }
            ],
        }

        with mock.patch.object(worker, "run_codex_session", return_value=failed), mock.patch.object(
            worker, "task_long_term_history_context", return_value={}
        ):
            result = worker.run_worker_agent_session(
                task,
                {
                    "model": "aginti",
                    "reasoning_effort": "medium",
                    "sandbox": "danger-full-access",
                    "timeout_seconds": 300,
                },
            )

        self.assertIn("Worker failed via aginti", result)
        self.assertFalse(task["agent_session"]["ok"])
        self.assertEqual(task["agent_session"]["failure_kind"], "permission_required")
        self.assertEqual(task["agent_session"]["message_source"], "session.stopped")
        serialized = json.dumps(task["agent_session"], ensure_ascii=False)
        self.assertNotIn("private diagnostic text", serialized)
        self.assertNotIn("must not persist", serialized)
        self.assertNotIn("private-session-identifier", serialized)

    def test_run_worker_codex_stops_after_completed_artifact_recovery(self) -> None:
        worker = load_worker()
        recovered = {
            "message": "Recovered complete report.",
            "confirmation": "",
            "files": ["/tmp/report.pdf"],
            "data": {"require_file_delivery": True},
        }
        task = {
            "chat": "wecom:group:labagent",
            "request": "Prepare the daily research report",
            "routine": {"id": "research_summary", "default_effort": "high"},
        }
        with mock.patch.object(worker, "run_worker_codex_once", return_value="Worker failed via codex: timeout") as run, mock.patch.object(
            worker,
            "recover_completed_research_artifacts",
            return_value=recovered,
        ):
            result = worker.run_worker_codex(task)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(json.loads(result)["message"], "Recovered complete report.")
        self.assertTrue(task["worker_policy_attempts"][0]["artifact_recovered"])
        self.assertFalse(task["worker_result_exhausted"])

    def test_worker_uses_group_worker_session_role(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        original = worker.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                return {"ok": True, "message": "done", "thread_id": "thread-worker", "resumed": True}

            worker.run_codex_session = fake_run_codex_session
            result = worker.run_worker_codex_once(
                {"chat": "懒人科研", "request": "summarize this paper"},
                {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "workspace-write", "timeout_seconds": 300},
            )
        finally:
            worker.run_codex_session = original

        self.assertEqual(result, "done")
        self.assertEqual(calls[0]["chat_name"], "懒人科研")
        self.assertEqual(calls[0]["role"], "worker")
        self.assertIn("fragment or follow-up", str(calls[0]["prompt"]))
        self.assertIn("Central orchestrator handoff", str(calls[0]["prompt"]))
        self.assertIn("WeChat is only the message transport", str(calls[0]["prompt"]))
        self.assertIn("Execution contract", str(calls[0]["prompt"]))
        self.assertIn("message_transport_only", str(calls[0]["prompt"]))
        self.assertIn("resume_per_chat_worker_session", str(calls[0]["prompt"]))
        self.assertIn("wechat_codex_sessions.run_codex_session", str(calls[0]["prompt"]))
        self.assertIn("central routine orchestrator", str(calls[0]["prompt"]))
        self.assertIn("Routine supervisor contract", str(calls[0]["prompt"]))
        self.assertIn("routine_contract.md", str(calls[0]["prompt"]))
        self.assertIn("Avoid sending the same answer again", str(calls[0]["prompt"]))
        self.assertIn("Strict source isolation", str(calls[0]["prompt"]))
        self.assertIn("Never use media, files, or generated artifacts from another chat", str(calls[0]["prompt"]))
        self.assertIn("If no exact matching source media is available", str(calls[0]["prompt"]))
        self.assertIn("explicit source/reference rows embedded in `request`", str(calls[0]["prompt"]))
        self.assertIn("LabCanvas tool playbook", str(calls[0]["prompt"]))
        self.assertIn("Match every input file/media path to this task's exact", str(calls[0]["prompt"]))
        self.assertIn("studio figure-grid", str(calls[0]["prompt"]))
        self.assertIn("AgInTi image-generation", str(calls[0]["prompt"]))
        self.assertIn("studio lab-task", str(calls[0]["prompt"]))
        self.assertIn("render-scene", str(calls[0]["prompt"]))
        self.assertIn("Shipinhao/Finder", str(calls[0]["prompt"]))
        self.assertIn("task.preflight.wechat_source_recovery", str(calls[0]["prompt"]))
        self.assertIn("task.preflight.shipinhao_comment_intel", str(calls[0]["prompt"]))
        self.assertIn("shipinhao_comment_intel.py", str(calls[0]["prompt"]))
        self.assertIn("@元宝", str(calls[0]["prompt"]))
        self.assertIn("英文全文", str(calls[0]["prompt"]))
        self.assertIn("Do not post a comment", str(calls[0]["prompt"]))
        self.assertIn("do not produce a \"deep analysis\"", str(calls[0]["prompt"]))
        self.assertIn("mobile WeChat user agent", str(calls[0]["prompt"]))
        self.assertIn("exact-title/account/identity queries", str(calls[0]["prompt"]))
        self.assertIn("do not return `waiting_confirmation`", str(calls[0]["prompt"]))
        self.assertIn("Link/read-later summary reports", str(calls[0]["prompt"]))
        self.assertIn("return a concise chat message by default", str(calls[0]["prompt"]))
        self.assertIn("Attach a PDF to WeChat only when explicitly requested", str(calls[0]["prompt"]))
        self.assertIn("Do not send a low-quality image/thumbnail", str(calls[0]["prompt"]))
        self.assertIn("lazyedit-publish-workflow/SKILL.md", str(calls[0]["prompt"]))
        self.assertIn("scripts/lazyedit_publish.py", str(calls[0]["prompt"]))
        self.assertIn("--correction-prompt-file", str(calls[0]["prompt"]))
        self.assertIn("--metadata-prompt-file", str(calls[0]["prompt"]))
        self.assertIn("Submit the durable LazyEdit job with `--no-wait`", str(calls[0]["prompt"]))
        self.assertIn("do not hold this agent turn with `--wait`", str(calls[0]["prompt"]))
        self.assertIn("deterministic worker poststage owns long monitoring", str(calls[0]["prompt"]))
        self.assertIn("verification gate", str(calls[0]["prompt"]))
        self.assertIn("Do not stop after a successful no-publish pass", str(calls[0]["prompt"]))
        self.assertIn("LALACHAN/RaraXia/AyaChan/SasaKun story-video generation", str(calls[0]["prompt"]))
        self.assertIn("words-card.jpg", str(calls[0]["prompt"]))
        self.assertIn("raraxia.jpeg", str(calls[0]["prompt"]))
        self.assertIn("ayachan.png", str(calls[0]["prompt"]))
        self.assertIn("sasakun.jpeg", str(calls[0]["prompt"]))
        self.assertIn("Trio.png", str(calls[0]["prompt"]))
        self.assertIn("Seedance 2.0 Mini 体验版", str(calls[0]["prompt"]))
        self.assertIn("Fast VIP", str(calls[0]["prompt"]))
        self.assertIn("Model selection must not block", str(calls[0]["prompt"]))
        self.assertIn("relatively cheaper suitable", str(calls[0]["prompt"]))
        self.assertIn("Do not paste local filesystem paths", str(calls[0]["prompt"]))
        self.assertIn("api/autopublish/queue", str(calls[0]["prompt"]))
        self.assertIn("lazyingart:8081/publish/queue", str(calls[0]["prompt"]))
        self.assertIn("fail closed", str(calls[0]["prompt"]))
        self.assertIn("nearby/older video", str(calls[0]["prompt"]))
        self.assertIn("files", str(calls[0]["prompt"]))
        self.assertEqual(worker.task_orchestrator_stage({"routine": {"id": "research_summary"}}), "routine:research_summary")
        self.assertEqual(calls[0]["reuse"], True)

    def test_worker_agent_packet_keeps_context_paths_but_drops_raw_finder_secrets(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        signed = "https://wxapp.tc.qq.com/video?stodownload=1&encfilekey=private-signed-token"
        raw_card = (
            "<finderFeed><objectId><![CDATA[object-private]]></objectId>"
            "<desc><![CDATA[Exact public talk]]></desc><mediaList><media>"
            f"<url><![CDATA[{signed}]]></url></media></mediaList></finderFeed>"
        )
        task = {
            "id": "finder-task",
            "chat": "链接",
            "request": f"Current coalesced request:\nPlease summarize this video. {raw_card}",
            "source": {"local_id": 44, "server_id": "server-44", "content": raw_card},
            "context": [
                {"local_id": 43, "content": raw_card, "sender_display": "owner"},
                {"local_id": 44, "content": "Please summarize this video.", "sender_display": "owner"},
            ],
            "route_decision": {"route_kind": "research_or_summary"},
            "preflight": {
                "shipinhao_media_transcript": {
                    "status": "transcribed",
                    "input_kind": "content_verified_public_mirror",
                    "agent_context_path": "/tmp/private/shipinhao-audio-transcript.md",
                    "media_path": "/tmp/private/source.mp4",
                    "source_url": signed,
                    "source_text_file": "/tmp/private/exact-source-card.txt",
                    "public_mirror_recovery": {
                        "status": "not_found",
                        "cover_path": "/tmp/private/card-cover.jpg",
                    },
                    "public_mirror_validation": {
                        "accepted": True,
                        "source_excerpt_verified": True,
                        "excerpt_start_seconds": 20.0,
                        "excerpt_end_seconds": 58.0,
                    },
                }
            },
        }

        def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
            calls.append({"prompt": prompt, **kwargs})
            return {"ok": True, "message": "done", "thread_id": "thread-worker", "resumed": True}

        with mock.patch.object(
            worker, "run_codex_session", side_effect=fake_run_codex_session
        ), mock.patch.object(worker, "task_long_term_history_context", return_value={}):
            result = worker.run_worker_agent_session(
                task,
                {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "danger-full-access", "timeout_seconds": 300},
            )
            packet = worker.worker_agent_task_view(task)

        prompt = str(calls[0]["prompt"])
        self.assertEqual(result, "done")
        self.assertIn("/tmp/private/shipinhao-audio-transcript.md", prompt)
        self.assertIn("/tmp/private/exact-source-card.txt", prompt)
        self.assertIn("/tmp/private/card-cover.jpg", prompt)
        self.assertIn("Please summarize this video", prompt)
        self.assertIn("source_excerpt_verified", prompt)
        self.assertNotIn("private-signed-token", prompt)
        self.assertNotIn("<finderFeed>", prompt)
        self.assertNotIn("stodownload", prompt)
        self.assertNotIn("source.mp4", json.dumps(packet, ensure_ascii=False))
        self.assertLess(len(json.dumps(packet, ensure_ascii=False)), len(json.dumps(task, ensure_ascii=False)))

    def test_worker_packet_retrieves_old_exact_chat_context_without_last_n_limit(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "memory.sqlite"
            with sqlite3.connect(db) as connection:
                connection.execute(
                    """
                    CREATE TABLE source_messages (
                        id INTEGER PRIMARY KEY,
                        chat_name TEXT,
                        direction TEXT,
                        sender_display TEXT,
                        body TEXT,
                        create_time INTEGER,
                        observed_at TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO source_messages VALUES (1, ?, 'inbound', 'owner', ?, 1, '')",
                    ("EchoMind", "Remember the rare uvular pronunciation problem."),
                )
                connection.executemany(
                    "INSERT INTO source_messages VALUES (?, ?, 'inbound', 'owner', ?, ?, '')",
                    [
                        (index, "EchoMind", f"ordinary recent row {index}", index)
                        for index in range(2, 302)
                    ],
                )
            task = {
                "id": "history-worker",
                "chat": "EchoMind",
                "request": "Help with the uvular pronunciation problem again.",
                "source": {"local_id": 302, "sender_display": "owner"},
                "routine": {"id": "general_worker", "purpose": "language help"},
            }
            with mock.patch.object(worker, "DEFAULT_MEMORY_DB", db):
                packet = worker.worker_agent_task_view(task)

        self.assertIn(
            "rare uvular pronunciation",
            packet["high_fidelity_same_chat_history"],
        )
        self.assertEqual(packet["history_compaction"]["scanned_messages"], 301)
        self.assertEqual(packet["history_compaction"]["represented_messages"], 301)
        self.assertEqual(packet["history_compaction"]["coverage_ratio"], 1.0)
        self.assertNotIn("exact_excerpt_source_ids", packet["history_compaction"])

    def test_aginti_worker_prompt_is_bounded_and_uses_one_selected_routine(self) -> None:
        worker = load_worker()
        task = {
            "id": "bounded-aginti-task",
            "chat": "LabAgent",
            "status": "running",
            "request": "Current coalesced request:\nCreate the requested PDF and send it back.",
            "artifact_dir": "/tmp/exact-task/artifacts",
            "source": {"local_id": 81, "sender_display": "Researcher"},
            "route_decision": {"route_kind": "research", "worker_needed": True},
            "routine": {
                "id": "general_worker",
                "title": "General worker",
                "purpose": "Use established project routines.",
                "rules": ["Do not redesign mature routines."],
                "stages": [{"id": "execute", "owner": "agent"}],
            },
            "routine_contract": {
                "json": "/tmp/exact-task/routine_contract.json",
                "markdown": "/tmp/exact-task/routine_contract.md",
                "cheat_sheet": "/tmp/exact-task/agent_routine_cheat_sheet.md",
            },
            "context": [
                {
                    "local_id": index,
                    "sender_display": "Researcher",
                    "content": f"context-{index} " + ("detail " * 1000),
                }
                for index in range(30)
            ],
            "interruptions": [
                {
                    "at": str(index),
                    "request": f"new-request-{index} " + ("update " * 1000),
                    "source": {"local_id": 100 + index, "sender_display": "Researcher"},
                }
                for index in range(20)
            ],
        }

        prompt = worker.build_aginti_worker_prompt(task)

        self.assertLess(len(prompt), 32000)
        self.assertIn("routine_contract.json", prompt)
        self.assertIn("new-request-19", prompt)
        self.assertIn("Create the requested PDF", prompt)
        self.assertIn("Do not redesign those systems", prompt)
        self.assertIn("short meaningful basename", prompt)
        self.assertIn("2026-08-22-organoid-imaging-review.pdf", prompt)
        self.assertIn('"artifact_root":"/tmp/exact-task/artifacts"', prompt)
        self.assertNotIn("For `task.routine.id=video_publish_existing`", prompt)

    def test_aginti_evidence_scope_excludes_daily_history_from_semantic_gates(self) -> None:
        worker = load_worker()
        task = {
            "id": "daily-scope",
            "chat": "LabAgent",
            "request": (
                "Prepare today's briefing. Recent same-group discussion: "
                "old output report-2026-08-25.md must include `old required term`."
            ),
            "daily_research": {
                "report_date": "2026-08-27",
                "topics": ["类器官与闭环实验"],
            },
            "artifact_dir": "/tmp/daily-scope",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "research_summary", "title": "Research"},
        }

        prompt = worker.build_aginti_worker_prompt(task)
        scope_line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("AGINTI_EVIDENCE_SCOPE_JSON:")
        )

        self.assertIn("2026-08-27", scope_line)
        self.assertIn("类器官与闭环实验", scope_line)
        self.assertNotIn("report-2026-08-25.md", scope_line)
        self.assertNotIn("old required term", scope_line)
        self.assertIn("report-2026-08-25.md", prompt)

    def test_aginti_evidence_scope_prefers_authoritative_message_ledger(self) -> None:
        worker = load_worker()
        task = {
            "id": "ledger-scope",
            "chat": "Shares",
            "request": "Old wrapper text with stale-output.pdf",
            "message_ledger": [
                {"item_id": "message:1", "text": "Read the first article."},
                {"item_id": "message:2", "text": "Compare it with the second article."},
            ],
            "artifact_dir": "/tmp/ledger-scope",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "research_summary", "title": "Research"},
        }

        prompt = worker.build_aginti_worker_prompt(task)
        scope_line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("AGINTI_EVIDENCE_SCOPE_JSON:")
        )

        self.assertIn("Read the first article", scope_line)
        self.assertIn("Compare it with the second article", scope_line)
        self.assertNotIn("stale-output.pdf", scope_line)

    def test_aginti_completion_repair_survives_compaction_and_drives_scope(self) -> None:
        worker = load_worker()
        task = {
            "id": "repair-scope",
            "chat": "LabAgent",
            "request": "Prepare today's report.",
            "daily_research": {
                "report_date": "2026-08-27",
                "topics": ["old broad topic"],
            },
            "artifact_dir": "/tmp/repair-scope",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "research_summary", "title": "Research"},
            "completion_audit_repair": {
                "missing": [
                    {
                        "item_id": "task:repair-scope",
                        "requirement": "Return the corrected PDF.",
                        "kind": "artifact",
                    }
                ],
                "artifact_repair": {
                    "artifact_root": "/tmp/repair-scope",
                    "source_candidates": [
                        {
                            "path": "/tmp/repair-scope/organoid-review.md",
                            "workspace_path": "output/repair-scope/organoid-review.md",
                        }
                    ],
                    "rejected_artifacts": [
                        {
                            "path": "/tmp/repair-scope/organoid-review.pdf",
                            "workspace_path": "output/repair-scope/organoid-review.pdf",
                            "issues": ["missing_complete_reference_section"],
                        }
                    ],
                },
            },
        }
        huge_history = {
            "full_memory": "historical-noise " * 10000,
            "exact_excerpts": "stale-output.pdf " * 10000,
            "manifest": {"represented_messages": 999},
        }

        with mock.patch.object(
            worker,
            "task_long_term_history_context",
            return_value=huge_history,
        ):
            prompt = worker.build_aginti_worker_prompt(task)

        scope_line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("AGINTI_EVIDENCE_SCOPE_JSON:")
        )
        self.assertIn("output/repair-scope/organoid-review.md", scope_line)
        self.assertIn("missing_complete_reference_section", scope_line)
        self.assertIn('"completion_audit_repair"', prompt)
        self.assertNotIn("historical-noise", prompt)
        self.assertNotIn("stale-output.pdf", prompt)

    def test_aginti_reprocess_correction_survives_compaction_and_drives_scope(self) -> None:
        worker = load_worker()
        task = {
            "id": "reprocess-scope",
            "chat": "LabAgent",
            "request": "Prepare today's report from the enrolled daily topic.",
            "daily_research": {
                "report_date": "2026-08-27",
                "topics": ["old broad topic"],
            },
            "artifact_dir": "/tmp/reprocess-scope",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "research_summary", "title": "Research"},
            "reprocess_requested_at": "2026-08-27T12:00:00",
            "reprocess_reason": (
                "Repair the exact rejected reader-facing PDF using only this task's "
                "existing report and evidence."
            ),
            "pdf_quality_rejections": [
                {
                    "path": "/tmp/reprocess-scope/old.pdf",
                    "issues": [
                        "internal_task_identity",
                        "missing_complete_reference_section",
                    ],
                }
            ],
        }
        huge_history = {
            "full_memory": "historical-noise " * 10000,
            "exact_excerpts": "stale-output.pdf " * 10000,
            "manifest": {"represented_messages": 999},
        }

        with mock.patch.object(
            worker,
            "task_long_term_history_context",
            return_value=huge_history,
        ):
            prompt = worker.build_aginti_worker_prompt(task)

        scope_line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("AGINTI_EVIDENCE_SCOPE_JSON:")
        )
        self.assertIn("Repair the exact rejected reader-facing PDF", scope_line)
        self.assertIn("materially revise a source file", scope_line.casefold())
        self.assertIn("missing_complete_reference_section", scope_line)
        self.assertIn('"reprocess"', prompt)
        self.assertIn('"pdf_quality_rejections"', prompt)
        self.assertNotIn("old broad topic", scope_line)
        self.assertNotIn("historical-noise", prompt)
        self.assertNotIn("stale-output.pdf", prompt)

    def test_aginti_reprocess_recovers_legacy_nested_pdf_rejections(self) -> None:
        worker = load_worker()
        task = {
            "id": "legacy-rejection-scope",
            "chat": "LabAgent",
            "request": "Repair and send the rejected PDF.",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "research_summary", "title": "Research"},
            "reprocess_requested_at": "2026-08-27T12:00:00",
            "reprocess_reason": "Repair the exact rejected reader-facing PDF.",
            "result": {
                "data": {
                    "pdf_quality_rejections": [
                        {
                            "path": "/tmp/legacy-report.pdf",
                            "issues": [
                                "internal_task_identity",
                                "missing_complete_reference_section",
                            ],
                        }
                    ]
                }
            },
        }

        packet = worker.aginti_worker_task_view(task)
        scope = worker.aginti_worker_evidence_scope_request(task, packet)

        self.assertEqual(
            packet["pdf_quality_rejections"][0]["issues"],
            ["internal_task_identity", "missing_complete_reference_section"],
        )
        self.assertIn("missing_complete_reference_section", scope)

    def test_aginti_reprocess_refreshes_stale_pdf_rejections_and_focuses_packet(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "organoid-review.pdf"
            report.write_bytes(b"%PDF-1.4\ncurrent")
            task = {
                "id": "current-rejection-scope",
                "chat": "LabAgent",
                "request": (
                    "Prepare today's briefing.\nRecent same-group discussion:\n"
                    + ("historical-noise " * 4000)
                ),
                "artifact_dir": tmp,
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
                "routine": {
                    "id": "research_summary",
                    "title": "Research",
                    "purpose": "Repair the current report.",
                    "rules": ["historical-rule " * 2000],
                },
                "reprocess_requested_at": "2026-08-27T12:00:00",
                "reprocess_reason": "Repair only the current PDF layout.",
                "pdf_quality_rejections": [
                    {
                        "path": str(report),
                        "issues": [
                            "internal_task_identity",
                            "missing_complete_reference_section",
                        ],
                    }
                ],
            }
            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=["orphan_final_pdf_page"],
            ):
                packet = worker.aginti_worker_task_view(task)
                prompt = worker.build_aginti_worker_prompt(task)

        self.assertEqual(
            packet["pdf_quality_rejections"][0]["issues"],
            ["orphan_final_pdf_page"],
        )
        self.assertNotIn("historical-noise", prompt)
        self.assertNotIn("historical-rule", prompt)
        self.assertLess(len(prompt), 18000)

    def test_aginti_reprocess_rediscovers_erased_task_local_pdf_rejections(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "organoid-review.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            task = {
                "id": "rediscovered-rejection-scope",
                "chat": "LabAgent",
                "request": "Repair and send the rejected PDF.",
                "artifact_dir": tmp,
                "route_decision": {"route_kind": "research_or_summary"},
                "routine": {"id": "research_summary", "title": "Research"},
                "reprocess_requested_at": "2026-08-27T12:00:00",
                "reprocess_reason": "Repair the exact rejected reader-facing PDF.",
                "result": {"message": "Worker failed before returning a file."},
            }
            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=[
                    "missing_reader_evidence_section",
                    "missing_source_level_methods_results_limits",
                ],
            ):
                packet = worker.aginti_worker_task_view(task)

        self.assertEqual(
            packet["pdf_quality_rejections"][0]["issues"],
            [
                "missing_reader_evidence_section",
                "missing_source_level_methods_results_limits",
            ],
        )

    def test_pdf_rejection_survives_agent_result_without_pdf(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Repair and send the rejected PDF.",
            "pdf_quality_rejections": [
                {
                    "path": "/tmp/rejected.pdf",
                    "issues": ["missing_complete_reference_section"],
                }
            ],
        }

        result = worker.enforce_reader_facing_pdf_quality(
            task,
            {"message": "Permission required.", "files": []},
        )

        self.assertEqual(result["data"]["pdf_quality_rejections"], [])
        self.assertEqual(
            task["pdf_quality_rejections"][0]["issues"],
            ["missing_complete_reference_section"],
        )

    def test_required_artifact_omission_cannot_finish_task(self) -> None:
        worker = load_worker()
        task = {
            "id": "missing-required-pdf",
            "daily_research": {"report_date": "2026-08-27"},
            "execution_contract": {"required_artifacts": ["compiled_pdf"]},
        }
        result = {
            "message": "The summary is ready but the PDF is missing.",
            "files": [],
            "confirmation": "",
        }

        self.assertTrue(worker.result_requires_file_delivery(task, result))
        self.assertFalse(worker.required_file_delivery_complete(task, result))
        self.assertTrue(worker.required_artifact_missing_from_result(task, result))

        worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], "worker_failed")
        self.assertEqual(task["worker_error"]["type"], "RequiredArtifactMissing")

    def test_worker_session_passes_compact_prompt_only_to_aginti(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        task = {
            "id": "backend-prompt-task",
            "chat": "LabAgent",
            "request": "Create a concise research PDF.",
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {
                "id": "general_worker",
                "title": "General worker",
                "purpose": "Complete the selected task.",
                "stages": [{"id": "execute", "owner": "agent"}],
            },
            "routine_contract": {"json": "/tmp/task/routine_contract.json"},
        }

        def fake_agent(prompt: str, **kwargs: object) -> dict[str, object]:
            calls.append({"prompt": prompt, **kwargs})
            return {"ok": True, "message": "done", "thread_id": "worker"}

        with mock.patch.object(worker, "run_codex_session", side_effect=fake_agent):
            result = worker.run_worker_agent_session(
                task,
                {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "medium",
                    "sandbox": "danger-full-access",
                    "timeout_seconds": 300,
                },
            )

        self.assertEqual(result, "done")
        self.assertIn("Bounded task packet", calls[0]["prompt"])
        backend_prompts = calls[0]["backend_prompts"]
        self.assertIsInstance(backend_prompts, dict)
        self.assertIn("Exact task packet", backend_prompts["aginti"])
        self.assertLess(len(backend_prompts["aginti"]), len(calls[0]["prompt"]))

    def test_all_worker_backends_receive_the_same_authoritative_message_ledger(self) -> None:
        worker = load_worker()
        task = {
            "id": "shares-ledger-229",
            "chat": "Shares鏈接",
            "request": "Read and summarize both shared articles.",
            "source": {"local_id": 229, "sender_display": "owner"},
            "route_decision": {"route_kind": "research_or_summary"},
            "routine": {"id": "general_worker", "title": "General worker"},
            "message_ledger": [
                {
                    "item_id": "message:message_1.db:228",
                    "sequence": 1,
                    "sender_display": "owner",
                    "text": "随感录：被权力污染的语言",
                },
                {
                    "item_id": "task:shares-ledger-229",
                    "sequence": 2,
                    "sender_display": "owner",
                    "text": "Tony Robbins on personal change",
                },
            ],
            "message_ledger_contract": {
                "schema": "labcanvas-message-ledger-v1",
                "coverage_required_per_item": True,
                "combined_reply_allowed": True,
            },
        }

        full = worker.worker_agent_task_view(task)
        aginti = worker.aginti_worker_task_view(task)
        prompt = worker.build_aginti_worker_prompt(task)

        full_ids = [item["item_id"] for item in full["message_ledger"]]
        aginti_ids = [item["item_id"] for item in aginti["message_ledger"]]
        self.assertEqual(full_ids, aginti_ids)
        self.assertEqual(
            [item["text"] for item in full["message_ledger"]],
            [item["text"] for item in aginti["message_ledger"]],
        )
        self.assertEqual(aginti["schema"], "labcanvas-agent-task-v2")
        self.assertIn("message:message_1.db:228", prompt)
        self.assertIn("task:shares-ledger-229", prompt)
        self.assertIn("随感录：被权力污染的语言", prompt)
        self.assertIn("Tony Robbins on personal change", prompt)

    def test_orchestrator_runs_deterministic_stage_without_codex_session(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-missing-source",
            "chat": "🍓我的设备",
            "request": "Current coalesced request:\npublish this video to YouTube",
            "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
            "context": [
                {"local_id": 14, "sender_display": "陈苗", "content": '<msg><videomsg md5="bea815fa6ed81bbd5da77ac6895c5fd9" /></msg>'},
                {"local_id": 16, "sender_display": "陈苗", "content": "publish this video"},
            ],
        }

        def forbidden_session(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("deterministic routine stage should not start Codex")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(worker, "worker_artifact_dir", return_value=Path(tmp)):
                with mock.patch.object(
                    worker,
                    "prepare_worker_preflight",
                    return_value={
                        "autopublish_video": {
                            "ok": False,
                            "message_local_ids": [14],
                            "recent_video_messages": [{"chat": "🍓我的设备", "recent_video_rows": 1}],
                            "artifact_resolution": {"ok": False, "error": "no same-chat artifact match"},
                        }
                    },
                ):
                    with mock.patch.object(worker, "run_codex_session", side_effect=forbidden_session):
                        result = worker.run_task_orchestrator(
                            task,
                            {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "danger-full-access", "timeout_seconds": 600},
                        )

        self.assertIn("我没有发布这个视频", result)
        self.assertEqual(task["orchestrator"]["last_action"], "deterministic_routine_stage")
        self.assertEqual(task["orchestrator"]["mode"], "routine_supervisor")

    def test_orchestrator_resumes_codex_session_for_nontrivial_stage(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
            calls.append({"prompt": prompt, **kwargs})
            return {"ok": True, "message": '{"message":"done","files":[],"confirmation":""}', "thread_id": "thread-worker", "resumed": True}

        task = {
            "id": "research-task",
            "chat": "懒人科研",
            "request": "Current coalesced request:\nsummarize this paper",
            "route_decision": {"route_kind": "research_or_summary"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(worker, "worker_artifact_dir", return_value=Path(tmp)):
                with mock.patch.object(worker, "prepare_worker_preflight", return_value={}):
                    with mock.patch.object(worker, "run_codex_session", side_effect=fake_run_codex_session):
                        result = worker.run_task_orchestrator(
                            task,
                            {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "danger-full-access", "timeout_seconds": 300},
                        )

        self.assertIn("done", result)
        self.assertEqual(task["orchestrator"]["last_action"], "resume_codex_worker_session")
        self.assertEqual(calls[0]["chat_name"], "懒人科研")
        self.assertEqual(calls[0]["role"], "worker")
        self.assertEqual(calls[0]["reuse"], True)
        self.assertIn("Execution contract", str(calls[0]["prompt"]))
        self.assertIn("resume_per_chat_worker_session", str(calls[0]["prompt"]))
        self.assertEqual(calls[0]["reuse"], True)
        self.assertIn("Central orchestrator handoff", str(calls[0]["prompt"]))
        self.assertIn("Instruction contract", str(calls[0]["prompt"]))
        self.assertIn("current_request_authoritative", str(calls[0]["prompt"]))
        self.assertIn("no_keyword_shrink", str(calls[0]["prompt"]))
        self.assertIn("Autonomy rule", str(calls[0]["prompt"]))
        self.assertIn("autonomous_completion_required", str(calls[0]["prompt"]))
        self.assertIn("worker_must_continue_via_routine_until_terminal_state", str(calls[0]["prompt"]))
        self.assertIn("Follow every safe, explicit instruction", str(calls[0]["prompt"]))
        self.assertIn("do not collapse the request to a smaller hardcoded action", str(calls[0]["prompt"]))
        self.assertIn("cheat_sheet", task["routine_contract"])

    def test_existing_video_publish_runs_agent_before_pipeline_verifier(self) -> None:
        worker = load_worker()
        order: list[str] = []
        policies: list[dict[str, object]] = []
        task = {
            "id": "publish-exact-video",
            "chat": "My devices",
            "request": "Publish this exact video to YouTube.",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "routine": {"id": "video_publish_existing"},
        }

        def agent(_task: dict, policy: dict) -> str:
            order.append("agent")
            policies.append(dict(policy))
            return '{"message":"LazyEdit job submitted","files":[],"confirmation":""}'

        def verifier(_task: dict) -> str:
            order.append("verify")
            return '{"message":"publish running","files":[],"confirmation":""}'

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(worker, "worker_artifact_dir", return_value=Path(tmp)),
                mock.patch.object(
                    worker,
                    "prepare_worker_preflight",
                    return_value={
                        "autopublish_video": {
                            "ok": True,
                            "status": "copied",
                            "target": str(Path(tmp) / "exact_COMPLETED.mp4"),
                        },
                        "lazyedit_context": {
                            "correction_prompt_file": str(Path(tmp) / "correction.md"),
                            "metadata_prompt_file": str(Path(tmp) / "metadata.md"),
                        },
                    },
                ),
                mock.patch.object(worker, "run_worker_agent_session", side_effect=agent),
                mock.patch.object(worker, "deterministic_preflight_result", side_effect=verifier),
                mock.patch.object(worker, "persist_task_progress"),
            ):
                result = worker.run_task_orchestrator(
                    task,
                    {
                        "model": "auto-code-review",
                        "reasoning_effort": "low",
                        "sandbox": "danger-full-access",
                        "timeout_seconds": 120,
                    },
                )

        self.assertIn("publish running", result)
        self.assertEqual(order, ["agent", "verify"])
        self.assertEqual(policies[0]["model"], "gpt-5.6-sol")
        self.assertEqual(policies[0]["reasoning_effort"], "low")
        self.assertEqual(
            task["orchestrator"]["last_action"],
            "verify_or_recover_publish_after_agent",
        )

    def test_lazyedit_null_video_list_is_temporary_unavailability(self) -> None:
        worker = load_worker()
        with mock.patch.object(
            worker,
            "lazyedit_api_get",
            return_value={"videos": None},
        ):
            videos = worker.lazyedit_videos()

        self.assertEqual(videos, [])

    def test_known_lazyedit_video_id_uses_exact_publish_queue_stem(self) -> None:
        worker = load_worker()
        autopub = {
            "target_name": "exact_trip_COMPLETED.mp4",
            "target": "/tmp/exact_trip_COMPLETED.mp4",
        }

        with mock.patch.object(
            worker,
            "lazyedit_api_get",
            return_value={
                "jobs": [
                    {
                        "video_id": 495,
                        "filename": "exact_trip_COMPLETED.zip",
                        "status": "done",
                    },
                    {
                        "video_id": 494,
                        "filename": "nearby_trip_COMPLETED.zip",
                        "status": "done",
                    },
                ]
            },
        ):
            video_id = worker.known_lazyedit_video_id_for_autopub(autopub)

        self.assertEqual(video_id, 495)

    def test_existing_video_publish_agent_caps_legacy_xhigh_policy(self) -> None:
        worker = load_worker()

        policy = worker.existing_video_publish_agent_policy(
            {
                "model": "gpt-5.5",
                "reasoning_effort": "xhigh",
                "timeout_seconds": 1200,
            }
        )

        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "medium")
        self.assertEqual(policy["timeout_seconds"], worker.timeout_for_effort("medium"))
        self.assertTrue(policy["reuse_session"])

    def test_existing_verified_publish_bypasses_agent_session(self) -> None:
        worker = load_worker()
        task = {
            "request": "Publish this exact video.",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "preflight": {
                "autopublish_video": {
                    "ok": True,
                    "target": "/tmp/exact_COMPLETED.mp4",
                }
            },
        }

        with (
            mock.patch.object(worker, "known_lazyedit_video_id_for_autopub", return_value=495),
            mock.patch.object(
                worker,
                "verify_lazyedit_publish_stage",
                return_value={
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 495,
                },
            ),
        ):
            supervise = worker.should_agent_supervise_existing_video_publish(task)

        self.assertFalse(supervise)
        self.assertEqual(task["publish_agent_bypassed"]["stage"], "published_verified")
        self.assertEqual(task["publish_agent_bypassed"]["video_id"], 495)

    def test_publish_waiting_login_does_not_escalate_worker_model(self) -> None:
        worker = load_worker()
        task = {
            "request": "Publish this video to Shipinhao.",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
        }
        result = json.dumps(
            {
                "message": "Waiting for login.",
                "publish_stage": {"stage": "waiting_login", "video_id": 495},
            }
        )

        with (
            mock.patch.object(
                worker,
                "choose_worker_policy",
                return_value={
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "medium",
                    "timeout_seconds": 600,
                },
            ),
            mock.patch.object(worker, "run_worker_codex_once", return_value=result) as run,
            mock.patch.object(worker, "escalated_policy") as escalate,
        ):
            actual = worker.run_worker_codex(task)

        self.assertEqual(actual, result)
        self.assertEqual(run.call_count, 1)
        escalate.assert_not_called()
        self.assertFalse(task["worker_result_exhausted"])

    def test_running_agent_supervised_publish_is_not_reissued(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "exact_COMPLETED.mp4"
            video.write_bytes(b"video")
            task = {
                "request": "Publish this video to YouTube.",
                "route_decision": {
                    "route_kind": "publish_video",
                    "public_publish_allowed": True,
                },
                "publish_agent_supervision": {"status": "completed"},
                "preflight": {
                    "lazyedit_context": {
                        "correction_prompt_file": str(Path(tmp) / "correction.md"),
                        "metadata_prompt_file": str(Path(tmp) / "metadata.md"),
                    }
                },
            }
            with (
                mock.patch.object(
                    worker,
                    "known_lazyedit_video_id_for_autopub",
                    return_value=72,
                ),
                mock.patch.object(
                    worker,
                    "verify_lazyedit_publish_stage",
                    return_value={
                        "verified": False,
                        "stage": "publish_running",
                        "video_id": 72,
                        "requested_platforms": ["youtube"],
                    },
                ),
                mock.patch.object(worker, "run_lazyedit_publish_command") as publish,
            ):
                raw = worker.run_deterministic_lazyedit_publish(
                    task,
                    {"ok": True, "target": str(video)},
                )

        payload = json.loads(raw or "{}")
        publish.assert_not_called()
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")
        self.assertEqual(
            payload["publish_poststage_retry"]["outcome"]["status"],
            "probe",
        )

    def test_worker_backfills_instruction_contract_for_legacy_task(self) -> None:
        worker = load_worker()
        task = {
            "id": "legacy-task",
            "chat": "懒人科研",
            "request": "Current coalesced request:\nmake a CAD render and send it back",
            "route_decision": {"route_kind": "cad_pcb_labcanvas"},
            "execution_contract": {"codex_exec_mode": "resume_per_chat_worker_session"},
        }

        worker.ensure_runtime_instruction_contract(task)

        self.assertTrue(task["instruction_contract"]["current_request_authoritative"])
        self.assertTrue(task["instruction_contract"]["preserve_safe_explicit_instructions"])
        self.assertTrue(task["instruction_contract"]["no_keyword_shrink"])
        self.assertTrue(task["instruction_contract"]["autonomous_completion_required"])
        self.assertTrue(task["instruction_contract"]["worker_must_continue_via_routine_until_terminal_state"])
        self.assertEqual(task["instruction_contract"]["route_kind"], "cad_pcb_labcanvas")
        self.assertEqual(task["execution_contract"]["instruction_contract"], task["instruction_contract"])

    def test_worker_writes_routine_contract_before_codex(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        original_session = worker.run_codex_session
        original_artifact_dir = worker.worker_artifact_dir
        try:
            with tempfile.TemporaryDirectory() as tmp:
                artifact_dir = Path(tmp) / "task-artifacts"

                def fake_artifact_dir(_task: dict[str, object]) -> Path:
                    return artifact_dir

                def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                    calls.append({"prompt": prompt, **kwargs})
                    return {"ok": True, "message": "done", "thread_id": "thread-worker", "resumed": False}

                worker.worker_artifact_dir = fake_artifact_dir
                worker.run_codex_session = fake_run_codex_session
                task = {
                    "id": "task-routine",
                    "chat": "懒人科研",
                    "request": "Current coalesced request:\nrender this PCB in Blender\n\nRecent history:\n",
                    "route_decision": {"route_kind": "cad_pcb_labcanvas", "project": "labcanvas"},
                    "source": {"local_id": 7},
                }

                result = worker.run_worker_codex_once(
                    task,
                    {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "workspace-write", "timeout_seconds": 300},
                )
                routine_json = artifact_dir / "routine_contract.json"
                routine_md = artifact_dir / "routine_contract.md"
                payload = json.loads(routine_json.read_text(encoding="utf-8"))
                routine_md_exists = routine_md.exists()
        finally:
            worker.run_codex_session = original_session
            worker.worker_artifact_dir = original_artifact_dir

        self.assertEqual(result, "done")
        self.assertEqual(task["routine"]["id"], "labcanvas_cad_pcb")
        self.assertEqual(payload["id"], "labcanvas_cad_pcb")
        self.assertTrue(routine_md_exists)
        self.assertIn("routine_contract", task)
        self.assertIn("labcanvas_cad_pcb", str(calls[0]["prompt"]))

    def test_worker_policy_caps_lalachan_video_generation_at_medium(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "写 RaraXia AyaChan SasaKun 故事并用小云雀生成视频"})

        self.assertEqual(policy["reasoning_effort"], "medium")

    def test_lazyedit_publish_skill_is_checked_in(self) -> None:
        skill = ROOT / "agentic_tools" / "wechat_gui_agent" / "skills" / "lazyedit-publish-workflow" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")

        self.assertIn("LazyEdit Publish Workflow", text)
        self.assertIn("autopublish-video", text)
        self.assertIn("scripts/lazyedit_publish.py", text)
        self.assertIn("Shipinhao", text)
        self.assertIn("--metadata-prompt-file", text)
        self.assertIn("temporary quality gate", text)

    def test_worker_result_collects_nested_and_plain_artifact_paths(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "render.png"
            step = Path(tmp) / "part.step"
            mp4 = Path(tmp) / "publish_preview.mp4"
            png.write_bytes(b"png")
            step.write_text("step", encoding="utf-8")
            mp4.write_bytes(b"video")
            raw = json.dumps({"message": "", "artifacts": [{"path": str(png)}], "videos": [str(mp4)]}, ensure_ascii=False)
            result = worker.parse_worker_result(raw)

            prepared = worker.prepare_result_files(result, f"Also created {step}")

        self.assertIn(str(png.resolve()), prepared["files"])
        self.assertIn(str(step.resolve()), prepared["files"])
        self.assertIn(str(mp4.resolve()), prepared["files"])
        self.assertEqual(prepared["message"], "")

    def test_worker_result_allows_safe_video_and_audio_artifacts(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "clip.mp4"
            audio = Path(tmp) / "voice.m4a"
            mp4.write_bytes(b"video")
            audio.write_bytes(b"audio")

            result = worker.prepare_result_files({"message": "", "confirmation": "", "files": [str(mp4), str(audio)]}, "")

        self.assertIn(str(mp4.resolve()), result["files"])
        self.assertIn(str(audio.resolve()), result["files"])

    def test_resend_task_result_uses_stored_result_without_rerunning_worker(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        original = worker.send_result_with_retries
        try:
            def fake_send_result_with_retries(result, target_chat, send_targets, *, task=None):
                calls.append({"result": result, "target_chat": target_chat, "send_targets": send_targets, "task": task})
                return []

            worker.send_result_with_retries = fake_send_result_with_retries
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-resend",
                            "chat": "🍓我的设备",
                            "status": "send_failed",
                            "result": {"message": "done", "confirmation": "", "files": []},
                        }
                    ],
                )
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = worker.resend_task_result(queue, "task-resend", "fallback-chat", send_targets=Path(tmp) / "targets.json")
                saved = worker.find_task(queue, "task-resend")
        finally:
            worker.send_result_with_retries = original

        self.assertEqual(code, 0)
        self.assertEqual(calls[0]["target_chat"], "🍓我的设备")
        self.assertEqual(calls[0]["result"]["message"], "done")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved["status"], "done")
        self.assertIn("resent_at", saved)

    def test_repair_stored_result_reapplies_contract_without_agent_and_sends_once(self) -> None:
        worker = load_worker()
        raw = json.dumps(
            {
                "message": (
                    "今天的故事：四个人在别墅院子挖土豆，再到厨房炸薯条。"
                    "现在只确认故事，不进入 LazyEdit 或发布流程。"
                ),
                "files": [],
                "confirmation": "这个故事可以吗？确认后我再生成视频。",
            },
            ensure_ascii=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "story-repair",
                        "chat": "MEMO",
                        "status": "done",
                        "request": "Current coalesced request:\n先给我故事，不要生成。",
                        "source": {"local_id": 4},
                        "context": [
                            {
                                "local_id": 4,
                                "content": "先给我故事，不要生成。",
                            }
                        ],
                        "route_decision": {
                            "route_kind": "generate_video",
                            "project": "lalachan",
                            "public_publish_allowed": False,
                        },
                        "result": {
                            "message": "我已拦截这个结果。",
                            "confirmation": "",
                            "files": [],
                            "raw": raw,
                            "contract_guard": "blocked_public_publish_claim_for_generate_video",
                        },
                    }
                ],
            )

            with (
                mock.patch.object(
                    worker,
                    "run_worker_codex",
                    side_effect=AssertionError("repair must not invoke the agent"),
                ),
                mock.patch.object(
                    worker,
                    "send_result_with_retries",
                    return_value=[],
                ) as sender,
                mock.patch.object(
                    worker,
                    "record_event",
                ) as event_recorder,
            ):
                first = worker.repair_stored_result_contract(
                    queue,
                    "story-repair",
                    send=True,
                    send_targets=Path(tmp) / "targets.json",
                )
                second = worker.repair_stored_result_contract(
                    queue,
                    "story-repair",
                    send=True,
                    send_targets=Path(tmp) / "targets.json",
                )

        self.assertEqual(sender.call_count, 1)
        self.assertEqual(event_recorder.call_count, 1)
        self.assertEqual(first["status"], "waiting_confirmation")
        self.assertIn("今天的故事", first["result"]["message"])
        self.assertEqual(
            first["result"]["contract_guard"],
            "generated_video_waiting_for_confirmation",
        )
        self.assertEqual(
            first["stored_contract_repair"]["delivery_status"],
            "sent",
        )
        self.assertFalse(first["stored_contract_repair"]["model_invoked"])
        self.assertFalse(
            first["stored_contract_repair"]["external_task_action_invoked"]
        )
        self.assertEqual(
            second["stored_contract_repair"]["last_noop_reason"],
            "same_repaired_result_already_sent",
        )

    def test_repair_stored_result_refuses_rejected_required_pdf(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "shallow-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            raw = json.dumps(
                {
                    "message": "报告已完成。",
                    "files": [str(report)],
                    "confirmation": "",
                },
                ensure_ascii=False,
            )
            queue = root / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-repair",
                        "chat": "LabAgent",
                        "status": "done",
                        "request": "请发送完整研究 PDF。",
                        "routine": {"id": "research_summary"},
                        "route_decision": {
                            "route_kind": "research_or_summary",
                            "require_file_delivery": True,
                        },
                        "execution_contract": {
                            "required_artifacts": ["compiled_pdf"],
                        },
                        "result": {
                            "message": "旧结果。",
                            "confirmation": "",
                            "files": [str(report)],
                            "raw": raw,
                        },
                    }
                ],
            )

            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=["orphan_final_pdf_page"],
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "no reader-quality required artifact",
                ):
                    worker.repair_stored_result_contract(
                        queue,
                        "research-repair",
                        send=True,
                        send_targets=root / "targets.json",
                    )

    def test_repair_stored_result_recovers_host_compiled_pdf_without_agent(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "full-report.pdf"
            report.write_bytes(b"%PDF-1.4\n% exact task report\n")
            raw = json.dumps(
                {
                    "message": "研究已完成。",
                    "files": [],
                    "confirmation": "",
                },
                ensure_ascii=False,
            )
            queue = root / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "host-pdf-repair",
                        "chat": "LabAgent",
                        "status": "done",
                        "request": "请发送完整研究 PDF。",
                        "routine": {"id": "research_summary"},
                        "route_decision": {
                            "route_kind": "research_or_summary",
                            "require_file_delivery": True,
                        },
                        "execution_contract": {
                            "required_artifacts": ["compiled_pdf"],
                        },
                        "message_coverage": {
                            "status": "supplement_required",
                            "expected_item_ids": ["task:host-pdf-repair"],
                            "covered_item_ids": [],
                            "unresolved_item_ids": ["task:host-pdf-repair"],
                            "missing": [
                                {
                                    "item_id": "task:host-pdf-repair",
                                    "requirement": "Create and return the PDF artifact.",
                                    "kind": "artifact",
                                }
                            ],
                        },
                        "result": {
                            "message": "旧结果。",
                            "confirmation": "",
                            "files": [],
                            "raw": raw,
                        },
                    }
                ],
            )
            recovered = {
                "message": "完整研究报告已整理完成。",
                "confirmation": "",
                "files": [str(report)],
                "data": {"require_file_delivery": True},
            }

            with (
                mock.patch.object(
                    worker,
                    "recover_completed_research_artifacts",
                    return_value=recovered,
                ) as recovery,
                mock.patch.object(
                    worker,
                    "reader_facing_pdf_quality_issues",
                    return_value=[],
                ),
                mock.patch.object(
                    worker,
                    "run_worker_codex",
                    side_effect=AssertionError("repair must not invoke the agent"),
                ),
            ):
                repaired = worker.repair_stored_result_contract(
                    queue,
                    "host-pdf-repair",
                )

        recovery.assert_called_once()
        self.assertEqual(repaired["result"]["files"], [str(report.resolve())])
        self.assertTrue(
            repaired["result"]["data"]["stored_result_contract_recovery"]
        )
        self.assertEqual(repaired["message_coverage"]["status"], "covered")
        self.assertFalse(repaired["stored_contract_repair"]["model_invoked"])

    def test_reconcile_repaired_artifact_coverage_keeps_unrelated_gap(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "full-report.pdf"
            pdf.write_bytes(b"%PDF-1.4\n% test fixture\n")
            task = {
                "id": "report-repair",
                "request": "Please return a complete PDF report.",
                "source": {"local_id": 9},
                "context": [
                    {"local_id": 9, "content": "Please return a complete PDF report."},
                    {"local_id": 10, "content": "Also answer the follow-up question."},
                ],
                "completion_audit": {
                    "status": "unavailable",
                    "attempts": [{"stage": "candidate", "status": "unavailable"}],
                    "repair_attempted": True,
                    "repair_succeeded": False,
                },
                "message_coverage": {
                    "status": "supplement_required",
                    "expected_item_ids": ["msg:9", "msg:10"],
                    "covered_item_ids": [],
                    "unresolved_item_ids": ["msg:9", "msg:10"],
                    "missing": [
                        {
                            "item_id": "msg:9",
                            "requirement": "Return the complete PDF report.",
                            "kind": "artifact",
                        },
                        {
                            "item_id": "msg:10",
                            "requirement": "Answer the separate follow-up question.",
                            "kind": "answer",
                        },
                    ],
                },
                "skipped_files": [
                    {
                        "path": str(pdf),
                        "reason": "reader-facing-pdf-quality:missing_complete_reference_section",
                    }
                ],
            }
            result = {
                "message": "The full report is attached.",
                "files": [str(pdf)],
                "data": {"pdf_quality_rejections": []},
            }
            with mock.patch.object(
                worker,
                "reader_facing_pdf_quality_issues",
                return_value=[],
            ):
                resolved = worker.reconcile_repaired_artifact_coverage(
                    task,
                    result,
                    checked_at="2026-08-25T13:30:00",
                )

        self.assertEqual(resolved, ["msg:9"])
        self.assertEqual(task["message_coverage"]["covered_item_ids"], ["msg:9"])
        self.assertEqual(task["message_coverage"]["unresolved_item_ids"], ["msg:10"])
        self.assertEqual(task["message_coverage"]["missing"][0]["item_id"], "msg:10")
        self.assertFalse(task["completion_audit"]["repair_succeeded"])
        self.assertNotIn("skipped_files", task)
        self.assertFalse(
            task["completion_audit"]["attempts"][-1]["model_invoked"]
        )

    def test_video_publish_preflight_writes_context_and_uses_exact_message_id(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-video",
            "chat": "🍓我的设备",
            "request": "publish the video at local_id14 to sph Ins y2b and correct subtitles with the context",
            "source": {"local_id": 16, "sender_display": "陈苗"},
            "context": [
                {"local_id": 10, "sender_display": "陈苗", "content": "Context is haircut and curly; use this to correct subtitles"},
                {
                    "local_id": 14,
                    "message_db": "message_1.db",
                    "local_type": 43,
                    "sender_display": "陈苗",
                    "content": '<msg><videomsg md5="bea815fa6ed81bbd5da77ac6895c5fd9" length="19452344" /></msg>',
                },
                {"local_id": 16, "sender_display": "陈苗", "content": "Could you publish it?"},
            ],
        }
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '{"ok": true, "status": "copied", "target": "/tmp/demo_COMPLETED.mp4"}', "")

        with tempfile.TemporaryDirectory() as tmp:
            task["queue_path"] = str(Path(tmp) / "empty_queue.jsonl")
            worker.write_tasks(Path(task["queue_path"]), [])
            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

            context_path = Path(preflight["lazyedit_context"]["correction_prompt_file"])
            metadata_path = Path(preflight["lazyedit_context"]["metadata_prompt_file"])
            context_text = context_path.read_text(encoding="utf-8")
            metadata_text = metadata_path.read_text(encoding="utf-8")

        self.assertTrue(context_path.name.endswith("correction_context.md"))
        self.assertTrue(metadata_path.name.endswith("metadata_brief.md"))
        self.assertIn("haircut and curly", context_text)
        self.assertIn("Current user request:", metadata_text)
        self.assertIn("publish the video at local_id14", metadata_text)
        self.assertIn("bea815fa6ed81bbd5da77ac6895c5fd9", context_text)
        self.assertEqual(preflight["autopublish_video"]["ok"], True)
        self.assertEqual(preflight["autopublish_video"]["message_local_ids"], [14])
        self.assertEqual(preflight["autopublish_video"]["message_refs"], ["message_1.db:14"])
        self.assertTrue(calls)
        self.assertIn("--message-local-id", calls[0])
        self.assertIn("14", calls[0])
        self.assertIn("--message-ref", calls[0])
        self.assertIn("message_1.db:14", calls[0])
        self.assertIn("--fetch-gui", calls[0])

    def test_lazyedit_prompts_exclude_transport_wrapper_and_raw_media_xml(self) -> None:
        worker = load_worker()
        wrapper = (
            "Treat this as a message forwarded from WeChat into the backend Codex session "
            "for this chat. Agent route decision: internal-only.\n\n"
            "Current coalesced request:\nPublish this exact video with background fill.\n\n"
            "Recent history:\ninternal transport history"
        )
        task = {
            "request": wrapper,
            "source": {
                "local_id": 16,
                "sender": "requester",
                "sender_display": "Requester",
                "kind": "text",
                "message_db": "message_1.db",
            },
            "context": [
                {
                    "local_id": 10,
                    "sender": "requester",
                    "sender_display": "Requester",
                    "kind": "text",
                    "local_type": 1,
                    "content": "The video shows robotic arms built by the creator.",
                },
                {
                    "local_id": 14,
                    "sender": "requester",
                    "kind": "video",
                    "local_type": 43,
                    "content": '<?xml version="1.0"?><msg><videomsg md5="abc123abc123abc1" /></msg>',
                },
                {
                    "local_id": 13,
                    "sender": "requester",
                    "kind": "image",
                    "local_type": 3,
                    "content": '<?xml version="1.0"?><msg><img md5="ffffeeeeffffeeee" /></msg>',
                },
                {
                    "local_id": 15,
                    "sender": "labcanvas-bot",
                    "kind": "text",
                    "local_type": 1,
                    "content": "Routine supervisor contract: do not expose this.",
                },
                {
                    "local_id": 16,
                    "sender": "requester",
                    "sender_display": "Requester",
                    "kind": "text",
                    "local_type": 1,
                    "content": "Publish with English, Japanese, Chinese, and French subtitles.",
                },
            ],
            "interruptions": [
                {
                    "request": (
                        "Treat this as a message forwarded from WeChat into the backend Codex session "
                        "for this chat.\n\nCurrent coalesced request:\n"
                        "Use the robotic-arm context to correct subtitles and metadata."
                    )
                }
            ],
        }

        correction = worker.build_lazyedit_correction_context(task)
        metadata = worker.build_lazyedit_metadata_brief(task)

        self.assertIn("robotic arms built by the creator", correction)
        self.assertIn("robotic-arm context", correction)
        self.assertIn("robotic-arm context", metadata)
        self.assertNotIn("Treat this as a message forwarded", correction)
        self.assertNotIn("Treat this as a message forwarded", metadata)
        self.assertNotIn("Routine supervisor contract", correction)
        self.assertNotIn("<?xml", correction)
        self.assertNotIn("<?xml", metadata)
        self.assertIn("abc123abc123abc1", correction)
        self.assertNotIn("ffffeeeeffffeeee", correction)
        self.assertNotIn("Request summary:", metadata)

    def test_video_message_ref_uses_newest_matching_shard_when_local_id_restarts(self) -> None:
        worker = load_worker()
        task = {
            "source": {"local_id": 8, "message_db": "message_1.db", "local_type": 1},
            "request": "Current coalesced request:\npublish the latest video",
            "context": [
                {
                    "local_id": 7,
                    "message_db": "message_0.db",
                    "local_type": 43,
                    "create_time": 100,
                    "content": '<msg><videomsg md5="' + ("a" * 32) + '" /></msg>',
                },
                {
                    "local_id": 7,
                    "message_db": "message_1.db",
                    "local_type": 43,
                    "create_time": 200,
                    "content": '<msg><videomsg md5="' + ("b" * 32) + '" /></msg>',
                },
                {
                    "local_id": 8,
                    "message_db": "message_1.db",
                    "local_type": 1,
                    "create_time": 201,
                    "content": "publish the latest video",
                },
            ],
        }

        self.assertEqual(worker.extract_video_local_ids_from_task(task), [7])
        self.assertEqual(worker.extract_video_message_refs_from_task(task), ["message_1.db:7"])

    def test_video_source_ignores_transport_wrapper_reference_row_ids(self) -> None:
        worker = load_worker()
        task = {
            "source": {
                "local_id": 60,
                "message_db": "message_1.db",
                "local_type": 1,
            },
            "request": (
                "Treat this as a message forwarded from WeChat.\n\n"
                "Chat: My devices\n"
                "Source/reference rows: local_id=53, local_id=59, local_id=60\n\n"
                "Current coalesced request:\n"
                "Also publish this video about a 3D print that went wrong.\n\n"
                "Recent history:\nold context"
            ),
            "context": [
                {
                    "local_id": 53,
                    "message_db": "message_1.db",
                    "local_type": 43,
                    "create_time": 100,
                    "content": '<msg><videomsg md5="' + ("a" * 32) + '" length="16693976" /></msg>',
                },
                {
                    "local_id": 54,
                    "message_db": "message_1.db",
                    "local_type": 1,
                    "create_time": 101,
                    "content": "The previous robot video should have Korean subtitles.",
                },
                {
                    "local_id": 59,
                    "message_db": "message_1.db",
                    "local_type": 43,
                    "create_time": 200,
                    "content": '<msg><videomsg md5="' + ("b" * 32) + '" length="4881427" /></msg>',
                },
                {
                    "local_id": 60,
                    "message_db": "message_1.db",
                    "local_type": 1,
                    "create_time": 201,
                    "content": "Also publish this video about a 3D print that went wrong.",
                },
            ],
        }

        self.assertEqual(worker.extract_video_local_ids_from_task(task), [59])
        self.assertEqual(worker.extract_video_message_refs_from_task(task), ["message_1.db:59"])
        correction = worker.build_lazyedit_correction_context(
            task,
            preflight={
                "audio_intake": {
                    "status": "transcribed",
                    "text": "这个怎么回事？怎么打印成这样了？",
                    "segments": [
                        {"start": 0.0, "end": 2.8, "text": "这个怎么回事？怎么打印成这样了？"}
                    ],
                }
            },
        )
        metadata = worker.build_lazyedit_metadata_brief(task)
        self.assertIn("3D print that went wrong", correction)
        self.assertIn("3D print that went wrong", metadata)
        self.assertNotIn("previous robot video", correction)
        self.assertIn('"local_id": 59', correction)
        self.assertNotIn('"local_id": 60', correction)
        self.assertIn("Verified Exact-Source Audio Transcript", correction)
        self.assertIn("怎么打印成这样", correction)

    def test_nonpublish_direct_video_preflight_saves_under_task_artifacts(self) -> None:
        worker = load_worker()
        task = {
            "id": "save-video-task",
            "chat": "🍓我的设备",
            "route_decision": {
                "route_kind": "process_existing_video",
                "needs_recent_media": True,
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nSave this WeChat video so I can ask follow-up questions.",
            "context": [
                {
                    "local_id": 57,
                    "sender_display": "陈苗",
                    "content": '<msg><videomsg md5="60699342dde76c611fdc48418a0648d0" length="841449" /></msg>',
                }
            ],
        }
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '{"ok": true, "status": "copied", "target": "/tmp/private/source.mp4"}', "")

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "artifact"
            with mock.patch.object(worker, "worker_artifact_dir", return_value=artifact_dir):
                with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                    payload = worker.run_autopublish_video_preflight(task)

        self.assertTrue(payload["ok"])
        self.assertIn("--dest", calls[0])
        self.assertIn(str(artifact_dir / "source_media"), calls[0])
        self.assertIn("--title", calls[0])
        self.assertIn("--replace", calls[0])
        self.assertEqual(payload["message_local_ids"], [57])
        self.assertEqual(payload["private_save_dest"], str(artifact_dir / "source_media"))

    def test_passive_video_preflight_stops_after_exact_source_save(self) -> None:
        worker = load_worker()
        task = {
            "id": "passive-video-task",
            "chat": "🍓My devices",
            "source": {
                "local_id": 64,
                "local_type": 43,
                "message_table": "Msg_exact",
            },
            "route_decision": {
                "route_kind": "file_download_or_save",
                "needs_recent_media": True,
                "passive_video_intake": True,
                "public_publish_allowed": False,
            },
            "request": "New WeChat video item received with no text instruction.",
            "context": [
                {
                    "local_id": 64,
                    "local_type": 43,
                    "content": '<msg><videomsg md5="' + ("a" * 32) + '" length="3230161" /></msg>',
                }
            ],
        }
        saved = {
            "ok": True,
            "status": "copied",
            "target": "/tmp/passive/source_video.mp4",
            "message_local_ids": [64],
        }

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "artifact"
            with mock.patch.object(worker, "should_resolve_recent_video_artifact", return_value=False):
                with mock.patch.object(worker, "should_prepare_media_resolution", return_value=False):
                    with mock.patch.object(worker, "task_requests_local_download_save", return_value=False):
                        with mock.patch.object(worker, "should_preflight_autopublish", return_value=True):
                            with mock.patch.object(worker, "run_autopublish_video_preflight", return_value=saved) as save:
                                with mock.patch.object(worker, "should_prepare_audio_intake", return_value=True):
                                    with mock.patch.object(worker, "prepare_audio_intake_preflight") as audio:
                                        payload = worker.prepare_worker_preflight(task, artifact_dir)

        save.assert_called_once_with(task)
        audio.assert_not_called()
        self.assertEqual(payload["autopublish_video"], saved)
        self.assertNotIn("audio_intake", payload)
        self.assertNotIn("lazyedit_context", payload)
        self.assertNotIn("lazyedit_options", payload)
        self.assertNotIn("publish_platforms", payload)

    def test_daily_runtime_contract_isolates_legacy_lane_and_drops_outbound_context(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:default:group:labagent",
            "request": (
                "Prepare the daily report.\n\n"
                "Recent same-group discussion:\n"
                "- outbound: old scheduled report\n\n"
                "Model-budgeted lifetime memory:\n"
                "old bot-authored history\n\n"
                "Requirements:\n"
                "- Use primary sources.\n"
                "- Return the verified PDF."
            ),
            "context": [
                {"direction": "inbound", "content": "current human question"},
                {"direction": "outbound", "content": "old scheduled report"},
            ],
            "daily_research": {
                "job_key": "member-job",
                "member_key": "member",
                "topics": ["organoid imaging"],
            },
            "execution_contract": {
                "session": {
                    "chat": "wecom:default:group:labagent",
                    "role": "worker",
                    "reuse": True,
                }
            },
        }

        changed = worker.ensure_daily_research_runtime_contract(task)

        expected_scope = "wecom:default:group:labagent::daily:member-job"
        self.assertTrue(changed)
        self.assertEqual(task["session_scope"], expected_scope)
        self.assertEqual(
            task["execution_contract"]["session"]["chat"],
            expected_scope,
        )
        self.assertEqual(
            [item["content"] for item in task["context"]],
            ["current human question"],
        )
        self.assertEqual(
            task["daily_research"]["active_context_policy"],
            "recent_inbound_human_messages_only",
        )
        self.assertNotIn("old scheduled report", task["request"])
        self.assertNotIn("old bot-authored history", task["request"])
        self.assertIn("current human question", task["request"])
        self.assertIn("- Use primary sources.", task["request"])
        self.assertTrue(task["daily_research"]["legacy_request_compacted"])

    def test_reprocess_task_clears_stale_result_and_preserves_source_context(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-1",
                        "chat": "🍓我的设备",
                        "request": "Current coalesced request:\nPlease publish this source video.",
                        "source": {"local_id": 58},
                        "context": [{"local_id": 58, "content": "[quoted video]"}],
                        "status": "send_retrying",
                        "superseded_at": "2026-01-01T00:00:00",
                        "superseded_by": "wrong-task",
                        "superseded_reason": "stale merge",
                        "result": {"message": "stale wrong result", "files": []},
                        "preflight": {"autopublish_video": {"status": "artifact-ledger-match"}},
                        "routine": {"id": "video_publish_existing", "rules": ["old rule"]},
                        "routine_contract": {"json": "/tmp/old.json"},
                        "orchestrator": {"stage": "old"},
                        "worker_policy": {"reasoning_effort": "ultra"},
                        "worker_policy_selected_attempt": 1,
                        "worker_policy_attempts": [{"attempt": 1}],
                        "worker_result_exhausted": True,
                        "worker_result_ready_at": "2026-06-25T10:39:56",
                        "worker_retry_context": {"kind": "old"},
                        "agent_session": {"thread_id_short": "deadbeef"},
                        "codex_session": {"thread_id_short": "deadbeef"},
                        "artifact_dir": "/tmp/old-artifacts",
                        "execution_contract": {"old": True},
                        "send_errors": ["timeout"],
                        "wecom_delivery": {"status": "sent"},
                        "existing_video_publish_poststage": {"video_id": 395},
                        "publish_agent_bypassed": {"video_id": 395, "stage": "published_verified"},
                        "publish_agent_supervision": {"status": "completed"},
                        "publish_agent_evidence": {"video_id": 395},
                        "publish_poststage_history": [{"video_id": 395}],
                        "completion_audit": {"status": "checked"},
                        "message_coverage": {"status": "covered"},
                        "sent_message_part_hashes": ["old-result"],
                        "coverage_status": "covered",
                        "coverage_checked_at": "2026-06-25T10:39:57",
                        "coverage_parent_task_id": "task-1",
                        "completed_at": "2026-06-25T10:39:57",
                    }
                ],
            )

            updated = worker.reprocess_task(queue, "task-1", reason="source resolver fixed")
            stored = worker.find_task(queue, "task-1")

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["source"], {"local_id": 58})
        self.assertEqual(stored["context"], [{"local_id": 58, "content": "[quoted video]"}])
        self.assertNotIn("result", stored)
        self.assertNotIn("superseded_at", stored)
        self.assertNotIn("superseded_by", stored)
        self.assertNotIn("superseded_reason", stored)
        self.assertNotIn("preflight", stored)
        self.assertNotIn("routine", stored)
        self.assertNotIn("routine_contract", stored)
        self.assertNotIn("orchestrator", stored)
        self.assertNotIn("worker_policy", stored)
        self.assertNotIn("worker_policy_selected_attempt", stored)
        self.assertNotIn("worker_policy_attempts", stored)
        self.assertNotIn("worker_result_exhausted", stored)
        self.assertNotIn("worker_result_ready_at", stored)
        self.assertNotIn("worker_retry_context", stored)
        self.assertNotIn("agent_session", stored)
        self.assertNotIn("codex_session", stored)
        self.assertNotIn("artifact_dir", stored)
        self.assertEqual(stored["execution_contract"], {"old": True})
        self.assertNotIn("send_errors", stored)
        self.assertNotIn("wecom_delivery", stored)
        self.assertNotIn("existing_video_publish_poststage", stored)
        self.assertNotIn("publish_agent_bypassed", stored)
        self.assertNotIn("publish_agent_supervision", stored)
        self.assertNotIn("publish_agent_evidence", stored)
        self.assertNotIn("publish_poststage_history", stored)
        self.assertNotIn("completion_audit", stored)
        self.assertNotIn("message_coverage", stored)
        self.assertNotIn("sent_message_part_hashes", stored)
        self.assertNotIn("coverage_status", stored)
        self.assertNotIn("coverage_checked_at", stored)
        self.assertNotIn("coverage_parent_task_id", stored)
        self.assertIn("expires_at", stored)
        self.assertEqual(stored["reprocess_reason"], "source resolver fixed")
        self.assertEqual(stored["reprocess_history"][0]["previous_status"], "send_retrying")
        self.assertIn("stale wrong result", stored["reprocess_history"][0]["previous_result_message_excerpt"])

    def test_reprocess_task_can_request_deterministic_artifact_recovery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "daily-failed",
                        "chat": "wecom:group:labagent",
                        "status": "worker_failed",
                        "daily_research": {"report_date": "2026-07-19"},
                        "worker_error": {"type": "WorkerAttemptsExhausted"},
                        "result": {"message": "timeout", "files": []},
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "daily-failed",
                reason="recover completed report",
                artifact_recovery_only=True,
            )

        self.assertEqual(updated["status"], "pending")
        self.assertTrue(updated["artifact_recovery_only"])
        self.assertNotIn("worker_error", updated)
        self.assertNotIn("expires_at", updated)

    def test_reprocess_verified_publish_preserves_result_for_delivery_only(self) -> None:
        worker = load_worker()
        result = {
            "message": "published",
            "confirmation": "",
            "files": [],
            "data": {
                "publish_stage": {
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 496,
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "publish-failed-send",
                        "chat": "MEMO写作—外语—挣钱",
                        "status": "send_failed",
                        "result": result,
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "publish-failed-send",
                reason="recover verified publication result delivery",
                artifact_recovery_only=True,
            )

        self.assertEqual(updated["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertEqual(updated["result"], result)
        self.assertTrue(updated["delivery_recovery_only"])
        self.assertEqual(updated["send_deferred_reason"], "manual_delivery_recovery")

    def test_reprocess_research_missing_required_pdf_uses_artifact_recovery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            report = Path(tmp) / "daily_briefing.md"
            report.write_text("# Daily briefing\n\nEvidence.\n", encoding="utf-8")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "daily-missing-pdf",
                        "chat": "wecom:group:labagent",
                        "status": "send_failed",
                        "daily_research": {"report_date": "2026-08-21"},
                        "route_decision": {"route_kind": "research_or_summary"},
                        "execution_contract": {
                            "required_artifacts": ["markdown_report", "compiled_pdf"]
                        },
                        "result": {
                            "message": "Research completed.",
                            "confirmation": "Internal worker confirmation with a local path.",
                            "files": [str(report)],
                        },
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "daily-missing-pdf",
                reason="recover completed report",
                artifact_recovery_only=True,
            )

        self.assertEqual(updated["status"], "pending")
        self.assertTrue(updated["artifact_recovery_only"])
        self.assertNotIn("delivery_recovery_only", updated)
        self.assertNotIn("result", updated)

    def test_reprocess_research_existing_pdf_sends_only_pdf_without_stored_text(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            report = Path(tmp) / "daily_briefing.md"
            report.write_text("# Daily briefing\n\nEvidence.\n", encoding="utf-8")
            pdf = Path(tmp) / "daily_briefing.zh.pdf"
            pdf.write_bytes(b"%PDF-1.4\nreport")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "daily-with-pdf",
                        "chat": "wecom:group:labagent",
                        "status": "send_failed",
                        "daily_research": {"report_date": "2026-08-21"},
                        "route_decision": {"route_kind": "research_or_summary"},
                        "execution_contract": {
                            "required_artifacts": ["markdown_report", "compiled_pdf"]
                        },
                        "result": {
                            "message": "Long report text already delivered.",
                            "confirmation": "Internal worker confirmation with a local path.",
                            "files": [str(pdf), str(report)],
                        },
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "daily-with-pdf",
                reason="recover completed report",
                artifact_recovery_only=True,
            )

        self.assertEqual(updated["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertTrue(updated["delivery_recovery_only"])
        self.assertEqual(
            updated["result"]["message"],
            "今日研究简报已完成，PDF 已附上。",
        )
        self.assertEqual(updated["result"]["confirmation"], "")
        self.assertEqual(updated["result"]["files"], [str(pdf.resolve())])
        self.assertNotIn(str(report.resolve()), updated["result"]["files"])

    def test_reprocess_applies_explicit_pdf_recovery_reason_before_reuse_check(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            pdf = Path(tmp) / "ready.pdf"
            pdf.write_bytes(b"%PDF-1.4\nready")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "failed-with-ready-pdf",
                        "chat": "MEMO写作—外语—挣钱",
                        "status": "worker_failed",
                        "route_decision": {"route_kind": "research_or_summary"},
                        "result": {
                            "message": "PDF 已附上。",
                            "confirmation": "",
                            "files": [str(pdf)],
                        },
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "failed-with-ready-pdf",
                reason="deliver the exact stored PDF without rerunning the agent",
                artifact_recovery_only=True,
            )

        self.assertEqual(updated["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertTrue(updated["delivery_recovery_only"])
        self.assertEqual(updated["result"]["files"], [str(pdf.resolve())])

    def test_publish_artifact_recovery_rebuilds_result_from_lazyedit_queue(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-recovery",
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "publish_poststage_history": [{"video_id": 496}],
        }
        queue_payload = {
            "jobs": [
                {
                    "id": 331,
                    "video_id": 496,
                    "status": "done",
                    "remote_status": "done",
                    "remote_job_id": "job-4",
                    "platforms": ["shipinhao", "youtube", "instagram"],
                    "filename": "exact_COMPLETED.zip",
                    "file_path": "/tmp/exact_COMPLETED.mp4",
                    "updated_at": "2026-07-29T22:38:30+08:00",
                }
            ]
        }

        with mock.patch.object(worker, "lazyedit_api_get", return_value=queue_payload):
            recovered = worker.recover_verified_publish_delivery_result(task)

        self.assertIsNotNone(recovered)
        assert recovered is not None
        stage = recovered["data"]["publish_stage"]
        self.assertTrue(stage["verified"])
        self.assertEqual(stage["video_id"], 496)
        self.assertEqual(
            stage["verified_platforms"],
            ["shipinhao", "youtube", "instagram"],
        )
        self.assertIn("job_id=331", recovered["message"])

    def test_artifact_recovery_never_falls_through_to_preflight_or_agent(self) -> None:
        worker = load_worker()
        task = {
            "id": "no-recovery",
            "chat": "LazyResearch",
            "status": worker.CLAIMED_STATUS,
            "artifact_recovery_only": True,
            "route_decision": {"route_kind": "other_worker"},
            "request": "recover only",
        }
        policy = {
            "model": "gpt-5.5",
            "reasoning_effort": "low",
            "timeout_seconds": 30,
            "reuse_session": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            with mock.patch.object(worker, "worker_artifact_dir", return_value=artifact_dir):
                with mock.patch.object(
                    worker,
                    "recover_completed_research_artifacts",
                    return_value=None,
                ):
                    with mock.patch.object(
                        worker,
                        "recover_verified_publish_delivery_result",
                        return_value=None,
                    ):
                        with mock.patch.object(worker, "prepare_worker_preflight") as preflight:
                            with mock.patch.object(worker, "run_worker_agent_session") as agent:
                                raw = worker.run_task_orchestrator(task, policy)

        payload = json.loads(raw)
        self.assertTrue(payload["no_reply"])
        self.assertEqual(
            payload["data"]["status"],
            "no_verified_stored_or_deterministic_result",
        )
        preflight.assert_not_called()
        agent.assert_not_called()

    def test_artifact_recovery_skips_model_completion_audit(self) -> None:
        worker = load_worker()
        task = {
            "id": "delivery-recovery",
            "artifact_recovery_only": True,
            "request": "recover stored result",
        }
        result = {
            "message": "published",
            "confirmation": "",
            "files": [],
        }

        with mock.patch.object(worker, "run_completion_audit") as audit:
            recovered = worker.audit_and_repair_worker_completion(task, result)

        self.assertEqual(recovered, result)
        self.assertEqual(
            task["completion_audit"]["status"],
            "skipped_delivery_recovery",
        )
        self.assertEqual(
            task["message_coverage"]["status"],
            "recovered_without_model_rerun",
        )
        audit.assert_not_called()

    def test_reprocess_pdf_research_reason_upgrades_route_and_delivery_contract(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-followup",
                        "chat": "wecom:group:labagent",
                        "request": "What is the clinical value?",
                        "status": "done",
                        "route_decision": {
                            "route_kind": "other_worker",
                            "require_file_delivery": False,
                        },
                        "execution_contract": {"required_artifacts": []},
                        "result": {"message": "Short answer only", "files": []},
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "research-followup",
                reason=(
                    "Create an evidence-grounded research report, compile a validated PDF, "
                    "and deliver it to the source chat."
                ),
            )

        self.assertEqual(updated["route_decision"]["route_kind"], "research_or_summary")
        self.assertTrue(updated["route_decision"]["require_file_delivery"])
        self.assertEqual(updated["execution_contract"]["required_artifacts"], ["pdf"])
        self.assertTrue(updated["execution_contract"]["research_evidence"]["required"])
        self.assertTrue(worker.task_contract_requires_file_delivery(updated))

    def test_reprocess_repairs_stale_generic_route_for_explicit_research(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "stale-research",
                        "chat": "wecom:group:labagent",
                        "request": "帮我调研下这段话是否有依据",
                        "status": "done",
                        "routine": {
                            "id": "general_worker",
                            "route_kind": "other_worker",
                        },
                        "execution_contract": {"required_artifacts": []},
                        "result": {"message": "unrelated fallback output", "files": []},
                    }
                ],
            )

            updated = worker.reprocess_task(
                queue,
                "stale-research",
                reason="rerun with repaired research routing",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["route_decision"]["route_kind"], "research_or_summary")
        self.assertEqual(updated["instruction_contract"]["route_kind"], "research_or_summary")
        self.assertTrue(updated["execution_contract"]["research_evidence"]["required"])
        self.assertEqual(
            updated["execution_contract"]["research_evidence"]["minimum_traceable_sources"],
            2,
        )
        self.assertEqual(updated["route_repair_reason"], "explicit_research_intent")

    def test_daily_research_keeps_pdf_delivery_required_after_reprocess(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            report = Path(tmp) / "daily.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "daily-report",
                        "chat": "wecom:group:labagent",
                        "status": "done",
                        "daily_research": {"report_date": "2026-07-22"},
                        "execution_contract": {"required_artifacts": ["compiled_pdf"]},
                        "result": {"message": "done", "files": [str(report)]},
                    }
                ],
            )

            updated = worker.reprocess_task(queue, "daily-report", reason="retry transport")

        self.assertEqual(updated["execution_contract"]["required_artifacts"], ["compiled_pdf"])
        self.assertTrue(worker.task_contract_requires_file_delivery(updated))

    def test_video_publish_preflight_uses_same_chat_artifact_ledger_when_wechat_cache_misses(self) -> None:
        worker = load_worker()
        video_bytes = b"generated-video-bytes"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_video = tmp_path / "legacy_generated_video.mp4"
            source_video.write_bytes(video_bytes)
            source_prompt = tmp_path / "legacy_generated_video_prompt.md"
            source_prompt.write_text(
                "Original generation prompt: a previous generated story-video scene.",
                encoding="utf-8",
            )
            md5 = worker.file_md5(source_video)
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "source-task",
                        "chat": "🍓我的设备",
                        "request": "Generate the older source video from the original prompt and script.",
                        "status": "done",
                        "result": {"message": "Generated and sent the compressed MP4.", "files": [str(source_video)]},
                        "sent_file_paths": [str(source_video)],
                        "artifact_dir": str(tmp_path),
                    }
                ],
            )
            task = {
                "id": "publish-task",
                "queue_path": str(queue),
                "chat": "🍓我的设备",
                "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                "request": "Current coalesced request:\n发布这个视频，用它的生成脚本 prompt 和视频本身发布",
                "source": {"local_id": 50, "sender_display": "陈苗"},
                "context": [
                    {
                        "local_id": 47,
                        "sender_display": "陈喵瞄秒妙",
                        "content": f'<msg><videomsg md5="{md5}" length="{len(video_bytes)}" /></msg>',
                    },
                    {
                        "local_id": 49,
                        "sender_display": "陈喵瞄秒妙",
                        "content": "我没有发布这个视频。官方客户端还没有把这一条完整 MP4 缓存到本地。",
                    },
                    {"local_id": 50, "sender_display": "陈苗", "content": "发布这个视频"},
                ],
            }

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                payload = {
                    "ok": False,
                    "error": "no matching mirrored video found",
                    "recent_video_messages": [{"chat": "🍓我的设备", "recent_video_rows": 1}],
                }
                return subprocess.CompletedProcess(command, 1, json.dumps(payload), "")

            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                with mock.patch.dict(worker.os.environ, {"LABCANVAS_AUTOPUBLISH_DIR": str(tmp_path / "AutoPublish")}):
                    preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")

            autopub = preflight["autopublish_video"]
            target = Path(autopub["target"])
            context_text = Path(preflight["lazyedit_context"]["correction_prompt_file"]).read_text(encoding="utf-8")
            target_name = target.name
            target_exists = target.is_file()
            target_bytes = target.read_bytes() if target_exists else b""

        self.assertTrue(autopub["ok"])
        self.assertEqual(autopub["status"], "artifact-ledger-match")
        self.assertEqual(autopub["md5"], md5)
        self.assertEqual(autopub["bytes"], len(video_bytes))
        self.assertEqual(autopub["source_task"]["id"], "source-task")
        self.assertTrue(autopub["source_task"]["supporting_materials"])
        self.assertIn("same-chat-task-ledger", autopub["matched_by"])
        self.assertTrue(target_name.endswith("_COMPLETED.mp4"))
        self.assertTrue(target_exists)
        self.assertEqual(target_bytes, video_bytes)
        self.assertIn("artifact-ledger-match", context_text)
        self.assertIn("original prompt and script", context_text)
        self.assertIn("Original generation prompt", context_text)
        self.assertIn("OBSOLETE-CACHE-MISS", context_text)

    def test_video_publish_preflight_uses_current_quoted_video_not_old_history(self) -> None:
        worker = load_worker()
        old_video_bytes = b"old-generated-video"
        current_video_bytes = b"current-quoted-video" * 600
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_video = tmp_path / "older_same_chat_video.mp4"
            old_video.write_bytes(old_video_bytes)
            old_md5 = worker.file_md5(old_video)
            current_md5 = hashlib.md5(current_video_bytes).hexdigest()
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-source-task",
                        "chat": "🍓我的设备",
                        "request": "Generate and publish an older same-chat video.",
                        "status": "done",
                        "result": {"message": "Generated old video.", "files": [str(old_video)]},
                        "sent_file_paths": [str(old_video)],
                    }
                ],
            )
            task = {
                "id": "publish-current-task",
                "queue_path": str(queue),
                "chat": "🍓我的设备",
                "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                "request": (
                    "Current coalesced request:\n"
                    "Please publish this newly quoted source video.\n[quoted 陈苗: [video]]\n\n"
                    "Same-chat reference media/context rows:\n"
                    "- local_id=47 old video context\n"
                    "- local_id=57 server_id=3774698196281921919 current video\n"
                    "- local_id=58 server_id=7695504197176236957 current quote"
                ),
                "source": {"local_id": 58, "sender_display": "陈苗"},
                "context": [
                    {
                        "local_id": 47,
                        "sender_display": "陈喵瞄秒妙",
                        "content": f'<msg><videomsg md5="{old_md5}" length="{len(old_video_bytes)}" /></msg>',
                    },
                    {
                        "local_id": 57,
                        "sender_display": "陈苗",
                        "content": f'<msg><videomsg md5="{current_md5}" length="{len(current_video_bytes)}" /></msg>',
                    },
                    {
                        "local_id": 58,
                        "sender_display": "陈苗",
                        "content": (
                            "Please publish this newly quoted source video.\n"
                            '<refermsg><svrid>3774698196281921919</svrid>'
                            f'<content><msg><videomsg md5="{current_md5}" '
                            f'length="{len(current_video_bytes)}" /></msg></content></refermsg>'
                        ),
                    },
                ],
            }

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                payload = {"ok": False, "error": "no matching mirrored video found"}
                return subprocess.CompletedProcess(command, 1, json.dumps(payload), "")

            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")

            autopub = preflight["autopublish_video"]
            artifact_resolution = autopub["artifact_resolution"]

        self.assertFalse(autopub["ok"])
        self.assertEqual(artifact_resolution["status"], "artifact-ledger-miss")
        self.assertEqual(artifact_resolution["refs"]["md5s"], [current_md5])
        self.assertEqual(artifact_resolution["refs"]["sizes"], [len(current_video_bytes)])
        self.assertEqual(artifact_resolution["refs"]["local_ids"], [57])
        self.assertEqual(artifact_resolution["refs"]["scope"], "source_video_local_ids")
        self.assertNotIn(old_md5, artifact_resolution["refs"]["md5s"])

    def test_file_download_preflight_resolves_recent_same_chat_generated_video(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            source_dir.mkdir()
            source_video = source_dir / "anniversary_monorail_dinner_xyq.mp4"
            source_video.write_bytes(b"generated-video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "source-task",
                        "chat": "懒人科研",
                        "created_at": "2026-06-23T09:07:09",
                        "status": "in_progress",
                        "artifact_dir": str(source_dir),
                    }
                ],
            )
            task = {
                "id": "send-task",
                "queue_path": str(queue),
                "chat": "懒人科研",
                "created_at": "2026-06-23T09:17:23",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "needs_recent_media": True,
                    "public_publish_allowed": False,
                },
                "request": "Current coalesced request:\nAnd send the video to this group",
            }

            preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")
            task["preflight"] = preflight
            raw = worker.deterministic_preflight_result(task)

        self.assertIn("resolved_video_artifact", preflight)
        self.assertNotIn("autopublish_video", preflight)
        payload = json.loads(raw or "{}")
        self.assertEqual(payload["files"], [str(source_video.resolve())])
        self.assertTrue(payload["data"]["require_file_delivery"])
        self.assertEqual(payload["data"]["resolved_video_artifact"]["status"], "recent-artifact-match")

    def test_explicit_downloads_save_copies_once_and_returns_concise_receipt(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source" / "book.pdf"
            source.parent.mkdir()
            source.write_bytes(b"%PDF-1.4\nbook")
            downloads = tmp_path / "Downloads"
            task = {
                "id": "save-book",
                "chat": "🍓My devices",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "delivery_mode": "local_save",
                    "needs_recent_media": True,
                },
                "request": "Current coalesced request:\n帮我把这本 PDF 保存到 Downloads",
                "preflight": {
                    "media_resolution": {
                        "copied": [
                            {
                                "task_copy_path": str(source),
                                "filename": source.name,
                                "size_bytes": source.stat().st_size,
                            }
                        ]
                    }
                },
            }

            with mock.patch.dict(
                worker.os.environ,
                {"WECHAT_LOCAL_DOWNLOADS_DIR": str(downloads)},
            ):
                saved = worker.prepare_local_download_save_preflight(task, task["preflight"])
                task["preflight"]["local_file_save"] = saved
                payload = json.loads(worker.deterministic_local_download_save_result(task) or "{}")

            target = downloads / "book.pdf"
            target_bytes = target.read_bytes()

        self.assertTrue(saved["verified"])
        self.assertEqual(target_bytes, b"%PDF-1.4\nbook")
        self.assertEqual(payload["message"], "已保存到 Downloads：book.pdf。")
        self.assertEqual(payload["files"], [])
        self.assertFalse(payload["data"]["require_file_delivery"])

    def test_local_save_result_path_is_not_echoed_as_chat_attachment(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            downloads = tmp_path / "Downloads"
            downloads.mkdir()
            target = downloads / "book.pdf"
            target.write_bytes(b"%PDF-1.4\nbook")
            task = {
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "delivery_mode": "local_save",
                },
                "request": "Current coalesced request:\nSave this PDF to Downloads",
            }
            result = {
                "message": "",
                "confirmation": "",
                "files": [str(target)],
                "no_reply": True,
            }
            with mock.patch.dict(
                worker.os.environ,
                {"WECHAT_LOCAL_DOWNLOADS_DIR": str(downloads)},
            ):
                prepared = worker.prepare_result_files(result, json.dumps(result), task=task)

        self.assertEqual(prepared["files"], [])
        self.assertEqual(prepared["message"], "已保存到 Downloads：book.pdf。")
        self.assertFalse(prepared["no_reply"])
        self.assertEqual(prepared["skipped_files"][0]["reason"], "local-save-no-chat-echo")

    def test_exact_file_identity_uses_attachment_context_in_rotated_message_db(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / ".private"
            db_dir = private / "wechat_decrypt" / "decrypted" / "message"
            db_dir.mkdir(parents=True)
            config_name = "my-devices.local.json"
            (private / config_name).write_text(
                json.dumps({"message_table": "Msg_test"}),
                encoding="utf-8",
            )
            xml = (
                "<msg><appmsg><title>全彩_示例文献.pdf</title><appattach>"
                "<fileext>pdf</fileext><totallen>169024640</totallen>"
                "<md5>5aea5aea5aea5aea5aea5aea5aea5aea</md5>"
                "</appattach></appmsg></msg>"
            )
            with sqlite3.connect(db_dir / "message_1.db") as conn:
                conn.execute(
                    "CREATE TABLE Msg_test ("
                    "local_id INTEGER, server_id TEXT, message_content BLOB, "
                    "compress_content BLOB, WCDB_CT_message_content INTEGER)"
                )
                conn.execute(
                    "INSERT INTO Msg_test VALUES (?, ?, ?, ?, ?)",
                    (3, "3001", xml, None, 0),
                )
            task = {
                "source": {
                    "config_id": config_name,
                    "local_id": 4,
                    "server_id": "4001",
                    "message_db": "message_1.db",
                },
                "context": [
                    {
                        "local_id": 3,
                        "server_id": "3001",
                        "message_db": "message_1.db",
                        "local_type": 49,
                    }
                ],
                "request": "Current coalesced request:\n帮我下载到 Downloads",
            }
            with mock.patch.object(worker, "PRIVATE", private):
                identity = worker.exact_source_file_identity(task)

        self.assertTrue(identity["source_verified"])
        self.assertEqual(identity["title"], "全彩_示例文献.pdf")
        self.assertEqual(identity["size_bytes"], 169024640)
        self.assertEqual(identity["source_message_db"], "message_1.db")

    def test_exact_file_identity_never_falls_through_to_duplicate_id_in_older_shard(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / ".private"
            db_dir = private / "wechat_decrypt" / "decrypted" / "message"
            db_dir.mkdir(parents=True)
            config_name = "my-devices.local.json"
            (private / config_name).write_text(
                json.dumps({"message_table": "Msg_test"}),
                encoding="utf-8",
            )
            older_xml = (
                "<msg><appmsg><title>wrong-older-book.pdf</title><appattach>"
                "<fileext>pdf</fileext><totallen>4096</totallen>"
                "</appattach></appmsg></msg>"
            )
            with sqlite3.connect(db_dir / "message_0.db") as conn:
                conn.execute(
                    "CREATE TABLE Msg_test ("
                    "local_id INTEGER, server_id TEXT, message_content BLOB, "
                    "compress_content BLOB, WCDB_CT_message_content INTEGER)"
                )
                conn.execute(
                    "INSERT INTO Msg_test VALUES (?, ?, ?, ?, ?)",
                    (3, "0", older_xml, None, 0),
                )
            with sqlite3.connect(db_dir / "message_1.db") as conn:
                conn.execute(
                    "CREATE TABLE Msg_test ("
                    "local_id INTEGER, server_id TEXT, message_content BLOB, "
                    "compress_content BLOB, WCDB_CT_message_content INTEGER)"
                )
            task = {
                "source": {
                    "config_id": config_name,
                    "local_id": 4,
                    "message_db": "message_1.db",
                },
                "context": [
                    {
                        "local_id": 3,
                        "message_db": "message_1.db",
                        "local_type": 49,
                    }
                ],
                "request": "Current coalesced request:\n保存这本书到 Downloads",
            }
            with mock.patch.object(worker, "PRIVATE", private):
                identity = worker.exact_source_file_identity(task)

        self.assertFalse(identity["source_verified"])
        self.assertNotEqual(identity.get("title"), "wrong-older-book.pdf")
        self.assertNotIn("source_message_db", identity)

    def test_file_download_lazyedit_request_copies_recent_video_to_intake_without_publish(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source"
            source_dir.mkdir()
            source_video = source_dir / "anniversary_monorail_dinner_xyq.mp4"
            source_video.write_bytes(b"generated-video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "source-task",
                        "chat": "懒人科研",
                        "created_at": "2026-06-23T09:07:09",
                        "status": "done",
                        "artifact_dir": str(source_dir),
                    }
                ],
            )
            task = {
                "id": "send-lazyedit-task",
                "queue_path": str(queue),
                "chat": "懒人科研",
                "created_at": "2026-06-23T09:17:23",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "needs_recent_media": True,
                    "public_publish_allowed": False,
                },
                "request": "Current coalesced request:\nThe video already generated. Send it here and submit to LazyEdit only.",
            }

            with mock.patch.dict(worker.os.environ, {"LABCANVAS_AUTOPUBLISH_DIR": str(tmp_path / "AutoPublish")}):
                preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")
                task["preflight"] = preflight
                raw = worker.deterministic_preflight_result(task)

            payload = json.loads(raw or "{}")
            lazyedit = payload["data"]["lazyedit_import"]
            lazyedit_target = Path(lazyedit["target"])
            lazyedit_target_exists = lazyedit_target.is_file()
            lazyedit_target_bytes = lazyedit_target.read_bytes() if lazyedit_target_exists else b""
            expected_source = str(source_video.resolve())

        self.assertFalse(lazyedit["public_publish"])
        self.assertTrue(lazyedit_target_exists)
        self.assertEqual(lazyedit_target_bytes, b"generated-video")
        self.assertEqual(payload["files"], [expected_source])

    def test_file_intake_preflight_copies_upload_and_returns_receipt(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "downloads" / "Game_Theory_101_Complete_Textbook_2011.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"%PDF-1.4\nminimal")
            artifact_dir = tmp_path / "artifact"
            task = {
                "id": "20260625123512-60",
                "chat": "🍓我的设备",
                "source": {"local_id": 60},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\n"
                    "New WeChat file upload received with no explicit instruction; run lightweight file intake first.\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {source} ({source.stat().st_size} bytes)"
                ),
            }

            preflight = worker.prepare_worker_preflight(task, artifact_dir)
            task["preflight"] = preflight
            raw = worker.deterministic_preflight_result(task)

            copied = preflight["file_intake"]["copied"][0]
            saved = Path(copied["saved_path"])
            saved_exists = saved.is_file()
            saved_bytes = saved.read_bytes() if saved_exists else b""
            payload = json.loads(raw or "{}")

        self.assertTrue(saved_exists)
        self.assertEqual(saved_bytes, b"%PDF-1.4\nminimal")
        self.assertEqual(copied["filename"], "Game_Theory_101_Complete_Textbook_2011.pdf")
        self.assertEqual(copied["size_bytes"], len(b"%PDF-1.4\nminimal"))
        self.assertIn("已做文件预检并保存", payload["message"])
        self.assertEqual(payload["files"], [])
        self.assertEqual(payload["data"]["status"], "saved")
        self.assertFalse(payload["data"]["require_file_delivery"])

    def test_file_intake_docx_falls_through_to_resumed_agent_with_readable_context(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "downloads" / "experiment_notes.docx"
            source.parent.mkdir(parents=True)
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr(
                    "word/document.xml",
                    """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                    <w:body><w:p><w:r><w:t>The lamp requires a regulated 5 V supply.</w:t></w:r></w:p></w:body>
                    </w:document>""",
                )
            task = {
                "id": "file-docx-read",
                "chat": "懒人科研",
                "source": {"local_id": 72, "kind": "file", "local_type": 49},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\n"
                    "New WeChat file upload received with no explicit instruction.\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {source} ({source.stat().st_size} bytes)"
                ),
            }

            preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")
            task["preflight"] = preflight
            document = preflight["file_intake"]["copied"][0]["document_read"]
            deterministic = worker.deterministic_preflight_result(task)
            content = Path(document["agent_context_path"]).read_text(encoding="utf-8")

        self.assertEqual(document["status"], "readable")
        self.assertIn("regulated 5 V supply", content)
        self.assertIsNone(deterministic)

    def test_file_intake_preflight_uses_current_file_not_old_recent_files(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            downloads = tmp_path / "downloads"
            downloads.mkdir(parents=True)
            current = downloads / "Chaos_Making_New_Science_2015.pdf"
            old = downloads / "Game_Theory_101_Complete_Textbook_2011.pdf"
            image = downloads / "old-thumb.jpg"
            current.write_bytes(b"%PDF-1.4\nchaos")
            old.write_bytes(b"%PDF-1.4\nold")
            image.write_bytes(b"jpg")
            artifact_dir = tmp_path / "artifact"
            task = {
                "id": "20260625130234-61",
                "chat": "🍓我的设备",
                "source": {"local_id": 61},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\n"
                    "陈苗: [WeChat file]\n"
                    "title: Chaos_Making_New_Science_2015.pdf\n"
                    "extension: pdf\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {old} ({old.stat().st_size} bytes)\n"
                    f"- {image} ({image.stat().st_size} bytes)\n"
                    f"- {current} ({current.stat().st_size} bytes)"
                ),
            }

            preflight = worker.prepare_worker_preflight(task, artifact_dir)
            copied = preflight["file_intake"]["copied"]

        self.assertEqual([item["filename"] for item in copied], ["Chaos_Making_New_Science_2015.pdf"])

    def test_file_intake_does_not_treat_missing_rar_as_recent_image(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_image = tmp_path / "downloads" / "619_old_thumb.jpg"
            old_image.parent.mkdir(parents=True)
            old_image.write_bytes(b"unrelated-jpeg")
            task = {
                "id": "20260718123216-624",
                "chat": "鏈接",
                "source": {"local_id": 624, "kind": "file/link", "local_type": 49},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\n"
                    "New WeChat file/link item received.\n"
                    "title: c12880光谱仪带数据存配套资料.rar\n"
                    "extension: rar\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {old_image} ({old_image.stat().st_size} bytes)\n"
                    "md5: 10bc7495e854bd2462741e045a45d708"
                ),
            }

            with mock.patch.dict(
                worker.os.environ,
                {
                    "WECHAT_MIRROR_DB": str(tmp_path / "missing-mirror.sqlite"),
                    "WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT": "1",
                },
            ):
                with mock.patch.object(
                    worker,
                    "codex_read_image_file",
                    side_effect=AssertionError("an unrelated thumbnail must not reach image analysis"),
                ):
                    preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")

        self.assertEqual(preflight["media_resolution"]["status"], "missing")
        self.assertEqual(preflight["media_resolution"]["expected_suffixes"], [".rar"])
        self.assertEqual(preflight["media_resolution"]["copied"], [])
        self.assertEqual(preflight["file_intake"]["status"], "missing")
        self.assertEqual(preflight["file_intake"]["copied"], [])
        self.assertEqual(worker.extract_request_synced_files_from_task(task), [])
        self.assertEqual(worker.current_request_file_md5(task["request"]), "")

    def test_file_intake_prefers_source_scoped_media_resolution_for_bare_image(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            exact = tmp_path / "source_media" / "current-image.jpg"
            old = tmp_path / "downloads" / "old-image.jpg"
            exact.parent.mkdir(parents=True)
            old.parent.mkdir(parents=True)
            exact.write_bytes(b"current-image-bytes")
            old.write_bytes(b"old-image-bytes")
            artifact_dir = tmp_path / "artifact"
            task = {
                "id": "20260703162934-69",
                "chat": "🍓我的设备",
                "source": {"local_id": 69, "kind": "image", "local_type": 3},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "preflight": {
                    "shipinhao_media_transcript": {
                        "status": "failed",
                        "failure_stage": "media_resolution",
                        "error": "expired card URL",
                    },
                    "media_resolution": {
                        "copied": [
                            {
                                "task_copy_path": str(exact),
                                "filename": exact.name,
                                "suffix": ".jpg",
                                "size_bytes": exact.stat().st_size,
                                "score": 245,
                                "match_reasons": ["token:current", "source_mtime_window"],
                                "image_metadata": {"status": "ok", "width": 500, "height": 281, "format": "JPEG", "mode": "RGB"},
                                "vision": {
                                    "status": "ok",
                                    "text_preview": "Visible text: large text\\nImage caption: a screenshot with a white text panel\\nNotes: none",
                                    "model": "gpt-5.5",
                                    "reasoning_effort": "low",
                                },
                                "ocr": {"status": "ok", "text_preview": "large text"},
                            }
                        ]
                    }
                },
                "request": (
                    "Current coalesced request:\n"
                    "New WeChat image upload received with no explicit instruction.\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {old} ({old.stat().st_size} bytes)"
                ),
            }

            with mock.patch.object(worker, "codex_read_image_file", side_effect=AssertionError("vision should be reused")):
                preflight = worker.prepare_file_intake_preflight(task, artifact_dir)

            copied = preflight["copied"]

        self.assertEqual([item["filename"] for item in copied], ["current-image.jpg"])
        self.assertIn("Visible text", copied[0]["vision"]["text_preview"])
        self.assertEqual(copied[0]["ocr"]["text_preview"], "large text")

    def test_file_intake_result_describes_bare_image(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "file_intake"},
            "preflight": {
                "file_intake": {
                    "copied": [
                        {
                            "filename": "current-image.jpg",
                            "saved_path": "/tmp/current-image.jpg",
                            "suffix": ".jpg",
                            "size_bytes": 94006,
                            "sha256": "2a3b0108c35f6d13172e3e04ece6e7a9",
                            "image_metadata": {"status": "ok", "width": 500, "height": 281, "format": "JPEG"},
                            "vision": {
                                "status": "ok",
                                "model": "gpt-5.5",
                                "reasoning_effort": "low",
                                "response_style": "natural_semantic",
                                "text_preview": "这是一张中文文章截图，核心在讨论如何把零散记录整理成可以持续复用的知识。标题强调先理解内容，再决定保存形式。",
                            },
                            "ocr": {"status": "ok", "text_preview": "BIG TITLE"},
                        }
                    ]
                }
            },
        }

        payload = json.loads(worker.deterministic_file_intake_result(task) or "{}")

        self.assertIn("这是一张中文文章截图", payload["message"])
        self.assertIn("先理解内容", payload["message"])
        self.assertNotIn("gpt-5.5", payload["message"])
        self.assertNotIn("OCR", payload["message"])
        self.assertNotIn("BIG TITLE", payload["message"])
        self.assertNotIn("Image caption", payload["message"])
        self.assertNotIn("sha256", payload["message"].lower())
        self.assertEqual(payload["data"]["status"], "image_read")

    def test_degraded_wecom_thumbnail_never_reaches_vision_or_ocr(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "wecom-preview.png"
            image.write_bytes(b"not-used-by-the-fidelity-gate")
            copied = [
                {
                    "task_copy_path": str(image),
                    "suffix": ".png",
                    "capture_kind": (
                        "wecom_android_exact_visible_image_preview_fallback"
                    ),
                    "fidelity": "degraded_visible_thumbnail",
                    "original_resolution_verified": False,
                    "image_metadata": {
                        "status": "ok",
                        "width": 388,
                        "height": 217,
                        "format": "PNG",
                    },
                }
            ]

            with mock.patch.object(
                worker,
                "codex_read_image_file",
                side_effect=AssertionError("thumbnail must not reach vision"),
            ), mock.patch.object(
                worker,
                "ocr_image_file",
                side_effect=AssertionError("thumbnail must not reach OCR"),
            ):
                worker.enrich_media_resolution_copies_with_image_read(
                    copied,
                    root / "artifact",
                )

        self.assertEqual(copied[0]["vision"]["status"], "deferred")
        self.assertEqual(
            copied[0]["vision"]["reason"],
            "native_resolution_source_required",
        )
        self.assertEqual(copied[0]["ocr"], copied[0]["vision"])

    def test_file_intake_naturalizes_legacy_labeled_image_read(self) -> None:
        worker = load_worker()
        message = worker.image_intake_description_message(
            {
                "vision": {
                    "status": "ok",
                    "text_preview": (
                        "Visible text: BIG TITLE\\n"
                        "Image caption: 这是一张带有大标题的文章截图。\\n"
                        "Notes: None"
                    ),
                },
                "ocr": {"status": "ok", "text_preview": "BIG TITLE"},
            }
        )

        self.assertIn("这是一张带有大标题的文章截图", message)
        self.assertIn("BIG TITLE", message)
        self.assertNotIn("Visible text", message)
        self.assertNotIn("Image caption", message)
        self.assertNotIn("Notes", message)
        self.assertNotIn("OCR", message)

    def test_image_read_prompt_context_uses_request_and_same_chat_text(self) -> None:
        worker = load_worker()
        task = {
            "request": "Current coalesced request:\n请告诉我这张图在讲什么。\n\nRecent history:\nignored",
            "source": {"local_id": 12},
            "context": [
                {"local_id": 10, "local_type": 1, "kind": "text", "content": "这是论文里的系统图。"},
                {"local_id": 12, "local_type": 3, "kind": "image", "content": "<img/>"},
            ],
        }

        context = worker.image_read_prompt_context(task)

        self.assertIn("请告诉我这张图在讲什么", context)
        self.assertIn("这是论文里的系统图", context)
        self.assertNotIn("<img", context)

    def test_media_resolution_preflight_prefers_decoded_image_and_exposes_task_copy(self) -> None:
        worker = load_worker()
        import wechat_mirror  # type: ignore

        token = "abc123abc123abc123abc123abc123ab"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mirror = tmp_path / "mirror"
            mirror.mkdir()
            raw_dat = mirror / f"{token}.dat"
            decoded_jpg = mirror / f"{token}.jpg"
            raw_dat.write_bytes(b"raw-wechat-image-container")
            decoded_jpg.write_bytes(b"\xff\xd8\xff\xe0decoded-jpeg")
            create_time = datetime.now().timestamp()
            db = tmp_path / "wechat_mirror.sqlite"
            event_id = wechat_mirror.record_event(
                chat_name="懒人科研",
                action="media-sync",
                status="copied",
                db_path=db,
                message="test image media sync",
            )
            wechat_mirror.record_media_files(
                chat_name="懒人科研",
                event_id=event_id,
                db_path=db,
                files=[
                    {
                        "source": str(tmp_path / "cache" / raw_dat.name),
                        "target": str(raw_dat),
                        "suffix": ".dat",
                        "bytes": raw_dat.stat().st_size,
                        "mtime": create_time,
                        "status": "copied",
                        "matched_by": f"token:{token}",
                    },
                    {
                        "source": str(tmp_path / "cache" / decoded_jpg.name),
                        "target": str(decoded_jpg),
                        "suffix": ".jpg",
                        "bytes": decoded_jpg.stat().st_size,
                        "mtime": create_time,
                        "status": "decoded",
                        "matched_by": f"token:{token}",
                        "decode_status": "decoded-xor",
                    },
                ],
            )
            task = {
                "id": "edit-image-task",
                "chat": "懒人科研",
                "source": {"local_id": 42, "server_id": "srv-42", "create_time": create_time},
                "route_decision": {"route_kind": "edit_existing_media", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\n"
                    f"Please edit this image. <msg><img md5=\"{token}\" /></msg>"
                ),
                "context": [
                    {
                        "local_id": 41,
                        "server_id": "img-41",
                        "local_type": 3,
                        "create_time": create_time,
                        "sender_display": "陈苗",
                        "content": f"<msg><img md5=\"{token}\" /></msg>",
                    },
                    {
                        "local_id": 42,
                        "server_id": "srv-42",
                        "local_type": 1,
                        "create_time": create_time,
                        "sender_display": "陈苗",
                        "content": "Please edit this image.",
                    },
                ],
            }

            with mock.patch.dict(
                worker.os.environ,
                {"WECHAT_MIRROR_DB": str(db), "WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT": "1"},
            ):
                candidates = worker.resolve_synced_media_from_mirror(task, limit=4)
                preflight = worker.prepare_worker_preflight(task, tmp_path / "artifact")
                task["preflight"] = preflight
                extracted = worker.extract_recent_synced_files_from_task(task)
                tool_context = worker.build_worker_tool_context(task)

            copied = preflight["media_resolution"]["copied"]
            first_copy = Path(copied[0]["task_copy_path"])
            first_copy_exists = first_copy.is_file()

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(Path(candidates[0]["mirror_path"]).suffix, ".jpg")
        self.assertIn("readable_image", candidates[0]["match_reasons"])
        self.assertEqual(Path(candidates[1]["mirror_path"]).suffix, ".dat")
        self.assertIn("raw_dat_penalty", candidates[1]["match_reasons"])
        self.assertEqual(first_copy.suffix, ".jpg")
        self.assertTrue(first_copy_exists)
        self.assertEqual(extracted[0], first_copy.resolve())
        self.assertIn("Media resolution preflight found source-scoped local files", tool_context)
        self.assertIn(str(first_copy), tool_context)
        self.assertIn("Do not say the image/file is missing", tool_context)

    def test_media_resolution_rejects_mtime_only_cross_chat_candidate(self) -> None:
        worker = load_worker()
        import wechat_mirror  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "outgoing-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            create_time = datetime.now().timestamp()
            db = tmp_path / "wechat_mirror.sqlite"
            event_id = wechat_mirror.record_event(
                chat_name="鏈接",
                action="media-sync",
                status="copied",
                db_path=db,
            )
            wechat_mirror.record_media_files(
                chat_name="鏈接",
                event_id=event_id,
                db_path=db,
                files=[
                    {
                        "source": str(report),
                        "target": str(report),
                        "suffix": ".pdf",
                        "bytes": report.stat().st_size,
                        "mtime": create_time,
                        "status": "copied",
                        "matched_by": "mtime",
                    }
                ],
            )
            task = {
                "chat": "鏈接",
                "source": {"create_time": create_time},
                "request": "Summarize the current message without an attachment.",
            }

            with mock.patch.dict(
                worker.os.environ,
                {"WECHAT_MIRROR_DB": str(db), "WECHAT_WORKER_ALLOW_MTIME_ONLY_MEDIA": "0"},
            ):
                candidates = worker.resolve_synced_media_from_mirror(task)

        self.assertEqual(candidates, [])

    def test_video_file_intake_does_not_borrow_appended_recent_files(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exact = root / "source_media" / "current-thumb.jpg"
            old_video = root / "downloads" / "old-video.mp4"
            exact.parent.mkdir(parents=True)
            old_video.parent.mkdir(parents=True)
            exact.write_bytes(b"current")
            old_video.write_bytes(b"old-video")
            task = {
                "source": {"local_id": 59, "kind": "video", "local_type": 43},
                "route_decision": {"route_kind": "file_intake", "needs_recent_media": True},
                "request": (
                    "Current coalesced request:\nNew WeChat video received.\n\n"
                    "Recent synced WeChat files:\n"
                    f"- {old_video} ({old_video.stat().st_size} bytes)"
                ),
                "preflight": {
                    "media_resolution": {
                        "copied": [
                            {
                                "task_copy_path": str(exact),
                                "suffix": ".jpg",
                                "matched_by": "exact-source-token",
                            }
                        ]
                    }
                },
            }

            self.assertFalse(worker.file_intake_has_explicit_non_image_request_files(task))
            items = worker.extract_file_intake_source_items(task)

        self.assertEqual(len(items), 1)
        self.assertEqual(Path(items[0]["task_copy_path"]), exact)

    def test_audio_intake_rejects_video_candidate_bound_to_multiple_rows(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            old_video = Path(tmp) / "old.mp4"
            old_video.write_bytes(b"old")
            task = {
                "source": {"local_id": 60, "local_type": 1},
                "request": "Current coalesced request:\npublish this video",
                "context": [
                    {"local_id": 53, "local_type": 43, "content": "[WeChat video] old"},
                    {"local_id": 59, "local_type": 43, "content": "[WeChat video] current"},
                ],
                "preflight": {
                    "autopublish_video": {
                        "target": str(old_video),
                        "message_local_ids": [53, 59],
                    }
                },
            }

            candidates = worker.audio_intake_media_candidates(task)

        self.assertEqual(worker.extract_video_local_ids_from_task(task), [59])
        self.assertEqual(candidates, [])

    def test_media_resolution_rejects_readable_candidate_without_exact_media_token(self) -> None:
        worker = load_worker()
        import wechat_mirror  # type: ignore

        expected_token = "11111111111111111111111111111111"
        unrelated_token = "22222222222222222222222222222222"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            unrelated = tmp_path / f"{unrelated_token}.jpg"
            unrelated.write_bytes(b"\xff\xd8\xff\xe0unrelated-jpeg")
            create_time = datetime.now().timestamp()
            db = tmp_path / "wechat_mirror.sqlite"
            event_id = wechat_mirror.record_event(
                chat_name="MEMO",
                action="media-sync",
                status="copied",
                db_path=db,
            )
            wechat_mirror.record_media_files(
                chat_name="MEMO",
                event_id=event_id,
                db_path=db,
                files=[
                    {
                        "source": str(unrelated),
                        "target": str(unrelated),
                        "suffix": ".jpg",
                        "bytes": unrelated.stat().st_size,
                        "mtime": create_time,
                        "status": "decoded",
                        "matched_by": f"token:{unrelated_token}",
                    }
                ],
            )
            task = {
                "chat": "MEMO",
                "source": {
                    "local_id": 90,
                    "local_type": 43,
                    "create_time": create_time,
                    "content": f"<msg><videomsg md5=\"{expected_token}\" /></msg>",
                },
                "request": "Edit this exact video.",
                "route_decision": {
                    "route_kind": "edit_existing_media",
                    "needs_recent_media": True,
                },
            }

            with mock.patch.dict(worker.os.environ, {"WECHAT_MIRROR_DB": str(db)}):
                candidates = worker.resolve_synced_media_from_mirror(task)

        self.assertEqual(candidates, [])

    def test_media_identity_tokens_ignore_incidental_task_and_cache_hashes(self) -> None:
        worker = load_worker()
        exact_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        cache_hash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        config_hash = "cccccccccccccccccccccccccccccccc"
        task = {
            "request": (
                "Process the current source.\n\n"
                "Recent synced WeChat files:\n"
                f"- /tmp/cache/{cache_hash}.jpg\n\n"
                f"route_config_hash={config_hash}"
            ),
            "source": {
                "local_type": 1,
                "content": f"config checksum {config_hash}",
            },
            "context": [
                {
                    "local_type": 3,
                    "kind": "image",
                    "content": f"<msg><img md5=\"{exact_token}\" /></msg>",
                }
            ],
        }

        self.assertEqual(worker.extract_media_tokens_from_task(task), [exact_token])

    def test_media_source_windows_ignore_ordinary_text_rows(self) -> None:
        worker = load_worker()
        task = {
            "source": {"local_type": 1, "create_time": 1000},
            "context": [
                {"local_type": 1, "create_time": 1500},
                {"local_type": 3, "kind": "image", "create_time": 2000},
            ],
        }

        with mock.patch.dict(
            worker.os.environ,
            {"WECHAT_WORKER_MEDIA_SOURCE_WINDOW_SECONDS": "10"},
        ):
            windows = worker.task_media_source_windows(task)

        self.assertEqual(windows, [(1990.0, 2010.0)])

    def test_media_resolution_retries_after_gui_cache_probe(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "mirror" / "fresh-image.jpg"
            source.parent.mkdir()
            source.write_bytes(b"\xff\xd8fresh-jpeg")
            task = {
                "id": "edit-image-gui-probe",
                "chat": "懒人科研",
                "route_decision": {"route_kind": "edit_existing_media", "needs_recent_media": True},
                "request": "Current coalesced request:\nPlease edit this image.",
            }

            with mock.patch.object(worker, "refresh_media_sync_for_task", side_effect=[{"status": "first"}, {"status": "second"}]):
                with mock.patch.object(worker, "resolve_synced_media_from_mirror", side_effect=[[], [{"mirror_path": str(source), "score": 90}]]):
                    with mock.patch.object(worker, "materialize_chat_for_media_cache", return_value={"status": "ok", "output_dir": str(tmp_path / "gui")}):
                        preflight = worker.prepare_media_resolution_preflight(task, tmp_path / "artifact")

            copied = preflight["copied"]
            copied_path = Path(copied[0]["task_copy_path"])
            copied_exists = copied_path.is_file()
            manifest_text = Path(preflight["manifest_md"]).read_text(encoding="utf-8")

        self.assertEqual(preflight["status"], "ok")
        self.assertEqual(preflight["gui_cache_probe"]["status"], "ok")
        self.assertEqual(preflight["second_refresh"]["status"], "second")
        self.assertTrue(copied_exists)
        self.assertIn("GUI Cache Probe", manifest_text)

    def test_media_resolution_records_image_ocr_and_exposes_transcript(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "mirror" / "legal-standard.png"
            source.parent.mkdir()
            source.write_bytes(b"png-bytes" * 5000)
            ocr_text = tmp_path / "artifact" / "image_text" / "legal-standard.ocr.txt"
            vision_text = tmp_path / "artifact" / "image_text" / "legal-standard.vision.txt"
            task = {
                "id": "read-image-task",
                "chat": "懒人科研",
                "route_decision": {"route_kind": "edit_existing_media", "needs_recent_media": True},
                "request": "Current coalesced request:\nPlease read and transcribe this image.",
            }

            with mock.patch.object(worker, "refresh_media_sync_for_task", return_value={"status": "refreshed"}):
                with mock.patch.object(worker, "resolve_synced_media_from_mirror", return_value=[{"mirror_path": str(source), "score": 99}]):
                    with mock.patch.object(
                        worker,
                        "image_file_metadata",
                        return_value={"status": "ok", "width": 1200, "height": 800, "format": "PNG", "mode": "RGB"},
                    ):
                        with mock.patch.object(
                            worker,
                            "ocr_image_file",
                            return_value={
                                "status": "ok",
                                "text_path": str(ocr_text),
                                "text_preview": "Legal standard image OCR text",
                                "languages": "eng+chi_sim+chi_tra+jpn",
                            },
                        ):
                            with mock.patch.object(
                                worker,
                                "codex_read_image_file",
                                return_value={
                                    "status": "ok",
                                    "text_path": str(vision_text),
                                    "text_preview": "Codex read: Article title and body text",
                                    "model": "gpt-5.5",
                                    "reasoning_effort": "low",
                                },
                            ):
                                preflight = worker.prepare_media_resolution_preflight(task, tmp_path / "artifact")
                                task["preflight"] = {"media_resolution": preflight}
                                tool_context = worker.build_media_resolution_tool_context(task)

            copied = preflight["copied"]
            manifest_text = Path(preflight["manifest_md"]).read_text(encoding="utf-8")

        self.assertEqual(copied[0]["ocr"]["status"], "ok")
        self.assertEqual(copied[0]["vision"]["status"], "ok")
        self.assertEqual(copied[0]["image_metadata"]["width"], 1200)
        self.assertIn("Codex image read:", tool_context)
        self.assertIn("Codex read: Article title and body text", tool_context)
        self.assertIn("OCR text:", tool_context)
        self.assertIn("Legal standard image OCR text", tool_context)
        self.assertIn("Codex image preview", manifest_text)
        self.assertIn("OCR preview", manifest_text)

    def test_gui_cache_probe_clicks_visible_image_when_image_source_is_missing(self) -> None:
        worker = load_worker()
        completed = subprocess.CompletedProcess(args=["wechat_chat_sync_loop.py"], returncode=0, stdout="opened", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "id": "image-cache-click",
                "chat": "懒人科研",
                "source": {"local_type": 3},
                "route_decision": {"route_kind": "edit_existing_media", "needs_recent_media": True},
                "request": "Current coalesced request:\nRead the image I sent.",
            }
            with mock.patch.object(worker.subprocess, "run", return_value=completed):
                with mock.patch.object(worker, "click_visible_media_for_cache", return_value={"status": "ok", "clicks": [{"x": 510, "y": 430}]}):
                    payload = worker.materialize_chat_for_media_cache(task, Path(tmp) / "artifact")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["image_click_probe"]["status"], "ok")
        self.assertEqual(payload["image_click_probe"]["clicks"][0]["x"], 510)

    def test_media_resolution_clicks_gui_when_only_thumbnail_image_is_cached(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            thumb = tmp_path / "mirror" / "thumb.jpg"
            original = tmp_path / "mirror" / "original.jpg"
            thumb.parent.mkdir()
            thumb.write_bytes(b"thumb")
            original.write_bytes(b"original" * 10000)
            task = {
                "id": "thumbnail-needs-cache-probe",
                "chat": "鏈接",
                "source": {"local_type": 3},
                "route_decision": {"route_kind": "edit_existing_media", "needs_recent_media": True},
                "request": "Current coalesced request:\nRead this image.",
            }

            def fake_metadata(path: Path) -> dict:
                if "thumb" in path.name:
                    return {"status": "ok", "width": 160, "height": 120, "format": "JPEG", "mode": "RGB"}
                return {"status": "ok", "width": 900, "height": 700, "format": "JPEG", "mode": "RGB"}

            with mock.patch.object(worker, "refresh_media_sync_for_task", side_effect=[{"status": "first"}, {"status": "second"}]):
                with mock.patch.object(
                    worker,
                    "resolve_synced_media_from_mirror",
                    side_effect=[
                        [{"mirror_path": str(thumb), "suffix": ".jpg", "score": 80}],
                        [{"mirror_path": str(original), "suffix": ".jpg", "score": 140}],
                    ],
                ):
                    with mock.patch.object(worker, "image_file_metadata", side_effect=fake_metadata):
                        with mock.patch.object(worker, "ocr_image_file", return_value={"status": "empty", "text_path": "", "text_preview": ""}):
                            with mock.patch.object(worker, "materialize_chat_for_media_cache", return_value={"status": "ok", "output_dir": str(tmp_path / "gui")}):
                                preflight = worker.prepare_media_resolution_preflight(task, tmp_path / "artifact")

        self.assertEqual(preflight["gui_cache_probe"]["status"], "ok")
        self.assertIn("cached_image_too_small", preflight["gui_cache_probe"]["reason"])
        self.assertEqual(Path(preflight["copied"][0]["task_copy_path"]).name, "original.jpg")

    def test_file_intake_result_does_not_auto_attach_saved_copy(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "chaos_making_new_science_2015.pdf"
            saved.write_bytes(b"%PDF-1.4\nchaos")
            result = {
                "message": "已做文件预检并保存。",
                "files": [],
                "data": {
                    "require_file_delivery": False,
                    "file_intake": {
                        "copied": [{"saved_path": str(saved)}],
                        "manifest_md": str(Path(tmp) / "file_intake_manifest.md"),
                    },
                },
            }
            raw = json.dumps(result, ensure_ascii=False)

            prepared = worker.prepare_result_files(result, raw)

        self.assertEqual(prepared["files"], [])

    def test_file_intake_nested_result_does_not_require_or_auto_attach_file(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "chaos_making_new_science_2015.pdf"
            saved.write_bytes(b"%PDF-1.4\nchaos")
            result = {
                "message": "已做文件预检并保存。",
                "files": [],
                "data": {
                    "message": "已做文件预检并保存。",
                    "files": [],
                    "data": {
                        "require_file_delivery": False,
                        "file_intake": {"copied": [{"saved_path": str(saved)}]},
                    },
                },
            }
            raw = json.dumps(result["data"], ensure_ascii=False)

            parsed = worker.parse_worker_result(raw)
            prepared = worker.prepare_result_files(parsed, raw)
            requires_delivery = worker.result_requires_file_delivery(
                {"route_decision": {"route_kind": "file_intake"}},
                {**prepared, "files": [str(saved)]},
            )

        self.assertEqual(parsed["files"], [])
        self.assertEqual(prepared["files"], [])
        self.assertFalse(requires_delivery)

    def test_lalachan_story_request_ignores_old_video_publish_context_for_preflight(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-story",
            "chat": "🍓我的设备",
            "request": (
                "Handle this WeChat request as backend work.\n\n"
                "Current coalesced request:\n"
                "Generate today’s LALACHAN story from the prompt: They go to the restaurant and find many gold.\n\n"
                "Recent history:\n"
                "陈苗: <msg><videomsg md5=\"bea815fa6ed81bbd5da77ac6895c5fd9\" /></msg>\n"
                "陈苗: Could you publish it?"
            ),
            "source": {"local_id": 19, "sender_display": "陈苗"},
            "context": [
                {"local_id": 14, "sender_display": "陈苗", "content": '<msg><videomsg md5="bea815fa6ed81bbd5da77ac6895c5fd9" /></msg>'},
                {"local_id": 16, "sender_display": "陈苗", "content": "Could you publish it?"},
                {"local_id": 19, "sender_display": "陈苗", "content": "Could you generate today lalachan story? They go to the restaurant and find many gold."},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            preflight = worker.prepare_worker_preflight(task, Path(tmp))

        self.assertEqual(preflight, {})
        self.assertFalse(worker.is_video_publish_task(task))
        self.assertFalse(worker.should_preflight_autopublish(task))

    def test_generate_video_route_blocks_old_publish_context_and_preflight(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "chat": "🍓我的设备",
            "route_decision": {
                "route_kind": "generate_video",
                "project": "lalachan",
                "needs_recent_media": False,
                "public_publish_allowed": False,
                "reason": "current request asks to generate a new video",
            },
            "request": (
                "Handle this WeChat request as backend work.\n\n"
                "Agent route decision:\n{\"route_kind\":\"generate_video\",\"public_publish_allowed\":false}\n\n"
                "Current coalesced request:\n"
                "Could you generate the video ? 30s cheap model and upload all images. Same profile and port\n\n"
                "Recent history:\n"
                "陈喵瞄秒妙: 已完成发布：video_id=393 platforms=shipinhao,youtube,instagram\n"
                "陈苗: <msg><videomsg md5=\"old-video\" /></msg>"
            ),
            "source": {"local_id": 29, "sender_display": "陈苗"},
            "context": [
                {"local_id": 14, "sender_display": "陈苗", "content": '<msg><videomsg md5="old-video" /></msg>'},
                {"local_id": 18, "sender_display": "bot", "content": "已完成发布：video_id=393 platforms=shipinhao,youtube,instagram"},
                {"local_id": 29, "sender_display": "陈苗", "content": "Could you generate the video ? 30s cheap model and upload all images. Same profile and port"},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            preflight = worker.prepare_worker_preflight(task, tmp_path)
            self.assertIn("generated_video_contract", preflight)
            contract = preflight["generated_video_contract"]
            self.assertTrue(Path(contract["json"]).is_file())
            contract_text = Path(contract["markdown"]).read_text(encoding="utf-8")
            contract_data = json.loads(Path(contract["json"]).read_text(encoding="utf-8"))

        self.assertIn("route_kind", contract_text)
        self.assertIn("Stage Permissions", contract_text)
        self.assertIn("Orchestration Routine", contract_text)
        self.assertIn("wechat_artifact_delivery_gate", contract_text)
        self.assertFalse(contract_data["stage_permissions"]["lazyedit_import"])
        self.assertIn("orchestration_routine", contract_data)
        self.assertIn("wechat_artifact_delivery_gate", [item["id"] for item in contract_data["orchestration_routine"]])
        self.assertIn("Do not publish", contract_text)
        self.assertNotIn("lazyedit_context", preflight)
        self.assertNotIn("autopublish_video", preflight)
        self.assertFalse(worker.is_video_publish_task(task))
        self.assertFalse(worker.should_preflight_autopublish(task))
        self.assertFalse(worker.should_deterministic_video_publish(task))

    def test_generate_video_publish_route_excludes_old_media_from_lazyedit_context(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-and-publish-video",
            "chat": "懒人科研",
            "route_decision": {
                "route_kind": "generate_video",
                "project": "lalachan",
                "needs_recent_media": False,
                "public_publish_allowed": True,
                "reason": "current request asks to generate a new video and publish the generated result",
            },
            "request": (
                "Handle this WeChat request as backend work.\n\n"
                "Current coalesced request:\n"
                "Generate a 30s video with a cheap mini model, send the video back, then use LazyEdit and publish to shipinhao ins y2b.\n\n"
                "Recent history:\n"
                "陈苗: <msg><videomsg md5=\"old-video\" length=\"12345\" /></msg>"
            ),
            "source": {"local_id": 132, "sender_display": "陈苗"},
            "context": [
                {"local_id": 110, "sender_display": "陈苗", "content": '<msg><videomsg md5="old-video" length="12345" /></msg>'},
                {
                    "local_id": 132,
                    "sender_display": "陈苗",
                    "content": "Generate a 30s video with a cheap mini model, send it back, then LazyEdit and publish it.",
                },
            ],
        }

        def fail_if_autopublish_runs(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("generated-video preflight must not inspect or copy old AutoPublish media")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(worker.subprocess, "run", side_effect=fail_if_autopublish_runs):
                preflight = worker.prepare_worker_preflight(task, tmp_path)
            contract_data = json.loads(Path(preflight["generated_video_contract"]["json"]).read_text(encoding="utf-8"))
            context_text = Path(preflight["lazyedit_context"]["correction_prompt_file"]).read_text(encoding="utf-8")

        self.assertTrue(worker.is_video_publish_task(task))
        self.assertFalse(worker.should_preflight_autopublish(task))
        self.assertIn("generated_video_contract", preflight)
        self.assertIn("lazyedit_context", preflight)
        self.assertNotIn("autopublish_video", preflight)
        self.assertTrue(contract_data["stage_permissions"]["lazyedit_import"])
        self.assertTrue(contract_data["stage_permissions"]["public_publish"])
        self.assertIn("resumed Codex worker agent", " ".join(contract_data["rules"]))
        self.assertIn("WeChat message sent with the video", " ".join(contract_data["rules"]))
        self.assertIn("Generate a 30s video", context_text)
        self.assertNotIn("old-video", context_text)

    def test_generate_video_route_rewrites_false_publish_result(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": (
                "Current coalesced request:\n"
                "Could you generate the video ? 30s cheap model and upload all images. Same profile and port"
            ),
        }
        result = {
            "message": "已自动完成 LazyEdit 处理并发布到 shipinhao,youtube,instagram",
            "files": ["/home/lachlan/Nutstore Files/AutoPublish/old_COMPLETED.mp4"],
            "confirmation": "",
        }

        guarded = worker.enforce_worker_result_contract(task, result, json.dumps(result, ensure_ascii=False))

        self.assertIn("拦截", guarded["message"])
        self.assertIn("生成新视频", guarded["message"])
        self.assertEqual(guarded["files"], [])
        self.assertEqual(guarded["contract_guard"], "blocked_public_publish_claim_for_generate_video")

    def test_generate_video_route_preserves_fresh_video_with_negative_publish_note(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nGenerate the video and send it back.",
        }
        result = {
            "message": (
                "故事采用别墅院子种土豆的温暖生活设定，已在 Lala Studio "
                "上传 8 张参考图后生成。视频约 10 秒、4:3；未公开发布。"
            ),
            "files": ["/tmp/villa_potato_garden_warm_15s.mp4"],
            "confirmation": "",
        }

        guarded = worker.enforce_worker_result_contract(
            task,
            result,
            json.dumps(result, ensure_ascii=False),
        )

        self.assertEqual(guarded["message"], result["message"])
        self.assertEqual(guarded["files"], result["files"])
        self.assertNotIn("contract_guard", guarded)

    def test_generated_video_story_confirmation_is_preserved_before_generation(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-story-first",
            "route_decision": {
                "route_kind": "generate_video",
                "project": "lalachan",
                "public_publish_allowed": False,
            },
            "request": (
                "Current coalesced request:\n"
                "先告诉我今天的故事，不要急着生成视频。"
            ),
        }
        result = {
            "message": (
                "今天的故事先从四个人在别墅院子挖土豆开始，最后一起炸薯条。"
                "现在只确认故事，不进入 LazyEdit 或发布流程。"
            ),
            "files": ["/tmp/lalachan_fries_story.md"],
            "confirmation": "这个故事可以吗？确认后我再生成视频。",
        }

        guarded = worker.enforce_worker_result_contract(
            task,
            result,
            json.dumps(result, ensure_ascii=False),
        )

        self.assertEqual(guarded["message"], result["message"])
        self.assertEqual(guarded["confirmation"], result["confirmation"])
        self.assertEqual(
            guarded["contract_guard"],
            "generated_video_waiting_for_confirmation",
        )
        self.assertEqual(
            guarded["data"]["generated_video_stage_state"],
            "waiting_confirmation_before_generation",
        )
        self.assertNotIn("我已拦截", guarded["message"])
        self.assertNotIn("还没有验证到新的 MP4", guarded["message"])

    def test_task_focus_uses_exact_rows_instead_of_transport_policy_wrappers(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-exact-focus",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": (
                "Treat this as a message forwarded from WeChat into the backend Codex "
                "session. Only enter LazyEdit if the current request asks for it.\n\n"
                "Current coalesced request:\n"
                "先告诉我故事，不要急着生成。\n\n"
                "Recent history:\nold publication request"
            ),
            "source": {"local_id": 4},
            "context": [
                {
                    "local_id": 4,
                    "content": "我希望生成今天的视频，先告诉我故事，不要急着生成。",
                }
            ],
            "interruptions": [
                {
                    "source": {"local_id": 7},
                    "request": (
                        "Treat this as a message forwarded from WeChat. "
                        "LazyEdit import/process is a separate permission."
                    ),
                    "context": [
                        {"local_id": 7, "content": "先给我文字版的故事"}
                    ],
                }
            ],
        }

        focused = worker.task_focus_text(task)
        stages = worker.generated_video_stage_permissions(task)

        self.assertIn("我希望生成今天的视频", focused)
        self.assertIn("先给我文字版的故事", focused)
        self.assertNotIn("separate permission", focused)
        self.assertNotIn("Only enter LazyEdit", focused)
        self.assertFalse(stages["lazyedit_import"])
        self.assertFalse(stages["public_publish"])

    def test_generate_video_route_rewrites_unrequested_lazyedit_result(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nGenerate the video and send the MP4 back here.",
        }
        result = {
            "message": "已完成 LazyEdit 导入和处理。",
            "files": [],
            "confirmation": "",
        }

        guarded = worker.enforce_worker_result_contract(task, result, json.dumps(result, ensure_ascii=False))

        self.assertIn("拦截", guarded["message"])
        self.assertEqual(guarded["contract_guard"], "blocked_unrequested_lazyedit_for_generate_video")

    def test_generate_video_route_requires_video_or_status_evidence(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nCould you generate the video?",
        }
        result = {"message": "已准备提示词。", "files": ["/tmp/prompt.md"], "confirmation": ""}

        guarded = worker.enforce_worker_result_contract(task, result, "已准备提示词。")

        self.assertIn("还没有验证到新的 MP4", guarded["message"])
        self.assertEqual(guarded["files"], ["/tmp/prompt.md"])
        self.assertEqual(guarded["contract_guard"], "missing_generated_video_completion_evidence")

    def test_generate_video_route_allows_poststage_result_after_video_delivery(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nGenerate the video, send it back, and upload it to LazyEdit only.",
            "sent_file_paths": ["/tmp/generated.mp4"],
            "generated_video_poststage": {"kind": "lazyedit_import", "video_path": "/tmp/generated.mp4"},
        }
        result = {
            "message": "已继续完成生成视频的 LazyEdit import/process 后续阶段：status=done; no public publish.",
            "files": [],
            "confirmation": "",
            "poststage": {"status": "done", "publish": False},
        }

        guarded = worker.enforce_worker_result_contract(task, result, json.dumps(result, ensure_ascii=False))

        self.assertNotIn("contract_guard", guarded)
        self.assertNotIn("还没有验证到新的 MP4", guarded["message"])
        self.assertEqual(guarded["files"], [])

    def test_generate_video_route_uses_medium_policy_and_no_progress_escalation(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": (
                "Current coalesced request:\n"
                "Could you generate the video ? 30s cheap model and upload all images. Same profile and port\n\n"
                "Recent history:\nold publish context should not make this xhigh"
            ),
        }

        policy = worker.choose_worker_policy(task)
        next_policy = worker.escalated_policy(policy, "已提交 Xiaoyunque 生成，正在生成中。", task=task)

        self.assertEqual(policy["model"], "auto-code-review")
        self.assertEqual(policy["reasoning_effort"], "medium")
        self.assertIsNone(next_policy)

    def test_generate_video_progress_stays_waiting_not_done(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-generate-video",
            "chat": "🍓我的设备",
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": "Current coalesced request:\nCould you generate the video?",
        }
        result = {
            "message": "已提交 Xiaoyunque，正在生成中。thread_url=https://xyq.jianying.com/home?thread_id=abc",
            "files": [],
            "confirmation": "",
            "raw": '{"generation":{"status":"submitted","thread_url":"https://xyq.jianying.com/home?thread_id=abc","page_id":"PAGE123456"}}',
            "data": {"generation": {"status": "submitted", "thread_url": "https://xyq.jianying.com/home?thread_id=abc", "page_id": "PAGE123456"}},
        }

        worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], worker.GENERATED_VIDEO_WAITING_STATUS)
        self.assertIn("next_poll_at", task)
        self.assertEqual(task["generated_video_monitor"]["thread_url"], "https://xyq.jianying.com/home?thread_id=abc")
        self.assertEqual(task["generated_video_monitor"]["page_id"], "PAGE123456")

    def test_generate_video_progress_is_not_sent_by_default(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": "Current coalesced request:\nCould you generate a 30s video?",
        }
        result = {"message": "已提交 Xiaoyunque，生成中。", "files": [], "confirmation": ""}

        self.assertFalse(worker.should_send_worker_result(task, result))

    def test_read_only_source_recovery_drops_verification_confirmation(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Current coalesced request:\nread this mp.weixin article",
            "preflight": {
                "wechat_source_recovery": {
                    "status": "reconstruction_required",
                    "verification_policy": "never_request_user_verification_for_read_only_research",
                }
            },
        }
        result = {
            "message": "Only the card title was readable.",
            "files": [],
            "confirmation": "Open it in native WeChat webview or provide screenshots.",
        }

        guarded = worker.enforce_worker_result_contract(task, result, json.dumps(result))

        self.assertEqual(guarded["confirmation"], "")
        self.assertEqual(guarded["contract_guard"], "read_only_source_never_waits_for_verification")
        self.assertTrue(worker.should_send_worker_result(task, guarded))

    def test_wecom_android_article_preflight_uses_native_exact_card_resolver(self) -> None:
        worker = load_worker()
        title = "第一次，我们看到了高自由度灵巧手的另一种可能。"
        task = {
            "request": f"公众号文章卡片\n<title>{title}</title>",
            "source": {
                "wecom_transport_channel": "wecom_android",
                "wecom_chat_id": "gui:LabAgent",
            },
        }
        process = mock.MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "url": "https://mp.weixin.qq.com/s/demo",
                    "title": title,
                    "identity_verified": True,
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            worker.subprocess, "run", return_value=process
        ) as run:
            result = worker.prepare_wecom_native_article_recovery(task, Path(tmp))

        self.assertTrue(result["ok"])
        command = run.call_args.args[0]
        self.assertIn("--chat", command)
        self.assertEqual(command[command.index("--chat") + 1], "LabAgent")
        self.assertEqual(command[command.index("--title") + 1], title)

    def test_source_recovery_injects_native_url_without_exposing_it_in_native_packet(self) -> None:
        worker = load_worker()
        task = {
            "request": "公众号文章卡片\n<title>Exact title</title>",
            "source": {
                "wecom_transport_channel": "wecom_android",
                "wecom_chat_id": "gui:LabAgent",
            },
        }
        captured: dict[str, object] = {}

        def recover(augmented, output_dir, timeout):
            captured["request"] = augmented["request"]
            manifest = output_dir / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("{}", encoding="utf-8")
            return {"status": "ok", "manifest_json": str(manifest), "articles": []}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            worker,
            "prepare_wecom_native_article_recovery",
            return_value={
                "ok": True,
                "url": "https://mp.weixin.qq.com/s/demo",
                "title": "Exact title",
                "identity_verified": True,
            },
        ), mock.patch.object(worker, "recover_task_sources", side_effect=recover):
            result = worker.prepare_wechat_source_recovery_preflight(task, Path(tmp))

        self.assertIn("https://mp.weixin.qq.com/s/demo", str(captured["request"]))
        self.assertNotIn("url", result["native_wecom_article"])
        self.assertTrue(result["native_wecom_article"]["identity_verified"])

    def test_unreadable_large_image_candidate_still_requests_gui_probe(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.jpg"
            bad.write_bytes(b"\xff\xd8\xff\xe0" + b"not-a-real-jpeg" * 4096)
            task = {
                "chat": "鏈接",
                "source": {"kind": "image", "local_type": 3},
                "route_decision": {"route_kind": "research_or_summary", "needs_recent_media": True},
                "request": "Current coalesced request:\nread this image",
            }
            reason = worker.media_gui_cache_probe_reason(
                task,
                [{"mirror_path": str(bad), "suffix": ".jpg", "size_bytes": bad.stat().st_size}],
            )

        self.assertTrue(reason.startswith("cached_image_unreadable"))

    def test_publish_progress_is_not_sent_by_default(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-task",
            "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
            "request": "Current coalesced request:\npublish this video to YouTube",
        }
        result = {
            "message": "未确认发布完成；video_id=393",
            "files": [],
            "confirmation": "",
            "data": {
                "publish_poststage_retry": {
                    "status": "publish_running",
                    "retry_seconds": 60,
                    "poststage": {"kind": "existing_video_publish", "video_id": 393, "platforms": ["youtube"]},
                }
            },
        }

        original = worker.os.environ.get("WECHAT_WORKER_SEND_PUBLISH_PROGRESS")
        try:
            worker.os.environ.pop("WECHAT_WORKER_SEND_PUBLISH_PROGRESS", None)
            self.assertFalse(worker.should_send_worker_result(task, result))
            worker.os.environ["WECHAT_WORKER_SEND_PUBLISH_PROGRESS"] = "1"
            self.assertTrue(worker.should_send_worker_result(task, result))
        finally:
            if original is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_PUBLISH_PROGRESS", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_PUBLISH_PROGRESS"] = original

    def test_publish_progress_is_suppressed_for_routine_only_task(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-task",
            "routine": {"id": "video_publish_existing"},
            "request": "Current coalesced request:\ncontinue checking publish status",
        }
        result = {
            "message": "未确认发布完成；video_id=393",
            "files": [],
            "confirmation": "",
            "data": {
                "publish_poststage_retry": {
                    "status": "publish_running",
                    "retry_seconds": 60,
                    "poststage": {"kind": "existing_video_publish", "video_id": 393, "platforms": ["youtube"]},
                }
            },
        }

        original = worker.os.environ.get("WECHAT_WORKER_SEND_PUBLISH_PROGRESS")
        try:
            worker.os.environ.pop("WECHAT_WORKER_SEND_PUBLISH_PROGRESS", None)
            self.assertTrue(worker.is_video_publish_task(task))
            self.assertFalse(worker.should_send_worker_result(task, result))
        finally:
            if original is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_PUBLISH_PROGRESS", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_PUBLISH_PROGRESS"] = original

    def test_generate_video_timeout_with_monitor_state_keeps_waiting(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": "Current coalesced request:\nCould you generate a video?",
            "generated_video_monitor": {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
            },
        }
        result = {"message": "Worker failed: timed out before completing the task.", "files": [], "confirmation": ""}

        self.assertTrue(worker.generated_video_result_is_nonterminal(task, result))
        self.assertFalse(worker.should_send_worker_result(task, result))

    def test_generated_video_probe_confirmation_triggers_thread_continuation(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc",
                        "status": ["下载", "请确认", "符合预期", "继续帮您生成视频"],
                        "tail": "故事板以及参考素材已生成成功，请确认故事脚本、参考角色图、视频总时长是否符合预期，如果符合预期我将继续帮您生成视频。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            helper = tmp_path / "xyq_continue_thread.py"
            helper.write_text("# helper", encoding="utf-8")
            task = {
                "id": "task-video",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nGenerate a 30s LALACHAN video.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "task-video.mp4",
                },
            }

            def fake_run(command, **_kwargs):
                self.assertIn("--submit", command)
                self.assertIn("--message", command)
                message = command[command.index("--message") + 1]
                self.assertIn("30秒", message)
                self.assertIn("允许±5秒", message)
                payload = {
                    "ok": True,
                    "status": "continued",
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                }
                return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

            with mock.patch.object(worker, "generated_video_continue_script", return_value=helper):
                with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                    raw = worker.deterministic_generated_video_continue_result(task)

        self.assertIsNotNone(raw)
        assert raw is not None
        result = json.loads(raw)
        self.assertIn("已向 Xiaoyunque 当前线程提交继续生成确认", result["message"])
        self.assertTrue(worker.generated_video_result_is_nonterminal(task, result))
        self.assertEqual(task["generated_video_continuations"][0]["status"], "continued")

    def test_monitor_only_generated_video_does_not_continue_thread(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc",
                        "status": ["请确认", "符合预期", "继续帮您生成视频"],
                        "tail": "故事板已生成，请确认。如果符合预期我将继续帮您生成视频。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = {
                "id": "task-video",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False, "no_new_xyq_submit": True},
                "request": "Current coalesced request:\nMonitor the existing generated video.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "task-video.mp4",
                    "monitor_only_no_resubmit": True,
                },
                "credit_guard": {"enabled": True},
            }

            with mock.patch.object(worker.subprocess, "run") as run_mock:
                raw = worker.deterministic_generated_video_continue_result(task)

        self.assertIsNone(raw)
        run_mock.assert_not_called()
        self.assertTrue(worker.generated_video_monitor_only(task))

    def test_monitor_only_generated_video_does_not_submit_new_job(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-video",
            "status": worker.CLAIMED_STATUS,
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False, "no_new_xyq_submit": True},
            "request": "Current coalesced request:\nGenerate a video.",
            "generated_video_monitor": {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
                "monitor_only_no_resubmit": True,
            },
        }

        with mock.patch.object(worker.subprocess, "run") as run_mock:
            raw = worker.deterministic_generated_video_submit_result(task)

        self.assertIsNone(raw)
        run_mock.assert_not_called()

    def test_pre_submit_failure_is_retryable_but_uncertain_submit_is_monitor_only(self) -> None:
        worker = load_worker()
        base = {
            "id": "task-video",
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nGenerate a video.",
        }
        pre_submit = {
            **base,
            "generated_video_submit_probe": {
                "status": "page_unavailable",
                "paid_action_attempted": False,
                "paid_action_state": "not_attempted",
            },
        }
        uncertain = {
            **base,
            "generated_video_submit_probe": {
                "status": "timeout",
                "paid_action_attempted": None,
                "paid_action_state": "unknown",
            },
        }

        self.assertFalse(worker.generated_video_monitor_only(pre_submit))
        self.assertTrue(worker.generated_video_monitor_only(uncertain))

    def test_deterministic_video_submit_defaults_to_dedicated_cdp_9344(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-video",
            "status": worker.CLAIMED_STATUS,
            "route_decision": {
                "route_kind": "generate_video",
                "public_publish_allowed": False,
            },
            "request": "Current coalesced request:\nGenerate a 15 second video.",
        }
        commands: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            payload = {
                "ok": False,
                "status": "page_unavailable",
                "paid_action_attempted": False,
                "paid_action_state": "not_attempted",
            }
            return subprocess.CompletedProcess(command, 1, json.dumps(payload), "")

        with (
            mock.patch.dict(
                worker.os.environ,
                {"WECHAT_WORKER_XYQ_CDP_URL": "", "XYQ_CDP_URL": ""},
                clear=False,
            ),
            mock.patch.object(worker, "generated_video_submit_script", return_value=Path("/tmp/xyq_submit_current.py")),
            mock.patch.object(worker, "persist_task_progress"),
            mock.patch.object(worker.subprocess, "run", side_effect=fake_run),
        ):
            raw = worker.deterministic_generated_video_submit_result(task)

        self.assertIsNone(raw)
        self.assertEqual(len(commands), 1)
        cdp_index = commands[0].index("--cdp-url") + 1
        self.assertEqual(commands[0][cdp_index], "http://127.0.0.1:9344")

    def test_story_confirmation_gate_blocks_deterministic_video_continue(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc",
                        "status": ["请确认", "继续帮您生成视频"],
                        "tail": "故事板已生成，请确认。如果符合预期，我将继续帮您生成视频。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = {
                "id": "task-video",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
                "request": "Current coalesced request:\nGenerate the LALACHAN video.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "task-video.mp4",
                },
                "interruptions": [
                    {
                        "source": {"local_id": 202, "server_id": "srv-202", "sender_display": "陈苗"},
                        "request": "The story is not what I want. Update the story and show it here first.",
                        "request_excerpt": "The story is not what I want. Update the story and show it here first.",
                    }
                ],
            }

            raw = worker.deterministic_generated_video_continue_result(task)

        self.assertIsNone(raw)
        self.assertEqual(task["story_confirmation_gate"]["status"], "blocked_deterministic_continue")
        self.assertIn("Update the story", task["story_confirmation_gate"]["latest_update"])

    def test_generated_video_continuation_prompt_includes_latest_confirmed_context(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
            "request": "Current coalesced request:\nGenerate a 30s LALACHAN video.",
            "interruptions": [
                {
                    "source": {"local_id": 202, "sender_display": "陈苗"},
                    "request": "Change the story ending: AyaChan finds a gold spoon under the restaurant floor.",
                    "request_excerpt": "Change the story ending: AyaChan finds a gold spoon under the restaurant floor.",
                },
                {
                    "source": {"local_id": 203, "sender_display": "陈苗"},
                    "request": "story ok generate video now",
                    "request_excerpt": "story ok generate video now",
                },
            ],
        }

        prompt = worker.generated_video_continuation_prompt(task)

        self.assertIn("30秒", prompt)
        self.assertIn("微信群最新确认/补充要求", prompt)
        self.assertIn("gold spoon", prompt)
        self.assertIn("story ok generate video now", prompt)
        self.assertTrue(worker.latest_same_chat_confirms_video_generation(task))

    def test_generated_video_probe_without_confirmation_does_not_continue(self) -> None:
        worker = load_worker()
        self.assertFalse(
            worker.generated_video_probe_needs_continuation(
                {"status": ["生成中"], "tail": "任务正在生成中，大约还需 8 分钟。", "videos": []}
            )
        )

    def test_generate_video_timeout_discovers_xyq_thread_from_browser(self) -> None:
        worker = load_worker()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    [
                        {"type": "page", "id": "PAGE123456", "title": "小云雀网页版", "url": "https://xyq.jianying.com/home?thread_id=abc&agent_name=pippit_nest_agent"},
                        {"type": "page", "id": "OTHER", "title": "Other", "url": "https://example.com"},
                    ],
                    ensure_ascii=False,
                ).encode("utf-8")

        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": "Current coalesced request:\nCould you generate a LALACHAN video with Xiaoyunque?",
        }
        result = {"message": "Worker failed: timeout", "files": [], "confirmation": ""}

        with mock.patch.object(worker.urllib.request, "urlopen", return_value=FakeResponse()):
            worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], worker.GENERATED_VIDEO_WAITING_STATUS)
        self.assertEqual(task["generated_video_monitor"]["page_id"], "PAGE123456")
        self.assertIn("thread_id=abc", task["generated_video_monitor"]["thread_url"])

    def test_in_progress_generated_video_adopts_probe_monitor(self) -> None:
        worker = load_worker()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    [
                        {
                            "type": "page",
                            "id": "PAGE-PROBE",
                            "title": "小云雀网页版",
                            "url": "https://xyq.jianying.com/home?thread_id=abc&agent_name=pippit_nest_agent",
                        }
                    ],
                    ensure_ascii=False,
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            queue = tmp_path / "queue.jsonl"
            artifact_dir = tmp_path / "artifact"
            artifact_dir.mkdir()
            (artifact_dir / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc&agent_name=pippit_nest_agent",
                        "status": ["生成创意", "进行中"],
                        "tail": "请生成一个 30 秒视频。任务进行中。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-generate-video",
                        "status": worker.CLAIMED_STATUS,
                        "worker_id": "pid:999999",
                        "claimed_at": "1970-01-01T00:00:00",
                        "artifact_dir": str(artifact_dir),
                        "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                        "request": "Current coalesced request:\nCould you generate a 30s LALACHAN video?",
                    }
                ],
            )

            with mock.patch.object(worker.urllib.request, "urlopen", return_value=FakeResponse()):
                adopted = worker.adopt_active_generated_video_tasks(queue)

            self.assertIsNotNone(adopted)
            rows = worker.read_tasks(queue)
            self.assertEqual(rows[0]["status"], worker.GENERATED_VIDEO_WAITING_STATUS)
            self.assertEqual(rows[0]["generated_video_monitor"]["page_id"], "PAGE-PROBE")
            self.assertIn("thread_id=abc", rows[0]["generated_video_monitor"]["thread_url"])
            self.assertIn("next_poll_at", rows[0])

    def test_in_progress_generated_video_does_not_adopt_while_worker_is_alive(self) -> None:
        worker = load_worker()
        task = {
            "id": "video-live-worker",
            "status": worker.CLAIMED_STATUS,
            "worker_id": "pid:12345",
            "claimed_at": "1970-01-01T00:00:00",
            "route_decision": {"route_kind": "generate_video"},
        }

        with mock.patch.object(worker, "process_alive", return_value=True):
            self.assertFalse(worker.generated_video_adoption_due(task, datetime.now()))

    def test_browser_monitor_discovery_rejects_threads_open_at_claim(self) -> None:
        worker = load_worker()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    [
                        {"type": "page", "id": "OLD-PAGE", "title": "old", "url": "https://xyq.jianying.com/home?thread_id=old-thread&tab_name=integrated-agent"},
                        {"type": "page", "id": "NEW-PAGE", "title": "new", "url": "https://xyq.jianying.com/home?thread_id=new-thread&tab_name=integrated-agent"},
                    ]
                ).encode("utf-8")

        task = {
            "route_decision": {"route_kind": "generate_video"},
            "request": "generate a new video",
            "generated_video_claim_baseline": {
                "page_ids": ["OLD-PAGE"],
                "thread_ids": ["old-thread"],
            },
        }
        with mock.patch.object(worker.urllib.request, "urlopen", return_value=FakeResponse()):
            monitor = worker.discover_generated_video_monitor_from_browser(task)

        self.assertEqual(monitor["page_id"], "NEW-PAGE")
        self.assertIn("thread_id=new-thread", monitor["thread_url"])

    def test_reprocess_wrong_generated_video_uses_fresh_artifact_directory(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-wrong-result",
                        "chat": "MEMO",
                        "request": "generate a new video",
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "done",
                        "artifact_dir": str(Path(tmp) / "old-artifacts"),
                        "generated_video_monitor": {"thread_url": "https://xyq.jianying.com/home?thread_id=old"},
                        "generation_wait_count": 2,
                        "sent_file_paths": [str(Path(tmp) / "old.mp4")],
                    }
                ],
            )

            task = worker.reprocess_task(
                queue,
                "video-wrong-result",
                reason="The result was an old video; generate a new video for this request.",
            )

        self.assertEqual(task["status"], "pending")
        self.assertNotIn("generated_video_monitor", task)
        self.assertNotIn("generation_wait_count", task)
        self.assertIn("-retry-", task["artifact_dir"])
        self.assertTrue(task["invalid_generated_video_reprocess"]["fresh_submission_required"])
        policy = worker.choose_worker_policy(task)
        self.assertEqual(policy["model"], "gpt-5.6-sol")
        self.assertEqual(policy["reasoning_effort"], "medium")
        self.assertFalse(policy["reuse_session"])

    def test_generate_video_status_backoff_uses_page_status(self) -> None:
        worker = load_worker()

        self.assertEqual(worker.generated_video_status_backoff_seconds("大约还需 8 分钟"), 312)
        self.assertEqual(worker.generated_video_status_backoff_seconds("预计还需 3 小时"), 1800)
        self.assertEqual(worker.generated_video_status_backoff_seconds("about 3 hours remaining"), 1800)
        self.assertEqual(worker.generated_video_status_backoff_seconds("about 12 minutes remaining"), 468)
        self.assertEqual(worker.generated_video_status_backoff_seconds("排队等待中"), 300)
        self.assertEqual(worker.generated_video_status_backoff_seconds("生成中"), 120)
        self.assertEqual(worker.generated_video_status_backoff_seconds("", "please generate 30s video"), 180)

    def test_generated_video_verification_policy_allows_five_second_duration_tolerance(self) -> None:
        worker = load_worker()
        task = {
            "request": "Current coalesced request:\nGenerate a 30s video with a cheap mini model.",
        }

        policy = worker.generated_video_verification_policy(task)

        self.assertEqual(policy["requested_duration_seconds"], 30)
        self.assertEqual(policy["duration_tolerance_seconds"], 5)
        self.assertEqual(policy["accepted_min_duration_seconds"], 25)
        self.assertEqual(policy["accepted_max_duration_seconds"], 35)

    def test_generated_video_exact_duration_uses_stricter_tolerance(self) -> None:
        worker = load_worker()
        task = {
            "request": "Current coalesced request:\nGenerate exactly 30s video.",
        }

        policy = worker.generated_video_verification_policy(task)

        self.assertEqual(policy["requested_duration_seconds"], 30)
        self.assertEqual(policy["duration_tolerance_seconds"], 1)

    def test_generated_video_stage_permissions_are_current_request_only(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": (
                "Current coalesced request:\n"
                "Generate a new Xiaoyunque video and send it back here.\n\n"
                "Recent history:\n"
                "old message said upload to LazyEdit and publish to YouTube"
            ),
        }

        stages = worker.generated_video_stage_permissions(task)

        self.assertTrue(stages["video_generation"])
        self.assertTrue(stages["generation"])
        self.assertTrue(stages["wechat_send_back"])
        self.assertFalse(stages["lazyedit_import"])
        self.assertFalse(stages["public_publish"])
        self.assertFalse(stages["publication"])
        self.assertFalse(stages["generation_is_publication"])
        self.assertIn("generation creates/downloads/sends artifacts", stages["stage_boundary"])
        self.assertEqual(stages["publish_platforms"], [])

    def test_generated_video_stage_permissions_allow_lazyedit_without_publish(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
            "request": "Current coalesced request:\nGenerate the video, upload it to LazyEdit only, and send the MP4 back.",
        }

        stages = worker.generated_video_stage_permissions(task)

        self.assertTrue(stages["lazyedit_import"])
        self.assertFalse(stages["public_publish"])
        self.assertFalse(stages["publication"])

    def test_generated_video_tool_context_requires_orchestration_routine(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
            "request": "Current coalesced request:\nGenerate the video, send it back, and publish to SPH.",
        }

        context = worker.build_generated_video_tool_context(task)

        self.assertIn("routine orchestration job", context)
        self.assertIn("Orchestration routine", context)
        self.assertIn("wechat_artifact_delivery_gate", context)
        self.assertIn("lazyedit_poststage", context)
        self.assertIn("public_publish", context)

    def test_generated_video_preflight_records_same_chat_interruptions(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-201",
            "chat": "懒人科研",
            "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
            "request": "Current coalesced request:\nGenerate the video first.",
            "source": {"local_id": 201, "server_id": "srv-201"},
            "interruptions": [
                {
                    "at": "2026-06-25T21:10:00",
                    "source": {"local_id": 202, "server_id": "srv-202", "sender_display": "陈苗"},
                    "request": "Current coalesced request:\nThe story is not what I want. Update it and show it here first.",
                    "request_excerpt": "The story is not what I want. Update it and show it here first.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            preflight = worker.prepare_worker_preflight(task, Path(tmp))
            interruption_manifest = preflight["interruptions"]
            manifest_text = Path(interruption_manifest["markdown"]).read_text(encoding="utf-8")
            contract_text = Path(preflight["generated_video_contract"]["markdown"]).read_text(encoding="utf-8")
            focus = worker.task_focus_text(task)
            context = worker.build_generated_video_tool_context(task)

        self.assertEqual(interruption_manifest["count"], 1)
        self.assertIn("Update it and show it here first", manifest_text)
        self.assertIn("update it and show it here first", focus.lower())
        self.assertIn("same-chat messages", contract_text)
        self.assertIn("stale Xiaoyunque run", context)

    def test_generated_video_focus_includes_approved_story_after_confirmation(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-206",
            "chat": "懒人科研",
            "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
            "request": "Current coalesced request:\nstory ok generate video now",
            "story_confirmation_result": {
                "message": "Approved story: AyaChan compares Uma Gumi and konnyaku before Kindle translation practice.",
                "files": ["/tmp/approved-story.md"],
                "confirmation": "这个故事可以用来生成 30s 视频吗？",
            },
            "approved_story_message": "Approved story: AyaChan compares Uma Gumi and konnyaku before Kindle translation practice.",
            "approved_story_files": ["/tmp/approved-story.md"],
        }

        with tempfile.TemporaryDirectory() as tmp:
            preflight = worker.prepare_worker_preflight(task, Path(tmp))
            contract_text = Path(preflight["generated_video_contract"]["markdown"]).read_text(encoding="utf-8")
            focus = worker.task_focus_text(task)

        self.assertIn("Approved story for video generation", focus)
        self.assertIn("Uma Gumi and konnyaku", focus)
        self.assertIn("/tmp/approved-story.md", focus)
        self.assertIn("Uma Gumi and konnyaku", contract_text)

    def test_worker_merges_pending_story_followup_into_active_video_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-201",
                        "chat": "懒人科研",
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "request": "Current coalesced request:\nGenerate a RaraXia video.",
                        "route_decision": {"route_kind": "generate_video", "project": "lalachan"},
                        "source": {"message_table": "MSG", "server_id": "srv-201", "local_id": 201},
                        "routine": {"id": "generated_video"},
                    },
                    {
                        "id": "task-202",
                        "chat": "懒人科研",
                        "status": "pending",
                        "request": "Current coalesced request:\nUpdate the story and show it here before generation.",
                        "route_decision": {"route_kind": "story_or_script", "project": "lalachan"},
                        "source": {"message_table": "MSG", "server_id": "srv-202", "local_id": 202},
                        "routine": {"id": "story_script_generation"},
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 1)
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertTrue(tasks[0]["interruption_pending"])
        self.assertEqual(tasks[0]["interruptions"][0]["source"]["local_id"], 202)
        self.assertEqual(tasks[1]["status"], "canceled_superseded")

    def test_worker_reconciles_legacy_bare_video_and_explicit_publish_rows(self) -> None:
        worker = load_worker()
        now = int(datetime.now().timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-64",
                        "chat": "🍓My devices",
                        "status": "worker_abandoned",
                        "request": "New WeChat video item received; inspect the bare WeChat video upload.",
                        "route_decision": {
                            "route_kind": "process_existing_video",
                            "public_publish_allowed": False,
                            "reason": "new bare WeChat video upload",
                        },
                        "routine": {"id": "video_publish_existing"},
                        "source": {
                            "message_table": "MSG",
                            "config_id": "devices",
                            "server_id": "srv-64",
                            "local_id": 64,
                            "local_type": 43,
                            "create_time": now,
                        },
                        "context": [
                            {
                                "message_table": "MSG",
                                "server_id": "srv-64",
                                "local_id": 64,
                                "local_type": 43,
                                "kind": "video",
                                "content": "<msg><videomsg /></msg>",
                            }
                        ],
                        "worker_result_ready_at": "2026-08-18T11:58:00",
                        "send_suppressed_reason": "agent_no_reply",
                    },
                    {
                        "id": "publish-65",
                        "chat": "🍓My devices",
                        "status": "worker_abandoned",
                        "request": "Current coalesced request:\n帮我发布这个视频",
                        "route_decision": {
                            "route_kind": "publish_video",
                            "public_publish_allowed": True,
                            "public_publish_intent": True,
                        },
                        "routine": {"id": "video_publish_existing"},
                        "source": {
                            "message_table": "MSG",
                            "config_id": "devices",
                            "server_id": "srv-65",
                            "local_id": 65,
                            "local_type": 1,
                            "create_time": now + 1,
                        },
                        "context": [
                            {
                                "message_table": "MSG",
                                "server_id": "srv-64",
                                "local_id": 64,
                                "local_type": 43,
                                "kind": "video",
                                "content": "<msg><videomsg /></msg>",
                            },
                            {
                                "message_table": "MSG",
                                "server_id": "srv-65",
                                "local_id": 65,
                                "local_type": 1,
                                "kind": "text",
                                "content": "帮我发布这个视频",
                            },
                        ],
                    },
                ],
            )

            promoted = worker.reconcile_passive_video_publish_followups(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(promoted, 1)
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[0]["source"]["local_id"], 64)
        self.assertEqual(tasks[0]["route_decision"]["route_kind"], "publish_video")
        self.assertTrue(tasks[0]["route_decision"]["public_publish_allowed"])
        self.assertEqual(tasks[0]["route_decision"]["exact_source_video_local_id"], 64)
        self.assertNotIn("worker_result_ready_at", tasks[0])
        self.assertNotIn("send_suppressed_reason", tasks[0])
        self.assertEqual(tasks[1]["status"], "canceled_superseded")
        self.assertEqual(tasks[1]["superseded_by"], "video-64")
        self.assertIn(
            "帮我发布这个视频",
            worker.build_lazyedit_metadata_brief(tasks[0]),
        )

    def test_passive_video_intake_success_is_private_and_skips_delivery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "source.mp4"
            video.write_bytes(b"exact-video")
            task = {
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "passive_video_intake": True,
                    "public_publish_allowed": False,
                },
                "source": {"local_id": 64, "local_type": 43},
                "preflight": {
                    "autopublish_video": {
                        "ok": True,
                        "target": str(video),
                        "message_local_ids": [64],
                    }
                },
            }

            raw = worker.deterministic_preflight_result(task)

        self.assertIsNotNone(raw)
        payload = json.loads(raw or "{}")
        self.assertTrue(payload["no_reply"])
        self.assertEqual(payload["files"], [])
        self.assertEqual(payload["data"]["passive_video_intake"]["status"], "cached")
        self.assertFalse(payload["data"]["passive_video_intake"]["publication_authorized"])
        self.assertFalse(payload["data"]["passive_video_intake"]["lazyedit_authorized"])

    def test_passive_video_contract_discards_agent_publish_claims_and_files(self) -> None:
        worker = load_worker()
        task = {
            "id": "video-passive",
            "route_decision": {
                "route_kind": "file_download_or_save",
                "passive_video_intake": True,
                "public_publish_allowed": False,
            },
            "source": {"local_id": 64, "local_type": 43},
        }
        malformed = {
            "message": "Published through LazyEdit.",
            "files": ["output/private-evidence.json", "output/video.mp4"],
            "confirmation": "Approve publication",
            "data": {"require_file_delivery": True},
        }

        guarded = worker.enforce_worker_result_contract(task, malformed, json.dumps(malformed))
        prepared = worker.prepare_result_files(guarded, json.dumps(malformed), task=task)

        self.assertTrue(prepared["no_reply"])
        self.assertEqual(prepared["message"], "")
        self.assertEqual(prepared["confirmation"], "")
        self.assertEqual(prepared["files"], [])
        self.assertFalse(prepared["data"]["require_file_delivery"])
        self.assertFalse(prepared["data"]["passive_video_intake"]["publication_authorized"])
        self.assertFalse(worker.should_send_worker_result(task, prepared))
        self.assertTrue(worker.task_forbids_chat_artifact_delivery(task))

    def test_passive_video_uses_private_cache_and_cannot_write_autopublish(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"exact-video")
            artifact_dir = root / "task"
            task = {
                "id": "video-passive",
                "artifact_dir": str(artifact_dir),
                "request": "old internal words mention LazyEdit publication",
                "route_decision": {
                    "route_kind": "file_download_or_save",
                    "passive_video_intake": True,
                    "public_publish_allowed": False,
                },
                "source": {"local_id": 64, "local_type": 43},
            }

            self.assertEqual(
                worker.nonpublish_video_preflight_dest(task),
                artifact_dir / "source_media",
            )
            cached = worker.copy_exact_video_artifact_to_private_cache(source, task)
            self.assertEqual(cached.parent, artifact_dir / "source_media")
            self.assertEqual(cached.read_bytes(), source.read_bytes())
            with self.assertRaisesRegex(RuntimeError, "cannot write to AutoPublish"):
                worker.copy_exact_video_artifact_to_autopublish(source, task)

    def test_passive_video_intake_missing_source_retries_without_chat_message(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {
                "route_kind": "file_download_or_save",
                "passive_video_intake": True,
                "public_publish_allowed": False,
            },
            "source": {"local_id": 64, "local_type": 43},
            "preflight": {
                "autopublish_video": {
                    "ok": False,
                    "error": "exact source video is not cached",
                    "message_local_ids": [64],
                    "message_refs": ["message_1.db:64"],
                }
            },
        }

        raw = worker.deterministic_preflight_result(task)
        result = worker.parse_worker_result(raw or "")
        worker.apply_send_outcome(task, result, [])

        self.assertTrue(result["no_reply"])
        self.assertEqual(task["status"], worker.EXISTING_VIDEO_PUBLISH_PENDING_STATUS)
        self.assertEqual(task["existing_video_publish_poststage"]["message_local_ids"], [64])
        self.assertTrue(task["existing_video_publish_poststage"]["passive_video_intake"])

    def test_worker_merges_consecutive_research_followup_into_active_session(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-201",
                        "chat": "LabAgent",
                        "status": worker.CLAIMED_STATUS,
                        "request": "Current coalesced request:\nCompare organoids and optical phenotyping.",
                        "route_decision": {"route_kind": "research_or_summary"},
                        "execution_contract": {"transport": "wecom"},
                        "source": {"message_table": "MSG", "sender_userid": "chen", "server_id": "srv-201", "local_id": 201},
                    },
                    {
                        "id": "research-202",
                        "chat": "LabAgent",
                        "status": "pending",
                        "request": "Current coalesced request:\nNow find a simpler direct quantitative biology tool.",
                        "route_decision": {"route_kind": "research_or_summary"},
                        "execution_contract": {"transport": "wecom"},
                        "source": {"message_table": "MSG", "sender_userid": "chen", "server_id": "srv-202", "local_id": 202},
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 1)
        self.assertTrue(tasks[0]["interruption_pending"])
        self.assertIn("simpler direct quantitative biology tool", tasks[0]["request"])
        self.assertEqual(tasks[1]["status"], "canceled_superseded")

    def test_worker_keeps_member_scoped_scheduled_daily_jobs_independent(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            base = {
                "chat": "LabAgent",
                "status": "pending",
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "scheduled_daily_research": True,
                    "serialized_daily_job": True,
                },
                "execution_contract": {"transport": "wecom"},
            }
            worker.write_tasks(
                queue,
                [
                    {
                        **base,
                        "id": "daily-member-a",
                        "request": "Research member A's topic.",
                        "source": {
                            "sender": "labcanvas-daily-scheduler",
                            "kind": "scheduled_daily_research",
                            "local_id": 101,
                            "member_key": "member-a",
                        },
                        "daily_research": {
                            "job_key": "job-a",
                            "member_key": "member-a",
                            "serialized": True,
                        },
                    },
                    {
                        **base,
                        "id": "daily-member-b",
                        "request": "Research member B's topic.",
                        "source": {
                            "sender": "labcanvas-daily-scheduler",
                            "kind": "scheduled_daily_research",
                            "local_id": 102,
                            "member_key": "member-b",
                        },
                        "daily_research": {
                            "job_key": "job-b",
                            "member_key": "member-b",
                            "serialized": True,
                        },
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 0)
        self.assertEqual([task["status"] for task in tasks], ["pending", "pending"])

    def test_worker_preserves_and_reads_wecom_pdf_from_merged_interruption(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper.pdf"
            paper.write_bytes(b"%PDF-1.4\nexact attachment")
            queue = root / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-301",
                        "chat": "LabAgent",
                        "status": worker.CLAIMED_STATUS,
                        "request": "Can this measurement become fully optical?",
                        "route_decision": {"route_kind": "research_or_summary"},
                        "execution_contract": {"transport": "wecom"},
                        "source": {
                            "sender": "member-a",
                            "server_id": "srv-301",
                            "local_id": 301,
                        },
                    },
                    {
                        "id": "research-302",
                        "chat": "LabAgent",
                        "status": "pending",
                        "request": "[file] paper.pdf",
                        "route_decision": {"route_kind": "file_intake"},
                        "execution_contract": {"transport": "wecom"},
                        "source": {
                            "sender": "member-a",
                            "server_id": "srv-302",
                            "local_id": 302,
                            "sender_display": "Member A",
                        },
                        "transport_preflight": {
                            "wecom_media": {
                                "status": "ready",
                                "source_transport": "wecom_android",
                                "copied": [
                                    {
                                        "kind": "document",
                                        "filename": "paper.pdf",
                                        "path": str(paper),
                                        "task_copy_path": str(paper),
                                        "sha256": "exact-paper-sha",
                                    }
                                ],
                            }
                        },
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)
            document_read = {
                "status": "readable",
                "agent_context_path": str(root / "agent-context.md"),
            }
            with mock.patch.object(
                worker,
                "analyze_document",
                return_value=document_read,
            ) as reader:
                preflight = worker.prepare_worker_preflight(tasks[0], root / "task")

        self.assertEqual(merged, 1)
        self.assertEqual(tasks[1]["status"], "canceled_superseded")
        self.assertIn("transport_preflight", tasks[0]["interruptions"][0])
        copied = preflight["wecom_media"]["copied"][0]
        self.assertEqual(copied["task_copy_path"], str(paper))
        self.assertEqual(copied["document_read"], document_read)
        self.assertEqual(copied["interruption_source"]["server_id"], "srv-302")
        reader.assert_called_once()

    def test_worker_promotes_story_row_when_followup_confirms_video_generation(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            story_file = tmp_path / "approved-story.md"
            story_file.write_text("# Story\n\nAyaChan compares Uma Gumi and konnyaku.", encoding="utf-8")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-201",
                        "chat": "懒人科研",
                        "status": "waiting_confirmation",
                        "created_at": "2026-06-25T21:10:00",
                        "request": "Current coalesced request:\nWrite the story first.",
                        "route_decision": {"route_kind": "story_or_script", "project": "lalachan", "public_publish_allowed": False},
                        "source": {"message_table": "MSG", "server_id": "srv-201", "local_id": 201},
                        "routine": {"id": "story_script_generation"},
                        "story_confirmation_required": True,
                        "generation_blocked_until_story_confirmed": True,
                        "sent_file_paths": [str(story_file)],
                    },
                    {
                        "id": "task-202",
                        "chat": "懒人科研",
                        "status": "pending",
                        "created_at": "2026-06-25T21:12:00",
                        "request": "Current coalesced request:\nstory ok generate video now",
                        "route_decision": {"route_kind": "generate_video", "project": "lalachan", "public_publish_allowed": False},
                        "source": {"message_table": "MSG", "server_id": "srv-202", "local_id": 202},
                        "routine": {"id": "generated_video"},
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 1)
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[0]["route_decision"]["route_kind"], "generate_video")
        self.assertEqual(tasks[0]["routine"]["id"], "generated_video")
        self.assertFalse(tasks[0]["story_confirmation_required"])
        self.assertFalse(tasks[0]["generation_blocked_until_story_confirmed"])
        self.assertEqual(tasks[0]["approved_story_files"], [str(story_file)])
        self.assertIn("Uma Gumi and konnyaku", tasks[0]["approved_story_message"])
        self.assertEqual(tasks[0]["stage_transition"]["reason"], "same_chat_generation_confirmation")
        self.assertEqual(tasks[1]["status"], "canceled_superseded")

    def test_worker_does_not_merge_story_followup_into_days_old_video_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-video-task",
                        "chat": "懒人科研",
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "created_at": "2026-06-23T00:10:12",
                        "request": "Current coalesced request:\nGenerate an old RaraXia video.",
                        "route_decision": {"route_kind": "generate_video", "project": "lalachan"},
                        "source": {"message_table": "MSG", "server_id": "srv-93", "local_id": 93},
                        "routine": {"id": "generated_video"},
                    },
                    {
                        "id": "new-story-task",
                        "chat": "懒人科研",
                        "status": "pending",
                        "created_at": "2026-06-25T21:16:21",
                        "request": "Current coalesced request:\nWrite the new story from today's group messages.",
                        "route_decision": {"route_kind": "story_or_script", "project": "lalachan"},
                        "source": {"message_table": "MSG", "server_id": "srv-206", "local_id": 206},
                        "routine": {"id": "story_script_generation"},
                    },
                ],
            )

            merged = worker.merge_existing_pending_interruptions(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(merged, 0)
        self.assertEqual(tasks[0]["status"], worker.GENERATED_VIDEO_WAITING_STATUS)
        self.assertEqual(tasks[1]["status"], "pending")
        self.assertNotIn("interruptions", tasks[0])

    def test_worker_suppresses_stale_result_when_interruption_arrived(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-201",
                        "chat": "懒人科研",
                        "status": worker.CLAIMED_STATUS,
                        "worker_id": "pid:999999",
                        "claimed_at": "2026-06-25T21:00:00",
                        "interruption_pending": True,
                        "last_interruption_at": "2026-06-25T21:01:00",
                        "request": "Current coalesced request:\nGenerate a RaraXia video.",
                        "route_decision": {"route_kind": "generate_video", "project": "lalachan"},
                    }
                ],
            )

            suppressed = worker.requeue_if_task_interrupted_during_run(
                queue,
                {"id": "task-201", "claimed_at": "2026-06-25T21:00:00", "worker_id": "pid:999999"},
            )
            stored = worker.read_tasks(queue)[0]

        self.assertTrue(suppressed)
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["reprocess_reason"], "interruption_arrived_during_worker_turn")
        self.assertIn("stale_result_suppressed_at", stored)

    def test_worker_allows_result_when_pending_interruption_was_already_claimed(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-201",
                        "chat": "懒人科研",
                        "status": worker.CLAIMED_STATUS,
                        "worker_id": "pid:999999",
                        "claimed_at": "2026-06-25T21:02:00",
                        "interruption_pending": True,
                        "interruption_count": 1,
                        "last_interruption_at": "2026-06-25T21:01:00",
                        "request": "Current coalesced request:\nGenerate a RaraXia video.",
                        "route_decision": {"route_kind": "generate_video", "project": "lalachan"},
                    }
                ],
            )
            claimed_task = {
                "id": "task-201",
                "claimed_at": "2026-06-25T21:02:00",
                "worker_id": "pid:999999",
                "interruption_pending": True,
            }

            suppressed = worker.requeue_if_task_interrupted_during_run(queue, claimed_task)
            stored = worker.read_tasks(queue)[0]

        self.assertFalse(suppressed)
        self.assertEqual(stored["status"], worker.CLAIMED_STATUS)
        self.assertFalse(claimed_task["interruption_pending"])
        self.assertEqual(claimed_task["interruption_handled_count"], 1)

    def test_generated_video_stage_permissions_allow_requested_publish_platforms_only(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
            "request": (
                "Current coalesced request:\n"
                "Generate the video and publish to SPH only.\n\n"
                "Recent history:\n"
                "old message mentioned YouTube and Instagram"
            ),
        }

        stages = worker.generated_video_stage_permissions(task)

        self.assertTrue(stages["lazyedit_import"])
        self.assertTrue(stages["public_publish"])
        self.assertTrue(stages["publication"])
        self.assertFalse(stages["generation_is_publication"])
        self.assertEqual(stages["publish_platforms"], ["shipinhao"])

    def test_generated_video_waiting_task_reclaims_only_after_poll_time(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-video",
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "generation_wait_count": 1,
                        "next_poll_at": 9999999999,
                    }
                ],
            )
            self.assertIsNone(worker.claim_next_pending(queue))
            rows = worker.read_tasks(queue)
            rows[0]["next_poll_at"] = 0
            worker.write_tasks(queue, rows)
            claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.CLAIMED_STATUS)
        self.assertEqual(claimed["generation_poll_history"][0]["wait_count"], 1)

    def test_claim_next_pending_prefers_fresh_pending_over_due_video_poll(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-video-poll",
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "generation_wait_count": 30,
                        "next_poll_at": 0,
                    },
                    {
                        "id": "fresh-message",
                        "status": "pending",
                        "created_at": "2026-06-23T08:00:00",
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "fresh-message")

    def test_stale_generated_video_wait_is_paused_not_reopened(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "ancient-video",
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "generation_wait_count": 30,
                        "next_poll_at": 0,
                        "created_at": "2026-06-22T00:00:00",
                        "route_decision": {"route_kind": "generate_video"},
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)

            rows = worker.read_tasks(queue)
        self.assertIsNone(claimed)
        self.assertEqual(rows[0]["status"], worker.GENERATED_VIDEO_STALE_PAUSED_STATUS)
        self.assertEqual(rows[0]["generation_pause_reason"], "stale_generated_video_wait_exceeded")

    def test_generated_video_monitor_download_result_returns_mp4(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            video = tmp_path / "task-video.mp4"
            video.write_bytes(b"video")
            task = {
                "id": "task-video",
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nCould you generate the video?",
            }
            monitor = {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
                "output_dir": str(tmp_path),
                "filename": "task-video.mp4",
            }

            with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                with mock.patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess(["watcher"], 0, f"DONE output={video}\n", "")):
                    raw = worker.run_generated_video_monitor(task, monitor)

        payload = json.loads(raw)
        self.assertIn("下载完成", payload["message"])
        self.assertEqual(payload["files"], [str(video.resolve())])

    def test_generated_video_monitor_uses_short_probe_cycle(self) -> None:
        worker = load_worker()
        captured: dict[str, object] = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(command, 1, "still running", "")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            task = {
                "id": "task-video",
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nCould you generate a 30s video?",
            }
            monitor = {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
                "output_dir": str(tmp_path),
                "filename": "task-video.mp4",
            }

            with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                    worker.run_generated_video_monitor(task, monitor)

        command = captured["command"]
        assert isinstance(command, list)
        self.assertEqual(command[command.index("--interval") + 1], "30")
        self.assertEqual(command[command.index("--max-polls") + 1], "1")
        self.assertLessEqual(int(captured["timeout"]), 60)

    def test_generated_video_monitor_credit_block_returns_confirmation(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            task = {
                "id": "task-video",
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nCould you generate a 30s video?",
            }
            monitor = {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
                "output_dir": str(tmp_path),
                "filename": "task-video.mp4",
            }

            with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                with mock.patch.object(
                    worker.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(["watcher"], 43, "blocking status seen; 积分不足", ""),
                ):
                    raw = worker.run_generated_video_monitor(task, monitor)

        payload = json.loads(raw)
        self.assertIn("积分不足", payload["message"])
        self.assertIn("积分不足", payload["confirmation"])
        self.assertEqual(payload["data"]["generated_video_blocker"]["kind"], "insufficient_credits")

    def test_generated_video_completed_artifact_overrides_later_credit_text(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc",
                        "status": ["积分不足", "积分不足", "完成"],
                        "tail": (
                            "生成分镜视频\n哎呀，积分不足\n"
                            "任务\n6\n渲染合成最终视频 (render_video)\n已完成\n"
                            "视频\n共 4 个\n生成结果\n1\nMP4\nfinal_video.mp4\n下载"
                        ),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = {
                "id": "task-video",
                "artifact_dir": str(tmp_path),
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "task-video.mp4",
                },
            }

            status = worker.inspect_generated_video_status(task)

        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "download_ready")
        self.assertIn("final_video.mp4", status["status_text"])

    def test_generated_video_monitor_credit_with_completed_artifact_requeues_download(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            (tmp_path / "watch_001.json").write_text(
                json.dumps(
                    {
                        "href": "https://xyq.jianying.com/home?thread_id=abc",
                        "status": ["积分不足", "完成"],
                        "tail": "渲染合成最终视频 (render_video)\n已完成\n视频\n共 4 个\n生成结果\n1\nMP4\nfinal_video.mp4",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = {
                "id": "task-video",
                "artifact_dir": str(tmp_path),
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nGenerate the video and send it back.",
            }
            monitor = {
                "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                "page_id": "PAGE123456",
                "output_dir": str(tmp_path),
                "filename": "task-video.mp4",
            }

            with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                with mock.patch.object(
                    worker.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(["watcher"], 43, "blocking status seen; 积分不足", ""),
                ):
                    raw = worker.run_generated_video_monitor(task, monitor)

        payload = json.loads(raw)
        self.assertEqual(payload["confirmation"], "")
        self.assertIn("final_video.mp4", payload["message"])
        self.assertTrue(payload["data"]["generated_video_download_ready"])
        self.assertTrue(worker.generated_video_result_is_nonterminal(task, payload))

    def test_existing_generated_video_file_returns_artifact_without_new_paid_action(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "generated.mp4"
            video.write_bytes(b"generated-video")
            task = {
                "id": "task-video-existing",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "route_decision": {
                    "route_kind": "generate_video",
                    "public_publish_allowed": False,
                    "no_new_xyq_submit": True,
                },
                "request": "Current coalesced request:\nGive me the generated video.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "generated.mp4",
                    "monitor_only_no_resubmit": True,
                },
                "credit_guard": {"enabled": True},
            }

            with mock.patch.object(worker, "generated_video_output_verification", return_value={"ok": True}):
                raw = worker.deterministic_existing_generated_video_file_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(payload["files"], [str(video.resolve())])
        self.assertTrue(payload["data"]["require_file_delivery"])
        self.assertEqual(payload["data"]["existing_generated_video_artifact"]["status"], "found")
        self.assertIn("不会重新提交", payload["message"])

    def test_preflight_prefers_existing_generated_video_before_continue_monitor_or_submit(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "generated.mp4"
            video.write_bytes(b"generated-video")
            task = {
                "id": "task-video-existing-preflight",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "route_decision": {
                    "route_kind": "generate_video",
                    "public_publish_allowed": False,
                    "monitor_only_no_resubmit": True,
                },
                "request": "Current coalesced request:\nThe video generated already; send it here.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "generated.mp4",
                },
                "generation_wait_count": 1,
            }

            with mock.patch.object(worker, "generated_video_output_verification", return_value={"ok": True}):
                with mock.patch.object(worker, "deterministic_generated_video_continue_result", side_effect=AssertionError("continue should not run")):
                    with mock.patch.object(worker, "deterministic_generated_video_monitor_result", side_effect=AssertionError("monitor should not run")):
                        with mock.patch.object(worker, "deterministic_generated_video_submit_result", side_effect=AssertionError("submit should not run")):
                            raw = worker.deterministic_preflight_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(payload["files"], [str(video.resolve())])
        self.assertIn("不会重新提交", payload["message"])

    def test_generation_waiting_resume_downloads_then_queues_requested_lazyedit_after_send(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_lazyedit(video_path: Path, task: dict[str, object], monitor: dict[str, object], *, publish: bool) -> dict[str, object]:
            calls.append({"video_path": video_path, "task": task, "monitor": monitor, "publish": publish})
            return {"ok": True, "status": "done"}

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            video = tmp_path / "generated.mp4"
            video.write_bytes(b"video")
            task = {
                "id": "task-video",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "claim_history": [{"status": worker.GENERATED_VIDEO_WAITING_STATUS}],
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nGenerate the video, upload it to LazyEdit only, and send the MP4 back.",
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "generated.mp4",
                },
            }

            original = worker.run_generated_video_lazyedit_command
            worker.run_generated_video_lazyedit_command = fake_lazyedit

            try:
                with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                    with mock.patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess(["watcher"], 0, f"DONE output={video}\n", "")):
                        raw = worker.deterministic_generated_video_monitor_result(task)

                self.assertIsNotNone(raw)
                payload = json.loads(raw or "{}")
                self.assertIn("已排队", payload["message"])
                self.assertIn("LazyEdit import/process", payload["message"])
                self.assertEqual(payload["files"], [str(video.resolve())])
                self.assertEqual(calls, [])

                result = worker.parse_worker_result(raw or "")
                result = worker.prepare_result_files(result, raw or "")
                worker.apply_send_outcome(task, result, [])

                self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
                self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery_before_poststage")

                task["sent_file_paths"] = [str(video.resolve())]
                worker.apply_send_outcome(task, result, [])
                self.assertEqual(task["status"], worker.GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS)
                self.assertEqual(task["generated_video_poststage"]["video_path"], str(video.resolve()))
                self.assertFalse(task["generated_video_poststage"]["publish"])

                task["status"] = worker.CLAIMED_STATUS
                raw_poststage = worker.deterministic_generated_video_poststage_result(task)
            finally:
                worker.run_generated_video_lazyedit_command = original

        self.assertIsNotNone(raw_poststage)
        poststage_payload = json.loads(raw_poststage or "{}")
        self.assertIn("LazyEdit import/process 后续阶段", poststage_payload["message"])
        self.assertEqual(calls[0]["video_path"], video.resolve())
        self.assertFalse(calls[0]["publish"])

    def test_generation_waiting_resume_downloads_then_queues_requested_publish_after_send(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_lazyedit(video_path: Path, task: dict[str, object], monitor: dict[str, object], *, publish: bool) -> dict[str, object]:
            calls.append({"video_path": video_path, "task": task, "monitor": monitor, "publish": publish})
            return {"ok": True, "status": "done", "platforms": worker.detect_publish_platforms(task, current_only=True)}

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            watcher = tmp_path / "watch_thread_dom_download.py"
            watcher.write_text("# watcher", encoding="utf-8")
            video = tmp_path / "generated.mp4"
            video.write_bytes(b"video")
            task = {
                "id": "task-video-publish",
                "status": worker.CLAIMED_STATUS,
                "artifact_dir": str(tmp_path),
                "claim_history": [{"status": worker.GENERATED_VIDEO_WAITING_STATUS}],
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
                "request": (
                    "Current coalesced request:\n"
                    "Generate the video, send it back here, and publish to SPH Ins y2b.\n\n"
                    "Recent history:\nold message mentioned only YouTube"
                ),
                "generated_video_monitor": {
                    "thread_url": "https://xyq.jianying.com/home?thread_id=abc",
                    "page_id": "PAGE123456",
                    "output_dir": str(tmp_path),
                    "filename": "generated.mp4",
                },
            }

            original = worker.run_generated_video_lazyedit_command
            worker.run_generated_video_lazyedit_command = fake_lazyedit

            try:
                with mock.patch.object(worker, "generated_video_watcher_script", return_value=watcher):
                    with mock.patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess(["watcher"], 0, f"DONE output={video}\n", "")):
                        raw = worker.deterministic_generated_video_monitor_result(task)

                self.assertIsNotNone(raw)
                payload = json.loads(raw or "{}")
                self.assertIn("已排队", payload["message"])
                self.assertIn("LazyEdit 并发布", payload["message"])
                self.assertEqual(payload["files"], [str(video.resolve())])
                self.assertEqual(calls, [])

                result = worker.parse_worker_result(raw or "")
                result = worker.prepare_result_files(result, raw or "")
                worker.apply_send_outcome(task, result, [])

                self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
                self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery_before_poststage")

                task["sent_file_paths"] = [str(video.resolve())]
                worker.apply_send_outcome(task, result, [])
                self.assertEqual(task["status"], worker.GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS)
                self.assertEqual(task["generated_video_poststage"]["video_path"], str(video.resolve()))
                self.assertTrue(task["generated_video_poststage"]["publish"])
                self.assertEqual(task["generated_video_poststage"]["platforms"], ["shipinhao", "youtube", "instagram"])

                task["status"] = worker.CLAIMED_STATUS
                raw_poststage = worker.deterministic_generated_video_poststage_result(task)
            finally:
                worker.run_generated_video_lazyedit_command = original

        self.assertIsNotNone(raw_poststage)
        poststage_payload = json.loads(raw_poststage or "{}")
        self.assertIn("LazyEdit/public publish 后续阶段", poststage_payload["message"])
        self.assertEqual(calls[0]["video_path"], video.resolve())
        self.assertTrue(calls[0]["publish"])
        self.assertEqual(worker.detect_publish_platforms(calls[0]["task"], current_only=True), ["shipinhao", "youtube", "instagram"])

    def test_generated_video_poststage_task_reclaims_after_artifact_delivery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            video = Path(tmp) / "generated.mp4"
            video.write_bytes(b"video")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-video-poststage",
                        "status": worker.GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS,
                        "poststage_queued_at": "2026-01-01T00:00:00",
                        "next_poststage_at": 0,
                        "generated_video_poststage": {
                            "kind": "lazyedit_import",
                            "video_path": str(video),
                            "publish": False,
                        },
                    }
                ],
            )
            claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.CLAIMED_STATUS)
        self.assertEqual(claimed["poststage_history"][0]["kind"], "lazyedit_import")

    def test_generated_video_poststage_timeout_requeues_without_completion(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "generated.mp4"
            video.write_bytes(b"video")
            task = {
                "id": "task-video-poststage-timeout",
                "status": worker.CLAIMED_STATUS,
                "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                "request": "Current coalesced request:\nGenerate the video and upload it to LazyEdit only.",
                "generated_video_poststage": {
                    "kind": "lazyedit_import",
                    "video_path": str(video),
                    "publish": False,
                    "monitor": {},
                },
            }

            original = worker.run_generated_video_lazyedit_command
            try:
                worker.run_generated_video_lazyedit_command = lambda *_args, **_kwargs: {"ok": False, "status": "timeout"}
                raw = worker.deterministic_generated_video_poststage_result(task)
            finally:
                worker.run_generated_video_lazyedit_command = original

            result = worker.parse_worker_result(raw or "")
            worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], worker.GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS)
        self.assertEqual(task["poststage_last_status"], "timeout")
        self.assertIn("next_poststage_at", task)

    def test_generated_video_final_mp4_is_sent_before_done_message(self) -> None:
        worker = load_worker()
        calls: list[tuple[str, str]] = []
        original_message = worker.send_message
        original_file = worker.send_file
        try:
            worker.send_message = lambda message, *_args, **_kwargs: calls.append(("message", str(message)))
            worker.send_file = lambda file_path, *_args, **_kwargs: calls.append(("file", str(Path(file_path).resolve())))
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "generated.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nCould you generate the video?",
                }
                errors = worker.send_result_with_retries(
                    {"message": "done", "confirmation": "", "files": [str(mp4)]},
                    "🍓我的设备",
                    targets,
                    task=task,
                )
        finally:
            worker.send_message = original_message
            worker.send_file = original_file

        self.assertEqual(errors, [])
        self.assertEqual(calls[0][0], "file")
        self.assertEqual(calls[1], ("message", "done"))
        self.assertIn("generated.mp4", "\n".join(task["sent_file_paths"]))

    def test_generated_video_mp4_send_failure_keeps_task_send_failed(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        original_message = worker.send_message
        original_file = worker.send_file
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(str(message))

            def fail_file(*_args, **_kwargs):
                raise RuntimeError("file picker unavailable")

            worker.send_file = fail_file
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "generated.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nCould you generate the video?",
                }
                result = {"message": "done", "confirmation": "", "files": [str(mp4)]}
                errors = worker.send_result_with_retries(result, "🍓我的设备", targets, task=task)
                worker.apply_send_outcome(task, result, errors)
        finally:
            worker.send_message = original_message
            worker.send_file = original_file
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertTrue(errors)
        self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery")
        self.assertEqual(messages, [])
        self.assertIn("file_send_errors", task)

    def test_non_generated_video_mp4_send_failure_blocks_text_only_completion(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        original_message = worker.send_message
        original_file = worker.send_file
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(str(message))

            def fail_file(*_args, **_kwargs):
                raise RuntimeError("file picker unavailable")

            worker.send_file = fail_file
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "saved-video.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "file_download_or_save", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nSend me the saved video.",
                }
                result = {"message": "done", "confirmation": "", "files": [str(mp4)]}
                errors = worker.send_result_with_retries(result, "🍓我的设备", targets, task=task)
                worker.apply_send_outcome(task, result, errors)
        finally:
            worker.send_message = original_message
            worker.send_file = original_file
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertTrue(errors)
        self.assertEqual(messages, [])
        self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery")

    def test_non_generated_video_mp4_send_success_records_required_delivery(self) -> None:
        worker = load_worker()
        calls: list[tuple[str, str]] = []
        original_message = worker.send_message
        original_file = worker.send_file
        try:
            worker.send_message = lambda message, *_args, **_kwargs: calls.append(("message", str(message)))
            worker.send_file = lambda file_path, *_args, **_kwargs: calls.append(("file", str(Path(file_path).resolve())))
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "saved-video.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "file_download_or_save", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nSend me the saved video.",
                }
                result = {"message": "done", "confirmation": "", "files": [str(mp4)]}
                errors = worker.send_result_with_retries(result, "🍓我的设备", targets, task=task)
                worker.apply_send_outcome(task, result, errors)
        finally:
            worker.send_message = original_message
            worker.send_file = original_file

        self.assertEqual(errors, [])
        self.assertEqual(calls[0][0], "file")
        self.assertEqual(calls[1], ("message", "done"))
        self.assertEqual(task["status"], "done")
        self.assertIn("saved-video.mp4", "\n".join(task["sent_file_paths"]))

    def test_real_mp4_exact_chat_sender_failure_blocks_required_delivery(self) -> None:
        worker = load_worker()
        original_sender = worker.run_android_wechat_sender
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"

            def fail_sender(*_args, **_kwargs):
                raise RuntimeError("exact-chat file sender failed with exit 1")

            worker.run_android_wechat_sender = fail_sender
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "sender-failed.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "file_download_or_save", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nSend me the saved video.",
                }
                result = {"message": "done", "confirmation": "", "files": [str(mp4)]}
                errors = worker.send_result_with_retries(result, "🍓我的设备", targets, task=task)
                worker.apply_send_outcome(task, result, errors)
        finally:
            worker.run_android_wechat_sender = original_sender
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertTrue(errors)
        self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery")
        self.assertNotIn("sent_file_paths", task)
        self.assertIn("file_send_errors", task)

    def test_guarded_file_send_is_one_exact_chat_transaction(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        bridge_calls: list[list[str]] = []
        original_sender = worker.run_android_wechat_sender
        original_bridge = worker.run_file_bridge_subprocess
        original_record = worker.record_event
        try:
            worker.run_android_wechat_sender = lambda **kwargs: calls.append(kwargs) or {"ok": True}
            worker.run_file_bridge_subprocess = lambda command, **_kwargs: bridge_calls.append(command)
            worker.record_event = lambda **_kwargs: None
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                report = tmp_path / "daily-report.pdf"
                report.write_bytes(b"%PDF-1.4\n")
                target = {
                    "name": "写作 外语 挣钱",
                    "query": "写作 外语 挣钱",
                    "expected_title": "写作 外语 挣钱",
                    "allow_search": False,
                }
                worker.send_file(
                    report,
                    "写作 外语 挣钱",
                    tmp_path / "unused.json",
                    target=target,
                )
        finally:
            worker.run_android_wechat_sender = original_sender
            worker.run_file_bridge_subprocess = original_bridge
            worker.record_event = original_record

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["chat"], "写作 外语 挣钱")
        self.assertEqual(calls[0]["files"], [report])
        self.assertTrue(str(calls[0]["task_id"]).startswith("adhoc-"))
        self.assertEqual(bridge_calls, [])

    def test_android_title_guard_file_send_falls_back_to_exact_desktop_transaction(self) -> None:
        worker = load_worker()
        desktop_calls: list[tuple[Path, dict[str, object]]] = []
        events: list[dict[str, object]] = []
        original_android = worker.run_android_wechat_sender
        original_desktop = worker.run_desktop_wechat_file_sender
        original_record = worker.record_event
        try:
            worker.run_android_wechat_sender = mock.Mock(
                side_effect=RuntimeError(
                    "WECHAT_ANDROID_SEND_FAILED: ANDROID_WECHAT_TITLE_GUARD: "
                    "exact target 'EchoMind' was not found"
                )
            )
            worker.run_desktop_wechat_file_sender = (
                lambda path, target: desktop_calls.append((path, target))
            )
            worker.record_event = lambda **kwargs: events.append(kwargs)
            with tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "echomind-daily-review.pdf"
                report.write_bytes(b"%PDF-1.4\n")
                target = {
                    "name": "EchoMind",
                    "query": "EchoMind",
                    "expected_title": "EchoMind",
                    "allow_search": True,
                }
                worker.send_file(
                    report,
                    "EchoMind",
                    Path(tmp) / "unused.json",
                    target=target,
                )
        finally:
            worker.run_android_wechat_sender = original_android
            worker.run_desktop_wechat_file_sender = original_desktop
            worker.record_event = original_record

        self.assertEqual(desktop_calls, [(report, target)])
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["metadata"]["transport"],
            "wechat_gui_after_android_preflight_failure",
        )

    def test_android_uncertain_file_send_failure_does_not_fallback(self) -> None:
        worker = load_worker()
        original_android = worker.run_android_wechat_sender
        original_desktop = worker.run_desktop_wechat_file_sender
        try:
            worker.run_android_wechat_sender = mock.Mock(
                side_effect=RuntimeError("WECHAT_ANDROID_SEND_TIMEOUT")
            )
            worker.run_desktop_wechat_file_sender = mock.Mock()
            with tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "report.pdf"
                report.write_bytes(b"%PDF-1.4\n")
                with self.assertRaisesRegex(RuntimeError, "ANDROID_SEND_TIMEOUT"):
                    worker.send_file(
                        report,
                        "EchoMind",
                        Path(tmp) / "unused.json",
                        target={"name": "EchoMind", "expected_title": "EchoMind"},
                    )
        finally:
            desktop = worker.run_desktop_wechat_file_sender
            worker.run_android_wechat_sender = original_android
            worker.run_desktop_wechat_file_sender = original_desktop

        desktop.assert_not_called()

    def test_chat_visible_text_never_exposes_local_artifact_paths(self) -> None:
        worker = load_worker()
        report = Path("/home/lachlan/ProjectsLFS/AgenticApp/output/report.pdf")
        source = Path("/home/lachlan/Nutstore Files/private notes/source.md")

        message = worker.message_with_saved_file_note(
            f"Report: {report}\nSource: {source}",
            [source],
        )

        self.assertNotIn("/home/", message)
        self.assertNotIn("ProjectsLFS", message)
        self.assertNotIn("Nutstore Files", message)
        self.assertIn("report.pdf", message)
        self.assertIn("source.md", message)
        unknown = worker.sanitize_chat_visible_text(
            "Report: /home/lachlan/Nutstore Files/private notes/unknown report.pdf 已完成"
        )
        self.assertEqual(unknown, "Report: unknown report.pdf 已完成")

    def test_chat_visible_text_uses_meaningful_delivery_alias(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            source = artifact_dir / "report-final.pdf"
            source.write_bytes(b"%PDF-1.4\norganoid evidence")
            task: dict[str, object] = {
                "id": "20260822124500-456",
                "chat": "LabAgent",
                "created_at": "2026-08-22T12:45:00+08:00",
                "request": "Create an organoid imaging biomarkers review.",
                "artifact_dir": str(artifact_dir),
            }
            prepared = worker.prepare_result_files(
                {
                    "message": f"Completed {source}; report-final.pdf is attached.",
                    "confirmation": "",
                    "files": [str(source)],
                },
                "",
                task=task,
            )
            delivery = Path(prepared["files"][0])

            visible = worker.sanitize_chat_visible_text(
                str(prepared["message"]),
                [delivery],
                task=task,
            )

        self.assertNotIn(str(source), visible)
        self.assertNotIn("report-final.pdf", visible)
        self.assertEqual(visible.count(delivery.name), 2)
        self.assertIn("organoid-imaging-biomarkers-review-report.pdf", visible)

        malformed_task = {
            "delivery_artifact_aliases": [{"display_name": "must-not-replace.pdf"}]
        }
        self.assertEqual(
            worker.sanitize_chat_visible_text("Sentence. Still intact.", task=malformed_task),
            "Sentence. Still intact.",
        )

    def test_chat_visible_text_removes_private_runtime_diagnostics(self) -> None:
        worker = load_worker()

        message = worker.sanitize_chat_visible_text(
            "研究报告已完成。\n"
            "未在本轮发送；deep_research/finish queue_orchestrator "
            "群 f8e5aa00112233445566 transport=wecom_android task_id=private-task\n"
            "PDF 已附上。"
        )

        self.assertEqual(message, "研究报告已完成。\nPDF 已附上。")
        self.assertNotIn("queue_orchestrator", message)
        self.assertNotIn("transport=", message)
        self.assertNotIn("f8e5aa", message)

    def test_file_bridge_unlocks_and_retries_when_wechat_locks(self) -> None:
        worker = load_worker()
        calls: list[list[str]] = []
        unlocks: list[str] = []
        original_run = worker.run_subprocess_group
        original_unlock = worker.unlock_wechat_for_file_send
        original_acquire = worker.acquire_gui_send_lock_or_raise
        original_release = worker.release_gui_send_lock
        original_delay = worker.os.environ.get("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY"] = "0"

            def fake_run(command: list[str], *, timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(command, 1, "", "WECHAT_LOCKED: Weixin for Linux is locked")
                return subprocess.CompletedProcess(command, 0, '{"status":"sent-file-submitted"}', "")

            worker.run_subprocess_group = fake_run
            worker.unlock_wechat_for_file_send = lambda: unlocks.append("unlock") or ""
            worker.acquire_gui_send_lock_or_raise = lambda: object()
            worker.release_gui_send_lock = lambda _lock: None

            worker.run_file_bridge_subprocess(["python", "bridge.py"], timeout=3)
        finally:
            worker.run_subprocess_group = original_run
            worker.unlock_wechat_for_file_send = original_unlock
            worker.acquire_gui_send_lock_or_raise = original_acquire
            worker.release_gui_send_lock = original_release
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY"] = original_delay

        self.assertEqual(len(calls), 2)
        self.assertEqual(unlocks, ["unlock"])

    def test_exact_chat_file_sender_unlocks_and_retries_when_wechat_locks(self) -> None:
        worker = load_worker()
        calls: list[list[str]] = []
        unlocks: list[str] = []
        original_send = worker.run_send_subprocess
        original_unlock = worker.unlock_wechat_for_file_send
        original_delay = worker.os.environ.get("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY"] = "0"

            def fake_send(command: list[str], timeout: int | None = None) -> None:
                calls.append(command)
                if len(calls) == 1:
                    raise RuntimeError("WECHAT_LOCKED: Weixin for Linux is locked")

            worker.run_send_subprocess = fake_send
            worker.unlock_wechat_for_file_send = lambda: unlocks.append("unlock") or ""
            worker.run_exact_chat_file_sender(["python", "wechat_gui_send.py", "--file", "report.pdf"])
        finally:
            worker.run_send_subprocess = original_send
            worker.unlock_wechat_for_file_send = original_unlock
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY"] = original_delay

        self.assertEqual(len(calls), 2)
        self.assertEqual(unlocks, ["unlock"])

    def test_unlock_serial_loads_ignored_supervisor_config(self) -> None:
        worker = load_worker()
        original_private = worker.PRIVATE
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            (private / "wechat_supervisor.local.env").write_text(
                "export WECHAT_UNLOCK_ADB_SERIAL='physical-device'\n",
                encoding="utf-8",
            )
            worker.PRIVATE = private
            with mock.patch.dict(
                worker.os.environ,
                {
                    "WECHAT_UNLOCK_ADB_SERIAL": "",
                    "ANDROID_SERIAL": "",
                },
                clear=False,
            ):
                try:
                    serial = worker.configured_wechat_unlock_serial()
                finally:
                    worker.PRIVATE = original_private

        self.assertEqual(serial, "physical-device")

    def test_mp4_sent_then_text_lock_stays_deferred(self) -> None:
        worker = load_worker()
        original_message = worker.send_message
        original_file = worker.send_file
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"

            def fail_message(*_args, **_kwargs):
                raise RuntimeError("WECHAT_LOCKED: Weixin for Linux is locked")

            worker.send_message = fail_message
            worker.send_file = lambda *_args, **_kwargs: None
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "sent-before-lock.mp4"
                mp4.write_bytes(b"video")
                targets = tmp_path / "targets.json"
                targets.write_text(
                    json.dumps({"🍓我的设备": {"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"}}, ensure_ascii=False),
                    encoding="utf-8",
                )
                task = {
                    "chat": "🍓我的设备",
                    "route_decision": {"route_kind": "file_download_or_save", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nSend me the saved video.",
                }
                result = {"message": "done", "confirmation": "", "files": [str(mp4)]}
                errors = worker.send_result_with_retries(result, "🍓我的设备", targets, task=task)
                worker.apply_send_outcome(task, result, errors)
        finally:
            worker.send_message = original_message
            worker.send_file = original_file
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertTrue(errors)
        self.assertEqual(task["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertIn("sent-before-lock.mp4", "\n".join(task["sent_file_paths"]))
        self.assertIn("post_artifact_send_errors", task)
        self.assertEqual(task["send_deferred_reason"], "wechat_locked")

    def test_lazyedit_import_is_not_public_publish_intent(self) -> None:
        worker = load_worker()

        self.assertFalse(worker.has_public_publish_intent("upload the generated video to LazyEdit only"))
        self.assertTrue(worker.wants_lazyedit_import("upload the generated video to LazyEdit only"))
        self.assertTrue(worker.has_public_publish_intent("publish the generated video to YouTube"))

    def test_generated_video_lazyedit_stage_separates_import_from_public_publish(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_lazyedit(video_path: Path, task: dict[str, object], monitor: dict[str, object], *, publish: bool) -> dict[str, object]:
            calls.append({"video_path": video_path, "publish": publish, "task": task, "monitor": monitor})
            return {"ok": True, "status": "done"}

        original = worker.run_generated_video_lazyedit_command
        try:
            worker.run_generated_video_lazyedit_command = fake_lazyedit
            import_msg = worker.maybe_run_generated_video_lazyedit_stage(
                Path("/tmp/generated.mp4"),
                {
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": False},
                    "request": "Current coalesced request:\nupload the generated video to LazyEdit only",
                },
                {},
            )
            publish_msg = worker.maybe_run_generated_video_lazyedit_stage(
                Path("/tmp/generated.mp4"),
                {
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
                    "request": "Current coalesced request:\npublish the generated video to SPH Ins y2b",
                },
                {},
            )
        finally:
            worker.run_generated_video_lazyedit_command = original

        self.assertIn("no public publish", import_msg)
        self.assertFalse(calls[0]["publish"])
        self.assertIn("public publish", publish_msg)
        self.assertTrue(calls[1]["publish"])
        self.assertEqual(worker.detect_publish_platforms(calls[1]["task"]), ["shipinhao", "youtube", "instagram"])

    def test_generated_video_lazyedit_command_uses_long_no_publish_defaults(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []
        original_values = {
            key: worker.os.environ.get(key)
            for key in (
                "WECHAT_WORKER_GENERATED_VIDEO_LAZYEDIT_TIMEOUT",
                "WECHAT_WORKER_LAZYEDIT_PROCESS_TIMEOUT",
                "WECHAT_WORKER_LAZYEDIT_REMOTE_TIMEOUT",
            )
        }
        try:
            for key in original_values:
                worker.os.environ.pop(key, None)

            def fake_run(command, **kwargs):
                calls.append({"command": command, "kwargs": kwargs})
                return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                outcome = worker.run_generated_video_lazyedit_command(
                    Path("/tmp/generated.mp4"),
                    {"request": "Current coalesced request:\nupload it to LazyEdit only"},
                    {},
                    publish=False,
                )
        finally:
            for key, value in original_values.items():
                if value is None:
                    worker.os.environ.pop(key, None)
                else:
                    worker.os.environ[key] = value

        self.assertTrue(outcome["ok"])
        shell_command = calls[0]["command"][2]
        self.assertIn("--no-publish", shell_command)
        self.assertIn("--process-timeout 10800", shell_command)
        self.assertIn("--publish-timeout 10800", shell_command)
        self.assertEqual(calls[0]["kwargs"]["timeout"], 21600)

    def test_generated_video_lazyedit_command_creates_context_prompts_when_missing(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run(command, **kwargs):
            calls.append({"command": command, "kwargs": kwargs})
            return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            artifact_dir = tmp_path / "artifact"
            video = tmp_path / "generated.mp4"
            video.write_bytes(b"video")
            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                outcome = worker.run_generated_video_lazyedit_command(
                    video,
                    {
                        "id": "task-video",
                        "artifact_dir": str(artifact_dir),
                        "request": "Current coalesced request:\nGenerate this LALACHAN story video and upload it to LazyEdit.",
                    },
                    {},
                    publish=False,
                )
            correction = artifact_dir / "lazyedit_correction_context.md"
            metadata = artifact_dir / "lazyedit_metadata_brief.md"
            correction_text = correction.read_text(encoding="utf-8")
            metadata_text = metadata.read_text(encoding="utf-8")

        self.assertTrue(outcome["ok"])
        shell_command = calls[0]["command"][2]
        self.assertIn("--correction-prompt-file", shell_command)
        self.assertIn("--metadata-prompt-file", shell_command)
        self.assertIn("lazyedit_correction_context.md", shell_command)
        self.assertIn("lazyedit_metadata_brief.md", shell_command)
        self.assertIn("WeChat Generated Video Context", correction_text)
        self.assertIn("LALACHAN story video", correction_text)
        self.assertIn("WeChat Generated Video Metadata Brief", metadata_text)

    def test_generated_video_lazyedit_command_publishes_requested_platforms(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run(command, **kwargs):
            calls.append({"command": command, "kwargs": kwargs})
            return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

        with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
            outcome = worker.run_generated_video_lazyedit_command(
                Path("/tmp/generated.mp4"),
                {
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
                    "request": "Current coalesced request:\npublish this generated video to SPH Ins y2b",
                },
                {},
                publish=True,
            )

        self.assertTrue(outcome["ok"])
        shell_command = calls[0]["command"][2]
        self.assertIn("--platforms shipinhao,youtube,instagram", shell_command)
        self.assertNotIn("--no-publish", shell_command)

    def test_generated_video_lazyedit_command_prefers_preflight_context_prompts(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        def fake_run(command, **kwargs):
            calls.append({"command": command, "kwargs": kwargs})
            return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

        with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
            outcome = worker.run_generated_video_lazyedit_command(
                Path("/tmp/generated.mp4"),
                {
                    "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
                    "request": "Current coalesced request:\npublish this generated video with context-corrected subtitles and metadata",
                    "preflight": {
                        "lazyedit_context": {
                            "correction_prompt_file": "/tmp/worker-rich-correction-context.md",
                            "metadata_prompt_file": "/tmp/worker-short-metadata-brief.md",
                        }
                    },
                },
                {
                    "story_file": "/tmp/monitor-story-only.md",
                    "prompt_file": "/tmp/monitor-prompt-only.md",
                },
                publish=True,
            )

        self.assertTrue(outcome["ok"])
        shell_command = calls[0]["command"][2]
        self.assertIn("--correction-prompt-file '/tmp/worker-rich-correction-context.md'", shell_command)
        self.assertIn("--metadata-prompt-file '/tmp/worker-short-metadata-brief.md'", shell_command)
        self.assertNotIn("/tmp/monitor-story-only.md", shell_command)
        self.assertNotIn("/tmp/monitor-prompt-only.md", shell_command)

    def test_generated_video_lazyedit_context_appends_generated_story_and_prompt(self) -> None:
        worker = load_worker()
        calls: list[dict[str, object]] = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            correction = tmp_path / "lazyedit_correction_context.md"
            metadata = tmp_path / "lazyedit_metadata_brief.md"
            story = tmp_path / "generated_story.md"
            prompt = tmp_path / "xyq_prompt.md"
            correction.write_text("wechat message context: publish the generated video\n", encoding="utf-8")
            metadata.write_text("metadata brief from WeChat message\n", encoding="utf-8")
            story.write_text("RaraXia and AyaChan find a luminous library under the city.", encoding="utf-8")
            prompt.write_text("Cinematic warm light, gentle narration, library adventure.", encoding="utf-8")

            def fake_run(command, **kwargs):
                calls.append({"command": command, "kwargs": kwargs})
                return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                outcome = worker.run_generated_video_lazyedit_command(
                    tmp_path / "generated.mp4",
                    {
                        "route_decision": {"route_kind": "generate_video", "public_publish_allowed": True},
                        "request": "Current coalesced request:\npublish this generated story video",
                        "preflight": {
                            "lazyedit_context": {
                                "correction_prompt_file": str(correction),
                                "metadata_prompt_file": str(metadata),
                            }
                        },
                    },
                    {"story_file": str(story), "prompt_file": str(prompt)},
                    publish=True,
                )

            correction_text = correction.read_text(encoding="utf-8")
            metadata_text = metadata.read_text(encoding="utf-8")

        self.assertTrue(outcome["ok"])
        self.assertTrue(calls)
        self.assertIn("Generated Video Script Context", correction_text)
        self.assertIn("RaraXia and AyaChan", correction_text)
        self.assertIn("Cinematic warm light", correction_text)
        self.assertIn("Generated Video Metadata Context", metadata_text)
        self.assertIn("Story/script excerpt", metadata_text)
        self.assertIn("Generation prompt excerpt", metadata_text)

    def test_exact_video_preflight_failure_returns_deterministic_fail_closed_result(self) -> None:
        worker = load_worker()
        task = {
            "preflight": {
                "autopublish_video": {
                    "ok": False,
                    "message_local_ids": [14],
                    "recent_video_messages": [{"chat": "🍓我的设备", "recent_video_rows": 1}],
                }
            }
        }

        raw = worker.deterministic_preflight_result(task)

        self.assertIsNotNone(raw)
        assert raw is not None
        payload = json.loads(raw)
        self.assertIn("没有发布", payload["message"])
        self.assertIn("fail-closed", payload["message"])
        self.assertIn("旧视频", payload["message"])
        self.assertEqual(payload["files"], [])
        retry = payload["publish_poststage_retry"]
        self.assertEqual(retry["stage"], "source_resolution")
        self.assertEqual(retry["poststage"]["message_local_ids"], [14])

    def test_successful_video_preflight_clears_source_resolution_retry(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "id": "publish-41",
                "chat": "My devices",
                "request": "publish the video to youtube",
                "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                "routine": {"id": "video_publish_existing"},
                "context": [{"local_id": 40, "local_type": 43, "kind": "video"}],
                "existing_video_publish_poststage": {
                    "stage": "source_resolution",
                    "message_local_ids": [40],
                },
                "next_publish_poststage_at": 123.0,
            }
            recovered = {
                "ok": True,
                "target": str(Path(tmp) / "video_COMPLETED.mp4"),
                "message_local_ids": [40],
            }
            with mock.patch.object(worker, "run_autopublish_video_preflight", return_value=recovered):
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

        self.assertTrue(preflight["autopublish_video"]["ok"])
        self.assertNotIn("existing_video_publish_poststage", task)
        self.assertNotIn("next_publish_poststage_at", task)
        self.assertIn("source_resolution_recovered_at", task)

    def test_exact_video_preflight_success_does_not_duplicate_running_publish(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "request": "Could you publish it to sph Ins y2b?",
                "preflight": {
                    "autopublish_video": {"ok": True, "target": str(target)},
                    "lazyedit_context": {
                        "correction_prompt_file": str(Path(tmp) / "correction.md"),
                        "metadata_prompt_file": str(Path(tmp) / "metadata.md"),
                    },
                },
            }
            calls: list[dict[str, object]] = []

            def fake_publish(**kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                return {"ok": True, "status": "done", "payload": {}}

            with mock.patch.object(worker, "wait_for_lazyedit_import", return_value=393):
                with mock.patch.object(worker, "run_lazyedit_publish_command", side_effect=fake_publish):
                    with mock.patch.object(worker, "lazyedit_api_get", return_value={"jobs": [{"video_id": 393, "id": 203, "status": "running", "remote_job_id": "job-1"}]}):
                        with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                            raw = worker.deterministic_preflight_result(task)

        self.assertIsNotNone(raw)
        payload = json.loads(raw or "{}")
        self.assertIn("未确认发布完成", payload["message"])
        self.assertNotIn("已确认发布完成", payload["message"])
        self.assertIn("video_id=393", payload["message"])
        self.assertIn("remote_job_id=job-1", payload["message"])
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")
        self.assertFalse(payload["publish_stage"]["verified"])
        self.assertIn("publish_poststage_retry", payload)
        self.assertEqual(calls, [])

    def test_exact_video_publish_falls_back_to_artifact_source_path(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "exact_video_COMPLETED.mp4"
            missing_target = Path(tmp) / "exact_video_completed.mp4"
            source.write_bytes(b"video")
            task = {
                "request": "publish this video to YouTube",
                "preflight": {
                    "autopublish_video": {
                        "ok": True,
                        "status": "artifact-ledger-match",
                        "target": str(missing_target),
                        "source_path": str(source),
                    },
                },
            }
            seen: list[Path] = []

            def fake_wait(target: Path, **_: object) -> int:
                seen.append(target)
                return 393

            with mock.patch.object(worker, "wait_for_lazyedit_import", side_effect=fake_wait):
                with mock.patch.object(worker, "run_lazyedit_publish_command", return_value={"ok": True, "status": "done", "payload": {}}):
                    with mock.patch.object(worker, "lazyedit_api_get", return_value={"jobs": [{"video_id": 393, "id": 203, "status": "running", "platforms": ["youtube"]}]}):
                        with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                            raw = worker.deterministic_preflight_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(seen, [source])
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")

    def test_exact_video_import_timeout_stays_resumable(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "request": "publish this video to YouTube",
                "preflight": {
                    "autopublish_video": {"ok": True, "target": str(target)},
                    "lazyedit_context": {},
                    "lazyedit_options": {},
                },
            }
            with mock.patch.object(worker, "wait_for_lazyedit_import", return_value=None):
                raw = worker.run_deterministic_lazyedit_publish(
                    task,
                    task["preflight"]["autopublish_video"],
                )

        payload = json.loads(raw or "{}")
        retry = payload["publish_poststage_retry"]
        self.assertEqual(retry["stage"], "waiting_import")
        self.assertEqual(retry["poststage"]["target"], str(target))
        self.assertIn("自动继续", payload["message"])
        self.assertNotIn("请再发", payload["message"])

        result = worker.parse_worker_result(raw or "")
        worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], worker.EXISTING_VIDEO_PUBLISH_PENDING_STATUS)
        self.assertEqual(task["existing_video_publish_poststage"]["target"], str(target))
        self.assertEqual(task["publish_poststage_last_status"], "waiting_import")

    def test_lazyedit_publish_options_preserve_explicit_layout_and_languages(self) -> None:
        worker = load_worker()
        task = {
            "request": (
                "Help me publish the video with bg fill and en/jp/zh/french at bottom\n"
                "The video is about the robotic arms built and use it to correct subtitles and metadata"
            )
        }

        options = worker.detect_lazyedit_publish_options(task)

        self.assertEqual(options["languages"], ["fr", "zh-Hant", "ja", "en"])
        self.assertTrue(options["portrait_blur_fill"])
        self.assertEqual(options["subtitle_band_style"], "bottom_anchored")
        self.assertEqual(options["subtitle_lift_ratio"], 0.0)

    def test_lazyedit_publish_options_support_lifted_subtitle_band(self) -> None:
        worker = load_worker()
        task = {
            "request": (
                "Publish with English, Japanese, Chinese, and French at the bottom, "
                "but keep a lifted subtitle band for extra bottom clearance"
            )
        }

        options = worker.detect_lazyedit_publish_options(task)

        self.assertEqual(options["languages"], ["fr", "zh-Hant", "ja", "en"])
        self.assertEqual(options["subtitle_band_style"], "lifted")
        self.assertEqual(options["subtitle_lift_ratio"], 0.1)

    def test_lazyedit_publish_options_leave_silent_layout_on_studio_settings(self) -> None:
        worker = load_worker()

        options = worker.detect_lazyedit_publish_options(
            {"request": "Publish with English, Japanese, Chinese, and French subtitles"}
        )

        self.assertEqual(options["languages"], ["fr", "zh-Hant", "ja", "en"])
        self.assertNotIn("subtitle_band_style", options)
        self.assertNotIn("subtitle_lift_ratio", options)

    def test_lazyedit_publish_command_applies_one_shot_layout_options(self) -> None:
        worker = load_worker()
        captured: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> dict[str, object]:
            captured.append(command)
            return {"ok": True, "status": "submitted"}

        with mock.patch.object(worker, "run_lazyedit_publish_subprocess", side_effect=fake_run):
            worker.run_lazyedit_publish_command(
                video_id=393,
                platforms=["shipinhao", "youtube", "instagram"],
                correction_prompt="/tmp/correction.md",
                metadata_prompt="/tmp/metadata.md",
                publish_options={
                    "languages": ["fr", "zh-Hant", "ja", "en"],
                    "portrait_blur_fill": True,
                    "subtitle_lift_ratio": 0.0,
                },
            )

        command = captured[0][2]
        self.assertIn("--languages 'fr,zh-Hant,ja,en'", command)
        self.assertIn("--portrait-blur-fill", command)
        self.assertIn("--subtitle-lift-ratio 0", command)

    def test_publish_agent_prompt_is_compact_and_source_scoped(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-41",
            "chat": "My devices",
            "request": "publish this robotic-arm video with bg fill and en jp zh french",
            "source": {"local_id": 41, "server_id": 99, "sender_display": "Tester"},
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
            },
            "routine": {"id": "video_publish_existing"},
            "preflight": {
                "autopublish_video": {
                    "ok": True,
                    "target": "/tmp/exact_COMPLETED.mp4",
                    "message_local_ids": [40],
                },
                "publish_platforms": {
                    "requested": ["shipinhao", "youtube", "instagram"],
                    "cli_value": "shipinhao,youtube,instagram",
                },
                "lazyedit_context": {
                    "correction_prompt_file": "/tmp/correction.md",
                    "metadata_prompt_file": "/tmp/metadata.md",
                },
                "lazyedit_options": {
                    "languages": ["fr", "zh-Hant", "ja", "en"],
                    "portrait_blur_fill": True,
                },
            },
            "context": [{"content": "x" * 100_000}],
        }

        prompt = worker.build_existing_video_publish_agent_prompt(task)

        self.assertLess(len(prompt), 12_000)
        self.assertIn("/tmp/exact_COMPLETED.mp4", prompt)
        self.assertIn("fr", prompt)
        self.assertIn("shipinhao,youtube,instagram", prompt)
        self.assertNotIn("x" * 1000, prompt)

    def test_publish_agent_ids_are_carried_into_exact_deterministic_state(self) -> None:
        worker = load_worker()
        task = {
            "preflight": {
                "autopublish_video": {
                    "ok": True,
                    "target": "/tmp/exact_COMPLETED.mp4",
                    "message_refs": ["message_1.db:40"],
                }
            },
            "publish_agent_supervision": {"status": "completed"},
        }

        worker.record_existing_video_publish_agent_evidence(
            task,
            '{"message":"Exact source imported as video_id 521; matching LazyEdit job 354 failed before remote submission."}',
        )

        autopub = task["preflight"]["autopublish_video"]
        self.assertEqual(autopub["lazyedit_video_id"], 521)
        self.assertEqual(autopub["publish_job_id"], 354)
        self.assertEqual(task["publish_agent_supervision"]["video_id"], 521)
        self.assertEqual(task["publish_agent_supervision"]["job_id"], 354)

    def test_exact_publish_identity_survives_same_source_preflight_refresh(self) -> None:
        worker = load_worker()
        previous = {
            "ok": True,
            "target": "/tmp/exact_COMPLETED.mp4",
            "message_refs": ["message_1.db:40"],
            "lazyedit_video_id": 521,
            "publish_job_id": 354,
        }
        current = {
            "ok": True,
            "target": "/other/exact_COMPLETED.mp4",
            "message_refs": ["message_1.db:40"],
        }

        worker.preserve_known_lazyedit_publish_identity(previous, current)

        self.assertEqual(current["lazyedit_video_id"], 521)
        self.assertEqual(current["publish_job_id"], 354)

    def test_exact_publish_identity_rejects_different_message_reference(self) -> None:
        worker = load_worker()
        previous = {
            "ok": True,
            "target": "/tmp/exact_COMPLETED.mp4",
            "message_refs": ["message_1.db:40"],
            "lazyedit_video_id": 521,
        }
        current = {
            "ok": True,
            "target": "/tmp/exact_COMPLETED.mp4",
            "message_refs": ["message_1.db:99"],
        }

        worker.preserve_known_lazyedit_publish_identity(previous, current)

        self.assertNotIn("lazyedit_video_id", current)

    def test_exact_video_publish_uses_known_id_without_duplicate_running_publish(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quoted_video_COMPLETED.mp4"
            source.write_bytes(b"video")
            task = {
                "request": "publish this quoted video to sph youtube instagram",
                "preflight": {
                    "autopublish_video": {
                        "ok": True,
                        "status": "artifact-ledger-match",
                        "target": str(source),
                        "source_path": str(source),
                        "source_task": {
                            "result_message_excerpt": "未确认发布完成；video_id=404；source=quoted_video_COMPLETED.mp4",
                        },
                    },
                },
            }
            calls: list[dict[str, object]] = []

            def fake_publish(**kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                return {"ok": True, "status": "done", "payload": {}}

            with mock.patch.object(worker, "wait_for_lazyedit_import") as wait_import:
                with mock.patch.object(worker, "run_lazyedit_publish_command", side_effect=fake_publish):
                    with mock.patch.object(worker, "lazyedit_api_get", return_value={"jobs": [{"video_id": 404, "id": 210, "status": "running", "platforms": ["shipinhao", "youtube", "instagram"]}]}):
                        with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                            raw = worker.deterministic_preflight_result(task)

        payload = json.loads(raw or "{}")
        wait_import.assert_not_called()
        self.assertEqual(calls, [])
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")

    def test_exact_video_publish_requires_terminal_platform_verification(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "request": "Could you publish it to sph Ins y2b?",
                "preflight": {"autopublish_video": {"ok": True, "target": str(target)}},
            }

            with mock.patch.object(worker, "wait_for_lazyedit_import", return_value=393):
                with mock.patch.object(worker, "run_lazyedit_publish_command", return_value={"ok": True, "status": "done", "payload": {}}):
                    with mock.patch.object(
                        worker,
                        "lazyedit_api_get",
                        return_value={
                            "jobs": [
                                {
                                    "video_id": 393,
                                    "id": 203,
                                    "status": "done",
                                    "remote_status": "done",
                                    "remote_job_id": "job-1",
                                    "platforms": ["shipinhao", "youtube", "instagram"],
                                }
                            ]
                        },
                    ):
                        with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                            raw = worker.deterministic_preflight_result(task)

        payload = json.loads(raw or "{}")
        self.assertIn("已确认发布完成", payload["message"])
        self.assertEqual(payload["publish_stage"]["stage"], "published_verified")
        self.assertTrue(payload["publish_stage"]["verified"])
        self.assertNotIn("publish_poststage_retry", payload)

    def test_exact_video_publish_rejects_terminal_unrequested_platform_without_reissue(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "request": (
                    "Current coalesced request:\n"
                    "Publish it to Shipinhao, YouTube, and Instagram."
                ),
                "route_decision": {
                    "route_kind": "publish_video",
                    "public_publish_allowed": True,
                },
                "routine": {"id": "video_publish_existing"},
                "preflight": {
                    "autopublish_video": {
                        "ok": True,
                        "target": str(target),
                        "video_id": 499,
                    }
                },
            }

            with mock.patch.object(worker, "run_lazyedit_publish_command") as publish:
                with mock.patch.object(
                    worker,
                    "lazyedit_api_get",
                    return_value={
                        "jobs": [
                            {
                                "video_id": 499,
                                "id": 332,
                                "status": "done",
                                "remote_status": "done",
                                "remote_job_id": "job-1",
                                "platforms": [
                                    "douyin",
                                    "shipinhao",
                                    "youtube",
                                    "instagram",
                                ],
                            }
                        ]
                    },
                ):
                    with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                        raw = worker.deterministic_preflight_result(task)

        publish.assert_not_called()
        payload = json.loads(raw or "{}")
        stage = payload["publish_stage"]
        self.assertEqual(stage["stage"], "published_with_unrequested_platform")
        self.assertFalse(stage["verified"])
        self.assertTrue(stage["requested_platforms_verified"])
        self.assertFalse(stage["platform_set_matches"])
        self.assertEqual(stage["unexpected_platforms"], ["douyin"])
        self.assertNotIn("publish_poststage_retry", payload)
        self.assertIn("不会自动重复发布", payload["message"])

    def test_publish_poststage_matches_only_its_exact_lazyedit_job_id(self) -> None:
        worker = load_worker()
        queue = {
            "jobs": [
                {
                    "id": 331,
                    "video_id": 499,
                    "status": "done",
                    "platforms": ["douyin"],
                },
                {
                    "id": 332,
                    "video_id": 499,
                    "status": "done",
                    "platforms": ["shipinhao", "youtube", "instagram"],
                },
            ]
        }

        with mock.patch.object(worker, "lazyedit_api_get", return_value=queue):
            jobs = worker.matching_lazyedit_publish_jobs(
                499,
                {"status": "probe", "job_id": 332},
            )

        self.assertEqual([job["id"] for job in jobs], [332])

    def test_exact_video_publish_skips_duplicate_when_already_verified(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "request": "publish this quoted video to sph youtube instagram",
                "preflight": {"autopublish_video": {"ok": True, "target": str(target)}},
            }

            with mock.patch.object(worker, "wait_for_lazyedit_import", return_value=404):
                with mock.patch.object(worker, "run_lazyedit_publish_command") as publish:
                    with mock.patch.object(
                        worker,
                        "lazyedit_api_get",
                        return_value={
                            "jobs": [
                                {
                                    "video_id": 404,
                                    "id": 210,
                                    "status": "done",
                                    "remote_status": "done",
                                    "remote_job_id": "job-1",
                                    "platforms": ["shipinhao", "youtube", "instagram"],
                                }
                            ]
                        },
                    ):
                        with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                            raw = worker.deterministic_preflight_result(task)

        publish.assert_not_called()
        payload = json.loads(raw or "{}")
        self.assertEqual(payload["publish_stage"]["stage"], "published_verified")
        self.assertTrue(payload["publish_stage"]["verified"])

    def test_unverified_existing_video_publish_stays_pending(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-task",
            "request": "Current coalesced request:\npublish this video to YouTube",
            "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
        }
        result = {
            "message": "未确认发布完成；video_id=393",
            "files": [],
            "confirmation": "",
            "data": {
                "publish_poststage_retry": {
                    "status": "publish_running",
                    "retry_seconds": 60,
                    "poststage": {
                        "kind": "existing_video_publish",
                        "video_id": 393,
                        "platforms": ["youtube"],
                        "target": "/tmp/exact_video_COMPLETED.mp4",
                    },
                    "outcome": {"status": "probe"},
                }
            },
        }

        worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], worker.EXISTING_VIDEO_PUBLISH_PENDING_STATUS)
        self.assertEqual(task["existing_video_publish_poststage"]["video_id"], 393)
        self.assertIn("next_publish_poststage_at", task)

    def test_publish_poststage_reissues_lazyedit_when_no_local_job_exists(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            correction = Path(tmp) / "correction.md"
            metadata = Path(tmp) / "metadata.md"
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            correction.write_text("story context", encoding="utf-8")
            metadata.write_text("metadata brief", encoding="utf-8")
            target.write_bytes(b"video")
            task = {
                "id": "publish-task",
                "status": worker.CLAIMED_STATUS,
                "request": "Current coalesced request:\npublish this video to sph and youtube",
                "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                "existing_video_publish_poststage": {
                    "kind": "existing_video_publish",
                    "video_id": 393,
                    "platforms": ["shipinhao", "youtube"],
                    "target": str(target),
                    "lazyedit_context": {
                        "correction_prompt_file": str(correction),
                        "metadata_prompt_file": str(metadata),
                    },
                },
            }
            calls: list[dict[str, object]] = []

            def fake_publish(**kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                return {"ok": True, "status": "done", "payload": {}}

            queue_responses = [
                {"jobs": []},
                {"jobs": []},
                {"jobs": [{"video_id": 393, "id": 203, "status": "running", "remote_job_id": "job-1", "platforms": ["shipinhao", "youtube"]}]},
            ]
            with mock.patch.object(worker, "lazyedit_api_get", side_effect=queue_responses):
                with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                    with mock.patch.object(worker, "run_lazyedit_publish_command", side_effect=fake_publish):
                        raw = worker.deterministic_existing_video_publish_poststage_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["video_id"], 393)
        self.assertEqual(calls[0]["platforms"], ["shipinhao", "youtube"])
        self.assertEqual(calls[0]["correction_prompt"], str(correction))
        self.assertEqual(calls[0]["metadata_prompt"], str(metadata))
        self.assertEqual(task["publish_poststage_reissue_count"], 1)
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")
        self.assertIn("publish_poststage_retry", payload)
        self.assertIn("publish_reissue", payload)

    def test_lazyedit_publish_command_uses_shell_stage_separators(self) -> None:
        worker = load_worker()
        command = worker.lazyedit_shell_command([
            "source ~/miniconda3/etc/profile.d/conda.sh",
            "conda activate lazyedit",
            "python scripts/lazyedit_publish.py",
            "--video-id 393",
            "--json",
        ])

        self.assertIn("source ~/miniconda3/etc/profile.d/conda.sh && conda activate lazyedit && python scripts/lazyedit_publish.py", command)
        self.assertNotIn("conda.sh conda activate", command)

    def test_lazyedit_publish_zero_exit_without_json_is_failure(self) -> None:
        worker = load_worker()
        proc = subprocess.CompletedProcess(["bash", "-lc", "true"], 0, stdout="", stderr="")

        result = worker.lazyedit_publish_proc_result(proc, command=["bash", "-lc", "true"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "no_json_output")
        self.assertEqual(result["payload"], {})

    def test_lazyedit_publish_failure_preserves_stderr_json_payload(self) -> None:
        worker = load_worker()
        proc = subprocess.CompletedProcess(
            ["bash", "-lc", "false"],
            1,
            stdout="",
            stderr='progress line\n{"error":"process failed","partial":{"video_id":409}}\n',
        )

        result = worker.lazyedit_publish_proc_result(proc, command=["bash", "-lc", "false"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["payload"]["error"], "process failed")
        self.assertEqual(result["payload"]["partial"]["video_id"], 409)

    def test_lazyedit_publish_watchdog_returns_login_blocker(self) -> None:
        worker = load_worker()

        class FakeProc:
            returncode: int | None = None

            def __init__(self) -> None:
                self.terminated = False

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                if not self.terminated:
                    raise subprocess.TimeoutExpired(["bash", "-lc", "cmd"], timeout)
                return "", ""

            def poll(self) -> int | None:
                return self.returncode

            def terminate(self) -> None:
                self.terminated = True
                self.returncode = -15

            def wait(self, timeout: float | None = None) -> int:
                if self.returncode is None:
                    self.returncode = -15
                return self.returncode

            def kill(self) -> None:
                self.terminated = True
                self.returncode = -9

        original_log_command = worker.LAZYEDIT_REMOTE_LOG_COMMAND
        fake_proc = FakeProc()
        try:
            worker.LAZYEDIT_REMOTE_LOG_COMMAND = "ssh demo tail-log"
            with mock.patch.object(worker, "lazyedit_publish_watchdog_poll_seconds", return_value=0.0):
                with mock.patch.object(worker.subprocess, "Popen", return_value=fake_proc):
                    with mock.patch.object(
                        worker,
                        "verify_lazyedit_publish_stage",
                        return_value={
                            "verified": False,
                            "stage": "waiting_login",
                            "video_id": 404,
                            "requested_platforms": ["shipinhao"],
                            "local_jobs": [{"id": 210, "video_id": 404, "status": "running"}],
                            "remote_jobs": [{"id": "job-1", "status": "running"}],
                            "blocker": {"kind": "remote_login_required"},
                        },
                    ):
                        result = worker.run_lazyedit_publish_command(
                            video_id=404,
                            platforms=["shipinhao"],
                            correction_prompt="",
                            metadata_prompt="",
                            target=Path("/tmp/quoted_COMPLETED.mp4"),
                        )
        finally:
            worker.LAZYEDIT_REMOTE_LOG_COMMAND = original_log_command

        self.assertEqual(result["status"], "waiting_login")
        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["publish_stage"]["stage"], "waiting_login")
        self.assertEqual(fake_proc.returncode, -15)

    def test_publish_poststage_does_not_reissue_when_local_job_exists(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-task",
            "status": worker.CLAIMED_STATUS,
            "request": "Current coalesced request:\npublish this video to YouTube",
            "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
            "existing_video_publish_poststage": {
                "kind": "existing_video_publish",
                "video_id": 393,
                "platforms": ["youtube"],
                "target": "/tmp/exact_video_COMPLETED.mp4",
            },
        }

        with mock.patch.object(
            worker,
            "lazyedit_api_get",
            return_value={"jobs": [{"video_id": 393, "id": 203, "status": "running", "remote_job_id": "job-1", "platforms": ["youtube"]}]},
        ):
            with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                with mock.patch.object(worker, "run_lazyedit_publish_command") as publish:
                    raw = worker.deterministic_existing_video_publish_poststage_result(task)

        payload = json.loads(raw or "{}")
        publish.assert_not_called()
        self.assertEqual(payload["publish_stage"]["stage"], "publish_running")
        self.assertIn("publish_poststage_retry", payload)
        self.assertNotIn("publish_reissue", payload)

    def test_publish_poststage_login_blocker_sends_qr_and_keeps_polling(self) -> None:
        worker = load_worker()
        task = {
            "id": "publish-task",
            "status": worker.CLAIMED_STATUS,
            "request": "Current coalesced request:\npublish this video to sph",
            "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
            "existing_video_publish_poststage": {
                "kind": "existing_video_publish",
                "video_id": 393,
                "platforms": ["shipinhao"],
                "target": "/tmp/exact_video_COMPLETED.mp4",
            },
        }

        with mock.patch.object(
            worker,
            "lazyedit_api_get",
            return_value={"jobs": [{"video_id": 393, "id": 203, "status": "running", "remote_job_id": "job-1", "platforms": ["shipinhao"]}]},
        ):
            with mock.patch.object(worker, "remote_publish_jobs_for", return_value=[{}]):
                with mock.patch.object(
                    worker,
                    "lazyedit_remote_blocker",
                    return_value={"stage": "waiting_login", "kind": "remote_login_required", "message": "Remote login required."},
                ):
                    with mock.patch.object(
                        worker,
                        "fetch_remote_publish_login_artifacts",
                        return_value=["/tmp/shipinhao-login-qr.png"],
                    ):
                        raw = worker.deterministic_existing_video_publish_poststage_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(payload["publish_stage"]["stage"], "waiting_login")
        self.assertEqual(payload["confirmation"], "")
        self.assertIn("视频号需要扫码登录", payload["message"])
        self.assertEqual(payload["files"], ["/tmp/shipinhao-login-qr.png"])
        self.assertEqual(payload["publish_poststage_retry"]["status"], "waiting_login")
        self.assertEqual(payload["publish_poststage_retry"]["retry_seconds"], 60)

        result = {
            "message": payload["message"],
            "confirmation": payload["confirmation"],
            "files": payload["files"],
            "data": payload,
        }
        worker.apply_send_outcome(task, result, [])
        self.assertEqual(task["status"], worker.EXISTING_VIDEO_PUBLISH_PENDING_STATUS)
        self.assertEqual(task["existing_video_publish_poststage"]["video_id"], 393)

    def test_deferred_publish_send_reverifies_before_retrying_stale_status(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            target = Path(tmp) / "exact_video_COMPLETED.mp4"
            target.write_bytes(b"video")
            task = {
                "id": "publish-task",
                "chat": "懒人科研",
                "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                "send_deferred_reason": "gui_send_busy",
                "last_send_attempt_at": "1970-01-01T00:00:00",
                "request": "Current coalesced request:\npublish this video to sph youtube instagram",
                "route_decision": {"route_kind": "publish_video", "public_publish_allowed": True},
                "existing_video_publish_poststage": {
                    "kind": "existing_video_publish",
                    "video_id": 404,
                    "platforms": ["shipinhao", "youtube", "instagram"],
                    "target": str(target),
                },
                "result": {
                    "message": "未确认发布完成；stage=waiting_login",
                    "confirmation": "Please login.",
                    "files": [],
                    "data": {"publish_stage": {"stage": "waiting_login"}},
                },
            }
            queue.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
            sent: list[str] = []

            def fake_send(result: dict[str, object], *_args: object, **_kwargs: object) -> list[str]:
                sent.append(str(result.get("message") or ""))
                return []

            with mock.patch.object(worker, "gui_send_lock_busy", return_value=False):
                with mock.patch.object(worker, "send_result_with_retries", side_effect=fake_send):
                    with mock.patch.object(worker, "record_event"):
                        with mock.patch.object(
                            worker,
                            "verify_lazyedit_publish_stage",
                            return_value={
                                "verified": True,
                                "stage": "published_verified",
                                "video_id": 404,
                                "requested_platforms": ["shipinhao", "youtube", "instagram"],
                                "verified_platforms": ["shipinhao", "youtube", "instagram"],
                                "local_jobs": [{"id": 210, "video_id": 404, "status": "done", "remote_status": "done"}],
                                "remote_jobs": [{"id": "job-1", "status": "done"}],
                                "blocker": {},
                                "source": target.name,
                            },
                        ):
                            handled = worker.flush_one_deferred_send(queue, "懒人科研", log_idle=False)

            rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertTrue(handled)
        self.assertIn("已确认发布完成", sent[0])
        self.assertEqual(rows[0]["status"], "done")
        self.assertEqual(rows[0]["publish_deferred_refresh_from"], "waiting_login")
        self.assertEqual(rows[0]["publish_deferred_refresh_to"], "published_verified")

    def test_detect_remote_publish_login_blocker_from_log(self) -> None:
        worker = load_worker()
        blocker = worker.detect_remote_publish_blocker_from_log(
            [{"id": 203, "filename": "demo_COMPLETED.zip", "remote_job_id": "job-1", "status": "running"}],
            [{"id": "job-1", "status": "running"}],
            "Received publish request: demo_COMPLETED.zip\nLogin iframe detected.\nLogin required, will check again in 5 seconds...",
        )

        self.assertEqual(blocker["stage"], "waiting_login")
        self.assertEqual(blocker["kind"], "remote_login_required")
        self.assertIn("demo_COMPLETED.zip", blocker["matched"])

    def test_remote_login_log_is_resolved_by_later_success(self) -> None:
        worker = load_worker()

        self.assertFalse(
            worker.remote_log_is_waiting_for_login(
                "Login required, will check again.\n"
                "Logged in successfully, stopping checks.\n"
                "Publishing on ShiPinHao...\n"
            )
        )

    def test_structured_login_attention_binds_to_exact_running_job(self) -> None:
        worker = load_worker()
        local_jobs = [
            {
                "id": 203,
                "remote_job_id": "job-1",
                "remote_status": "running",
                "status": "running",
                "attention": {
                    "platform": "shipinhao",
                    "kind": "login_qr",
                    "status": "required",
                    "revision": 3,
                    "artifact_url": (
                        "/api/autopublish/jobs/job-1/attention/3"
                    ),
                    "media_type": "image/png",
                },
            }
        ]
        remote_jobs = [{"id": "job-1", "status": "running"}]
        blocker = worker.structured_publish_attention(
            local_jobs,
            remote_jobs,
        )

        self.assertEqual(blocker["stage"], "waiting_login")
        self.assertEqual(blocker["matched"], ["job-1"])
        self.assertEqual(blocker["correlation"], "lazyedit_job_attention")
        self.assertEqual(blocker["attention"]["revision"], 3)

    def test_login_qr_delivery_deduplicates_revision_and_accepts_refresh(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            task = {"id": "publish-task"}
            current = {"data": b"\x89PNG\r\n\x1a\nfirst"}
            verification = {
                "stage": "waiting_login",
                "blocker": {
                    "attention": {
                        "kind": "login_qr",
                        "status": "required",
                        "revision": 1,
                        "artifact_url": (
                            "/api/autopublish/jobs/job-1/attention/1"
                        ),
                    }
                },
            }

            with mock.patch.object(worker, "worker_artifact_dir", return_value=Path(tmp)):
                with mock.patch.object(
                    worker.urllib.request,
                    "urlopen",
                    side_effect=lambda *_args, **_kwargs: io.BytesIO(current["data"]),
                ):
                    first = worker.fetch_remote_publish_login_artifacts(
                        task,
                        verification,
                    )
                    duplicate = worker.fetch_remote_publish_login_artifacts(
                        task,
                        verification,
                    )
                    current["data"] = b"\x89PNG\r\n\x1a\nrefreshed"
                    verification["blocker"]["attention"].update(
                        {
                            "revision": 2,
                            "artifact_url": (
                                "/api/autopublish/jobs/job-1/attention/2"
                            ),
                        }
                    )
                    refreshed = worker.fetch_remote_publish_login_artifacts(
                        task,
                        verification,
                    )

        self.assertEqual(len(first), 1)
        self.assertEqual(duplicate, [])
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(task["publish_login_attention_revision"], 2)

    def test_save_to_publish_folder_without_publish_does_not_auto_publish(self) -> None:
        worker = load_worker()
        task = {
            "request": "Save this video to the publish folder but no need to publish yet",
            "preflight": {"autopublish_video": {"ok": True, "target": "/tmp/exact_video_COMPLETED.mp4"}},
        }

        self.assertFalse(worker.should_deterministic_video_publish(task))

    def test_worker_result_skips_private_artifacts(self) -> None:
        worker = load_worker()
        private_file = worker.PRIVATE / "unit-test-private-render.png"
        private_file.parent.mkdir(parents=True, exist_ok=True)
        private_file.write_bytes(b"private")
        try:
            prepared = worker.prepare_result_files({"message": "done", "confirmation": "", "files": [str(private_file)]}, "")
        finally:
            private_file.unlink(missing_ok=True)

        self.assertEqual(prepared["files"], [])
        self.assertEqual(prepared["skipped_files"][0]["reason"], "private-path")

    def test_worker_result_never_delivers_internal_routine_evidence(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name in (
                "routine_contract.md",
                "routine_contract.json",
                "same_chat_interruptions.json",
                "finder_feed_request.private.json",
            ):
                path = root / name
                path.write_text("private worker evidence", encoding="utf-8")
                paths.append(str(path))

            prepared = worker.prepare_result_files(
                {"message": "done", "confirmation": "", "files": paths},
                "",
            )

        self.assertEqual(prepared["files"], [])
        self.assertEqual(
            {item["reason"] for item in prepared["skipped_files"]},
            {"internal-evidence"},
        )

    def test_bare_file_intake_does_not_send_the_uploaded_source_back(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "daily-review.pdf"
            source.write_bytes(b"%PDF-1.4\nsource")
            task = {
                "request": (
                    "Current coalesced request:\n"
                    "[WeChat file]\n"
                    "title: daily-review.pdf\n"
                    "size_bytes: 15\n"
                ),
                "route_decision": {"route_kind": "file_intake"},
                "preflight": {
                    "file_intake": {
                        "copied": [
                            {
                                "task_copy_path": str(source),
                                "saved_path": str(source),
                            }
                        ]
                    }
                },
            }

            prepared = worker.prepare_result_files(
                {"message": f"Saved copy: {source}", "confirmation": "", "files": []},
                f"Saved copy: {source}",
                task=task,
            )

        self.assertEqual(prepared["files"], [])
        self.assertEqual(prepared["skipped_files"][0]["reason"], "source-intake-echo")

    def test_file_intake_can_return_source_when_explicitly_requested(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "requested.pdf"
            source.write_bytes(b"%PDF-1.4\nsource")
            task = {
                "request": "Current coalesced request:\nPlease send this file back.",
                "route_decision": {"route_kind": "file_intake"},
                "preflight": {
                    "file_intake": {
                        "copied": [{"task_copy_path": str(source)}],
                    }
                },
            }

            prepared = worker.prepare_result_files(
                {"message": "Here it is.", "confirmation": "", "files": [str(source)]},
                "",
                task=task,
            )

        self.assertEqual(prepared["files"], [str(source.resolve())])

    def test_aginti_fallback_can_only_deliver_current_task_artifacts(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "current-task"
            artifact_dir.mkdir()
            current = artifact_dir / "report.pdf"
            unrelated = root / "old-task.pdf"
            current.write_bytes(b"%PDF current")
            unrelated.write_bytes(b"%PDF old")
            task = {
                "artifact_dir": str(artifact_dir),
                "agent_session": {"backend": "aginti"},
            }

            prepared = worker.prepare_result_files(
                {
                    "message": "done",
                    "confirmation": "",
                    "files": [str(current), str(unrelated)],
                },
                "",
                task=task,
            )
            delivered = Path(prepared["files"][0])
            delivered_parent = delivered.parent
            delivered_name = delivered.name
            delivered_bytes = delivered.read_bytes()
            current_bytes = current.read_bytes()

        self.assertEqual(delivered_parent.name, "delivery")
        self.assertTrue(delivered_name.endswith("-labcanvas-report.pdf"))
        self.assertEqual(delivered_bytes, current_bytes)
        self.assertEqual(
            prepared["skipped_files"][0]["reason"],
            "aginti-unscoped-artifact",
        )

    def test_worker_result_treats_null_files_as_empty(self) -> None:
        worker = load_worker()

        prepared = worker.prepare_result_files({"message": "ok", "confirmation": "", "files": None}, "")

        self.assertEqual(prepared["files"], [])

    def test_worker_result_does_not_extract_http_urls_as_files(self) -> None:
        worker = load_worker()
        raw = "请打开 http://127.0.0.1:6107/vnc_lite.html?host=127.0.0.1&port=6107 继续验证。"

        prepared = worker.prepare_result_files({"message": "ok", "confirmation": raw, "files": []}, raw)

        self.assertEqual(prepared["files"], [])
        self.assertNotIn("skipped_files", prepared)

    def test_send_result_retries_transient_failure(self) -> None:
        worker = load_worker()
        calls = []
        original = worker.send_result_once
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"

            def flaky_send(*args: object) -> None:
                calls.append(args)
                if len(calls) == 1:
                    raise RuntimeError("title guard transient")

            worker.send_result_once = flaky_send
            errors = worker.send_result_with_retries({"message": "ok", "confirmation": "", "files": []}, "EchoMind", Path("/tmp/no-targets.json"))
        finally:
            worker.send_result_once = original
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 2)

    def test_worker_sanitizer_preserves_complete_long_answer(self) -> None:
        worker = load_worker()
        answer = "完整回答。" * 600

        cleaned = worker.sanitize_worker_chat_message(answer, max_chars=1200)

        self.assertEqual(cleaned, answer)
        self.assertNotIn("已截断", cleaned)

    def test_chat_message_split_is_numbered_and_lossless(self) -> None:
        worker = load_worker()
        answer = "".join(f"句子{index:03d}。" for index in range(120))

        parts = worker.split_chat_message(answer, max_chars=240)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 240 for part in parts))
        bodies = [part.split("\n", 1)[1] for part in parts]
        self.assertEqual("".join(bodies), answer)
        self.assertTrue(parts[0].startswith(f"[1/{len(parts)}]\n"))

    def test_chat_message_parts_are_retry_safe(self) -> None:
        worker = load_worker()
        task: dict[str, object] = {}
        answer = "".join(f"段落{index:03d}。" for index in range(300))
        sent: list[str] = []
        original_send = worker.send_message
        try:
            worker.send_message = lambda message, *_args, **_kwargs: sent.append(message)
            worker.send_result_text_parts(
                answer,
                field="message",
                task=task,
                target_chat="EchoMind",
                send_targets=Path("/tmp/no-targets.json"),
                target={"name": "EchoMind"},
            )
            first_count = len(sent)
            worker.send_result_text_parts(
                answer,
                field="message",
                task=task,
                target_chat="EchoMind",
                send_targets=Path("/tmp/no-targets.json"),
                target={"name": "EchoMind"},
            )
        finally:
            worker.send_message = original_send

        self.assertGreater(first_count, 1)
        self.assertEqual(len(sent), first_count)
        self.assertEqual(len(task["sent_message_part_hashes"]), first_count)

    def test_very_long_answer_becomes_complete_pdf_delivery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            task: dict[str, object] = {
                "id": "long-answer-1",
                "chat": "LabAgent",
                "artifact_dir": str(artifact_dir),
            }
            answer = "完整的研究说明。" * 1000
            result: dict[str, object] = {
                "message": answer,
                "confirmation": "",
                "files": [],
            }

            def fake_render(source: Path, output: Path) -> Path:
                self.assertIn(answer, source.read_text(encoding="utf-8"))
                output.write_bytes(b"%PDF-1.4\ncomplete")
                return output

            with mock.patch.object(worker, "render_markdown_pdf", side_effect=fake_render):
                worker.prepare_long_response_delivery(task, result)

            pdf = next(artifact_dir.glob("*-labagent-report.pdf"))
            markdown = pdf.with_suffix(".md")
            self.assertTrue(pdf.is_file())
            self.assertIn(answer, markdown.read_text(encoding="utf-8"))
            self.assertEqual(result["files"], [str(pdf)])
            self.assertTrue(result["data"]["require_file_delivery"])
            self.assertEqual(
                result["data"]["long_response_delivery"]["status"],
                "compiled",
            )
            self.assertNotIn("已截断", str(result["message"]))

    def test_generic_generated_artifact_gets_meaningful_delivery_name(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            source = artifact_dir / "delivery-confirmation.pdf"
            source.write_bytes(b"%PDF-1.4\norganoid evidence")
            task: dict[str, object] = {
                "id": "20260822124500-123",
                "chat": "LabAgent",
                "created_at": "2026-08-22T12:45:00+08:00",
                "request": (
                    "Current coalesced request:\n"
                    "Please create a detailed PDF report about organoid imaging biomarkers."
                ),
                "artifact_dir": str(artifact_dir),
            }

            prepared = worker.prepare_result_files(
                {"message": "Done.", "confirmation": "", "files": [str(source)]},
                "",
                task=task,
            )

            delivered = Path(prepared["files"][0])
            self.assertEqual(
                delivered.name,
                "2026-08-22-about-organoid-imaging-biomarkers-report.pdf",
            )
            self.assertEqual(delivered.read_bytes(), source.read_bytes())
            self.assertEqual(task["delivery_artifact_aliases"][0]["display_name"], delivered.name)
            self.assertTrue(source.is_file())

            for filename in (
                "file-v2.txt",
                "final-report-v3.pdf",
                "报告.pdf",
                "結果.docx",
                "レポート.pdf",
            ):
                with self.subTest(filename=filename):
                    self.assertTrue(
                        worker.artifact_name_needs_delivery_alias(filename, task)
                    )
            self.assertFalse(
                worker.artifact_name_needs_delivery_alias(
                    "organoid-review-delivery.pdf", task
                )
            )

            with mock.patch.object(worker.os, "link", side_effect=OSError("cross-device")):
                repeated = worker.ensure_meaningful_delivery_path(source, task)
            self.assertEqual(repeated, delivered)
            self.assertEqual(len(task["delivery_artifact_aliases"]), 1)

    def test_exact_inbound_file_keeps_its_original_filename(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            source = artifact_dir / "report.pdf"
            source.write_bytes(b"%PDF-1.4\nexact inbound")
            task: dict[str, object] = {
                "id": "source-file",
                "chat": "LabAgent",
                "request": "Please send this file back.",
                "artifact_dir": str(artifact_dir),
                "route_decision": {"route_kind": "file_intake"},
                "preflight": {
                    "file_intake": {
                        "copied": [{"task_copy_path": str(source)}],
                    }
                },
            }

            prepared = worker.prepare_result_files(
                {"message": "Here it is.", "confirmation": "", "files": [str(source)]},
                "",
                task=task,
            )

            self.assertEqual(prepared["files"], [str(source.resolve())])
            self.assertNotIn("delivery_artifact_aliases", task)

    def test_pdf_compile_failure_keeps_all_numbered_text(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            task: dict[str, object] = {
                "id": "long-answer-2",
                "chat": "LabAgent",
                "artifact_dir": tmp,
            }
            answer = "不能丢失的内容。" * 1000
            result: dict[str, object] = {
                "message": answer,
                "confirmation": "",
                "files": [],
            }
            with mock.patch.object(worker, "render_markdown_pdf", return_value=None):
                worker.prepare_long_response_delivery(task, result)

        self.assertEqual(result["message"], answer)
        self.assertEqual(result["files"], [])
        self.assertEqual(
            result["data"]["long_response_delivery"]["status"],
            "pdf_compile_failed_parts_preserved",
        )

    def test_send_result_defers_immediately_when_wechat_locked(self) -> None:
        worker = load_worker()
        calls = []
        original = worker.send_result_once
        try:
            def locked_send(*args: object, **kwargs: object) -> None:
                calls.append((args, kwargs))
                raise RuntimeError("WECHAT_LOCKED: Weixin for Linux is locked")

            worker.send_result_once = locked_send
            task: dict[str, object] = {}
            errors = worker.send_result_with_retries(
                {"message": "ok", "confirmation": "", "files": []},
                "EchoMind",
                Path("/tmp/no-targets.json"),
                task=task,
            )
            worker.apply_send_outcome(task, {"message": "ok", "confirmation": "", "files": []}, errors)
        finally:
            worker.send_result_once = original

        self.assertEqual(len(calls), 1)
        self.assertTrue(worker.send_errors_indicate_wechat_locked(errors))
        self.assertEqual(task["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertEqual(task["send_deferred_reason"], "wechat_locked")

    def test_send_result_defers_immediately_when_wecom_security_verification_is_required(self) -> None:
        worker = load_worker()
        calls = []
        original = worker.send_result_once
        try:
            def auth_required(*args: object, **kwargs: object) -> None:
                calls.append((args, kwargs))
                raise RuntimeError("WECOM_GUI_AUTH_REQUIRED: device_environment_abnormal")

            worker.send_result_once = auth_required
            task: dict[str, object] = {}
            errors = worker.send_result_with_retries(
                {"message": "", "confirmation": "", "files": ["report.pdf"]},
                "wecom:group",
                Path("/tmp/no-targets.json"),
                task=task,
            )
            worker.apply_send_outcome(task, {"message": "", "confirmation": "", "files": ["report.pdf"]}, errors)
        finally:
            worker.send_result_once = original

        self.assertEqual(len(calls), 1)
        self.assertTrue(worker.send_errors_indicate_wecom_auth_required(errors))
        self.assertEqual(task["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertEqual(task["send_deferred_reason"], "wecom_auth_required")

    def test_send_result_defers_immediately_when_gui_sender_busy(self) -> None:
        worker = load_worker()
        calls = []
        original = worker.send_result_once
        try:
            def busy_send(*args: object, **kwargs: object) -> None:
                calls.append((args, kwargs))
                raise RuntimeError("WECHAT_SEND_BUSY: serialized GUI sender is already sending")

            worker.send_result_once = busy_send
            task: dict[str, object] = {}
            errors = worker.send_result_with_retries(
                {"message": "ok", "confirmation": "", "files": []},
                "EchoMind",
                Path("/tmp/no-targets.json"),
                task=task,
            )
            worker.apply_send_outcome(task, {"message": "ok", "confirmation": "", "files": []}, errors)
        finally:
            worker.send_result_once = original

        self.assertEqual(len(calls), 1)
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(task["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertEqual(task["send_deferred_reason"], "gui_send_busy")

    def test_send_result_defers_immediately_when_gui_sender_times_out(self) -> None:
        worker = load_worker()
        calls = []
        original = worker.send_result_once
        try:
            def timeout_send(*args: object, **kwargs: object) -> None:
                calls.append((args, kwargs))
                raise RuntimeError("WECHAT_SEND_TIMEOUT: GUI sender timed out after 120 seconds")

            worker.send_result_once = timeout_send
            task: dict[str, object] = {}
            errors = worker.send_result_with_retries(
                {"message": "ok", "confirmation": "", "files": []},
                "EchoMind",
                Path("/tmp/no-targets.json"),
                task=task,
            )
            worker.apply_send_outcome(task, {"message": "ok", "confirmation": "", "files": []}, errors)
        finally:
            worker.send_result_once = original

        self.assertEqual(len(calls), 1)
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(task["status"], worker.SEND_DEFERRED_LOCKED_STATUS)
        self.assertEqual(task["send_deferred_reason"], "gui_send_timeout")

    def test_android_transport_disconnect_is_retried(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: Remote end closed connection without response",
            "attempt 2: WeCom Android transport is unavailable",
        ]

        self.assertTrue(worker.send_errors_indicate_transient_transport(errors))
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(
            worker.send_deferred_reason_from_errors(errors),
            "wecom_transport_transient",
        )

        task = {
            "status": "send_failed",
            "send_errors": errors,
            "completed_at": "2026-01-01T00:00:00",
        }
        with mock.patch.dict(
            worker.os.environ,
            {"WECOM_TRANSPORT_SEND_MAX_RETRIES": "3"},
            clear=False,
        ):
            self.assertTrue(worker.failed_send_retryable(task, worker.datetime.now()))

    def test_reaper_kills_orphaned_gui_sender_after_short_timeout(self) -> None:
        worker = load_worker()
        run_calls = [
            subprocess.CompletedProcess(["pgrep"], 0, "1234\n", ""),
            subprocess.CompletedProcess(["ps"], 0, "1 16\n", ""),
        ]
        with mock.patch.object(worker.subprocess, "run", side_effect=run_calls), mock.patch.object(
            worker.os, "kill"
        ) as kill_mock, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_ORPHAN_GUI_SEND_SECONDS": "15",
                "WECHAT_WORKER_STALE_GUI_SEND_SECONDS": "180",
            },
            clear=False,
        ):
            worker.reap_stale_orphaned_gui_senders()

        kill_mock.assert_called_once_with(1234, worker.signal.SIGTERM)

    def test_run_send_subprocess_delegates_gui_lock_wait_to_sender(self) -> None:
        worker = load_worker()
        original_lock_busy = worker.gui_send_lock_busy
        original_run = worker.run_subprocess_group
        try:
            worker.gui_send_lock_busy = lambda: True
            calls: list[list[str]] = []

            def successful_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            worker.run_subprocess_group = successful_run
            command = ["python3", "-c", "print('unused')"]
            worker.run_send_subprocess(command, timeout=1)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            worker.run_subprocess_group = original_run

        self.assertEqual(calls, [command])

    def test_run_send_subprocess_timeout_is_deferable(self) -> None:
        worker = load_worker()
        original_lock_busy = worker.gui_send_lock_busy
        original_run = worker.run_subprocess_group
        try:
            worker.gui_send_lock_busy = lambda: False

            def timeout_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                raise subprocess.TimeoutExpired(command, 120)

            worker.run_subprocess_group = timeout_run
            with self.assertRaisesRegex(RuntimeError, "WECHAT_SEND_TIMEOUT") as context:
                worker.run_send_subprocess(["python3", "-c", "print('unused')"], timeout=120)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            worker.run_subprocess_group = original_run

        self.assertTrue(worker.send_errors_indicate_deferable([str(context.exception)]))

    def test_title_guard_failures_retry_safely_with_distinct_reasons(self) -> None:
        worker = load_worker()
        blank = ["attempt 1: Opened chat title guard failed for EchoMind: OCR=''."]
        wrong = ["attempt 1: Opened chat title guard failed for EchoMind: OCR='OtherChat'."]

        self.assertTrue(worker.send_errors_indicate_deferable(blank))
        self.assertEqual(worker.send_deferred_reason_from_errors(blank), "title_guard_blank")
        self.assertTrue(worker.send_errors_indicate_title_guard_failure(wrong))
        self.assertTrue(worker.send_errors_indicate_deferable(wrong))
        self.assertEqual(worker.send_deferred_reason_from_errors(wrong), "title_guard_failed")

    def test_compact_exception_text_preserves_final_actionable_line(self) -> None:
        worker = load_worker()
        exc = RuntimeError("beginning\n" + ("trace detail\n" * 200) + "FINAL TITLE GUARD FAILURE")

        compact = worker.compact_exception_text(exc, limit=240)

        self.assertLessEqual(len(compact), 240)
        self.assertTrue(compact.startswith("beginning"))
        self.assertTrue(compact.endswith("FINAL TITLE GUARD FAILURE"))

    def test_wechat_entry_required_error_is_retryable(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: send command failed with exit 1; "
            "stderr=WECHAT_ENTRY_REQUIRED: WeChat is visible but not in the main chat UI"
        ]

        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), "wechat_entry_required")

    def test_wecom_gui_pre_send_verification_error_is_retryable(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: WeCom transport HTTP 500: "
            "WECOM_GUI_COMPOSE_UNVERIFIED: composer did not contain the exact Unicode message"
        ]

        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(
            worker.send_deferred_reason_from_errors(errors),
            "gui_compose_verification",
        )

    def test_wecom_nonempty_draft_is_deferred_without_overwrite(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: WeCom delivery errors: "
            "BridgeError: refusing to overwrite a non-empty WeCom draft"
        ]

        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(
            worker.send_deferred_reason_from_errors(errors),
            "gui_compose_verification",
        )

    def test_wecom_gui_post_send_uncertainty_is_not_automatically_retried(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: WECOM_GUI_SEND_UNCERTAIN: composer did not clear after Send"
        ]

        self.assertFalse(worker.send_errors_indicate_deferable(errors))

    def test_claim_next_deferred_send_repairs_legacy_wecom_composer_failure(self) -> None:
        worker = load_worker()
        with mock.patch.dict(
            worker.os.environ,
            {"WECOM_GUI_COMPOSE_RETRY_BACKOFF_SECONDS": "0"},
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "wecom-compose-failed",
                            "chat": "wecom:external-gui:group:one",
                            "status": "send_failed",
                            "send_errors": [
                                "WeCom composer did not contain the exact Unicode message"
                            ],
                            "last_send_attempt_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_deferred_reason"], "gui_compose_verification")

    def test_newer_same_chat_message_suppresses_unsent_stale_confirmation(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-question",
                        "chat": "wecom:external-gui:group:one",
                        "status": "send_failed",
                        "created_at": "2026-07-19T08:51:00",
                        "send_errors": ["WeCom composer did not contain the exact Unicode message"],
                        "result": {"message": "confirm it", "confirmation": "Which protein?", "files": []},
                    },
                    {
                        "id": "new-answer",
                        "chat": "wecom:external-gui:group:one",
                        "status": "pending",
                        "created_at": "2026-07-19T08:52:00",
                        "source": {"kind": "text", "authorization_role": "group_member"},
                    },
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)
            tasks = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertEqual(tasks[0]["status"], "canceled_superseded")
        self.assertEqual(tasks[0]["superseded_by"], "new-answer")

    def test_wecom_legacy_task_uses_exact_source_row_not_router_rewrite(self) -> None:
        worker = load_worker()
        task = {
            "request": "Do not proceed until the name is confirmed.",
            "source": {"transport": "wecom", "create_time": 1234, "local_id": 999},
            "context": [
                {
                    "local_id": 9,
                    "create_time": 1234,
                    "content": "一个蛋白的名字，调研肿瘤影响并画信号通路图",
                    "is_self": False,
                }
            ],
        }

        focused = worker.task_focus_text(task)

        self.assertEqual(focused, "一个蛋白的名字，调研肿瘤影响并画信号通路图")
        self.assertNotIn("Do not proceed", focused)

    def test_queue_timestamps_normalize_explicit_timezone_to_local_naive(self) -> None:
        worker = load_worker()
        source = "2026-07-19T09:00:19+08:00"

        parsed = worker.parse_iso_datetime(source)
        expected = datetime.fromisoformat(source).astimezone().replace(tzinfo=None)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIsNone(parsed.tzinfo)
        self.assertEqual(parsed, expected)

    def test_claim_next_deferred_send_repairs_retryable_send_failed(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS")
        original_max_retries = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES")
        try:
            worker.os.environ["WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS"] = "0"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = "5"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-send-failed",
                            "chat": "EchoMind",
                            "status": "send_failed",
                            "send_errors": ["attempt 1: Opened chat title guard failed for EchoMind: OCR=''."],
                            "created_at": "2026-06-22T00:00:00",
                            "completed_at": "2026-06-22T00:00:00",
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
                self.assertEqual(claimed["send_deferred_reason"], "title_guard_blank")
                self.assertEqual(claimed["send_retry_count"], 1)
        finally:
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS"] = original_backoff
            if original_max_retries is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = original_max_retries

    def test_claim_next_deferred_send_recovers_transport_failed_after_retry_limit(self) -> None:
        worker = load_worker()
        original_timeout_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_failed_max = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES")
        original_transient_max = worker.os.environ.get("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES")
        original_recovery = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = "0"
            worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = "5"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES"] = "1"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-timeout-send-failed",
                            "chat": "鏈接",
                            "status": "send_failed",
                            "send_deferred_reason": "gui_send_timeout",
                            "send_retry_count": 5,
                            "send_errors": [
                                "attempt 1: send command failed with exit 124; stderr=WECHAT_SEND_TIMEOUT",
                                "transient send retry limit reached (5 attempts)",
                            ],
                            "result": {"message": "summary", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
                self.assertEqual(claimed["send_retry_count"], 1)
                self.assertEqual(claimed["send_failed_recovery_count"], 1)
                self.assertEqual(claimed["send_deferred_reason"], "gui_send_timeout")
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_timeout_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_timeout_backoff
            if original_failed_max is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = original_failed_max
            if original_transient_max is None:
                worker.os.environ.pop("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = original_transient_max
            if original_recovery is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES"] = original_recovery

    def test_claim_next_deferred_send_has_one_default_transport_recovery_cycle(self) -> None:
        worker = load_worker()
        env_keys = (
            "WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS",
            "WECHAT_WORKER_FAILED_SEND_MAX_RETRIES",
            "WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES",
        )
        saved = {key: worker.os.environ.get(key) for key in env_keys}
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = "0"
            worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES", None)
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "default-recovery",
                            "chat": "写作 外语 挣钱",
                            "status": "send_failed",
                            "send_deferred_reason": "gui_send_timeout",
                            "send_retry_count": 2,
                            "send_errors": ["attempt 1: WECHAT_SEND_TIMEOUT"],
                            "result": {"message": "organized memo", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
            self.assertEqual(claimed["send_failed_recovery_count"], 1)
            self.assertEqual(claimed["send_retry_count"], 1)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            for key, value in saved.items():
                if value is None:
                    worker.os.environ.pop(key, None)
                else:
                    worker.os.environ[key] = value

    def test_claim_next_deferred_send_recovers_stale_transport_after_recovery_cap(self) -> None:
        worker = load_worker()
        original_busy_backoff = worker.os.environ.get("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS")
        original_failed_max = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES")
        original_transient_max = worker.os.environ.get("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES")
        original_recovery = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES")
        original_stale = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS")
        original_allow_stale = worker.os.environ.get("WECHAT_WORKER_ALLOW_STALE_SEND_RECOVERY")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = "0"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = "0"
            worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = "5"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES"] = "1"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS"] = "60"
            worker.os.environ["WECHAT_WORKER_ALLOW_STALE_SEND_RECOVERY"] = "1"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-busy-send-failed",
                            "chat": "鏈接",
                            "status": "send_failed",
                            "send_deferred_reason": "gui_send_busy",
                            "send_retry_count": 5,
                            "send_failed_recovery_count": 1,
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "send_errors": [
                                "attempt 1: WECHAT_SEND_BUSY: serialized GUI sender is already sending",
                                "transient send retry limit reached (5 attempts)",
                            ],
                            "result": {"message": "summary", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
                self.assertEqual(claimed["send_retry_count"], 1)
                self.assertEqual(claimed["send_failed_recovery_count"], 2)
                self.assertEqual(claimed["send_deferred_reason"], "gui_send_busy")
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_busy_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = original_busy_backoff
            if original_failed_max is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = original_failed_max
            if original_transient_max is None:
                worker.os.environ.pop("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = original_transient_max
            if original_recovery is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES"] = original_recovery
            if original_stale is None:
                worker.os.environ.pop("WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS"] = original_stale
            if original_allow_stale is None:
                worker.os.environ.pop("WECHAT_WORKER_ALLOW_STALE_SEND_RECOVERY", None)
            else:
                worker.os.environ["WECHAT_WORKER_ALLOW_STALE_SEND_RECOVERY"] = original_allow_stale

    def test_claim_next_deferred_send_stops_transient_retry_loop(self) -> None:
        worker = load_worker()
        original_max = worker.os.environ.get("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES")
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS")
        try:
            worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = "2"
            worker.os.environ["WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS"] = "0"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-loop",
                            "chat": "EchoMind",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "title_guard_blank",
                            "send_retry_count": 2,
                            "send_errors": ["attempt 1: Opened chat title guard failed for EchoMind: OCR=''."],
                        }
                    ],
                )

                self.assertIsNone(worker.claim_next_deferred_send(queue))
                tasks = worker.read_tasks(queue)
                self.assertEqual(tasks[0]["status"], "send_failed")
                self.assertIn("retry limit reached", tasks[0]["send_errors"][-1])
        finally:
            if original_max is None:
                worker.os.environ.pop("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = original_max
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS"] = original_backoff

    def test_wecom_transport_retry_limit_is_bounded_without_queue_growth(self) -> None:
        worker = load_worker()
        original_max = worker.os.environ.get("WECOM_TRANSPORT_SEND_MAX_RETRIES")
        original_backoff = worker.os.environ.get("WECOM_TRANSPORT_SEND_BACKOFF_SECONDS")
        try:
            worker.os.environ["WECOM_TRANSPORT_SEND_MAX_RETRIES"] = "3"
            worker.os.environ["WECOM_TRANSPORT_SEND_BACKOFF_SECONDS"] = "0"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                repeated_history = [
                    {
                        "repaired_at": f"2026-07-27T10:00:{index:02d}",
                        "reason": "wecom_transport_transient",
                        "from_status": "send_failed",
                    }
                    for index in range(40)
                ]
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "wecom-send-failed",
                            "chat": "LabAgent",
                            "status": "send_failed",
                            "send_deferred_reason": "wecom_transport_transient",
                            "send_retry_count": 3,
                            "send_errors": [
                                "attempt 1: WeCom Android transport is unavailable",
                                *(
                                    "transient send retry limit reached (3 attempts)"
                                    for _ in range(40)
                                ),
                            ],
                            "send_failed_repair_history": repeated_history,
                            "result": {"message": "report", "files": ["/tmp/report.pdf"]},
                        }
                    ],
                )

                self.assertIsNone(worker.claim_next_deferred_send(queue))
                first = worker.read_tasks(queue)[0]
                self.assertEqual(first["status"], "send_failed")
                self.assertEqual(len(first["send_errors"]), 2)
                self.assertEqual(
                    len(first["send_failed_repair_history"]),
                    worker.DEFAULT_SEND_FAILURE_HISTORY_LIMIT,
                )

                self.assertIsNone(worker.claim_next_deferred_send(queue))
                second = worker.read_tasks(queue)[0]
                self.assertEqual(second["send_errors"], first["send_errors"])
                self.assertEqual(
                    second["send_failed_repair_history"],
                    first["send_failed_repair_history"],
                )
        finally:
            if original_max is None:
                worker.os.environ.pop("WECOM_TRANSPORT_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECOM_TRANSPORT_SEND_MAX_RETRIES"] = original_max
            if original_backoff is None:
                worker.os.environ.pop("WECOM_TRANSPORT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECOM_TRANSPORT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_wecom_transport_can_use_its_final_configured_retry(self) -> None:
        worker = load_worker()
        original_max = worker.os.environ.get("WECOM_TRANSPORT_SEND_MAX_RETRIES")
        original_backoff = worker.os.environ.get("WECOM_TRANSPORT_SEND_BACKOFF_SECONDS")
        try:
            worker.os.environ["WECOM_TRANSPORT_SEND_MAX_RETRIES"] = "3"
            worker.os.environ["WECOM_TRANSPORT_SEND_BACKOFF_SECONDS"] = "0"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "wecom-final-retry",
                            "chat": "LabAgent",
                            "status": "send_failed",
                            "send_deferred_reason": "wecom_transport_transient",
                            "send_retry_count": 2,
                            "send_errors": [
                                "attempt 1: WeCom Android transport is unavailable"
                            ],
                            "result": {"message": "report", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
                self.assertEqual(claimed["send_retry_count"], 3)
                self.assertEqual(len(claimed["send_failed_repair_history"]), 1)
        finally:
            if original_max is None:
                worker.os.environ.pop("WECOM_TRANSPORT_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECOM_TRANSPORT_SEND_MAX_RETRIES"] = original_max
            if original_backoff is None:
                worker.os.environ.pop("WECOM_TRANSPORT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECOM_TRANSPORT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_claim_next_deferred_send_can_filter_chat(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "other-chat",
                            "chat": "鏈接",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "result": {"message": "other", "files": []},
                        },
                        {
                            "id": "publish-chat",
                            "chat": "懒人科研",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "result": {"message": "publish", "files": []},
                        },
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue, chat_filter="懒人科研")

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["id"], "publish-chat")
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_claim_next_deferred_send_prioritizes_verified_publish_completion(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "older-summary",
                            "chat": "鏈接",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "created_at": "2026-06-23T10:00:00",
                            "result": {"message": "summary", "files": []},
                        },
                        {
                            "id": "verified-publish",
                            "chat": "懒人科研",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "created_at": "2026-06-23T10:10:00",
                            "result": {
                                "message": "published",
                                "files": [],
                                "data": {"publish_stage": {"verified": True, "stage": "published_verified"}},
                            },
                        },
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["id"], "verified-publish")
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_claim_next_deferred_send_uses_newest_within_same_priority(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "older-summary",
                            "chat": "鏈接",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "last_send_attempt_at": "2026-06-23T10:00:00",
                            "result": {"message": "older", "files": []},
                        },
                        {
                            "id": "newer-summary",
                            "chat": "鏈接",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "last_send_attempt_at": "2026-06-23T10:30:00",
                            "result": {"message": "newer", "files": []},
                        },
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["id"], "newer-summary")
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_verified_publish_completion_has_larger_transient_retry_budget(self) -> None:
        worker = load_worker()
        original_max = worker.os.environ.get("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES")
        try:
            worker.os.environ["WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES"] = "12"
            task = {
                "send_deferred_reason": "gui_send_timeout",
                "send_retry_count": 5,
                "result": {
                    "message": "published",
                    "files": [],
                    "data": {"publish_stage": {"verified": True, "stage": "published_verified"}},
                },
            }

            self.assertFalse(worker.transient_send_retry_limit_reached(task))
        finally:
            if original_max is None:
                worker.os.environ.pop("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES"] = original_max

    def test_verified_publish_send_failed_is_retryable(self) -> None:
        worker = load_worker()
        original_max = worker.os.environ.get("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES")
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES"] = "12"
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "verified-publish-failed-send",
                            "chat": "懒人科研",
                            "status": "send_failed",
                            "send_deferred_reason": "gui_send_timeout",
                            "send_retry_count": 5,
                            "send_errors": [
                                "attempt 1: send command failed with exit -15",
                                "transient send retry limit reached (5 attempts)",
                            ],
                            "result": {
                                "message": "published",
                                "files": [],
                                "data": {"publish_stage": {"verified": True, "stage": "published_verified"}},
                            },
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue, chat_filter="懒人科研")

                self.assertIsNotNone(claimed)
                assert claimed is not None
                self.assertEqual(claimed["id"], "verified-publish-failed-send")
                self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_max is None:
                worker.os.environ.pop("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES", None)
            else:
                worker.os.environ["WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES"] = original_max
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

    def test_android_publish_completion_message_is_ascii_and_contains_evidence(self) -> None:
        worker = load_worker()
        result = {
            "message": "已确认发布完成。",
            "files": [],
            "data": {
                "publish_stage": {
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 404,
                    "verified_platforms": ["shipinhao", "youtube", "instagram"],
                    "local_jobs": [{"id": 210, "remote_job_id": "job-1"}],
                    "remote_jobs": [{"id": "job-1"}],
                }
            },
        }

        message = worker.android_publish_completion_message(result)

        self.assertEqual(message.encode("ascii").decode("ascii"), message)
        self.assertIn("video_id 404", message)
        self.assertIn("shipinhao youtube instagram", message)
        self.assertIn("LazyEdit job 210", message)
        self.assertIn("remote job job-1", message)

    def test_nested_agent_envelope_preserves_verified_publish_fallback(self) -> None:
        worker = load_worker()
        result = {
            "message": "published",
            "files": [],
            "data": {
                "message": "published",
                "data": {
                    "publish_stage": {
                        "verified": True,
                        "stage": "published_verified",
                        "video_id": 496,
                        "verified_platforms": ["shipinhao", "youtube", "instagram"],
                        "local_jobs": [{"id": 331, "remote_job_id": "job-4"}],
                        "remote_jobs": [{"id": "job-4"}],
                    }
                },
            },
        }

        self.assertTrue(worker.verified_publish_result_completion(result))
        message = worker.android_publish_completion_message(result)
        self.assertIn("video_id 496", message)
        self.assertIn("LazyEdit job 331", message)
        self.assertIn("remote job job-4", message)

    def test_verified_publish_send_uses_android_fallback_after_title_guard_blank(self) -> None:
        worker = load_worker()
        original_flag = worker.os.environ.get("WECHAT_WORKER_ANDROID_TEXT_FALLBACK")
        result = {
            "message": "已确认发布完成。",
            "files": [],
            "data": {
                "publish_stage": {
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 404,
                    "verified_platforms": ["shipinhao", "youtube", "instagram"],
                    "local_jobs": [{"id": 210, "remote_job_id": "job-1"}],
                    "remote_jobs": [{"id": "job-1"}],
                }
            },
        }
        task = {"id": "publish-task", "chat": "懒人科研"}
        calls: list[str] = []

        def fail_gui(*_args, **_kwargs):
            raise RuntimeError("Opened chat title guard failed for 懒人科研: OCR=''.")

        def fake_android(_result, target_chat, _task, **_kwargs):
            calls.append(target_chat)
            _task["android_text_fallback_send"] = {"sent_at": "now"}

        try:
            worker.os.environ["WECHAT_WORKER_ANDROID_TEXT_FALLBACK"] = "1"
            with mock.patch.object(worker, "send_result_once", side_effect=fail_gui):
                with mock.patch.object(worker, "send_result_text_via_android_fallback", side_effect=fake_android):
                    errors = worker.send_result_with_retries(result, "懒人科研", Path("/tmp/send-targets.json"), task=task)
        finally:
            if original_flag is None:
                worker.os.environ.pop("WECHAT_WORKER_ANDROID_TEXT_FALLBACK", None)
            else:
                worker.os.environ["WECHAT_WORKER_ANDROID_TEXT_FALLBACK"] = original_flag

        self.assertEqual(errors, [])
        self.assertEqual(calls, ["懒人科研"])
        self.assertIn("android_text_fallback_send", task)

    def test_android_text_fallback_uses_guarded_native_sender(self) -> None:
        worker = load_worker()
        result = {
            "message": "已确认发布完成。",
            "files": [],
            "data": {
                "publish_stage": {
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 404,
                    "verified_platforms": ["shipinhao"],
                }
            },
        }

        task = {"id": "publish-task", "chat": "懒人科研"}
        target = {"name": "懒人科研", "expected_title": "懒人科研"}
        with mock.patch.object(worker, "guarded_send_target", return_value=target), mock.patch.object(
            worker,
            "run_android_wechat_sender",
            return_value={"ok": True, "components": [{"status": "sent"}]},
        ) as sender, mock.patch.object(worker, "record_event") as record_event:
            worker.send_result_text_via_android_fallback(
                result,
                "懒人科研",
                task,
            )

        self.assertEqual(sender.call_args.kwargs["task_id"], "publish-task")
        self.assertEqual(sender.call_args.kwargs["target"], target)
        self.assertEqual(sender.call_args.kwargs["messages"], ["已确认发布完成。"])
        record_event.assert_called_once_with(
            chat_name="懒人科研",
            action="android_text_send",
            direction="outbound",
            message="已确认发布完成。",
            status="sent",
            db_path=worker.DEFAULT_DB,
            metadata={"task_id": "publish-task", "transport": "wechat_android"},
        )
        self.assertEqual(task["android_text_fallback_send"]["transport"], "wechat_android")

    def test_android_text_fallback_waits_until_required_file_was_sent(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            result = {"message": "PDF 已附上。", "files": [str(report)]}
            task = {
                "id": "report-task",
                "chat": "Shares鏈接",
                "request": "Send the PDF report.",
                "route_decision": {"route_kind": "research_summary"},
            }
            errors = ["WECHAT_LOCKED: desktop pre-send guard"]

            self.assertFalse(worker.android_text_fallback_allowed(task, result, errors))
            task["sent_file_paths"] = [str(report.resolve())]
            self.assertTrue(worker.android_text_fallback_allowed(task, result, errors))

    def test_claim_next_deferred_send_respects_backoff(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-deferred",
                            "chat": "EchoMind",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "last_send_attempt_at": "2099-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )
                self.assertIsNone(worker.claim_next_deferred_send(queue))
                worker.os.environ["WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS"] = "0"
                claimed = worker.claim_next_deferred_send(queue)
        finally:
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_retry_count"], 1)

    def test_claim_next_deferred_send_retries_gui_busy_when_lane_free(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-gui-busy",
                            "chat": "🍓我的设备",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_busy",
                            "last_send_attempt_at": "2099-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )
                claimed = worker.claim_next_deferred_send(queue)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_retry_count"], 1)

    def test_claim_next_deferred_send_waits_for_busy_gui_lane(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: True
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-gui-busy",
                            "chat": "🍓我的设备",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_busy",
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )
                claimed = worker.claim_next_deferred_send(queue)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNone(claimed)

    def test_claim_next_deferred_send_retries_gui_timeout_when_lane_free(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-gui-timeout",
                            "chat": "EchoMind",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_retry_count"], 1)

    def test_send_retrying_waits_longer_than_sender_timeout(self) -> None:
        worker = load_worker()
        original_stale = worker.os.environ.get("WECHAT_WORKER_STALE_SEND_RETRY_SECONDS")
        original_timeout = worker.os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS")
        try:
            worker.os.environ.pop("WECHAT_WORKER_STALE_SEND_RETRY_SECONDS", None)
            worker.os.environ["WECHAT_WORKER_SEND_TIMEOUT_SECONDS"] = "120"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                claimed_at = (datetime.now() - timedelta(seconds=60)).isoformat(timespec="seconds")
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-active-send",
                            "chat": "🍓我的设备",
                            "status": worker.SEND_RETRYING_STATUS,
                            "send_retry_claimed_at": claimed_at,
                            "send_retry_count": 1,
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)
        finally:
            if original_stale is None:
                worker.os.environ.pop("WECHAT_WORKER_STALE_SEND_RETRY_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_STALE_SEND_RETRY_SECONDS"] = original_stale
            if original_timeout is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_TIMEOUT_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_TIMEOUT_SECONDS"] = original_timeout

        self.assertIsNone(claimed)

    def test_claim_next_deferred_send_waits_for_timeout_when_gui_lane_busy(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: True
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-gui-timeout",
                            "chat": "EchoMind",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "gui_send_timeout",
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNone(claimed)

    def test_claim_next_deferred_send_retries_entry_required_when_lane_free(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_ENTRY_SEND_BACKOFF_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_ENTRY_SEND_BACKOFF_SECONDS"] = "0"
            worker.gui_send_lock_busy = lambda: False
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-entry-required",
                            "chat": "EchoMind",
                            "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                            "send_deferred_reason": "wechat_entry_required",
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "result": {"message": "ok", "confirmation": "", "files": []},
                        }
                    ],
                )

                claimed = worker.claim_next_deferred_send(queue)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_ENTRY_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_ENTRY_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_retry_count"], 1)

    def test_claim_next_deferred_send_handles_required_artifact_delivery(self) -> None:
        worker = load_worker()
        original_backoff = worker.os.environ.get("WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS")
        try:
            worker.os.environ["WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS"] = "0"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                worker.write_tasks(
                    queue,
                    [
                        {
                            "id": "task-artifact-deferred",
                            "chat": "🍓我的设备",
                            "status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                            "send_deferred_reason": "required_artifact_delivery",
                            "last_send_attempt_at": "2026-01-01T00:00:00",
                            "result": {"message": "done", "confirmation": "", "files": ["/tmp/generated.mp4"]},
                        }
                    ],
                )
                claimed = worker.claim_next_deferred_send(queue)
        finally:
            if original_backoff is None:
                worker.os.environ.pop("WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS"] = original_backoff

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertEqual(claimed["send_retry_count"], 1)

    def test_required_artifact_delivery_respects_deferred_backoff(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {"WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS": "300"},
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-artifact-backoff",
                        "chat": "Shares",
                        "status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                        "send_deferred_reason": "required_artifact_delivery",
                        "last_send_attempt_at": datetime.now().isoformat(timespec="seconds"),
                        "result": {
                            "message": "done",
                            "confirmation": "",
                            "files": ["/tmp/report.pdf"],
                        },
                    }
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(int(stored.get("send_retry_count") or 0), 0)

    def test_required_artifact_delivery_stops_at_transient_retry_cap(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS": "0",
                "WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES": "2",
            },
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-artifact-retry-cap",
                        "chat": "Shares",
                        "status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                        "send_deferred_reason": "required_artifact_delivery",
                        "send_retry_count": 2,
                        "last_send_attempt_at": "2026-01-01T00:00:00",
                        "result": {
                            "message": "done",
                            "confirmation": "",
                            "files": ["/tmp/report.pdf"],
                        },
                    }
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)

            self.assertIsNone(claimed)
            stored = worker.read_tasks(queue)[0]

        self.assertEqual(stored["status"], "send_failed")
        self.assertEqual(stored["send_retry_count"], 2)
        self.assertIn("retry limit reached", stored["send_errors"][-1])

    def test_repair_missing_artifact_delivery_requeues_done_mp4(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "unsent.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-done-unsent",
                        "chat": "🍓我的设备",
                        "status": "done",
                        "completed_at": "2026-01-01T00:00:00",
                        "result": {"message": "sent", "confirmation": "", "files": [str(video)]},
                    }
                ],
            )

            payload = worker.repair_missing_artifact_deliveries(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(payload["repaired_count"], 1)
        self.assertEqual(tasks[0]["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(tasks[0]["send_deferred_reason"], "required_artifact_delivery")
        self.assertNotIn("completed_at", tasks[0])

    def test_repair_missing_artifact_delivery_skips_best_effort_research_files(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            summary = tmp_path / "summary.md"
            summary.write_text("summary", encoding="utf-8")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-done-research",
                        "chat": "鏈接",
                        "status": "done",
                        "completed_at": "2026-01-01T00:00:00",
                        "route_decision": {"route_kind": "research_or_summary"},
                        "result": {"message": "sent", "confirmation": "", "files": [str(summary)]},
                    }
                ],
            )

            payload = worker.repair_missing_artifact_deliveries(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(payload["repaired_count"], 0)
        self.assertEqual(tasks[0]["status"], "done")

    def test_repair_missing_artifact_delivery_skips_sent_mp4(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "sent.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-done-sent",
                        "chat": "🍓我的设备",
                        "status": "done",
                        "completed_at": "2026-01-01T00:00:00",
                        "sent_file_paths": [str(video.resolve())],
                        "result": {"message": "sent", "confirmation": "", "files": [str(video)]},
                    }
                ],
            )

            payload = worker.repair_missing_artifact_deliveries(queue)
            tasks = worker.read_tasks(queue)

        self.assertEqual(payload["repaired_count"], 0)
        self.assertEqual(tasks[0]["status"], "done")

    def test_repair_missing_artifact_delivery_does_not_loop_terminal_send_failure(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "unsent.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "task-terminal-send-failure",
                        "chat": "Shares",
                        "status": "send_failed",
                        "send_retry_count": 2,
                        "result": {
                            "message": "done",
                            "confirmation": "",
                            "files": [str(report)],
                        },
                    }
                ],
            )

            first = worker.repair_missing_artifact_deliveries(queue)
            second = worker.repair_missing_artifact_deliveries(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertEqual(first["repaired_count"], 0)
        self.assertEqual(second["repaired_count"], 0)
        self.assertEqual(stored["status"], "send_failed")
        self.assertEqual(stored["send_retry_count"], 2)

    def test_claim_deferred_send_renews_bounded_delivery_lease(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_DEFERRED_SEND_GLOBAL_COOLDOWN_SECONDS": "0",
                "WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS": "0",
            },
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "renew-lease",
                        "chat": "Shares",
                        "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "send_expires_at": "2999-01-01T00:00:00",
                        "last_send_attempt_at": "2000-01-01T00:00:00",
                        "result": {"message": "reply", "files": []},
                    }
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["status"], worker.SEND_RETRYING_STATUS)
        self.assertNotEqual(claimed["send_expires_at"], "2999-01-01T00:00:00")
        renewed = worker.parse_iso_datetime(claimed["send_expires_at"])
        self.assertIsNotNone(renewed)
        assert renewed is not None
        remaining = (renewed - worker.datetime.now()).total_seconds()
        self.assertGreater(remaining, 25 * 60)
        self.assertLessEqual(remaining, 30 * 60)

    def test_recover_recent_expired_transport_delivery_is_bounded_and_scoped(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            now = worker.datetime.now()
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "wecom-recent",
                        "chat": "wecom:external-gui:group:one",
                        "status": "send_expired",
                        "source": {"transport": "wecom"},
                        "expired_from_status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "expired_at": (now - worker.timedelta(minutes=5)).isoformat(timespec="seconds"),
                        "send_deferred_reason": "gui_compose_verification",
                        "result": {"message": "done", "confirmation": "", "files": [str(report)]},
                    },
                    {
                        "id": "wechat-recent",
                        "chat": "other",
                        "status": "send_expired",
                        "source": {"transport": "wechat"},
                        "expired_from_status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "expired_at": (now - worker.timedelta(minutes=5)).isoformat(timespec="seconds"),
                        "result": {"message": "other", "confirmation": "", "files": []},
                    },
                    {
                        "id": "wecom-stale",
                        "chat": "wecom:external-gui:group:old",
                        "status": "send_expired",
                        "route": {"transport": "wecom"},
                        "expired_from_status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                        "expired_at": (now - worker.timedelta(hours=13)).isoformat(timespec="seconds"),
                        "result": {"message": "old", "confirmation": "", "files": [str(report)]},
                    },
                ],
            )

            payload = worker.recover_recent_expired_transport_deliveries(
                queue,
                transport="wecom",
                max_age_seconds=12 * 60 * 60,
                limit=1,
            )
            tasks = {task["id"]: task for task in worker.read_tasks(queue)}

        self.assertEqual(payload["recovered_count"], 1)
        self.assertEqual(tasks["wecom-recent"]["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(tasks["wecom-recent"]["send_deferred_reason"], "transport_reconnected")
        self.assertEqual(tasks["wecom-recent"]["transport_recovery_count"], 1)
        self.assertEqual(tasks["wecom-recent"]["send_retry_count"], 0)
        self.assertEqual(tasks["wechat-recent"]["status"], "send_expired")
        self.assertEqual(tasks["wecom-stale"]["status"], "send_expired")

    def test_recover_recent_expired_transport_delivery_does_not_requeue_twice(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "wecom-once",
                        "chat": "wecom:external-gui:group:one",
                        "status": "send_expired",
                        "source": {"transport": "wecom"},
                        "expired_from_status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "expired_at": worker.datetime.now().isoformat(timespec="seconds"),
                        "result": {"message": "done", "confirmation": "", "files": []},
                    }
                ],
            )

            first = worker.recover_recent_expired_transport_deliveries(queue, transport="wecom")
            second = worker.recover_recent_expired_transport_deliveries(queue, transport="wecom")

        self.assertEqual(first["recovered_count"], 1)
        self.assertEqual(second["recovered_count"], 0)

    def test_recover_expired_transport_can_target_one_exact_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            now = worker.datetime.now().isoformat(timespec="seconds")
            common = {
                "chat": "Shares",
                "status": "send_expired",
                "source": {"transport": "wechat"},
                "expired_from_status": worker.SEND_DEFERRED_LOCKED_STATUS,
                "expired_at": now,
                "result": {"message": "stored reply", "files": []},
            }
            worker.write_tasks(
                queue,
                [
                    {"id": "recover-me", **common},
                    {"id": "leave-expired", **common},
                ],
            )

            payload = worker.recover_recent_expired_transport_deliveries(
                queue,
                transport="wechat",
                task_ids=["recover-me"],
            )
            tasks = {task["id"]: task for task in worker.read_tasks(queue)}

        self.assertEqual(payload["recovered_count"], 1)
        self.assertEqual(tasks["recover-me"]["send_deferred_reason"], "transport_reconnected")
        self.assertEqual(tasks["leave-expired"]["status"], "send_expired")

    def test_recover_recent_expired_transport_infers_legacy_personal_wechat_route(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "legacy-wechat",
                        "chat": "写作 外语 挣钱",
                        "status": "send_expired",
                        "route": {
                            "config_id": "xiezuo-waiyu-zhengqian-direct-chatops.local.json",
                            "message_table": "Msg_deadbeef",
                        },
                        "expired_from_status": "send_failed",
                        "expired_at": worker.datetime.now().isoformat(timespec="seconds"),
                        "result": {"message": "done", "confirmation": "", "files": []},
                    }
                ],
            )

            payload = worker.recover_recent_expired_transport_deliveries(
                queue,
                transport="wechat",
            )
            task = worker.read_tasks(queue)[0]

        self.assertEqual(payload["recovered_count"], 1)
        self.assertEqual(task["send_deferred_reason"], "transport_reconnected")

    def test_recover_recent_expired_transport_delivery_deduplicates_same_artifacts(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first_dir = tmp_path / "first"
            second_dir = tmp_path / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first_report = first_dir / "report.pdf"
            second_report = second_dir / "report.pdf"
            first_report.write_bytes(b"same-report")
            second_report.write_bytes(b"same-report")
            now = worker.datetime.now()
            queue = tmp_path / "queue.jsonl"
            common = {
                "chat": "wecom:external-gui:group:one",
                "status": "send_expired",
                "source": {"transport": "wecom"},
                "expired_from_status": worker.SEND_DEFERRED_LOCKED_STATUS,
            }
            worker.write_tasks(
                queue,
                [
                    {
                        **common,
                        "id": "older",
                        "expired_at": (now - worker.timedelta(minutes=2)).isoformat(timespec="seconds"),
                        "result": {"message": "old wording", "confirmation": "", "files": [str(first_report)]},
                    },
                    {
                        **common,
                        "id": "newer",
                        "expired_at": (now - worker.timedelta(minutes=1)).isoformat(timespec="seconds"),
                        "result": {"message": "new wording", "confirmation": "", "files": [str(second_report)]},
                    },
                ],
            )

            payload = worker.recover_recent_expired_transport_deliveries(queue, transport="wecom", limit=3)
            tasks = {task["id"]: task for task in worker.read_tasks(queue)}

        self.assertEqual(payload["recovered_count"], 1)
        self.assertEqual(tasks["newer"]["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(tasks["older"]["status"], "send_expired")
        self.assertIn(
            {"id": "older", "reason": "duplicate_recent_delivery"},
            payload["skipped"],
        )

    def test_send_result_does_not_attach_markdown_pdf_companion_by_default(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        files: list[Path] = []
        original_message = worker.send_message
        original_file = worker.send_file
        original_render = worker.render_markdown_pdf
        original_language_source = worker.ensure_markdown_language_source
        try:
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(message)
            worker.send_file = lambda file_path, *_args, **_kwargs: files.append(Path(file_path))

            def fake_language_source(source: Path, language: str) -> Path:
                translated = source.with_name(f"{source.stem}.{language}.md")
                translated.write_text(f"# Story {language}\n", encoding="utf-8")
                return translated

            def fake_render_markdown_pdf(source: Path, output: Path) -> Path:
                output.write_bytes(b"%PDF-1.4\n")
                return output

            worker.ensure_markdown_language_source = fake_language_source
            worker.render_markdown_pdf = fake_render_markdown_pdf
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                story = root / "story.md"
                preview = root / "preview.png"
                story.write_text("# Story\n", encoding="utf-8")
                preview.write_bytes(b"png")
                task: dict[str, object] = {}
                worker.send_result_once(
                    {
                        "message": "done",
                        "confirmation": "",
                        "files": [str(story), str(preview)],
                    },
                    "🍓我的设备",
                    Path("/tmp/no-targets.json"),
                    target={"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"},
                    task=task,
                )
        finally:
            worker.send_message = original_message
            worker.send_file = original_file
            worker.ensure_markdown_language_source = original_language_source
            worker.render_markdown_pdf = original_render

        self.assertEqual(files, [story, preview])
        self.assertNotIn("unsent_saved_files", task)
        self.assertEqual(messages, ["done"])

    def test_research_summary_suppresses_optional_report_artifacts(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        files: list[Path] = []
        original_message = worker.send_message
        original_file = worker.send_file
        try:
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(message)
            worker.send_file = lambda file_path, *_args, **_kwargs: files.append(Path(file_path))
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = root / "summary.md"
                preview = root / "thumbnail.png"
                report.write_text("# Notes\n", encoding="utf-8")
                preview.write_bytes(b"png")
                task: dict[str, object] = {
                    "routine": {"id": "research_summary"},
                    "route_decision": {"route_kind": "research_or_summary"},
                    "request": "Current coalesced request:\nread this link",
                }
                worker.send_result_once(
                    {
                        "message": "I could only read the page metadata; the article body was blocked.",
                        "confirmation": "",
                        "files": [str(report), str(preview)],
                    },
                    "鏈接",
                    Path("/tmp/no-targets.json"),
                    target={"name": "鏈接", "query": "鏈接", "expected_title": "鏈接"},
                    task=task,
                )
        finally:
            worker.send_message = original_message
            worker.send_file = original_file

        self.assertEqual(files, [])
        self.assertEqual(messages, ["I could only read the page metadata; the article body was blocked."])
        self.assertEqual(len(task["suppressed_chat_files"]), 2)

    def test_message_only_contract_overrides_agent_forced_pdf_delivery(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "message_only": True,
                "artifact_delivery": "forbidden",
            },
            "execution_contract": {
                "required_artifacts": [],
                "artifact_delivery": "forbidden",
            },
            "request": "Return one message. Create no files or attachments.",
        }
        result = {
            "message": "One useful idea.",
            "files": ["/tmp/unrequested-report.pdf"],
            "data": {
                "require_file_delivery": True,
                "send_report_to_wechat": True,
            },
        }

        worker.enforce_worker_result_response_policy(task, result)

        self.assertFalse(worker.result_requires_file_delivery(task, result))
        self.assertFalse(worker.result_allows_chat_artifact_delivery(task, result))
        self.assertEqual(worker.required_delivery_file_paths(result, task), [])
        self.assertFalse(result["data"]["require_file_delivery"])
        self.assertFalse(result["data"]["send_report_to_wechat"])
        self.assertEqual(result["data"]["artifact_delivery"], "local_only")

    def test_message_only_contract_creates_missing_delivery_data(self) -> None:
        worker = load_worker()
        task = {
            "route_decision": {
                "message_only": True,
                "artifact_delivery": "forbidden",
            }
        }
        result = {"message": "One useful idea.", "files": []}

        worker.enforce_worker_result_response_policy(task, result)

        self.assertFalse(result["data"]["require_file_delivery"])
        self.assertFalse(result["data"]["send_report_to_wechat"])
        self.assertEqual(result["data"]["artifact_delivery"], "local_only")

    def test_reader_facing_pdf_quality_rejects_internal_work_record(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Prepare and send a PDF research report.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            internal_text = (
                "Reader title " + ("substantive evidence " * 30)
                + "\n任务: wecom-inspiration-20260824-abcd\n"
                + "聊天: wecom:external-gui:group:private\n"
                + "输出契约 {\"message\": \"\", \"files\": []}"
            )
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(internal_text, ""),
            ):
                result = worker.enforce_reader_facing_pdf_quality(
                    task,
                    {"message": "Report ready.", "files": [str(report)]},
                )

        self.assertEqual(result["files"], [])
        issues = result["data"]["pdf_quality_rejections"][0]["issues"]
        self.assertIn("internal_task_identity", issues)
        self.assertIn("transport_identity", issues)
        self.assertIn("agent_output_contract", issues)

    def test_reader_facing_pdf_allows_reproducible_tmp_example_but_rejects_private_paths(self) -> None:
        worker = load_worker()
        patterns = worker.PDF_INTERNAL_TRANSPORT_PATTERNS

        example_issues = {
            label
            for pattern, label in patterns
            if pattern.search("Create an isolated environment at /tmp/venvcheck.")
        }
        private_issues = {
            label
            for pattern, label in patterns
            if pattern.search(
                "/home/lachlan/ProjectsLFS/AgenticApp/output/wecom/private-report.pdf"
            )
        }
        temporary_worker_issues = {
            label
            for pattern, label in patterns
            if pattern.search("/tmp/labcanvas-task-123/report.md")
        }

        self.assertNotIn("private_runtime_path", example_issues)
        self.assertIn("private_runtime_path", private_issues)
        self.assertIn("private_runtime_path", temporary_worker_issues)

    def test_pdf_quality_extractor_reads_pdftotext_from_stdout(self) -> None:
        worker = load_worker()
        report = Path("/tmp/reader-report.pdf")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Reader-facing report text",
            stderr="",
        )
        with (
            mock.patch.object(worker.shutil, "which", return_value="/usr/bin/pdftotext"),
            mock.patch.object(worker.subprocess, "run", return_value=completed) as run,
        ):
            text, error = worker.extract_pdf_text_for_quality(report)

        self.assertEqual(text, "Reader-facing report text")
        self.assertEqual(error, "")
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/pdftotext", "-layout", "-nopgbrk", str(report), "-"],
        )

    def test_pdf_page_quality_extractor_preserves_page_boundaries(self) -> None:
        worker = load_worker()
        report = Path("/tmp/reader-report.pdf")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="First page\fSecond page\f",
            stderr="",
        )
        with (
            mock.patch.object(worker.shutil, "which", return_value="/usr/bin/pdftotext"),
            mock.patch.object(worker.subprocess, "run", return_value=completed) as run,
        ):
            pages, error = worker.extract_pdf_page_texts_for_quality(report)

        self.assertEqual(pages, ["First page", "Second page"])
        self.assertEqual(error, "")
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/pdftotext", "-layout", str(report), "-"],
        )

    def test_pdf_layout_quality_rejects_orphan_final_page(self) -> None:
        worker = load_worker()
        pages = [
            "LABCANVAS RESEARCH BRIEF August 25, 2026\n" + ("A" * 900) + "\n1",
            "LABCANVAS RESEARCH BRIEF August 25, 2026\n" + ("B" * 1100) + "\n2",
            "LABCANVAS RESEARCH BRIEF August 25, 2026\n"
            + ("Evidence boundary note. " * 4)
            + "\n3",
        ]
        with mock.patch.object(
            worker,
            "extract_pdf_page_texts_for_quality",
            return_value=(pages, ""),
        ):
            audit = worker.analyze_pdf_layout_for_quality(Path("/tmp/report.pdf"))

        self.assertEqual(audit["page_count"], 3)
        self.assertIn("orphan_final_pdf_page", audit["issues"])
        self.assertNotIn("blank_or_nearly_blank_pdf_page", audit["issues"])

    def test_pdf_layout_quality_accepts_substantive_final_page(self) -> None:
        worker = load_worker()
        pages = ["A" * 900, "B" * 1100, "C" * 700]
        with mock.patch.object(
            worker,
            "extract_pdf_page_texts_for_quality",
            return_value=(pages, ""),
        ):
            audit = worker.analyze_pdf_layout_for_quality(Path("/tmp/report.pdf"))

        self.assertEqual(audit["issues"], [])

    def test_terminal_report_note_is_relocated_before_references(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.md"
            report.write_text(
                "# Report\n\n"
                "## Evidence boundary\n\nSubstantive discussion.\n\n"
                "## 参考文献\n\n1. Source A.\n\n2. Source B.\n\n"
                "**证据边界说明**：该说明应与正文相邻，而不是单独占据末页。\n",
                encoding="utf-8",
            )

            first = worker.relocate_terminal_report_note_before_references(report)
            revised = report.read_text(encoding="utf-8")
            second = worker.relocate_terminal_report_note_before_references(report)

        self.assertTrue(first["changed"])
        self.assertLess(revised.index("证据边界说明"), revised.index("## 参考文献"))
        self.assertIn("1. Source A.", revised)
        self.assertFalse(second["changed"])

    def test_preferred_research_pdf_rebuilds_stale_exact_sibling(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.zh.md"
            pdf = root / "report.zh.pdf"
            pdf.write_bytes(b"old-pdf")
            report.write_text("# 新报告\n", encoding="utf-8")
            os.utime(pdf, (1, 1))

            def fake_render(_source: Path, output: Path) -> Path:
                output.write_bytes(b"new-pdf")
                return output

            with mock.patch.object(
                worker,
                "render_markdown_pdf",
                side_effect=fake_render,
            ) as render:
                selected = worker.preferred_research_report_pdf(report, "zh")
                pdf_bytes = pdf.read_bytes()

        self.assertEqual(selected, pdf)
        self.assertEqual(pdf_bytes, b"new-pdf")
        render.assert_called_once_with(report, pdf)

    def test_completion_recovery_repaginates_terminal_note_before_model_repair(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "reader-report.md"
            report.write_text(
                "# Report\n\n## Evidence\n\nMethods and results.\n\n"
                "## References\n\n1. Source A.\n\n2. Source B.\n\n"
                "**Evidence note**: This short note belongs before the references.\n",
                encoding="utf-8",
            )
            pdf = root / "reader-report.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            task = {
                "id": "layout-repair",
                "artifact_dir": str(root),
                "routine": {"id": "research_summary"},
                "route_decision": {"route_kind": "research_or_summary"},
                "request": "Create and return the PDF report.",
            }
            bad = {
                "message": "Report ready.",
                "files": [],
                "data": {
                    "report_path": str(report),
                    "pdf_quality_rejections": [
                        {
                            "path": str(pdf),
                            "issues": ["orphan_final_pdf_page"],
                        }
                    ],
                },
            }
            good = {
                "message": "Report ready.",
                "files": [str(pdf)],
                "data": {
                    "report_path": str(report),
                    "pdf_quality_rejections": [],
                },
            }
            audit = {
                "status": "checked",
                "coverage_complete": True,
                "covered_item_ids": ["task:layout-repair"],
                "missing": [],
                "repair_recommended": False,
            }
            attempts: list[dict[str, object]] = []
            with (
                mock.patch.object(
                    worker,
                    "recover_completed_research_artifacts",
                    side_effect=[{"files": [str(pdf)]}, {"files": [str(pdf)]}],
                ) as recover,
                mock.patch.object(
                    worker,
                    "enforce_reader_facing_pdf_quality",
                    side_effect=[bad, good],
                ),
                mock.patch.object(worker, "run_completion_audit", return_value=audit),
            ):
                result, recovered_audit, accepted = worker.recover_completion_pdf_artifact(
                    task,
                    {"message": "draft", "files": []},
                    attempts,
                    stage="deterministic_recovery",
                )

            revised = report.read_text(encoding="utf-8")

        self.assertTrue(accepted)
        self.assertEqual(recovered_audit, audit)
        self.assertIn(str(pdf), result["files"])
        self.assertEqual(recover.call_count, 2)
        self.assertLess(revised.index("Evidence note"), revised.index("## References"))
        self.assertIn(
            "deterministic_recovery:host_layout_repair",
            [str(item.get("stage")) for item in attempts],
        )

    def test_pdf_render_audit_persists_page_previews_and_manifest(self) -> None:
        worker = load_worker()
        task = {
            "execution_contract": {
                "required_artifacts": ["compiled_pdf", "render_audit"],
                "report_quality": {"independent_review_before_delivery": True},
            }
        }
        layout = {
            "status": "checked",
            "page_count": 2,
            "page_body_char_counts": [800, 700],
            "issues": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")

            def fake_render(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                prefix = Path(command[-1])
                prefix.with_name(prefix.name + "-1.png").write_bytes(b"png-one")
                prefix.with_name(prefix.name + "-2.png").write_bytes(b"png-two")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                mock.patch.object(worker.shutil, "which", return_value="/usr/bin/pdftoppm"),
                mock.patch.object(worker.subprocess, "run", side_effect=fake_render),
            ):
                audit = worker.persist_pdf_render_audit(task, report, layout)

            manifest = Path(audit["manifest_path"])
            payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(payload["render_status"], "rendered")
        self.assertEqual(payload["page_count"], 2)
        self.assertEqual(payload["rendered_pages"], ["page-1.png", "page-2.png"])

    def test_pdf_render_audit_retries_a_cached_failed_render(self) -> None:
        worker = load_worker()
        task = {
            "execution_contract": {
                "required_artifacts": ["compiled_pdf", "render_audit"],
            }
        }
        layout = {
            "status": "checked",
            "page_count": 1,
            "page_body_char_counts": [800],
            "issues": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            audit_dir = report.parent / "report-render-audit"
            audit_dir.mkdir()
            source = {
                "filename": report.name,
                "bytes": report.stat().st_size,
                "mtime_ns": report.stat().st_mtime_ns,
            }
            (audit_dir / "render-audit.json").write_text(
                json.dumps(
                    {
                        "version": worker.PDF_LAYOUT_AUDIT_VERSION,
                        "source": source,
                        "page_count": 1,
                        "render_status": "failed",
                        "rendered_pages": [],
                    }
                ),
                encoding="utf-8",
            )

            def fake_render(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                prefix = Path(command[-1])
                prefix.with_name(prefix.name + "-1.png").write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                mock.patch.object(worker.shutil, "which", return_value="/usr/bin/pdftoppm"),
                mock.patch.object(worker.subprocess, "run", side_effect=fake_render) as run,
            ):
                audit = worker.persist_pdf_render_audit(task, report, layout)

        self.assertEqual(audit["render_status"], "rendered")
        self.assertEqual(run.call_count, 1)

    def test_markdown_pdf_retries_compact_layout_for_orphan_final_page(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "report.md"
            output = root / "report.pdf"
            source.write_text("# Report\n\nSubstantive content.\n", encoding="utf-8")

            def fake_compile(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                destination = Path(command[command.index("-o") + 1])
                compact = str(worker.NATURE_REPORT_COMPACT_LATEX_HEADER) in command
                destination.write_bytes(b"compact-pdf" if compact else b"normal-pdf")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                mock.patch.object(
                    worker,
                    "resolve_markdown_pdf_tool",
                    return_value="/usr/bin/pandoc",
                ),
                mock.patch.object(worker.subprocess, "run", side_effect=fake_compile) as run,
                mock.patch.object(
                    worker,
                    "analyze_pdf_layout_for_quality",
                    side_effect=[
                        {"issues": ["orphan_final_pdf_page"]},
                        {"issues": []},
                    ],
                ),
            ):
                rendered = worker.render_markdown_pdf(source, output)
                final_bytes = output.read_bytes()

        self.assertEqual(rendered, output.resolve())
        self.assertEqual(final_bytes, b"compact-pdf")
        self.assertEqual(run.call_count, 2)
        self.assertIn(
            str(worker.NATURE_REPORT_COMPACT_LATEX_HEADER),
            run.call_args_list[1].args[0],
        )

    def test_markdown_pdf_removes_failed_compact_retry(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "report.md"
            output = root / "report.pdf"
            source.write_text("# Report\n\nSubstantive content.\n", encoding="utf-8")

            def fake_compile(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                destination = Path(command[command.index("-o") + 1])
                compact = str(worker.NATURE_REPORT_COMPACT_LATEX_HEADER) in command
                destination.write_bytes(b"compact-pdf" if compact else b"normal-pdf")
                return subprocess.CompletedProcess(
                    command,
                    1 if compact else 0,
                    "",
                    "failed",
                )

            with (
                mock.patch.object(
                    worker,
                    "resolve_markdown_pdf_tool",
                    return_value="/usr/bin/pandoc",
                ),
                mock.patch.object(worker.subprocess, "run", side_effect=fake_compile),
                mock.patch.object(
                    worker,
                    "analyze_pdf_layout_for_quality",
                    return_value={"issues": ["orphan_final_pdf_page"]},
                ),
            ):
                rendered = worker.render_markdown_pdf(source, output)
                compact_output = root / "report.compact.tmp.pdf"

            self.assertEqual(rendered, output.resolve())
            self.assertFalse(compact_output.exists())

    def test_reader_facing_pdf_quality_rejects_orphan_final_page(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Prepare and send a PDF research report.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "orphan-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            clean_text = "Research report\n" + ("Verified evidence and analysis. " * 40)
            layout = {
                "status": "checked",
                "page_count": 4,
                "page_body_char_counts": [900, 850, 1000, 80],
                "issues": ["orphan_final_pdf_page"],
            }
            with (
                mock.patch.object(
                    worker,
                    "extract_pdf_text_for_quality",
                    return_value=(clean_text, ""),
                ),
                mock.patch.object(
                    worker,
                    "analyze_pdf_layout_for_quality",
                    return_value=layout,
                ),
            ):
                result = worker.enforce_reader_facing_pdf_quality(
                    task,
                    {"message": "Report ready.", "files": [str(report)]},
                )

        self.assertEqual(result["files"], [])
        self.assertIn(
            "orphan_final_pdf_page",
            result["data"]["pdf_quality_rejections"][0]["issues"],
        )

    def test_reader_facing_pdf_quality_accepts_substantive_clean_report(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Prepare and send a PDF research report.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "lumenbench-handoff.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            clean_text = "LumenBench project handoff\n" + ("Verified current state and evidence. " * 30)
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(clean_text, ""),
            ):
                result = worker.enforce_reader_facing_pdf_quality(
                    task,
                    {"message": "Report ready.", "files": [str(report)]},
                )

        self.assertEqual(result["files"], [str(report.resolve())])
        self.assertEqual(result["data"]["pdf_quality_rejections"], [])

    def test_reader_facing_research_pdf_requires_sources_limits_and_next_steps(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "execution_contract": {
                "research_evidence": {
                    "required": True,
                    "minimum_traceable_sources": 2,
                    "state_uncertainty_and_limitations": True,
                    "include_actionable_next_steps": True,
                }
            },
            "request": "Prepare and send a source-grounded PDF research report.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "shallow-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            shallow_text = "Research report\n" + ("General background without traceable evidence. " * 35)
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(shallow_text, ""),
            ):
                issues = worker.reader_facing_pdf_quality_issues(task, report)

        self.assertIn("insufficient_traceable_research_sources", issues)
        self.assertIn("missing_reader_evidence_section", issues)
        self.assertIn("missing_uncertainty_or_limitations", issues)
        self.assertIn("missing_actionable_next_steps", issues)

    def test_scheduled_full_report_rejects_polished_summary_reflow(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "scheduled_daily_research": True,
            },
            "daily_research": {"topics": ["organoid imaging"]},
            "execution_contract": {
                "research_evidence": {
                    "required": True,
                    "minimum_traceable_sources": 3,
                    "state_uncertainty_and_limitations": True,
                    "include_actionable_next_steps": True,
                },
                "report_quality": {
                    "materially_deeper_than_chat": True,
                    "required_dimensions": [
                        "source_level_methods_results_and_limitations",
                        "cross_source_synthesis_and_tensions",
                        "evidence_boundaries_and_uncertainty",
                        "actionable_experiments_or_decisions",
                        "complete_traceable_references",
                    ],
                },
            },
            "request": "Prepare the full daily report PDF.",
        }
        polished_summary = """
        每日研究简报
        三篇论文形成感知、控制、预测的闭环。
        DOI: 10.1000/source-a DOI: 10.1000/source-b DOI: 10.1000/source-c
        论文一准确率 70%，论文二活力 95%，论文三减少约 50%。
        合读与综合分析表明三者互补。
        局限与不确定性：这些数据尚未独立复现。
        """ + ("背景信息。" * 180)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "daily-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(polished_summary, ""),
            ):
                issues = worker.reader_facing_pdf_quality_issues(task, report)

        self.assertIn("missing_actionable_next_steps", issues)
        self.assertIn("missing_source_level_methods_results_limits", issues)
        self.assertIn("missing_actionable_experiments_or_decisions", issues)
        self.assertIn("missing_complete_reference_section", issues)
        self.assertNotIn("missing_cross_source_synthesis", issues)

    def test_scheduled_full_report_accepts_explicit_depth_dimensions(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "execution_contract": {
                "research_evidence": {
                    "required": True,
                    "minimum_traceable_sources": 3,
                    "state_uncertainty_and_limitations": True,
                    "include_actionable_next_steps": True,
                },
                "report_quality": {
                    "required_dimensions": [
                        "source_level_methods_results_and_limitations",
                        "cross_source_synthesis_and_tensions",
                        "evidence_boundaries_and_uncertainty",
                        "actionable_experiments_or_decisions",
                        "complete_traceable_references",
                    ]
                },
            },
            "request": "Prepare the full daily report PDF.",
        }
        full_report = """
        # 证据与方法
        研究设计与实验系统：比较队列、样本、对照组和数据集。
        主要结果与定量结果：准确率 82%，并报告 AUROC 0.86。
        DOI: 10.1000/source-a DOI: 10.1000/source-b DOI: 10.1000/source-c
        # 跨论文综合分析
        三项研究的一致之处与分歧构成可检验张力。
        # 证据边界与局限
        直接证据、间接证据、假设和不确定性分开陈述。
        # 下一步与建议实验
        优先实验是独立队列复现，并预注册决策阈值。
        九、完整可追溯参考文献
        1. Source A. doi:10.1000/source-a
        2. Source B. doi:10.1000/source-b
        3. Source C. doi:10.1000/source-c
        """ + ("证据解释与决策影响。" * 100)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "daily-report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(full_report, ""),
            ):
                issues = worker.reader_facing_pdf_quality_issues(task, report)

        self.assertEqual(issues, [])

    def test_research_evidence_accepts_per_source_result_claim_heading(self) -> None:
        worker = load_worker()
        report = """
        一、读者证据速览
        DOI: 10.1000/source-a DOI: 10.1000/source-b DOI: 10.1000/source-c

        三、论文一
        方法（来源层面）
        比较实验组、对照组和纵向成像数据集。
        结果 / 主张（作者报告）
        作者报告成熟度提升，并给出定量读出。
        局限（来源层面）
        样本规模和跨批次泛化仍不确定。

        六、跨来源综合分析
        三项研究的一致之处与分歧构成可检验张力。
        七、证据边界与局限
        直接证据、推断和不确定性分开陈述。
        八、可执行下一步
        优先实验是独立队列复现，并预注册决策阈值。
        九、完整参考文献
        1. Source A. doi:10.1000/source-a
        2. Source B. doi:10.1000/source-b
        3. Source C. doi:10.1000/source-c
        """

        evidence = worker.research_report_evidence_summary(report)

        self.assertTrue(evidence["has_methods_detail"])
        self.assertTrue(evidence["has_results_detail"])
        self.assertTrue(evidence["has_uncertainty"])

    def test_standards_report_accepts_methods_mechanism_facts_and_qualified_references(self) -> None:
        worker = load_worker()
        report = """
        ## 证据与方法
        2. 方法
        对 Python 官方文档、PEP 405 和 PEP 668 做来源核查，并比较规范边界。

        3. 来源一
        机制事实：虚拟环境通过独立解释器前缀隔离项目依赖。
        https://docs.python.org/3/library/venv.html

        4. 来源二
        规范事实：PEP 405 定义 pyvenv.cfg 与解释器前缀行为。
        https://peps.python.org/pep-0405/

        5. 来源三
        核查结果：PEP 668 区分外部管理的系统环境和项目环境。
        https://peps.python.org/pep-0668/

        ## 跨来源综合分析
        三个来源的一致之处是将系统包管理与项目依赖分离，张力在于工具责任边界。

        ## 证据边界与局限
        规范事实不等同于所有 Linux 发行版的实测行为，仍有不确定性。

        ## 下一步
        在目标发行版运行 /tmp/venvcheck，并记录解释器与 pip 前缀作为验证。

        7. 参考文献（可追溯）
        1. Python venv documentation. https://docs.python.org/3/library/venv.html
        2. PEP 405. https://peps.python.org/pep-0405/
        3. PEP 668. https://peps.python.org/pep-0668/
        """

        evidence = worker.research_report_evidence_summary(report)

        self.assertEqual(evidence["traceable_source_count"], 3)
        self.assertTrue(evidence["has_evidence_section"])
        self.assertTrue(evidence["has_methods_detail"])
        self.assertTrue(evidence["has_results_detail"])
        self.assertTrue(evidence["has_cross_source_synthesis"])
        self.assertTrue(evidence["has_uncertainty"])
        self.assertTrue(evidence["has_actionable_next_steps"])
        self.assertTrue(evidence["has_reference_section"])

    def test_reader_facing_pdf_quality_rejects_corrupt_searchable_text(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Prepare and send a PDF research report.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            extracted = "Reader-facing report\n" + ("Verified evidence and analysis. " * 30)
            extracted = extracted.replace("Verified", "Ver\x1cied", 1)
            with mock.patch.object(
                worker,
                "extract_pdf_text_for_quality",
                return_value=(extracted, ""),
            ):
                result = worker.enforce_reader_facing_pdf_quality(
                    task,
                    {"message": "Report ready.", "files": [str(report)]},
                )

        self.assertEqual(result["files"], [])
        self.assertIn(
            "broken_text_extraction",
            result["data"]["pdf_quality_rejections"][0]["issues"],
        )

    def test_required_delivery_includes_source_and_cad_artifacts(self) -> None:
        worker = load_worker()
        result = {
            "files": [
                "/tmp/story.md",
                "/tmp/paper.tex",
                "/tmp/render.png",
                "/tmp/board.kicad_pcb",
                "/tmp/model.step",
                "/tmp/video.mp4",
            ]
        }

        required = [path.suffix for path in worker.required_delivery_file_paths(result)]

        self.assertEqual(required, [".md", ".tex", ".png", ".kicad_pcb", ".step", ".mp4"])

    def test_wecom_research_delivery_keeps_sources_local_by_default(self) -> None:
        worker = load_worker()
        task = {
            "source": {"transport": "wecom"},
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Write Markdown and LaTeX sources, then send the compiled PDF.",
        }
        files = [Path("/tmp/report.pdf"), Path("/tmp/report.md"), Path("/tmp/report.tex")]

        selected = worker.wecom_research_delivery_files(task, files)

        self.assertEqual(selected, [Path("/tmp/report.pdf")])

    def test_wechat_research_required_delivery_ignores_local_markdown_source(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "require_file_delivery": True,
            },
            "request": "Please send the finished report PDF.",
        }
        result = {
            "files": [
                "/tmp/report.pdf",
                "/tmp/report.md",
            ]
        }

        required = worker.required_delivery_file_paths(result, task)

        self.assertEqual(required, [Path("/tmp/report.pdf")])
        self.assertEqual(task["suppressed_chat_files"], ["/tmp/report.md"])

    def test_wecom_research_delivery_allows_explicit_source_request(self) -> None:
        worker = load_worker()
        task = {
            "source": {"transport": "wecom"},
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Send the PDF and send the Markdown source file too.",
        }
        files = [Path("/tmp/report.pdf"), Path("/tmp/report.md"), Path("/tmp/report.tex")]

        selected = worker.wecom_research_delivery_files(task, files)

        self.assertEqual(selected, files)

    def test_ordinary_research_summary_keeps_optional_artifacts_local(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Read this article and tell me what matters.",
        }
        result = {
            "files": ["/tmp/report.pdf", "/tmp/report.md", "/tmp/report.tex"],
            "data": {
                "source_read_quality": "full",
                "send_report_to_wechat": True,
            },
        }

        self.assertFalse(worker.result_allows_chat_artifact_delivery(task, result))
        self.assertEqual(
            worker.research_summary_delivery_files(
                task,
                [Path("/tmp/report.pdf"), Path("/tmp/report.md"), Path("/tmp/report.tex")],
            ),
            [Path("/tmp/report.pdf")],
        )

    def test_explicit_pdf_summary_sends_pdf_without_sources(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "request": "Read this paper and send me a PDF report.",
        }
        files = [Path("/tmp/report.pdf"), Path("/tmp/report.md"), Path("/tmp/report.tex")]

        self.assertTrue(worker.result_allows_chat_artifact_delivery(task, {"files": [str(path) for path in files]}))
        self.assertEqual(
            worker.research_summary_delivery_files(task, files),
            [Path("/tmp/report.pdf")],
        )

    def test_scheduled_research_contract_still_allows_required_pdf(self) -> None:
        worker = load_worker()
        task = {
            "routine": {"id": "research_summary"},
            "route_decision": {
                "route_kind": "research_or_summary",
                "scheduled_daily_research": True,
                "require_file_delivery": True,
            },
            "execution_contract": {"required_artifacts": ["compiled_pdf"]},
            "request": "Today's scheduled research briefing.",
        }

        self.assertTrue(worker.result_allows_chat_artifact_delivery(task, {"files": ["/tmp/report.pdf"]}))

    def test_required_delivery_respects_pdf_only_execution_contract(self) -> None:
        worker = load_worker()
        task = {
            "source": {"transport": "wecom"},
            "routine": {"id": "research_summary"},
            "route_decision": {"route_kind": "research_or_summary"},
            "execution_contract": {"required_artifacts": ["compiled_pdf"]},
            "request": "Send the report PDF.",
        }
        result = {"files": ["/tmp/report.pdf", "/tmp/report.md", "/tmp/report.tex"]}

        required = worker.required_delivery_file_paths(result, task)

        self.assertEqual(required, [Path("/tmp/report.pdf")])

    def test_wecom_delivery_ledger_prevents_resending_complete_batch(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.pdf"
            report.write_bytes(b"%PDF-1.4\n")
            chat = "wecom:default:group:abc"
            task = {
                "id": "task-complete",
                "chat": chat,
                "source": {
                    "transport": "wecom",
                    "chat": chat,
                    "wecom_chat_id": "private-chat-id",
                },
                "routine": {"id": "research_summary"},
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
                "execution_contract": {"required_artifacts": ["pdf"]},
                "request": "Send the report PDF.",
            }
            result = {"message": "Research complete.", "confirmation": "", "files": [str(report)]}
            ledger = {
                "ok": True,
                "complete": True,
                "sent_messages": ["Research complete."],
                "pending_messages": [],
                "sent_files": [str(report.resolve())],
                "pending_files": [],
            }

            def reconcile(_endpoint, _token, _payload, current_task):
                worker.record_wecom_delivery_payload(current_task, ledger, source="component_ledger")
                return ledger

            with mock.patch.object(worker, "wecom_transport_settings", return_value=("http://relay", "token")), mock.patch.object(
                worker, "wecom_native_reply_mentions", return_value=[]
            ), mock.patch.object(worker, "query_wecom_delivery_status", side_effect=reconcile), mock.patch.object(
                worker.urllib.request, "urlopen"
            ) as urlopen:
                worker.send_result_once_wecom(result, chat, task)

        urlopen.assert_not_called()
        self.assertEqual(task["sent_file_paths"], [str(report.resolve())])

    def test_wecom_delivery_records_only_verified_sent_text_in_router_history(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            task = {
                "id": "task-history",
                "chat": "wecom:default:group:abc",
                "wecom_history_db": str(history),
            }
            payload = {
                "ok": True,
                "complete": True,
                "sent_messages": ["Research complete."],
                "pending_messages": [],
                "sent_files": [],
                "pending_files": [],
            }

            worker.record_wecom_delivery_payload(task, payload, source="send_response")
            worker.record_wecom_delivery_payload(task, payload, source="component_ledger")
            with sqlite3.connect(history) as conn:
                rows = conn.execute(
                    "SELECT direction, sender_display, body FROM messages ORDER BY id"
                ).fetchall()

        self.assertEqual(rows, [("outbound", "LabAgent", "Research complete.")])
        self.assertEqual(len(task["wecom_history_recorded_message_hashes"]), 1)

    def test_wecom_pending_text_does_not_create_outbound_router_history(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            task = {
                "id": "task-pending-history",
                "chat": "wecom:default:group:abc",
                "wecom_history_db": str(history),
            }
            payload = {
                "ok": False,
                "complete": False,
                "sent_messages": [],
                "pending_messages": ["Still pending."],
                "sent_files": [],
                "pending_files": [],
            }

            worker.record_wecom_delivery_payload(task, payload, source="partial_send_response")

        self.assertFalse(history.exists())
        self.assertNotIn("wecom_history_recorded_message_hashes", task)

    def test_wecom_partial_ledger_retries_only_missing_file(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.pdf"
            second = Path(tmp) / "second.pdf"
            first.write_bytes(b"%PDF-1.4\nfirst")
            second.write_bytes(b"%PDF-1.4\nsecond")
            chat = "wecom:default:group:abc"
            task = {
                "id": "task-partial",
                "chat": chat,
                "source": {
                    "transport": "wecom",
                    "chat": chat,
                    "wecom_chat_id": "private-chat-id",
                },
                "routine": {"id": "research_summary"},
                "route_decision": {
                    "route_kind": "research_or_summary",
                    "require_file_delivery": True,
                },
                "execution_contract": {"required_artifacts": ["pdf"]},
                "request": "Send both PDF reports.",
            }
            result = {
                "message": "Research complete.",
                "confirmation": "",
                "files": [str(first), str(second)],
            }
            ledger = {
                "ok": False,
                "complete": False,
                "sent_messages": ["Research complete."],
                "pending_messages": [],
                "sent_files": [str(first.resolve())],
                "pending_files": [str(second.resolve())],
            }

            def reconcile(_endpoint, _token, _payload, current_task):
                worker.record_wecom_delivery_payload(current_task, ledger, source="component_ledger")
                return ledger

            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {
                    "ok": True,
                    "sent_messages": [],
                    "sent_files": [str(second.resolve())],
                    "errors": [],
                }
            ).encode("utf-8")
            with mock.patch.object(worker, "wecom_transport_settings", return_value=("http://relay", "token")), mock.patch.object(
                worker, "wecom_native_reply_mentions", return_value=[]
            ), mock.patch.object(worker, "query_wecom_delivery_status", side_effect=reconcile), mock.patch.object(
                worker.urllib.request, "urlopen", return_value=response
            ) as urlopen:
                worker.send_result_once_wecom(result, chat, task)

            request = urlopen.call_args.args[0]
            payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(payload["message"], "")
        self.assertEqual(payload["files"], [str(second.resolve())])
        self.assertEqual(set(task["sent_file_paths"]), {str(first.resolve()), str(second.resolve())})

    def test_wecom_send_exposes_transport_error_before_generic_missing_artifact(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "structure.png"
            image.write_bytes(b"png")
            chat = "wecom:default:group:abc"
            task = {
                "id": "protein-task",
                "chat": chat,
                "source": {
                    "transport": "wecom",
                    "chat": chat,
                    "wecom_chat_id": "private-chat-id",
                },
                "route_decision": {"route_kind": "design_or_render", "require_file_delivery": True},
            }
            result = {"message": "done", "confirmation": "", "files": [str(image)]}
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {
                    "ok": False,
                    "sent_messages": [],
                    "sent_files": [],
                    "errors": [
                        {
                            "kind": "file",
                            "path": str(image),
                            "error": "BridgeError: exact allowlisted WeCom chat is not visible: LabAgent",
                        }
                    ],
                }
            ).encode("utf-8")
            pending = {
                "ok": False,
                "complete": False,
                "sent_messages": [],
                "pending_messages": ["done"],
                "sent_files": [],
                "pending_files": [str(image.resolve())],
            }

            def reconcile(_endpoint, _token, _payload, current_task):
                worker.record_wecom_delivery_payload(current_task, pending, source="component_ledger")
                return pending

            with mock.patch.object(worker, "wecom_transport_settings", return_value=("http://relay", "token")), mock.patch.object(
                worker, "wecom_native_reply_mentions", return_value=[]
            ), mock.patch.object(worker, "query_wecom_delivery_status", side_effect=[None, pending]), mock.patch.object(
                worker.urllib.request, "urlopen", return_value=response
            ):
                with self.assertRaisesRegex(RuntimeError, "exact allowlisted WeCom chat is not visible"):
                    worker.send_result_once_wecom(result, chat, task)

        self.assertEqual(task["wecom_transport_errors"][0]["kind"], "file")

    def test_research_summary_files_are_best_effort_unless_explicitly_required(self) -> None:
        worker = load_worker()
        task = {"route_decision": {"route_kind": "research_or_summary"}}
        result = {"message": "summary", "files": ["/tmp/summary.md", "/tmp/thumb.png"]}

        self.assertFalse(worker.result_requires_file_delivery(task, result))
        result["data"] = {"require_file_delivery": True}
        self.assertTrue(worker.result_requires_file_delivery(task, result))

        result["data"] = {}
        task["route_decision"]["require_file_delivery"] = True
        self.assertTrue(worker.result_requires_file_delivery(task, result))

        task["route_decision"]["require_file_delivery"] = False
        task["execution_contract"] = {"required_artifacts": ["pdf"]}
        self.assertTrue(worker.result_requires_file_delivery(task, result))

    def test_load_send_target_registry_overrides_direct_coordinates(self) -> None:
        worker = load_worker()
        direct = {
            "name": "鏈接",
            "query": "鏈接",
            "expected_title": "鏈接",
            "result_click": [165, 125],
            "fallback_clicks": [[165, 100]],
        }
        registry = {
            "鏈接": {
                "name": "鏈接",
                "query": "鏈接",
                "expected_title": "鏈接",
                "result_click": [165, 170],
                "fallback_clicks": [[165, 170], [240, 170]],
            }
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(worker, "load_direct_config_send_target", return_value=direct):
            target_path = Path(tmp) / "send_targets.json"
            target_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

            target = worker.load_send_target("鏈接", target_path)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target["result_click"], [165, 170])
        self.assertEqual(target["fallback_clicks"], [[165, 170], [240, 170]])

    def test_worker_send_message_disables_wechat_search_by_default(self) -> None:
        worker = load_worker()
        calls: list[list[str]] = []
        original_run_send = worker.run_send_subprocess
        try:
            worker.run_send_subprocess = lambda command, **_kwargs: calls.append(command)
            worker.send_message(
                "done",
                "🍓我的设备",
                Path("/tmp/no-targets.json"),
                target={"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"},
            )
        finally:
            worker.run_send_subprocess = original_run_send

        self.assertEqual(len(calls), 1)
        self.assertIn("--no-search", calls[0])

    def test_worker_send_message_allows_wechat_search_only_when_configured(self) -> None:
        worker = load_worker()
        calls: list[list[str]] = []
        original_run_send = worker.run_send_subprocess
        try:
            worker.run_send_subprocess = lambda command, **_kwargs: calls.append(command)
            worker.send_message(
                "done",
                "🍓我的设备",
                Path("/tmp/no-targets.json"),
                target={"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备", "allow_search": True},
            )
        finally:
            worker.run_send_subprocess = original_run_send

        self.assertEqual(len(calls), 1)
        self.assertNotIn("--no-search", calls[0])
        self.assertIn("--allow-search", calls[0])

    def test_required_file_send_failure_blocks_completion_message(self) -> None:
        worker = load_worker()
        sent_messages: list[str] = []
        original_message = worker.send_message
        original_file = worker.send_file
        try:
            worker.send_message = lambda message, *_args, **_kwargs: sent_messages.append(message)

            def fail_file(*_args, **_kwargs):
                raise RuntimeError("file picker unavailable")

            worker.send_file = fail_file
            task: dict[str, object] = {}
            with tempfile.TemporaryDirectory() as tmp:
                targets = Path(tmp) / "targets.json"
                targets.write_text(
                    json.dumps(
                        {
                            "🍓我的设备": {
                                "name": "🍓我的设备",
                                "query": "我的设备",
                                "expected_title": "🍓我的设备",
                            }
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                errors = worker.send_result_with_retries(
                    {"message": "done", "confirmation": "", "files": ["/tmp/preview.png"]},
                    "🍓我的设备",
                    targets,
                    task=task,
                )
        finally:
            worker.send_message = original_message
            worker.send_file = original_file

        self.assertEqual(len(errors), 2)
        self.assertIn("required artifact delivery failed", errors[0])
        self.assertEqual(sent_messages, [])
        self.assertIn("file_send_errors", task)

    def test_worker_route_guard_rejects_cross_chat_send(self) -> None:
        worker = load_worker()
        task = {
            "chat": "🍓我的设备",
            "source": {"chat": "🍓我的设备"},
            "route": {
                "chat": "🍓我的设备",
                "send_target_name": "🍓我的设备",
                "expected_title": "🍓我的设备",
            },
        }
        target = {"name": "鏈接", "query": "鏈接", "expected_title": "鏈接"}

        with self.assertRaisesRegex(RuntimeError, "route mismatch"):
            worker.validate_worker_send_route(task, "鏈接", target)

    def test_worker_requires_guarded_target_for_send(self) -> None:
        worker = load_worker()
        original_allow = worker.os.environ.get("WECHAT_ALLOW_UNGUARDED_SEND")
        try:
            worker.os.environ.pop("WECHAT_ALLOW_UNGUARDED_SEND", None)
            with self.assertRaisesRegex(RuntimeError, "missing send_target"):
                worker.guarded_send_target("not-a-real-chat-for-tests", Path("/tmp/no-targets.json"))
        finally:
            if original_allow is None:
                worker.os.environ.pop("WECHAT_ALLOW_UNGUARDED_SEND", None)
            else:
                worker.os.environ["WECHAT_ALLOW_UNGUARDED_SEND"] = original_allow

    def test_claim_next_pending_marks_task_in_progress_once(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps({"id": "task-1", "chat": "demo", "request": "publish", "status": "pending"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

            first = worker.claim_next_pending(queue)
            second = worker.claim_next_pending(queue)
            rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first["id"], "task-1")
        self.assertEqual(first["status"], "in_progress")
        self.assertIn("worker_id", first)
        self.assertIsNone(second)
        self.assertEqual(rows[0]["status"], "in_progress")

    def test_claim_next_pending_recovers_new_read_only_schedule_once(self) -> None:
        worker = load_worker()
        now = datetime.now()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "scheduled-retry",
                        "chat": "wecom:default:group:labagent",
                        "request": "Prepare one scheduled inspiration.",
                        "status": "worker_failed",
                        "created_at": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
                        "completed_at": (now - timedelta(minutes=2)).isoformat(timespec="seconds"),
                        "source": {"local_type": "scheduled_group_inspiration"},
                        "route_decision": {"public_publish_allowed": False},
                        "scheduled_recovery": {
                            "version": 1,
                            "kind": "group_inspiration",
                            "read_only": True,
                            "max_attempts": 1,
                            "delay_seconds": 0,
                            "max_age_seconds": 3600,
                        },
                        "agent_session": {
                            "backend": "aginti",
                            "provider": "deepseek",
                            "failure_kind": "transient_backend_unavailable",
                        },
                        "completion_audit": {"status": "incomplete"},
                        "worker_error": {"type": "BackendExecutionFailed"},
                        "result": {"message": "stale failure", "files": []},
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]
            duplicate = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "scheduled-retry")
        self.assertEqual(claimed["status"], "in_progress")
        self.assertEqual(claimed["scheduled_recovery_count"], 1)
        self.assertEqual(len(claimed["scheduled_recovery_history"]), 1)
        self.assertEqual(
            claimed["scheduled_recovery_history"][0]["backend"],
            "aginti",
        )
        self.assertNotIn("result", claimed)
        self.assertNotIn("worker_error", claimed)
        self.assertNotIn("agent_session", claimed)
        self.assertEqual(stored["status"], "in_progress")
        self.assertIsNone(duplicate)

    def test_claim_next_pending_never_replays_legacy_or_delivered_schedule_failure(self) -> None:
        worker = load_worker()
        now = datetime.now()
        base = {
            "chat": "wecom:default:group:labagent",
            "request": "Prepare one scheduled inspiration.",
            "status": "worker_failed",
            "created_at": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
            "completed_at": (now - timedelta(minutes=2)).isoformat(timespec="seconds"),
            "source": {"local_type": "scheduled_group_inspiration"},
            "route_decision": {"public_publish_allowed": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {**base, "id": "legacy-failure"},
                    {
                        **base,
                        "id": "delivered-failure",
                        "sent_at": now.isoformat(timespec="seconds"),
                        "scheduled_recovery": {
                            "version": 1,
                            "read_only": True,
                            "max_attempts": 1,
                            "delay_seconds": 0,
                            "max_age_seconds": 3600,
                        },
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertEqual([task["status"] for task in stored], ["worker_failed", "worker_failed"])
        self.assertTrue(all("scheduled_recovery_count" not in task for task in stored))

    def test_claim_next_pending_never_replays_partially_delivered_schedule_failure(self) -> None:
        worker = load_worker()
        now = datetime.now()
        base = {
            "chat": "wecom:default:group:labagent",
            "request": "Prepare one scheduled inspiration.",
            "status": "worker_failed",
            "created_at": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
            "completed_at": (now - timedelta(minutes=2)).isoformat(timespec="seconds"),
            "source": {"local_type": "scheduled_group_inspiration"},
            "route_decision": {"public_publish_allowed": False},
            "scheduled_recovery": {
                "version": 1,
                "read_only": True,
                "max_attempts": 1,
                "delay_seconds": 0,
                "max_age_seconds": 3600,
            },
        }
        tasks = [
            {**base, "id": "partial-text", "sent_message_part_hashes": ["part-1"]},
            {**base, "id": "partial-file", "sent_file_paths": ["/tmp/report.pdf"]},
            {
                **base,
                "id": "partial-wecom",
                "wecom_delivery": {
                    "status": "partial",
                    "sent_messages": ["Research is in progress."],
                    "sent_file_count": 0,
                },
            },
            {
                **base,
                "id": "android-fallback",
                "android_text_fallback_send": {
                    "sent_at": now.isoformat(timespec="seconds"),
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(queue, tasks)

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertTrue(all(task["status"] == "worker_failed" for task in stored))
        self.assertTrue(all("scheduled_recovery_count" not in task for task in stored))

    def test_claim_next_pending_does_not_replay_schedule_superseded_in_same_lane(self) -> None:
        worker = load_worker()
        now = datetime.now()
        policy = {
            "version": 1,
            "read_only": True,
            "max_attempts": 1,
            "delay_seconds": 0,
            "max_age_seconds": 3600,
        }
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-daily-failure",
                        "chat": "wecom:default:group:labagent",
                        "request": "Old daily task.",
                        "status": "worker_failed",
                        "created_at": (now - timedelta(minutes=5)).isoformat(
                            timespec="seconds"
                        ),
                        "completed_at": (now - timedelta(minutes=4)).isoformat(
                            timespec="seconds"
                        ),
                        "source": {"local_type": "scheduled_daily_research"},
                        "daily_research": {"member_key": "member-a"},
                        "route_decision": {"public_publish_allowed": False},
                        "scheduled_recovery": policy,
                    },
                    {
                        "id": "new-daily-result",
                        "chat": "wecom:default:group:labagent",
                        "request": "New daily task.",
                        "status": "done",
                        "created_at": (now - timedelta(minutes=2)).isoformat(
                            timespec="seconds"
                        ),
                        "source": {"local_type": "scheduled_daily_research"},
                        "daily_research": {"member_key": "member-a"},
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertEqual(stored[0]["status"], "worker_failed")
        self.assertNotIn("scheduled_recovery_count", stored[0])

    def test_scheduled_worker_failure_retries_same_task_and_delivers_once(self) -> None:
        worker = load_worker()
        now = datetime.now()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "scheduled-e2e",
                        "chat": "wecom:default:group:labagent",
                        "request": "Share one concise research inspiration.",
                        "status": "pending",
                        "created_at": (now - timedelta(minutes=1)).isoformat(timespec="seconds"),
                        "source": {"local_type": "scheduled_group_inspiration"},
                        "route_decision": {
                            "route_kind": "other_worker",
                            "public_publish_allowed": False,
                        },
                        "scheduled_recovery": {
                            "version": 1,
                            "kind": "group_inspiration",
                            "read_only": True,
                            "max_attempts": 1,
                            "delay_seconds": 0,
                            "max_age_seconds": 3600,
                        },
                    }
                ],
            )
            passthrough = lambda _task, result, *_args, **_kwargs: result
            with (
                mock.patch.dict(
                    worker.os.environ,
                    {"WECHAT_WORKER_COMPACT_STDOUT": "1"},
                    clear=False,
                ),
                mock.patch.object(
                    worker,
                    "run_worker_codex",
                    side_effect=[
                        "Worker failed via aginti: Temporary failure in name resolution",
                        json.dumps(
                            {
                                "message": "A source-grounded inspiration.",
                                "confirmation": "",
                                "files": [],
                            }
                        ),
                    ],
                ) as backend,
                mock.patch.object(
                    worker,
                    "enforce_worker_result_contract",
                    side_effect=passthrough,
                ),
                mock.patch.object(
                    worker,
                    "attach_audio_transcript_reference",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(
                    worker,
                    "prepare_result_files",
                    side_effect=lambda result, *_args, **_kwargs: result,
                ),
                mock.patch.object(
                    worker,
                    "recover_verified_shipinhao_delivery_result",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(
                    worker,
                    "enforce_reader_facing_pdf_quality",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(
                    worker,
                    "audit_and_repair_worker_completion",
                    side_effect=lambda _task, result: result,
                ),
                mock.patch.object(worker, "record_event"),
                mock.patch.object(
                    worker,
                    "send_result_with_retries",
                    return_value=[],
                ) as sender,
            ):
                first = worker.process_one(
                    queue,
                    "wecom",
                    send=True,
                    send_targets=Path(tmp) / "targets.json",
                    log_idle=False,
                )
                failed = worker.find_task(queue, "scheduled-e2e")
                second = worker.process_one(
                    queue,
                    "wecom",
                    send=True,
                    send_targets=Path(tmp) / "targets.json",
                    log_idle=False,
                )
                completed = worker.find_task(queue, "scheduled-e2e")

        self.assertTrue(first)
        self.assertEqual(failed["status"], "worker_failed")
        self.assertTrue(second)
        self.assertEqual(completed["status"], "done")
        self.assertEqual(completed["scheduled_recovery_count"], 1)
        self.assertEqual(backend.call_count, 2)
        sender.assert_called_once()
        self.assertEqual(
            sender.call_args.args[0]["message"],
            "A source-grounded inspiration.",
        )

    def test_claim_next_pending_expires_old_backlog_without_running_it(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {"WECHAT_WORKER_PENDING_TASK_TTL_SECONDS": "60"},
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-task",
                        "chat": "EchoMind",
                        "request": "old request",
                        "status": "pending",
                        "created_at": "2000-01-01T00:00:00",
                        "expires_at": "2000-01-01T00:01:00",
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], "expired_stale")
        self.assertEqual(stored["expire_reason"], "pending_task_ttl_exceeded")

    def test_claim_next_pending_expires_old_confirmation_without_running_it(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {"WECHAT_WORKER_PENDING_TASK_TTL_SECONDS": "60"},
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-confirmation",
                        "chat": "LazyResearch",
                        "request": "download a paper",
                        "status": "waiting_confirmation",
                        "created_at": "2000-01-01T00:00:00",
                        "expires_at": "2000-01-01T00:01:00",
                        "result": {
                            "message": "The source requires an authenticated account.",
                            "confirmation": "Sign in and reply done.",
                            "files": [],
                        },
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], "expired_stale")
        self.assertEqual(stored["expired_from_status"], "waiting_confirmation")
        self.assertEqual(stored["expire_reason"], "confirmation_ttl_exceeded")
        self.assertIn("result", stored)

    def test_claim_next_pending_preserves_old_daily_research_without_deadline(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_PENDING_TASK_TTL_SECONDS": "60",
                "WECHAT_WORKER_EXPIRE_LEGACY_QUEUE": "1",
            },
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-daily",
                        "chat": "wecom:group:labagent",
                        "request": "daily research report",
                        "status": "pending",
                        "created_at": "2000-01-01T00:00:00",
                        "daily_research": {"report_date": "2026-07-19"},
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNotNone(claimed)
        self.assertEqual(stored["status"], "in_progress")
        self.assertNotIn("expired_at", stored)

    def test_claim_next_deferred_send_expires_old_outbox_without_sending(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_DEFERRED_SEND_TTL_SECONDS": "60",
                "WECHAT_WORKER_DEFERRED_SEND_GLOBAL_COOLDOWN_SECONDS": "0",
            },
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-send",
                        "chat": "EchoMind",
                        "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "created_at": "2000-01-01T00:00:00",
                        "last_send_attempt_at": "2000-01-01T00:00:00",
                        "send_expires_at": "2000-01-01T00:01:00",
                        "send_deferred_reason": "gui_send_timeout",
                        "result": {"message": "old reply", "confirmation": "", "files": []},
                    }
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], "send_expired")
        self.assertEqual(stored["expire_reason"], "deferred_send_ttl_exceeded")

    def test_required_artifact_outbox_precedes_ordinary_deferred_text(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_DEFERRED_SEND_GLOBAL_COOLDOWN_SECONDS": "0",
                "WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS": "0",
            },
            clear=False,
        ):
            queue = Path(tmp) / "queue.jsonl"
            image = Path(tmp) / "structure.png"
            image.write_bytes(b"png")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "old-text",
                        "chat": "LabAgent",
                        "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "last_send_attempt_at": "2000-01-01T00:00:00",
                        "result": {"message": "old scheduled note", "files": []},
                    },
                    {
                        "id": "current-artifact",
                        "chat": "LabAgent",
                        "status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                        "last_send_attempt_at": "2000-01-01T00:00:00",
                        "route_decision": {"route_kind": "design_or_render"},
                        "result": {"message": "structure ready", "files": [str(image)]},
                    },
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "current-artifact")

    def test_wecom_supervisor_namespace_flushes_deferred_outbox(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {"WECHAT_WORKER_DEFERRED_SEND_GLOBAL_COOLDOWN_SECONDS": "0"},
            clear=False,
        ):
            queue = Path(tmp) / "wecom.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "wecom-artifact",
                        "chat": "wecom:external-gui:group:abc",
                        "status": worker.SEND_DEFERRED_ARTIFACT_STATUS,
                        "last_send_attempt_at": "2000-01-01T00:00:00",
                        "result": {"message": "ready", "files": []},
                    }
                ],
            )
            with mock.patch.object(worker, "send_result_with_retries", return_value=[]), mock.patch.object(
                worker, "record_event"
            ), mock.patch.object(worker, "log_worker_event"):
                handled = worker.flush_one_deferred_send(queue, "wecom", log_idle=False)

            stored = worker.read_tasks(queue)[0]

        self.assertTrue(handled)
        self.assertEqual(stored["status"], "done")

    def test_process_one_persists_worker_result_before_transport_send(self) -> None:
        worker = load_worker()
        observed: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [{"id": "task-ready", "chat": "LabAgent", "request": "render", "status": "pending"}],
            )

            def inspect_persisted_result(_result, _chat, _targets, *, task=None):
                stored = worker.find_task(queue, "task-ready")
                assert stored is not None
                observed.append(stored)
                return []

            with mock.patch.object(
                worker,
                "run_worker_codex",
                return_value=json.dumps({"message": "finished", "files": []}),
            ), mock.patch.object(
                worker,
                "run_completion_audit",
                return_value={
                    "status": "checked",
                    "coverage_complete": True,
                    "expected_item_ids": ["task:task-ready"],
                    "covered_item_ids": ["task:task-ready"],
                    "missing": [],
                    "repair_recommended": False,
                    "complexity": "low",
                },
            ), mock.patch.object(
                worker, "send_result_with_retries", side_effect=inspect_persisted_result
            ), mock.patch.object(worker, "record_event"), mock.patch.object(worker, "log_worker_event"):
                handled = worker.process_one(queue, "LabAgent", send=True, log_idle=False)

        self.assertTrue(handled)
        self.assertEqual(observed[0]["result"]["message"], "finished")
        self.assertIn("worker_result_ready_at", observed[0])

    def test_deferred_send_global_cooldown_prevents_restart_burst(self) -> None:
        worker = load_worker()
        now_text = datetime.now().isoformat(timespec="seconds")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_WORKER_DEFERRED_SEND_TTL_SECONDS": "3600",
                "WECHAT_WORKER_DEFERRED_SEND_GLOBAL_COOLDOWN_SECONDS": "30",
                "WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS": "0",
            },
            clear=False,
        ), mock.patch.object(worker, "gui_send_lock_busy", return_value=False):
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "just-flushed",
                        "chat": "懒人科研",
                        "status": "done",
                        "send_retry_claimed_at": now_text,
                    },
                    {
                        "id": "recent-send",
                        "chat": "EchoMind",
                        "status": worker.SEND_DEFERRED_LOCKED_STATUS,
                        "created_at": now_text,
                        "last_send_attempt_at": now_text,
                        "send_deferred_reason": "gui_send_timeout",
                        "result": {"message": "reply", "confirmation": "", "files": []},
                    }
                ],
            )

            claimed = worker.claim_next_deferred_send(queue)

        self.assertIsNone(claimed)

    def test_claim_next_pending_recovers_stale_in_progress_task(self) -> None:
        worker = load_worker()
        original = worker.os.environ.get("WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS")
        try:
            worker.os.environ["WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS"] = "1"
            with tempfile.TemporaryDirectory() as tmp:
                queue = Path(tmp) / "queue.jsonl"
                queue.write_text(
                    json.dumps(
                        {
                            "id": "task-1",
                            "chat": "demo",
                            "request": "publish",
                            "status": "in_progress",
                            "worker_id": "pid:old",
                            "claimed_at": "2000-01-01T00:00:00",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                claimed = worker.claim_next_pending(queue)
                rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
        finally:
            if original is None:
                worker.os.environ.pop("WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS", None)
            else:
                worker.os.environ["WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS"] = original

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "task-1")
        self.assertEqual(claimed["status"], "in_progress")
        self.assertEqual(claimed["claim_history"][0]["worker_id"], "pid:old")
        self.assertEqual(rows[0]["claim_history"][0]["worker_id"], "pid:old")

    def test_claim_next_pending_abandons_dead_worker_pid_without_replay(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "task-1",
                        "chat": "demo",
                        "request": "publish",
                        "status": "in_progress",
                        "worker_id": "pid:999999",
                        "claimed_at": datetime.now().isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(worker, "process_alive", return_value=False):
                claimed = worker.claim_next_pending(queue)
            rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertIsNone(claimed)
        self.assertEqual(rows[0]["status"], "worker_abandoned")
        self.assertEqual(rows[0]["abandoned_reason"], "claiming_worker_process_ended")

    def test_claim_next_pending_recovers_recent_safe_dead_worker_once(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-1",
                        "chat": "Shares",
                        "request": "read this source",
                        "routine": {"id": "research_summary"},
                        "status": "worker_abandoned",
                        "abandoned_at": datetime.now().isoformat(timespec="seconds"),
                        "abandoned_reason": "claiming_worker_process_ended",
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            rows = worker.read_tasks(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "research-1")
        self.assertEqual(claimed["status"], worker.CLAIMED_STATUS)
        self.assertEqual(claimed["dead_worker_recovery_count"], 1)
        self.assertNotIn("abandoned_reason", claimed)
        self.assertEqual(rows[0]["dead_worker_recovery_history"][0]["attempt"], 1)

    def test_claim_next_pending_recovers_generated_video_proven_pre_submit(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-pre-submit",
                        "chat": "MEMO",
                        "request": "generate a video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "worker_abandoned",
                        "abandoned_at": datetime.now().isoformat(timespec="seconds"),
                        "abandoned_reason": "claiming_worker_process_ended",
                        "generated_video_submit_probe": {
                            "status": "page_unavailable",
                            "paid_action_attempted": False,
                            "paid_action_state": "not_attempted",
                        },
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "video-pre-submit")
        self.assertEqual(claimed["status"], worker.CLAIMED_STATUS)
        self.assertEqual(claimed["dead_worker_recovery_count"], 1)
        self.assertNotIn("abandoned_reason", stored)

    def test_claim_next_pending_does_not_recover_generated_video_after_uncertain_submit(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-uncertain-submit",
                        "chat": "MEMO",
                        "request": "generate a video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "worker_abandoned",
                        "abandoned_at": datetime.now().isoformat(timespec="seconds"),
                        "abandoned_reason": "claiming_worker_process_ended",
                        "generated_video_submit_probe": {
                            "status": "timeout",
                            "paid_action_attempted": None,
                            "paid_action_state": "unknown",
                        },
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], "worker_abandoned")
        self.assertNotIn("dead_worker_recovery_count", stored)

    def test_claim_next_pending_cancels_generation_superseded_by_delivered_newer_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "newer-result.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-old",
                        "chat": "MEMO",
                        "request": "generate a video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": worker.GENERATED_VIDEO_WAITING_STATUS,
                        "source": {
                            "config_id": "memo-direct",
                            "message_table": "MSG",
                            "local_id": 16,
                        },
                        "next_poll_at": 0,
                    },
                    {
                        "id": "video-new",
                        "chat": "MEMO",
                        "request": "generate a video with the added reference",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "done",
                        "source": {
                            "config_id": "memo-direct",
                            "message_table": "MSG",
                            "local_id": 17,
                        },
                        "context": [
                            {
                                "local_id": 16,
                                "content": "generate a video",
                            }
                        ],
                        "sent_file_paths": [str(video)],
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)
            tasks = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertEqual(tasks[0]["status"], "canceled_superseded")
        self.assertEqual(tasks[0]["superseded_by"], "video-new")
        self.assertEqual(
            tasks[0]["superseded_reason"],
            "newer_same_chat_generation_completed_and_delivered",
        )
        self.assertTrue(tasks[0]["recovery_canceled_before_external_action"])
        self.assertEqual(tasks[0]["coverage_status"], "covered")
        self.assertEqual(
            tasks[0]["message_coverage"]["covered_item_ids"],
            ["task:video-old"],
        )
        self.assertEqual(
            tasks[0]["message_coverage"]["covered_by_superseding_task_id"],
            "video-new",
        )

    def test_independent_later_generation_in_same_chat_does_not_supersede(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "independent-result.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-old",
                        "chat": "MEMO",
                        "request": "generate the first video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "pending",
                        "source": {
                            "config_id": "memo-direct",
                            "message_table": "MSG",
                            "local_id": 16,
                        },
                    },
                    {
                        "id": "video-new",
                        "chat": "MEMO",
                        "request": "generate a separate second video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "done",
                        "source": {
                            "config_id": "memo-direct",
                            "message_table": "MSG",
                            "local_id": 17,
                        },
                        "context": [
                            {
                                "local_id": 15,
                                "content": "unrelated earlier discussion",
                            }
                        ],
                        "sent_file_paths": [str(video)],
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)
            tasks = worker.read_tasks(queue)

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], "video-old")
        self.assertEqual(tasks[0]["status"], worker.CLAIMED_STATUS)

    def test_reconcile_closes_legacy_generation_supersession_coverage(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "newer-result.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-old",
                        "chat": "MEMO",
                        "request": "generate a video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "canceled_superseded",
                        "superseded_by": "video-new",
                        "superseded_reason": (
                            "newer_same_chat_generation_completed_and_delivered"
                        ),
                        "coverage_status": "unresolved_after_retry",
                        "message_coverage": {
                            "status": "deferred_nonterminal",
                            "expected_item_ids": [
                                "task:video-old",
                                "task:interruption-2",
                            ],
                            "covered_item_ids": [],
                            "unresolved_item_ids": [],
                            "missing": [],
                        },
                    },
                    {
                        "id": "video-new",
                        "chat": "MEMO",
                        "request": "generate the updated video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "done",
                        "sent_file_paths": [str(video)],
                    },
                ],
            )

            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 0)
            tasks = worker.read_tasks(queue)
            checked_at = tasks[0]["message_coverage"]["checked_at"]
            self.assertEqual(worker.reconcile_numbered_message_coverage(queue), 0)
            tasks = worker.read_tasks(queue)

        self.assertEqual(tasks[0]["coverage_status"], "covered")
        self.assertEqual(tasks[0]["message_coverage"]["checked_at"], checked_at)
        self.assertEqual(
            tasks[0]["message_coverage"]["covered_item_ids"],
            ["task:video-old", "task:interruption-2"],
        )
        self.assertEqual(
            tasks[0]["message_coverage"]["covered_by_superseding_task_id"],
            "video-new",
        )

    def test_delivered_generation_in_another_chat_does_not_supersede_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "other-chat.mp4"
            video.write_bytes(b"video")
            queue = tmp_path / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "video-old",
                        "chat": "MEMO",
                        "request": "generate a video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "pending",
                        "source": {
                            "config_id": "memo-direct",
                            "message_table": "MSG",
                            "local_id": 16,
                        },
                    },
                    {
                        "id": "video-other",
                        "chat": "My devices",
                        "request": "generate another video",
                        "routine": {"id": "generated_video"},
                        "route_decision": {"route_kind": "generate_video"},
                        "status": "done",
                        "source": {
                            "config_id": "devices-direct",
                            "message_table": "OTHER",
                            "local_id": 17,
                        },
                        "sent_file_paths": [str(video)],
                    },
                ],
            )

            claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "video-old")

    def test_claim_next_pending_does_not_recover_old_abandoned_task(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "research-old",
                        "chat": "Shares",
                        "request": "old source",
                        "routine": {"id": "research_summary"},
                        "status": "worker_abandoned",
                        "abandoned_at": "2000-01-01T00:00:00",
                        "abandoned_reason": "claiming_worker_process_ended",
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            rows = worker.read_tasks(queue)

        self.assertIsNone(claimed)
        self.assertEqual(rows[0]["status"], "worker_abandoned")
        self.assertNotIn("dead_worker_recovery_count", rows[0])

    def test_claim_next_pending_does_not_recover_publication_after_dead_worker(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "publish-abandoned",
                        "chat": "My devices",
                        "request": "publish the exact video",
                        "routine": {"id": "video_publish_existing"},
                        "status": "worker_abandoned",
                        "abandoned_at": datetime.now().isoformat(timespec="seconds"),
                        "abandoned_reason": "claiming_worker_process_ended",
                    }
                ],
            )

            claimed = worker.claim_next_pending(queue)
            stored = worker.read_tasks(queue)[0]

        self.assertIsNone(claimed)
        self.assertEqual(stored["status"], "worker_abandoned")
        self.assertNotIn("dead_worker_recovery_count", stored)

    def test_claim_next_pending_serializes_active_tasks_per_chat(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            now_text = datetime.now().isoformat(timespec="seconds")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "shares-active",
                        "chat": "Shares",
                        "status": worker.CLAIMED_STATUS,
                        "worker_id": "pid:111",
                        "claimed_at": now_text,
                    },
                    {
                        "id": "shares-next",
                        "chat": "Shares",
                        "status": "pending",
                        "created_at": now_text,
                    },
                    {
                        "id": "research-next",
                        "chat": "LazyResearch",
                        "status": "pending",
                        "created_at": now_text,
                    },
                ],
            )

            with mock.patch.object(worker, "process_alive", return_value=True):
                claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "research-next")

    def test_claim_next_pending_serializes_due_poststage_for_active_chat(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            now_text = datetime.now().isoformat(timespec="seconds")
            worker.write_tasks(
                queue,
                [
                    {
                        "id": "devices-active",
                        "chat": "🍓My devices",
                        "status": worker.CLAIMED_STATUS,
                        "worker_id": "pid:111",
                        "claimed_at": now_text,
                    },
                    {
                        "id": "devices-publish-poll",
                        "chat": "🍓My devices",
                        "status": worker.EXISTING_VIDEO_PUBLISH_PENDING_STATUS,
                        "next_publish_poststage_at": 0,
                    },
                    {
                        "id": "research-next",
                        "chat": "LazyResearch",
                        "status": "pending",
                        "created_at": now_text,
                    },
                ],
            )

            with mock.patch.object(worker, "process_alive", return_value=True):
                claimed = worker.claim_next_pending(queue)

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "research-next")

    def test_rewrite_task_preserves_interruptions_added_after_worker_claim(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            current = {
                "id": "shares-active",
                "chat": "Shares",
                "status": worker.CLAIMED_STATUS,
                "worker_id": "pid:111",
                "claimed_at": "2026-07-29T12:00:00",
                "request": "Current coalesced request:\nSummarize the first source.",
                "interruptions": [
                    {
                        "at": "2026-07-29T12:01:00",
                        "incoming_task_id": "shares-next",
                        "source": {
                            "message_table": "messages",
                            "server_id": "srv-2",
                            "local_id": 2,
                        },
                        "request": "Compare it with the second source too.",
                        "request_excerpt": "Compare it with the second source too.",
                    }
                ],
                "interruption_pending": True,
                "interruption_count": 1,
                "last_interruption_at": "2026-07-29T12:01:00",
            }
            worker.write_tasks(queue, [current])
            stale_worker_snapshot = {
                "id": "shares-active",
                "chat": "Shares",
                "status": worker.CLAIMED_STATUS,
                "worker_id": "pid:111",
                "claimed_at": "2026-07-29T12:00:00",
                "request": "Current coalesced request:\nSummarize the first source.",
                "worker_progress": "reading",
            }

            worker.rewrite_task(queue, stale_worker_snapshot)
            stored = worker.read_tasks(queue)[0]

        self.assertEqual(stored["worker_progress"], "reading")
        self.assertTrue(stored["interruption_pending"])
        self.assertEqual(stored["interruption_count"], 1)
        self.assertEqual(stored["interruptions"][0]["incoming_task_id"], "shares-next")
        self.assertIn("Compare it with the second source too.", stored["request"])

    def test_worker_sandbox_can_be_downgraded_by_env(self) -> None:
        worker = load_worker()
        original = worker.os.environ.get("WECHAT_WORKER_CODEX_SANDBOX")
        try:
            worker.os.environ["WECHAT_WORKER_CODEX_SANDBOX"] = "workspace"
            self.assertEqual(worker.worker_sandbox(), "workspace-write")
        finally:
            if original is None:
                worker.os.environ.pop("WECHAT_WORKER_CODEX_SANDBOX", None)
            else:
                worker.os.environ["WECHAT_WORKER_CODEX_SANDBOX"] = original

    def test_inline_group_voice_becomes_durable_agent_context(self) -> None:
        worker = load_worker()
        task = {
            "id": "voice-task",
            "chat": "EchoMind",
            "source": {
                "local_id": 88,
                "local_type": 34,
                "voice_transcript": "今日は雨ですが、散歩したいです。",
                "voice_language": "ja",
                "voice_duration": 3.2,
            },
            "context": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = worker.prepare_audio_intake_preflight(task, Path(tmp))
            context = Path(result["agent_context_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["status"], "transcribed")
        self.assertEqual(result["input_kind"], "wechat_voice_rows")
        self.assertIn("今日は雨ですが", context)
        self.assertIn("local_id=88", context)

    def test_local_group_video_audio_is_handed_to_reusable_transcriber(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "source_media" / "exact-video.mp4"
            video.parent.mkdir()
            video.write_bytes(b"video")
            agent_context = root / "audio_intake" / "agent-context.md"
            agent_context.parent.mkdir()
            agent_context.write_text("# transcript\n", encoding="utf-8")
            task = {
                "id": "video-task",
                "chat": "鏈接",
                "source": {"local_id": 91, "local_type": 43, "kind": "video"},
                "preflight": {
                    "media_resolution": {
                        "status": "ok",
                        "copied": [{"task_copy_path": str(video), "suffix": ".mp4"}],
                    }
                },
            }
            expected = {
                "status": "transcribed",
                "input_kind": "local_wechat_media",
                "agent_context_path": str(agent_context),
            }
            with mock.patch.object(worker, "run_audio_intake_transcriber", return_value=expected) as transcribe:
                result = worker.prepare_audio_intake_preflight(task, root)

        self.assertEqual(result, expected)
        transcribe.assert_called_once_with(video.resolve(), output_dir=root / "audio_intake", source_local_id=91)

    def test_audio_intake_reuses_dedicated_voice_python_selector(self) -> None:
        worker = load_worker()
        with mock.patch.dict(
            worker.os.environ,
            {
                "WECHAT_AUDIO_TRANSCRIBE_PYTHON": "",
                "WECHAT_VOICE_TRANSCRIBE_PYTHON": "",
            },
            clear=False,
        ):
            selected = worker.audio_transcribe_python(lambda _config: "/opt/whisper/bin/python")

        self.assertEqual(selected, "/opt/whisper/bin/python")

    def test_audio_intake_explicit_python_overrides_fallback_selector(self) -> None:
        worker = load_worker()
        selector = mock.Mock(return_value="/opt/whisper/bin/python")
        with mock.patch.dict(
            worker.os.environ,
            {"WECHAT_AUDIO_TRANSCRIBE_PYTHON": "/custom/asr/python"},
            clear=False,
        ):
            selected = worker.audio_transcribe_python(selector)

        self.assertEqual(selected, "/custom/asr/python")
        selector.assert_not_called()

    def test_encoded_file_card_type_still_runs_media_resolution(self) -> None:
        worker = load_worker()
        encoded_type = (51 << 32) | 49
        task = {
            "source": {"local_type": encoded_type, "kind": "file/link"},
            "route_decision": {"route_kind": "research_or_summary", "needs_recent_media": True},
            "request": "Please summarize the shared source.",
        }

        self.assertEqual(worker.wechat_base_message_type(encoded_type), 49)
        self.assertTrue(worker.should_prepare_media_resolution(task))

    def test_publish_video_uses_exact_autopublish_preflight_not_generic_media_resolution(self) -> None:
        worker = load_worker()
        task = {
            "source": {"local_type": 43, "kind": "video"},
            "route_decision": {
                "route_kind": "publish_video",
                "needs_recent_media": True,
                "public_publish_allowed": True,
            },
            "request": "Publish this exact video.",
        }

        self.assertFalse(worker.should_prepare_media_resolution(task))

    def test_publish_video_audio_uses_exact_autopublish_copy(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "source_media" / "exact-video.mp4"
            video.parent.mkdir()
            video.write_bytes(b"video")
            task = {
                "id": "publish-video-audio",
                "chat": "My devices",
                "source": {"local_id": 91, "local_type": 43, "kind": "video"},
                "route_decision": {
                    "route_kind": "publish_video",
                    "needs_recent_media": True,
                    "public_publish_allowed": True,
                },
                "routine": {"id": "video_publish_existing"},
                "request": "Publish this exact video to YouTube.",
            }
            copied = {
                "ok": True,
                "status": "copied",
                "target": str(video),
                "message_local_ids": [91],
            }
            audio = {
                "status": "transcribed",
                "input_kind": "local_wechat_media",
                "agent_context_path": str(root / "audio_intake" / "agent-context.md"),
            }
            with mock.patch.object(worker, "run_autopublish_video_preflight", return_value=copied):
                with mock.patch.object(worker, "run_audio_intake_transcriber", return_value=audio) as transcribe:
                    preflight = worker.prepare_worker_preflight(task, root / "task")

        self.assertEqual(preflight["audio_intake"], audio)
        transcribe.assert_called_once_with(
            video.resolve(),
            output_dir=root / "task" / "audio_intake",
            source_local_id=91,
        )

    def test_resumed_worker_prompt_requires_audio_context_before_reasoning(self) -> None:
        worker = load_worker()
        calls: list[str] = []
        task = {
            "id": "audio-agent-task",
            "chat": "懒人科研",
            "request": "Please answer the voice request.",
            "source": {"local_id": 92, "local_type": 34, "voice_transcript": "请设计一个支架。"},
            "preflight": {
                "audio_intake": {
                    "status": "transcribed",
                    "input_kind": "wechat_voice_rows",
                    "agent_context_path": "/tmp/private/audio-agent-context.md",
                }
            },
        }

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            calls.append(prompt)
            return {"ok": True, "message": "done", "thread_id": "audio-thread", "resumed": True}

        with mock.patch.object(worker, "run_codex_session", side_effect=fake_agent):
            result = worker.run_worker_agent_session(
                task,
                {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "danger-full-access", "timeout_seconds": 300},
            )

        self.assertEqual(result, "done")
        self.assertIn("/tmp/private/audio-agent-context.md", calls[0])
        self.assertIn("Deterministic code owns exact same-chat media resolution", calls[0])
        self.assertIn("请设计一个支架", calls[0])

    def test_verified_voice_transcript_is_returned_beside_agent_answer(self) -> None:
        worker = load_worker()
        task = {
            "source": {
                "local_id": 93,
                "local_type": 34,
                "voice_transcript": "请把这个实验方案画成图。",
            },
            "preflight": {"audio_intake": {"status": "transcribed"}},
        }

        result = worker.attach_audio_transcript_reference(
            task,
            {"message": "我会先整理机制和对照组。", "confirmation": "", "files": []},
        )

        self.assertEqual(
            result["message"],
            "🎙️ 转写：请把这个实验方案画成图。\n\n我会先整理机制和对照组。",
        )
        self.assertFalse(result["no_reply"])
        self.assertEqual(result["data"]["audio_transcript_reference"]["source_local_id"], 93)

    def test_downloaded_wecom_voice_transcript_is_returned_once(self) -> None:
        worker = load_worker()
        task = {
            "source": {"local_id": 94, "local_type": "voice", "kind": "voice"},
            "preflight": {
                "audio_intake": {
                    "status": "cached",
                    "text": "Could you compare these two protocols?",
                    "agent_context_path": "/tmp/private/audio-agent-context.md",
                    "model": "private-model-name",
                }
            },
        }
        original = {"message": "Yes. I will compare the controls first.", "confirmation": "", "files": []}

        first = worker.attach_audio_transcript_reference(task, original)
        second = worker.attach_audio_transcript_reference(task, first)

        self.assertEqual(first, second)
        self.assertEqual(first["message"].count("🎙️ 转写："), 1)
        self.assertNotIn("/tmp/private", first["message"])
        self.assertNotIn("private-model-name", first["message"])

    def test_unverified_audio_does_not_create_transcript_reference(self) -> None:
        worker = load_worker()
        task = {
            "source": {"local_id": 95, "local_type": "voice", "kind": "voice"},
            "preflight": {"audio_intake": {"status": "failed", "text": "unverified words"}},
        }
        original = {"message": "Audio recovery is still pending.", "confirmation": "", "files": []}

        result = worker.attach_audio_transcript_reference(task, original)

        self.assertIs(result, original)
        self.assertNotIn("转写", result["message"])

    def test_wechat_send_env_extends_gui_alarm_to_worker_timeout(self) -> None:
        worker = load_worker()
        originals = {
            "WECHAT_WORKER_SEND_TIMEOUT_SECONDS": worker.os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS"),
            "WECHAT_WORKER_GUI_SEND_MAX_SECONDS": worker.os.environ.get("WECHAT_WORKER_GUI_SEND_MAX_SECONDS"),
            "WECHAT_GUI_SEND_MAX_SECONDS": worker.os.environ.get("WECHAT_GUI_SEND_MAX_SECONDS"),
        }
        try:
            worker.os.environ["WECHAT_WORKER_SEND_TIMEOUT_SECONDS"] = "180"
            worker.os.environ.pop("WECHAT_WORKER_GUI_SEND_MAX_SECONDS", None)
            worker.os.environ.pop("WECHAT_GUI_SEND_MAX_SECONDS", None)

            env = worker.wechat_send_env()
        finally:
            for key, value in originals.items():
                if value is None:
                    worker.os.environ.pop(key, None)
                else:
                    worker.os.environ[key] = value

        self.assertEqual(env["WECHAT_GUI_SEND_MAX_SECONDS"], "175")

    def test_grant_orchestrator_initializes_durable_workspace(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "task"
            task = {
                "id": "grant-task",
                "chat": "LabAgent",
                "request": "Write a vascular organoid grant with an editable figure and PDF.",
                "artifact_dir": str(artifact_dir),
                "route_decision": {"route_kind": "grant_proposal", "grant_title": "Vascular Organoids"},
                "routine": {"id": "grant_proposal"},
            }
            policy = {
                "model": "gpt-5.6-sol",
                "reasoning_effort": "xhigh",
                "timeout_seconds": 10800,
                "reuse_session": True,
            }
            with (
                mock.patch.object(worker, "prepare_worker_preflight", return_value={}),
                mock.patch.object(worker, "deterministic_preflight_result", return_value=None),
                mock.patch.object(worker, "persist_task_progress"),
                mock.patch.object(worker, "run_worker_agent_session", return_value="agent-result"),
            ):
                result = worker.run_task_orchestrator(task, policy)

            project = Path(task["grant_workspace"]["project_dir"])
            goal_exists = (project / "goal.json").is_file()
            prompt_exists = (project / "agent_goal_prompt.md").is_file()

        self.assertEqual(result, "agent-result")
        self.assertTrue(goal_exists)
        self.assertTrue(prompt_exists)
        self.assertIn("grant_workspace", worker.worker_agent_task_view(task))

    def test_grant_result_resumes_until_validation_passes(self) -> None:
        worker = load_worker()
        task = {
            "id": "grant-task",
            "route_decision": {"route_kind": "grant_proposal"},
            "routine": {"id": "grant_proposal"},
        }
        result = {
            "message": "drafted",
            "confirmation": "",
            "files": [],
            "data": {"grant_completion_pending": True, "grant_validation": {"ok": False}},
        }

        worker.apply_send_outcome(task, result, [])

        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["grant_validation_attempts"], 1)
        self.assertFalse(worker.should_send_worker_result(task, result))

    def test_grant_pdf_is_recovered_and_required_for_delivery(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "grant"
            (project / "figures" / "renders").mkdir(parents=True)
            pdf = project / "proposal.pdf"
            pdf.write_bytes(b"%PDF-1.4\nproposal")
            preview = project / "figures" / "renders" / "overview.png"
            preview.write_bytes(b"figure preview")
            (project / "figures" / "figure_manifest.json").write_text(
                json.dumps(
                    {
                        "editable": True,
                        "overview": "figures/renders/overview.png",
                        "assembly_source": "figures/figure_assembly.tex",
                        "parts": [],
                    }
                ),
                encoding="utf-8",
            )
            task = {
                "id": "grant-task",
                "route_decision": {"route_kind": "grant_proposal"},
                "routine": {"id": "grant_proposal"},
                "grant_workspace": {"project_dir": str(project)},
            }

            prepared = worker.prepare_result_files(
                {"message": "complete", "confirmation": "", "files": []},
                "",
                task=task,
            )

        self.assertEqual(prepared["files"][0], str(pdf.resolve()))
        self.assertIn(str(preview.resolve()), prepared["files"])
        self.assertTrue(worker.result_requires_file_delivery(task, prepared))
        self.assertEqual(worker.required_delivery_file_paths(prepared, task)[0], pdf.resolve())


if __name__ == "__main__":
    unittest.main()

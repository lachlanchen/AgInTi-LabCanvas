from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "wechat_completion_audit.py"
)
SCRIPTS_DIR = str(SCRIPT.parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SPEC = importlib.util.spec_from_file_location("wechat_completion_audit_for_tests", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class WeChatCompletionAuditTests(unittest.TestCase):
    def test_audit_requires_named_external_premise_grounding(self) -> None:
        task = self.task()
        task["route_decision"] = {
            "route_kind": "research_or_summary",
            "external_fact_grounding_required": True,
        }

        prompt = audit.completion_audit_prompt(
            task,
            {"message": "This analogy suggests a useful platform strategy.", "files": []},
            audit.coverage_items(task),
        )
        packet = json.loads(prompt.split("Task packet:\n", 1)[1])

        self.assertTrue(
            packet["current_route_state"]["external_fact_grounding_required"]
        )
        self.assertIn("actual relevant identity, product, mechanism, or role", prompt)
        self.assertIn("skips the named premise", prompt)

    def test_audit_prompt_distinguishes_local_sources_from_outbound_files(self) -> None:
        task = self.task()
        output_root = audit.ROOT / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "report.md").write_text("source", encoding="utf-8")
            (artifact_dir / "report.tex").write_text("source", encoding="utf-8")
            (artifact_dir / "report.pdf").write_bytes(b"%PDF-1.4\n")
            task["artifact_dir"] = str(artifact_dir)
            task["reprocess_reason"] = (
                "Keep Markdown and XeLaTeX sources locally and send only the PDF."
            )
            prompt = audit.completion_audit_prompt(
                task,
                {"message": "Complete.", "files": [str(artifact_dir / "report.pdf")]},
                audit.coverage_items(task),
            )

        packet = json.loads(prompt.split("Task packet:\n", 1)[1])
        self.assertEqual(
            packet["candidate_result"]["files"],
            [{"name": "report.pdf", "suffix": ".pdf"}],
        )
        self.assertEqual(
            {item["name"] for item in packet["task_local_artifacts"]},
            {"report.md", "report.pdf", "report.tex"},
        )
        self.assertIn("never a", prompt)
        self.assertIn("request to send or attach that file", prompt)

    def test_reprocess_reason_is_an_authoritative_coverage_item(self) -> None:
        task = self.task()
        task["reprocess_reason"] = "Create and return a validated PDF supplement."

        items = audit.coverage_items(task)
        reprocess_item = next(item for item in items if item["kind"] == "reprocess")

        self.assertEqual(reprocess_item["item_id"], f"reprocess:{task['id']}")
        missing = audit.deterministic_missing_requirements(
            task,
            {"message": "The research is complete.", "files": []},
        )
        self.assertTrue(any(item["kind"] == "artifact" for item in missing))

    def task(self) -> dict:
        return {
            "id": "parent-101",
            "chat": "LabAgent",
            "original_request": "请直接回答这个成像问题。",
            "source": {
                "local_id": 101,
                "sender_display": "Prof Ma",
            },
            "interruptions": [
                {
                    "incoming_task_id": "child-102",
                    "request": "请同时提供详细 PDF 报告。",
                    "source": {
                        "local_id": 102,
                        "sender_display": "Prof Ma",
                    },
                },
                {
                    "incoming_task_id": "child-103",
                    "request": "PDF 要包含证据和局限性。",
                    "source": {
                        "local_id": 103,
                        "sender_display": "Prof Ma",
                    },
                },
            ],
        }

    def test_consecutive_rows_keep_hard_queue_task_ids(self) -> None:
        items = audit.coverage_items(self.task())

        self.assertEqual(
            [item["item_id"] for item in items],
            ["task:parent-101", "task:child-102", "task:child-103"],
        )
        self.assertEqual([item["sequence"] for item in items], [1, 2, 3])
        self.assertEqual([item["source_id"] for item in items], ["101", "102", "103"])

    def test_transport_message_ledger_is_authoritative_for_coalesced_sources(self) -> None:
        task = {
            "id": "shares-229",
            "chat": "Shares鏈接",
            "original_request": "Summarize the latest article.",
            "source": {"local_id": 229, "sender_display": "owner"},
            "message_ledger": [
                {
                    "item_id": "message:message_1.db:228",
                    "sequence": 1,
                    "source_id": "srv-228",
                    "sender_display": "owner",
                    "text": "随感录：被权力污染的语言",
                },
                {
                    "item_id": "task:shares-229",
                    "sequence": 2,
                    "source_id": "srv-229",
                    "sender_display": "owner",
                    "text": "Tony Robbins on personal change",
                },
            ],
        }

        items = audit.coverage_items(task)

        self.assertEqual(
            [item["item_id"] for item in items],
            ["message:message_1.db:228", "task:shares-229"],
        )
        self.assertEqual(
            [item["text"] for item in items],
            ["随感录：被权力污染的语言", "Tony Robbins on personal change"],
        )
        self.assertEqual([item["sequence"] for item in items], [1, 2])

    def test_hard_ids_do_not_drop_long_consecutive_burst(self) -> None:
        task = {
            "id": "parent",
            "original_request": "message 0",
            "interruptions": [
                {
                    "incoming_task_id": f"child-{index}",
                    "request": f"message {index}",
                }
                for index in range(1, 32)
            ],
        }

        items = audit.coverage_items(task)

        self.assertEqual(len(items), 32)
        self.assertEqual(items[-1]["item_id"], "task:child-31")

    def test_long_burst_is_checked_in_batches_without_losing_ids(self) -> None:
        task = {
            "id": "parent",
            "original_request": "message 0",
            "interruptions": [
                {
                    "incoming_task_id": f"child-{index}",
                    "request": f"message {index}",
                }
                for index in range(1, 32)
            ],
        }
        seen: list[list[str]] = []

        def runner(prompt: str, **_kwargs: object) -> dict:
            payload_text = prompt.split("Task packet:\n", 1)[1]
            payload = json.loads(payload_text)
            item_ids = [
                item["item_id"]
                for item in payload["request_items"]
            ]
            seen.append(item_ids)
            return {
                "ok": True,
                "backend": "codex",
                "model": "gpt-5.3-codex-spark",
                "message": json.dumps(
                    {
                        "covered_item_ids": item_ids,
                        "missing": [],
                        "legitimate_blocker": False,
                        "complexity": "low",
                        "summary": "checked",
                    }
                ),
            }

        with mock.patch.dict(
            audit.os.environ,
            {"WECHAT_COMPLETION_AUDIT_BATCH_SIZE": "5"},
            clear=False,
        ):
            result = audit.run_completion_audit(
                task,
                {"message": "all messages handled", "files": []},
                runner=runner,
            )

        self.assertEqual(len(seen), 7)
        self.assertEqual(
            [item_id for batch in seen for item_id in batch],
            result["expected_item_ids"],
        )
        self.assertEqual(len(result["covered_item_ids"]), 32)
        self.assertTrue(result["coverage_complete"])

    def test_missing_list_does_not_truncate_numbered_rows(self) -> None:
        missing = [
            {
                "item_id": f"task:{index}",
                "requirement": f"requirement {index}",
                "kind": "action",
            }
            for index in range(30)
        ]

        self.assertEqual(len(audit.merge_missing(missing, [])), 30)
        self.assertEqual(len(audit.normalize_missing(missing)), 30)

    def test_explicit_pdf_requires_direct_answer_and_pdf_file(self) -> None:
        task = self.task()

        no_pdf = audit.deterministic_missing_requirements(
            task,
            {"message": "直接回答。", "files": []},
        )
        no_answer = audit.deterministic_missing_requirements(
            task,
            {"message": "", "files": ["/tmp/report.pdf"]},
        )
        complete = audit.deterministic_missing_requirements(
            task,
            {"message": "直接回答和报告摘要。", "files": ["/tmp/report.pdf"]},
        )

        self.assertEqual([item["kind"] for item in no_pdf], ["artifact"])
        self.assertEqual([item["kind"] for item in no_answer], ["reply"])
        self.assertEqual(complete, [])

    def test_message_only_schedule_cannot_infer_or_force_pdf_artifact(self) -> None:
        task = self.task()
        task["route_decision"] = {"message_only": True}

        missing = audit.deterministic_missing_requirements(
            task,
            {"message": "One concise inspiration message.", "files": []},
        )
        items = audit.coverage_items(task)
        grounded, rejected = audit.ground_model_missing_requirements(
            task,
            items,
            [
                {
                    "item_id": items[0]["item_id"],
                    "requirement": "Create and return the explicitly requested PDF artifact.",
                    "kind": "artifact",
                }
            ],
        )

        self.assertEqual(missing, [])
        self.assertEqual(grounded, [])
        self.assertEqual(rejected, {items[0]["item_id"]})

    def test_explicit_truncation_marker_requires_complete_repair(self) -> None:
        task = {
            "id": "plain-long-1",
            "original_request": "请完整回答这个问题。",
            "source": {"local_id": 1},
        }

        missing = audit.deterministic_missing_requirements(
            task,
            {"message": "回答只有开头。\n...[已截断]", "files": []},
        )

        self.assertTrue(any(item["kind"] == "reply" for item in missing))
        self.assertTrue(any("complete answer" in item["requirement"] for item in missing))

    def test_checker_marks_an_undecided_numbered_message_missing(self) -> None:
        def runner(_prompt: str, **_kwargs: object) -> dict:
            return {
                "ok": True,
                "backend": "codex",
                "model": "gpt-5.3-codex-spark",
                "message": (
                    '{"covered_item_ids":["task:parent-101","task:child-102"],'
                    '"missing":[],"legitimate_blocker":false,'
                    '"complexity":"low","summary":"checked"}'
                ),
            }

        result = audit.run_completion_audit(
            self.task(),
            {"message": "回答。", "files": ["/tmp/report.pdf"]},
            runner=runner,
        )

        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["missing"][0]["item_id"], "task:child-103")
        self.assertTrue(result["repair_recommended"])

    def test_checker_failure_is_bounded_but_pdf_contract_still_repairs(self) -> None:
        def runner(_prompt: str, **_kwargs: object) -> dict:
            raise TimeoutError("bounded timeout")

        result = audit.run_completion_audit(
            self.task(),
            {"message": "回答。", "files": []},
            runner=runner,
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["repair_recommended"])
        self.assertEqual(result["missing"][0]["kind"], "artifact")

    def test_legitimate_blocker_covers_only_the_explicitly_blocked_item(self) -> None:
        def runner(_prompt: str, **_kwargs: object) -> dict:
            return {
                "ok": True,
                "backend": "codex",
                "model": "gpt-5.3-codex-spark",
                "message": json.dumps(
                    {
                        "covered_item_ids": [
                            "task:parent-101",
                            "task:child-102",
                        ],
                        "missing": [
                            {
                                "item_id": "task:child-103",
                                "requirement": "Evidence limitations were not addressed.",
                                "kind": "reply",
                            }
                        ],
                        "legitimate_blocker": True,
                        "complexity": "low",
                        "summary": "PDF is blocked, but another request remains missing.",
                    }
                ),
            }

        result = audit.run_completion_audit(
            self.task(),
            {
                "message": "PDF delivery is blocked by an approval gate.",
                "files": [],
            },
            runner=runner,
        )

        self.assertIn("task:child-102", result["covered_item_ids"])
        self.assertNotIn("task:child-103", result["covered_item_ids"])
        self.assertEqual(
            [item["item_id"] for item in result["missing"]],
            ["task:child-103"],
        )

    def test_negated_pdf_does_not_create_artifact_contract(self) -> None:
        task = {
            "id": "no-pdf",
            "original_request": "只要一句话，不要 PDF。",
            "source": {"local_id": 9},
        }

        self.assertEqual(
            audit.deterministic_missing_requirements(
                task,
                {"message": "一句话。", "files": []},
            ),
            [],
        )

    def test_worker_envelope_does_not_turn_pdf_policy_into_user_request(self) -> None:
        task = {
            "id": "article-777",
            "chat": "Shares鏈接",
            "original_request": (
                "Return a natural concise answer plus files only when requested. "
                "Do not include Markdown, TeX, PDF, or screenshots unless the current "
                "message explicitly asks for a report.\n\n"
                "Current coalesced request:\n"
                "陈苗: [WeChat article] 丘脑智能完成融资，讨论多模态长期记忆\n\n"
                "Recent history:\n"
                "older unrelated PDF discussion"
            ),
            "source": {"local_id": 777, "sender_display": "陈苗"},
        }
        items = audit.coverage_items(task)

        self.assertEqual(
            items[0]["text"],
            "陈苗: [WeChat article] 丘脑智能完成融资，讨论多模态长期记忆",
        )
        self.assertFalse(audit.explicit_pdf_requested(items))
        self.assertEqual(
            audit.deterministic_missing_requirements(
                task,
                {"message": "文章重点是长期记忆基础设施。", "files": []},
            ),
            [],
        )

    def test_attachment_intake_envelope_is_not_a_second_human_request(self) -> None:
        task = {
            "id": "publish-78",
            "chat": "My devices",
            "request": (
                "Worker policy text.\n\n"
                "Current coalesced request:\n"
                "Chen: New WeChat video item received; inspect its message "
                "metadata, card/link fields, and recent synced files/media, "
                "then summarize or process it.\n"
                "metadata: [WeChat video] <msg><videomsg length=\"123\"/></msg>\n"
                "Chen: 帮我发布一下这个视频\n\n"
                "Recent history:\nolder text"
            ),
            "source": {"local_id": 78, "sender_display": "Chen"},
        }

        items = audit.coverage_items(task)

        self.assertEqual(items[0]["text"], "Chen: 帮我发布一下这个视频")

    def test_exact_transport_rows_override_suspended_publish_wrappers(self) -> None:
        task = {
            "id": "publish-parent",
            "request": (
                "This is a suspended WeChat public-publish task. Wait for a "
                "different participant.\n\nSame-chat reference rows:\n"
                "title: unrelated-reference.pdf"
            ),
            "source": {
                "local_id": 20,
                "server_id": 2000,
                "sender": "owner",
                "sender_display": "Chen",
            },
            "context": [
                {
                    "local_id": 20,
                    "server_id": 2000,
                    "sender": "owner",
                    "sender_display": "Chen",
                    "content": "owner:\n你能发布今天的视频吗",
                }
            ],
            "interruptions": [
                {
                    "incoming_task_id": "publish-child",
                    "request": (
                        "This is another suspended wrapper.\n"
                        "title: unrelated-reference.pdf"
                    ),
                    "source": {
                        "local_id": 23,
                        "server_id": 2300,
                        "sender": "owner",
                        "sender_display": "Chen",
                    },
                    "context": [
                        {
                            "local_id": 23,
                            "server_id": 2300,
                            "sender": "owner",
                            "sender_display": "Chen",
                            "content": "owner:\n可以发布吗",
                        }
                    ],
                }
            ],
        }

        items = audit.coverage_items(task)

        self.assertEqual(
            [item["text"] for item in items],
            ["你能发布今天的视频吗", "可以发布吗"],
        )
        self.assertFalse(audit.explicit_pdf_requested(items))

    def test_completion_model_cannot_resurrect_superseded_publish_confirmation(self) -> None:
        task = {
            "id": "publish-parent",
            "source": {
                "local_id": 20,
                "server_id": 2000,
                "sender": "owner",
            },
            "context": [
                {
                    "local_id": 20,
                    "server_id": 2000,
                    "sender": "owner",
                    "content": "owner:\n你能发布今天的视频吗",
                }
            ],
            "route_decision": {
                "route_kind": "publish_video",
                "public_publish_allowed": True,
                "requires_third_party_publish_confirmation": False,
                "requester_publish_override": True,
            },
        }

        def runner(_prompt: str, **_kwargs: object) -> dict:
            return {
                "ok": True,
                "backend": "codex",
                "model": "gpt-5.3-codex-spark",
                "message": json.dumps(
                    {
                        "covered_item_ids": [],
                        "missing": [
                            {
                                "item_id": "task:publish-parent",
                                "requirement": (
                                    "Wait for third-party confirmation before "
                                    "public publication."
                                ),
                                "kind": "action",
                            },
                            {
                                "item_id": "task:publish-parent",
                                "requirement": "Create an unrelated PDF.",
                                "kind": "artifact",
                            },
                        ],
                        "legitimate_blocker": False,
                        "complexity": "low",
                        "summary": "stale wrapper inference",
                    }
                ),
            }

        result = audit.run_completion_audit(
            task,
            {
                "message": "发布完成；检测到额外平台并已如实报告。",
                "files": [],
                "data": {
                    "publish_stage": {
                        "verified": False,
                        "stage": "published_with_unrequested_platform",
                        "requested_platforms": ["shipinhao"],
                        "verified_platforms": ["douyin", "shipinhao"],
                        "unexpected_platforms": ["douyin"],
                        "requested_platforms_verified": True,
                        "platform_set_matches": False,
                    }
                },
            },
            runner=runner,
        )

        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["covered_item_ids"], ["task:publish-parent"])
        self.assertEqual(result["missing"], [])

    def test_naked_attachment_keeps_only_default_intake_contract(self) -> None:
        task = {
            "id": "video-77",
            "original_request": (
                "Chen: New WeChat video item received; inspect its message "
                "metadata, card/link fields, and recent synced files/media, "
                "then summarize or process it.\n"
                "metadata: [WeChat video] <msg/>"
            ),
            "source": {"local_id": 77, "sender_display": "Chen"},
        }

        items = audit.coverage_items(task)

        self.assertEqual(
            items[0]["text"],
            (
                "Incoming WeChat video attachment: apply the configured default "
                "intake behavior for this chat."
            ),
        )

    def test_link_inbox_policy_does_not_create_pdf_request(self) -> None:
        task = {
            "id": "finder-780",
            "request": (
                "Worker policy.\n\n"
                "Current coalesced request:\n"
                "Chen: New WeChat file/link item received; inspect its message "
                "metadata, card/link fields, and recent synced files/media, then "
                "summarize or process it.\n"
                "metadata: [WeChat video channel]\n"
                "title: Unsupported placeholder\n"
                "url: https://support.weixin.qq.com/update/\n"
                "channel: Example\n"
                "channel_description: example video\n\n"
                "Link/read-later inbox source received. Return one concise summary. "
                "Do not include PDF unless explicitly requested.\n"
                "Structured source text:\n[WeChat video channel]"
            ),
            "source": {"local_id": 780, "sender_display": "Chen"},
        }

        items = audit.coverage_items(task)

        self.assertEqual(
            items[0]["text"],
            (
                "Incoming WeChat file/link attachment: apply the configured "
                "default intake behavior for this chat."
            ),
        )
        self.assertFalse(audit.explicit_pdf_requested(items))

    def test_link_inbox_interruption_policy_does_not_create_pdf_request(self) -> None:
        envelope = (
            "Chen: New WeChat file/link item received; inspect its message "
            "metadata, card/link fields, and recent synced files/media, then "
            "summarize or process it.\n"
            "metadata: [WeChat video channel]\n"
            "title: Example\n\n"
            "Link/read-later inbox source received. Do not include PDF unless "
            "explicitly requested.\n"
            "Structured source text:\nExample"
        )
        task = {
            "id": "finder-parent",
            "request": (
                "Current coalesced request:\n"
                f"{envelope}"
            ),
            "interruptions": [
                {
                    "incoming_task_id": "finder-child",
                    "request": envelope,
                    "source": {"local_id": 781, "sender_display": "Chen"},
                }
            ],
            "source": {"local_id": 780, "sender_display": "Chen"},
        }

        items = audit.coverage_items(task)

        self.assertEqual(len(items), 2)
        self.assertTrue(
            all("default intake behavior" in item["text"] for item in items)
        )
        self.assertFalse(audit.explicit_pdf_requested(items))

    def test_uploaded_pdf_metadata_does_not_request_outbound_pdf(self) -> None:
        task = {
            "id": "pdf-upload-146",
            "request": (
                "Current coalesced request:\n"
                "Chen: New WeChat file upload received with no explicit "
                "instruction; run source-scoped file intake first. Sync/save the "
                "exact source attachment, record filename/type/size/checksum and "
                "a task-scoped copy path, then safely inspect ZIP/Word/PDF/text "
                "content and give a concise natural preliminary summary.\n"
                "metadata: [WeChat file]\n"
                "title: recent-items.zh.pdf\n"
                "extension: pdf\n"
                "size_bytes: 131684\n"
                "md5: abc123"
            ),
            "source": {"local_id": 146, "sender_display": "Chen"},
        }

        items = audit.coverage_items(task)

        self.assertEqual(
            items[0]["text"],
            (
                "Incoming WeChat file attachment: apply the configured default "
                "intake behavior for this chat."
            ),
        )
        self.assertFalse(audit.explicit_pdf_requested(items))

    def test_completion_model_cannot_invent_pdf_artifact_requirement(self) -> None:
        task = {
            "id": "finder-780",
            "original_request": (
                "Chen: New WeChat file/link item received; inspect its message "
                "metadata, card/link fields, and recent synced files/media, then "
                "summarize or process it.\n"
                "metadata: [WeChat video channel]\n"
                "title: Example"
            ),
            "source": {"local_id": 780, "sender_display": "Chen"},
        }

        def runner(_prompt: str, **_kwargs: object) -> dict:
            return {
                "ok": True,
                "backend": "codex",
                "model": "gpt-5.3-codex-spark",
                "message": json.dumps(
                    {
                        "covered_item_ids": [],
                        "missing": [
                            {
                                "item_id": "task:finder-780",
                                "requirement": "Create the requested PDF.",
                                "kind": "artifact",
                            }
                        ],
                        "legitimate_blocker": False,
                        "complexity": "low",
                        "summary": "incorrect artifact inference",
                    }
                ),
            }

        result = audit.run_completion_audit(
            task,
            {"message": "这是一条视频号内容摘要。", "files": []},
            runner=runner,
        )

        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["covered_item_ids"], ["task:finder-780"])
        self.assertEqual(result["missing"], [])

    def test_unavailable_checker_does_not_block_without_deterministic_gap(self) -> None:
        task = {
            "id": "plain-1",
            "original_request": "请简要说明这条消息。",
            "source": {"local_id": 1},
        }

        def runner(_prompt: str, **_kwargs: object) -> dict:
            raise TimeoutError("quota unavailable")

        result = audit.run_completion_audit(
            task,
            {"message": "简要说明。", "files": []},
            runner=runner,
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["covered_item_ids"], ["task:plain-1"])
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["repair_recommended"])

    def test_audit_packet_includes_bounded_terminal_publish_evidence(self) -> None:
        task = {
            "id": "publish-78",
            "original_request": "帮我发布一下这个视频",
            "source": {"local_id": 78},
        }
        result = {
            "message": "发布完成。",
            "files": [],
            "data": {
                "publish_stage": {
                    "verified": True,
                    "stage": "published_verified",
                    "video_id": 495,
                    "requested_platforms": ["shipinhao", "youtube"],
                    "verified_platforms": ["shipinhao", "youtube"],
                    "local_jobs": [
                        {
                            "id": 330,
                            "status": "done",
                            "remote_status": "done",
                            "filename": "private.zip",
                        }
                    ],
                    "remote_jobs": [
                        {
                            "id": "remote-330",
                            "status": "done",
                            "filename": "private.zip",
                        }
                    ],
                }
            },
        }

        prompt = audit.completion_audit_prompt(
            task,
            result,
            audit.coverage_items(task),
        )
        packet = json.loads(prompt.split("Task packet:\n", 1)[1])

        self.assertEqual(
            packet["candidate_result"]["publish_stage"],
            {
                "verified": True,
                "stage": "published_verified",
                "video_id": 495,
                "requested_platforms": ["shipinhao", "youtube"],
                "verified_platforms": ["shipinhao", "youtube"],
                "local_jobs": [
                    {"id": 330, "status": "done", "remote_status": "done"}
                ],
                "remote_jobs": [{"id": "remote-330", "status": "done"}],
            },
        )


if __name__ == "__main__":
    unittest.main()

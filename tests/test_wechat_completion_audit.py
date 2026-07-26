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


if __name__ == "__main__":
    unittest.main()

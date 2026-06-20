from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


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
    def test_worker_policy_selects_high_for_cad_or_pcb_tasks(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "design a PCB and render the CAD in Blender"})

        self.assertEqual(policy["model"], "gpt-5.5")
        self.assertEqual(policy["reasoning_effort"], "high")
        self.assertEqual(policy["sandbox"], "danger-full-access")
        self.assertEqual(policy["timeout_seconds"], 600)

    def test_worker_policy_uses_medium_for_literature_summary(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "summarize this PDF paper"})

        self.assertEqual(policy["reasoning_effort"], "medium")

    def test_worker_policy_escalates_weak_low_result(self) -> None:
        worker = load_worker()
        next_policy = worker.escalated_policy(
            {"model": "gpt-5.5", "reasoning_effort": "low", "sandbox": "workspace-write", "timeout_seconds": 120},
            "Worker failed: timed out before completing the task.",
        )

        self.assertIsNotNone(next_policy)
        self.assertEqual(next_policy["reasoning_effort"], "medium")

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
        self.assertIn("Avoid sending the same answer again", str(calls[0]["prompt"]))
        self.assertIn("Strict source isolation", str(calls[0]["prompt"]))
        self.assertIn("Never use media, files, or generated artifacts from another chat", str(calls[0]["prompt"]))
        self.assertIn("If no exact matching source media is available", str(calls[0]["prompt"]))
        self.assertIn("LabCanvas tool playbook", str(calls[0]["prompt"]))
        self.assertIn("Match every input file/media path to this task's exact", str(calls[0]["prompt"]))
        self.assertIn("studio figure-grid", str(calls[0]["prompt"]))
        self.assertIn("AgInTi image-generation", str(calls[0]["prompt"]))
        self.assertIn("studio lab-task", str(calls[0]["prompt"]))
        self.assertIn("render-scene", str(calls[0]["prompt"]))
        self.assertIn("Shipinhao/Finder", str(calls[0]["prompt"]))
        self.assertIn("@元宝", str(calls[0]["prompt"]))
        self.assertIn("英文全文", str(calls[0]["prompt"]))
        self.assertIn("Do not post a comment", str(calls[0]["prompt"]))
        self.assertIn("do not produce a \"deep analysis\"", str(calls[0]["prompt"]))
        self.assertIn("files", str(calls[0]["prompt"]))

    def test_worker_result_collects_nested_and_plain_artifact_paths(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "render.png"
            step = Path(tmp) / "part.step"
            png.write_bytes(b"png")
            step.write_text("step", encoding="utf-8")
            raw = json.dumps({"message": "", "artifacts": [{"path": str(png)}]}, ensure_ascii=False)
            result = worker.parse_worker_result(raw)

            prepared = worker.prepare_result_files(result, f"Also created {step}")

        self.assertIn(str(png.resolve()), prepared["files"])
        self.assertIn(str(step.resolve()), prepared["files"])
        self.assertIn("Generated 2 artifact", prepared["message"])

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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


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
        self.assertIn("explicit source/reference rows embedded in `request`", str(calls[0]["prompt"]))
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
        self.assertIn("lazyedit-publish-workflow/SKILL.md", str(calls[0]["prompt"]))
        self.assertIn("scripts/lazyedit_publish.py", str(calls[0]["prompt"]))
        self.assertIn("--correction-prompt-file", str(calls[0]["prompt"]))
        self.assertIn("--metadata-prompt-file", str(calls[0]["prompt"]))
        self.assertIn("api/autopublish/queue", str(calls[0]["prompt"]))
        self.assertIn("lazyingart:8081/publish/queue", str(calls[0]["prompt"]))
        self.assertIn("fail closed", str(calls[0]["prompt"]))
        self.assertIn("nearby/older video", str(calls[0]["prompt"]))
        self.assertIn("files", str(calls[0]["prompt"]))

    def test_lazyedit_publish_skill_is_checked_in(self) -> None:
        skill = ROOT / "agentic_tools" / "wechat_gui_agent" / "skills" / "lazyedit-publish-workflow" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")

        self.assertIn("LazyEdit Publish Workflow", text)
        self.assertIn("autopublish-video", text)
        self.assertIn("scripts/lazyedit_publish.py", text)
        self.assertIn("Shipinhao", text)
        self.assertIn("--metadata-prompt-file", text)

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
        self.assertIn("Generated 3 artifact", prepared["message"])

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
            with mock.patch.object(worker.subprocess, "run", side_effect=fake_run):
                preflight = worker.prepare_worker_preflight(task, Path(tmp))

            context_path = Path(preflight["lazyedit_context"]["correction_prompt_file"])
            metadata_path = Path(preflight["lazyedit_context"]["metadata_prompt_file"])
            context_text = context_path.read_text(encoding="utf-8")

        self.assertTrue(context_path.name.endswith("correction_context.md"))
        self.assertTrue(metadata_path.name.endswith("metadata_brief.md"))
        self.assertIn("haircut and curly", context_text)
        self.assertIn("bea815fa6ed81bbd5da77ac6895c5fd9", context_text)
        self.assertEqual(preflight["autopublish_video"]["ok"], True)
        self.assertEqual(preflight["autopublish_video"]["message_local_ids"], [14])
        self.assertTrue(calls)
        self.assertIn("--message-local-id", calls[0])
        self.assertIn("14", calls[0])
        self.assertIn("--fetch-gui", calls[0])

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

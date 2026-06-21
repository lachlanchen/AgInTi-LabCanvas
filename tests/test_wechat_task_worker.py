from __future__ import annotations

import contextlib
import io
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

    def test_worker_policy_selects_xhigh_for_full_autonomous_tasks(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "fully implement this WeChat automation, commit and push"})

        self.assertEqual(policy["model"], "gpt-5.5")
        self.assertEqual(policy["reasoning_effort"], "xhigh")
        self.assertEqual(policy["timeout_seconds"], 1200)

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

    def test_worker_policy_escalates_to_xhigh_for_failed_high_result(self) -> None:
        worker = load_worker()
        next_policy = worker.escalated_policy(
            {"model": "gpt-5.5", "reasoning_effort": "high", "sandbox": "danger-full-access", "timeout_seconds": 600},
            "Worker failed: cannot complete the CAD export.",
        )

        self.assertIsNotNone(next_policy)
        assert next_policy is not None
        self.assertEqual(next_policy["model"], "gpt-5.5")
        self.assertEqual(next_policy["reasoning_effort"], "xhigh")
        self.assertEqual(next_policy["timeout_seconds"], 1200)

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

    def test_run_worker_codex_retries_until_xhigh_success(self) -> None:
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
        self.assertIn("verification gate", str(calls[0]["prompt"]))
        self.assertIn("Do not stop after a successful no-publish pass", str(calls[0]["prompt"]))
        self.assertIn("LALACHAN/RaraXia/AyaChan/SasaKun story-video generation", str(calls[0]["prompt"]))
        self.assertIn("words-card.jpg", str(calls[0]["prompt"]))
        self.assertIn("raraxia.jpeg", str(calls[0]["prompt"]))
        self.assertIn("ayachan.png", str(calls[0]["prompt"]))
        self.assertIn("sasakun.jpeg", str(calls[0]["prompt"]))
        self.assertIn("Trio.png", str(calls[0]["prompt"]))
        self.assertIn("Seedance 2.0 Fast non-VIP", str(calls[0]["prompt"]))
        self.assertIn("Do not paste local filesystem paths", str(calls[0]["prompt"]))
        self.assertIn("api/autopublish/queue", str(calls[0]["prompt"]))
        self.assertIn("lazyingart:8081/publish/queue", str(calls[0]["prompt"]))
        self.assertIn("fail closed", str(calls[0]["prompt"]))
        self.assertIn("nearby/older video", str(calls[0]["prompt"]))
        self.assertIn("files", str(calls[0]["prompt"]))

    def test_worker_policy_selects_high_for_lalachan_video_generation(self) -> None:
        worker = load_worker()
        policy = worker.choose_worker_policy({"request": "写 RaraXia AyaChan SasaKun 故事并用小云雀生成视频"})

        self.assertEqual(policy["reasoning_effort"], "high")

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

    def test_exact_video_preflight_success_runs_deterministic_lazyedit_publish(self) -> None:
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
                        raw = worker.deterministic_preflight_result(task)

        self.assertIsNotNone(raw)
        payload = json.loads(raw or "{}")
        self.assertIn("video_id=393", payload["message"])
        self.assertIn("remote_job_id=job-1", payload["message"])
        self.assertEqual(calls[0]["platforms"], ["shipinhao", "youtube", "instagram"])
        self.assertEqual(calls[0]["video_id"], 393)

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

    def test_send_result_notes_markdown_files_without_gui_file_send(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        files: list[Path] = []
        original_message = worker.send_message
        original_file = worker.send_file
        try:
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(message)
            worker.send_file = lambda file_path, *_args, **_kwargs: files.append(Path(file_path))
            task: dict[str, object] = {}
            worker.send_result_once(
                {
                    "message": "done",
                    "confirmation": "",
                    "files": ["/tmp/story.md", "/tmp/preview.png"],
                },
                "🍓我的设备",
                Path("/tmp/no-targets.json"),
                target={"name": "🍓我的设备", "query": "我的设备", "expected_title": "🍓我的设备"},
                task=task,
            )
        finally:
            worker.send_message = original_message
            worker.send_file = original_file

        self.assertEqual(files, [Path("/tmp/preview.png")])
        self.assertEqual(task["unsent_saved_files"], ["/tmp/story.md"])
        self.assertIn("Saved files:", messages[0])
        self.assertIn("/tmp/story.md", messages[0])

    def test_optional_file_send_failure_does_not_retry_whole_message(self) -> None:
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

        self.assertEqual(errors, [])
        self.assertEqual(sent_messages, ["done"])
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

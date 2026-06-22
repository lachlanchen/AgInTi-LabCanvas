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

        self.assertEqual(policy["model"], "gpt-5.5")
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

    def test_generate_video_status_backoff_uses_page_status(self) -> None:
        worker = load_worker()

        self.assertEqual(worker.generated_video_status_backoff_seconds("大约还需 8 分钟"), 312)
        self.assertEqual(worker.generated_video_status_backoff_seconds("预计还需 3 小时"), 1800)
        self.assertEqual(worker.generated_video_status_backoff_seconds("about 3 hours remaining"), 1800)
        self.assertEqual(worker.generated_video_status_backoff_seconds("about 12 minutes remaining"), 468)
        self.assertEqual(worker.generated_video_status_backoff_seconds("排队等待中"), 300)
        self.assertEqual(worker.generated_video_status_backoff_seconds("生成中"), 120)
        self.assertEqual(worker.generated_video_status_backoff_seconds("", "please generate 30s video"), 180)

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
        self.assertTrue(stages["wechat_send_back"])
        self.assertFalse(stages["lazyedit_import"])
        self.assertFalse(stages["public_publish"])
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

    def test_real_mp4_bridge_failure_blocks_required_delivery(self) -> None:
        worker = load_worker()
        original_run_send = worker.run_send_subprocess
        original_bridge = worker.run_file_bridge_subprocess
        original_delay = worker.os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY")
        try:
            worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = "0"
            worker.run_send_subprocess = lambda *_args, **_kwargs: None

            def fail_bridge(*_args, **_kwargs):
                raise RuntimeError("file bridge failed with exit 1")

            worker.run_file_bridge_subprocess = fail_bridge
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                mp4 = tmp_path / "bridge-failed.mp4"
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
            worker.run_send_subprocess = original_run_send
            worker.run_file_bridge_subprocess = original_bridge
            if original_delay is None:
                worker.os.environ.pop("WECHAT_WORKER_SEND_RETRY_DELAY", None)
            else:
                worker.os.environ["WECHAT_WORKER_SEND_RETRY_DELAY"] = original_delay

        self.assertTrue(errors)
        self.assertEqual(task["status"], worker.SEND_DEFERRED_ARTIFACT_STATUS)
        self.assertEqual(task["send_deferred_reason"], "required_artifact_delivery")
        self.assertNotIn("sent_file_paths", task)
        self.assertIn("file_send_errors", task)

    def test_mp4_sent_then_text_lock_closes_artifact_delivery(self) -> None:
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
        self.assertEqual(task["status"], "done")
        self.assertIn("sent-before-lock.mp4", "\n".join(task["sent_file_paths"]))
        self.assertIn("post_artifact_send_errors", task)
        self.assertNotIn("send_deferred_reason", task)

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

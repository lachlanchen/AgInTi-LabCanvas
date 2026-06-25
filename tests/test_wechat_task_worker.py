from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import hashlib
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
        self.assertIn("wechat selftest --suite all", wrapper_text)
        self.assertIn("wechat_supervisor.local.env", wrapper_text)
        self.assertIn('source "$PRIVATE_ENV"', wrapper_text)

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

    def test_blank_title_guard_detects_short_ascii_ocr_noise(self) -> None:
        worker = load_worker()
        errors = [
            "RuntimeError: Opened chat title guard failed for EchoMind: OCR='3 - oO\\n|'.",
        ]

        self.assertTrue(worker.send_errors_indicate_blank_title_guard(errors))
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), "title_guard_blank")

    def test_blank_title_guard_does_not_hide_real_wrong_chat_title(self) -> None:
        worker = load_worker()
        errors = [
            "RuntimeError: Opened chat title guard failed for EchoMind: OCR='鏈接'.",
        ]

        self.assertFalse(worker.send_errors_indicate_blank_title_guard(errors))
        self.assertFalse(worker.send_errors_indicate_deferable(errors))

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
        self.assertIn("@元宝", str(calls[0]["prompt"]))
        self.assertIn("英文全文", str(calls[0]["prompt"]))
        self.assertIn("Do not post a comment", str(calls[0]["prompt"]))
        self.assertIn("do not produce a \"deep analysis\"", str(calls[0]["prompt"]))
        self.assertIn("Do not open an external Chrome/browser for mp.weixin by default", str(calls[0]["prompt"]))
        self.assertIn("native WeChat article/webview", str(calls[0]["prompt"]))
        self.assertIn("WECHAT_ALLOW_EXTERNAL_BROWSER_FOR_MP_WEIXIN=1", str(calls[0]["prompt"]))
        self.assertIn("waiting_confirmation", str(calls[0]["prompt"]))
        self.assertIn("Link/read-later summary reports", str(calls[0]["prompt"]))
        self.assertIn("Markdown report", str(calls[0]["prompt"]))
        self.assertIn("PDF report", str(calls[0]["prompt"]))
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
        self.assertTrue(calls)
        self.assertIn("--message-local-id", calls[0])
        self.assertIn("14", calls[0])
        self.assertIn("--fetch-gui", calls[0])

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
                        "result": {"message": "stale wrong result", "files": []},
                        "preflight": {"autopublish_video": {"status": "artifact-ledger-match"}},
                        "routine": {"id": "video_publish_existing", "rules": ["old rule"]},
                        "routine_contract": {"json": "/tmp/old.json"},
                        "orchestrator": {"stage": "old"},
                        "worker_policy_attempts": [{"attempt": 1}],
                        "artifact_dir": "/tmp/old-artifacts",
                        "execution_contract": {"old": True},
                        "send_errors": ["timeout"],
                        "existing_video_publish_poststage": {"video_id": 395},
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
        self.assertNotIn("preflight", stored)
        self.assertNotIn("routine", stored)
        self.assertNotIn("routine_contract", stored)
        self.assertNotIn("orchestrator", stored)
        self.assertNotIn("worker_policy_attempts", stored)
        self.assertNotIn("artifact_dir", stored)
        self.assertNotIn("execution_contract", stored)
        self.assertNotIn("send_errors", stored)
        self.assertNotIn("existing_video_publish_poststage", stored)
        self.assertEqual(stored["reprocess_reason"], "source resolver fixed")
        self.assertEqual(stored["reprocess_history"][0]["previous_status"], "send_retrying")
        self.assertIn("stale wrong result", stored["reprocess_history"][0]["previous_result_message_excerpt"])

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
                            preflight = worker.prepare_media_resolution_preflight(task, tmp_path / "artifact")
                            task["preflight"] = {"media_resolution": preflight}
                            tool_context = worker.build_media_resolution_tool_context(task)

            copied = preflight["copied"]
            manifest_text = Path(preflight["manifest_md"]).read_text(encoding="utf-8")

        self.assertEqual(copied[0]["ocr"]["status"], "ok")
        self.assertEqual(copied[0]["image_metadata"]["width"], 1200)
        self.assertIn("OCR text:", tool_context)
        self.assertIn("Legal standard image OCR text", tool_context)
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

    def test_generate_video_publish_route_keeps_lazyedit_context_without_old_autopublish(self) -> None:
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
        self.assertIn("old-video", context_text)

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
        self.assertEqual(calls[0]["platforms"], ["shipinhao", "youtube", "instagram"])
        self.assertEqual(calls[0]["video_id"], 393)

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

    def test_exact_video_publish_uses_known_lazyedit_video_id_from_source_task(self) -> None:
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
        self.assertEqual(calls[0]["video_id"], 404)
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

    def test_publish_poststage_login_blocker_waits_for_confirmation(self) -> None:
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
                    raw = worker.deterministic_existing_video_publish_poststage_result(task)

        payload = json.loads(raw or "{}")
        self.assertEqual(payload["publish_stage"]["stage"], "waiting_login")
        self.assertIn("Please complete the platform login", payload["confirmation"])
        self.assertIn("poststage", payload)
        self.assertNotIn("publish_poststage_retry", payload)

        result = {"message": payload["message"], "confirmation": payload["confirmation"], "files": [], "data": payload}
        worker.apply_send_outcome(task, result, [])
        self.assertEqual(task["status"], "waiting_confirmation")
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

    def test_run_send_subprocess_defers_when_gui_lock_is_busy(self) -> None:
        worker = load_worker()
        original_lock_busy = worker.gui_send_lock_busy
        original_run = worker.run_subprocess_group
        try:
            worker.gui_send_lock_busy = lambda: True

            def fail_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("busy send lane should not spawn a GUI sender")

            worker.run_subprocess_group = fail_run
            with self.assertRaisesRegex(RuntimeError, "WECHAT_SEND_BUSY"):
                worker.run_send_subprocess(["python3", "-c", "print('unused')"], timeout=1)
        finally:
            worker.gui_send_lock_busy = original_lock_busy
            worker.run_subprocess_group = original_run

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

    def test_blank_title_guard_error_is_retryable_but_wrong_title_is_not(self) -> None:
        worker = load_worker()
        blank = ["attempt 1: Opened chat title guard failed for EchoMind: OCR=''."]
        wrong = ["attempt 1: Opened chat title guard failed for EchoMind: OCR='OtherChat'."]

        self.assertTrue(worker.send_errors_indicate_deferable(blank))
        self.assertEqual(worker.send_deferred_reason_from_errors(blank), "title_guard_blank")
        self.assertFalse(worker.send_errors_indicate_deferable(wrong))

    def test_wechat_entry_required_error_is_retryable(self) -> None:
        worker = load_worker()
        errors = [
            "attempt 1: send command failed with exit 1; "
            "stderr=WECHAT_ENTRY_REQUIRED: WeChat is visible but not in the main chat UI"
        ]

        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), "wechat_entry_required")

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

    def test_claim_next_deferred_send_recovers_stale_transport_after_recovery_cap(self) -> None:
        worker = load_worker()
        original_busy_backoff = worker.os.environ.get("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS")
        original_failed_max = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES")
        original_transient_max = worker.os.environ.get("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES")
        original_recovery = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES")
        original_stale = worker.os.environ.get("WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS")
        original_lock_busy = worker.gui_send_lock_busy
        try:
            worker.os.environ["WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS"] = "0"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_MAX_RETRIES"] = "0"
            worker.os.environ["WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES"] = "5"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES"] = "1"
            worker.os.environ["WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS"] = "60"
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

        def fake_android(_result, target_chat, _task):
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

    def test_send_result_attaches_markdown_and_pdf_companion_by_default(self) -> None:
        worker = load_worker()
        messages: list[str] = []
        files: list[Path] = []
        original_message = worker.send_message
        original_file = worker.send_file
        original_render = worker.render_markdown_pdf
        try:
            worker.send_message = lambda message, *_args, **_kwargs: messages.append(message)
            worker.send_file = lambda file_path, *_args, **_kwargs: files.append(Path(file_path))
            def fake_render_markdown_pdf(source: Path, output: Path) -> Path:
                output.write_bytes(b"%PDF-1.4\n")
                return output

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
            worker.render_markdown_pdf = original_render

        self.assertEqual(files, [story, story.with_suffix(".pdf"), preview])
        self.assertNotIn("unsent_saved_files", task)
        self.assertEqual(messages, ["done"])

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

    def test_research_summary_files_are_best_effort_unless_explicitly_required(self) -> None:
        worker = load_worker()
        task = {"route_decision": {"route_kind": "research_or_summary"}}
        result = {"message": "summary", "files": ["/tmp/summary.md", "/tmp/thumb.png"]}

        self.assertFalse(worker.result_requires_file_delivery(task, result))
        result["data"] = {"require_file_delivery": True}
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

    def test_claim_next_pending_recovers_dead_worker_pid_immediately(self) -> None:
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

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["id"], "task-1")
        self.assertEqual(claimed["status"], "in_progress")
        self.assertEqual(claimed["claim_history"][0]["worker_id"], "pid:999999")
        self.assertEqual(rows[0]["claim_history"][0]["worker_id"], "pid:999999")

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


if __name__ == "__main__":
    unittest.main()

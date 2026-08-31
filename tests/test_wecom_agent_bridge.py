from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ingest():
    module = load_module(
        "wecom_ingest_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_ingest.py",
    )
    module.quota_warning_for_request = lambda _request: ""
    return module


def load_worker():
    return load_module(
        "wechat_task_worker_for_wecom_tests",
        ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_task_worker.py",
    )


def load_wecom_ops():
    return load_module(
        "wecom_ops_for_tests",
        ROOT / "src" / "agenticapp" / "wecom_ops.py",
    )


def load_daily():
    return load_module(
        "wecom_daily_research_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_daily_research.py",
    )


def load_cli_bridge():
    return load_module(
        "wecom_cli_bridge_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_cli_bridge.py",
    )


def load_cli_guard():
    return load_module(
        "wecom_cli_transport_guard_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_cli_transport_guard.py",
    )


def load_gui_bridge():
    return load_module(
        "wecom_gui_bridge_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_gui_bridge.py",
    )


def load_android_bridge():
    return load_module(
        "wecom_android_bridge_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_bridge.py",
    )


class WeComAgentBridgeTests(unittest.TestCase):
    def test_android_bridge_restores_requested_dual_layout(self) -> None:
        bridge_module = load_android_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = root / "layout"
            layout.write_text("dual\n", encoding="utf-8")
            bridge = bridge_module.AndroidBridge(
                {
                    "serial": "device",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "queue": str(root / "queue.jsonl"),
                    "history_db": str(root / "history.sqlite"),
                    "staging_dir": str(root / "staging"),
                    "android_layout_path": str(layout),
                }
            )

            def adb_shell(*args, **_kwargs):
                if args[:3] == ("am", "stack", "list"):
                    return "Stack id=1 displayId=0\nStack id=2 displayId=7\n"
                if args[:3] == ("dumpsys", "window", "displays"):
                    return (
                        "Display: mDisplayId=7\n"
                        "  mFocusedApp=com.tencent.wework/.launch.WwMainActivity\n"
                        "Display: mDisplayId=0\n"
                    )
                if args[:3] == ("dumpsys", "activity", "activities"):
                    return (
                        "Display #7 (activities from top to bottom):\n"
                        "  mResumedActivity: ActivityRecord{x u0 "
                        "com.tencent.wework/.launch.WwMainActivity t1}\n"
                    )
                return ""

            with mock.patch.object(bridge, "adb_shell", side_effect=adb_shell) as shell:
                restored = bridge.restore_dual_layout_locked()

            self.assertTrue(restored)
            calls = [call.args for call in shell.call_args_list]
            self.assertIn(
                (
                    "am",
                    "start",
                    "--display",
                    "0",
                    "-f",
                    "0x04000000",
                    "-n",
                    bridge_module.PERSONAL_WECHAT_MAIN_ACTIVITY,
                ),
                calls,
            )
            self.assertTrue(
                any(call[:4] == ("am", "start", "--display", "7") for call in calls)
            )
            self.assertFalse(bridge.refresh_dual_mirror_if_needed())

    def test_android_bridge_restarts_only_blank_virtual_wecom_mirror(self) -> None:
        bridge_module = load_android_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = root / "layout"
            layout.write_text("dual\n", encoding="utf-8")
            bridge = bridge_module.AndroidBridge(
                {
                    "serial": "device",
                    "target_groups": ["LabAgent"],
                    "state_db": str(root / "state.sqlite"),
                    "queue": str(root / "queue.jsonl"),
                    "history_db": str(root / "history.sqlite"),
                    "staging_dir": str(root / "staging"),
                    "android_layout_path": str(layout),
                    "android_dual_tmux_target": "dual-session:wecom-virtual.0",
                }
            )

            def adb_shell(*args, **_kwargs):
                if args[:3] == ("am", "stack", "list"):
                    return "Stack id=1 displayId=0\nStack id=2 displayId=7\n"
                if args[:3] == ("dumpsys", "window", "displays"):
                    return (
                        "Display: mDisplayId=7\n"
                        "  mFocusedApp=com.miui.home/.launcher.SecondaryDisplayLauncher\n"
                        "Display: mDisplayId=0\n"
                    )
                return ""

            with mock.patch.object(bridge, "adb_shell", side_effect=adb_shell):
                restored = bridge.restore_dual_layout_locked()

            self.assertTrue(restored)
            with mock.patch.object(
                bridge_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as run:
                refreshed = bridge.refresh_dual_mirror_if_needed()

            self.assertTrue(refreshed)
            run.assert_called_once()
            self.assertEqual(
                run.call_args.args[0],
                [
                    "tmux",
                    "respawn-pane",
                    "-k",
                    "-t",
                    "dual-session:wecom-virtual.0",
                ],
            )

    def test_wecom_router_preserves_complete_long_response(self) -> None:
        ingest = load_ingest()
        answer = "完整回答。" * 500

        self.assertEqual(ingest.sanitize_chat_response(answer), answer)

    def test_wecom_gui_chunks_are_readable_numbered_and_lossless(self) -> None:
        bridge = load_gui_bridge()
        text = "".join(f"段落{index:03d}。" for index in range(100))

        parts = bridge.chunk_text(text, 240)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 240 for part in parts))
        self.assertEqual("".join(part.split("\n", 1)[1] for part in parts), text)

    def sample_event(self, **updates):
        event = {
            "transport": "wecom",
            "account_id": "default",
            "message_id": "msg-001",
            "chat_id": "private-chat-id",
            "chat_type": "group",
            "sender_userid": "private-user-id",
            "create_time": 1784300000,
            "msgtype": "text",
            "text": "Design and render a simple C-mount holder.",
            "quote_text": "",
            "attachments": [],
        }
        event.update(updates)
        return event

    def test_canonical_chat_key_hides_raw_chat_id(self) -> None:
        ingest = load_ingest()
        event = self.sample_event()

        chat = ingest.canonical_chat_name(event)

        self.assertTrue(chat.startswith("wecom:default:group:"))
        self.assertNotIn(event["chat_id"], chat)
        self.assertEqual(chat, ingest.canonical_chat_name(event))

    def test_first_group_message_returns_labagent_task_guide(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(transport_channel="wecom_bot_websocket")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ingest, "record_event"):
            root = Path(tmp)
            result = ingest.ingest_event(
                event,
                queue=root / "queue.jsonl",
                history_db=root / "history.sqlite",
                route_with_agent=False,
            )

        self.assertTrue(result["queued"])
        self.assertIn("LabAgent 已连接", result["ack"])
        self.assertIn("#daily", result["ack"])
        self.assertIn("CAD/PCB", result["ack"])

    def test_internal_and_external_groups_keep_distinct_agent_sessions(self) -> None:
        ingest = load_ingest()
        internal = self.sample_event(
            account_id="internal",
            transport_channel="wecom_bot_websocket",
            chat_id="same-platform-id",
        )
        external = self.sample_event(
            account_id="external",
            transport_channel="wecom_cli",
            chat_id="same-platform-id",
        )
        internal_chat = ingest.canonical_chat_name(internal)
        external_chat = ingest.canonical_chat_name(external)

        self.assertNotEqual(internal_chat, external_chat)
        self.assertTrue(internal_chat.startswith("wecom:internal:group:"))
        self.assertTrue(external_chat.startswith("wecom:external:group:"))

    def test_wecom_telemetry_uses_separate_mirror_database(self) -> None:
        ingest = load_ingest()
        mirror = ingest.MIRROR_DB.resolve()

        self.assertEqual(mirror.parent.name, "wecom")
        self.assertEqual(mirror.name, "wecom_mirror.sqlite")
        self.assertNotIn("wechat_gui_agent", str(mirror))

    def test_wecom_member_knowledge_cli_is_available(self) -> None:
        from agenticapp.cli import build_parser

        args = build_parser().parse_args(
            [
                "wecom",
                "knowledge",
                "search",
                "--query",
                "organoid mechanics",
                "--member-key",
                "member-key-a",
                "--kind",
                "insight",
                "--json",
            ]
        )

        self.assertEqual(args.action, "search")
        self.assertEqual(args.query, "organoid mechanics")
        self.assertEqual(args.member_key, "member-key-a")
        self.assertEqual(args.kind, "insight")

    def test_wecom_worker_disables_personal_wechat_fallbacks(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_worker_loop.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("WECHAT_WORKER_DISABLE_GUI_FILE_DOWNLOAD=1", source)
        self.assertIn("WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT=1", source)
        self.assertIn("WECHAT_WORKER_ANDROID_TEXT_FALLBACK=0", source)
        self.assertIn("WECHAT_WORKER_DISABLE_AUTOPUBLISH_PREFLIGHT=1", source)
        self.assertIn('WECHAT_WORKER_CODEX_MODEL="${WECHAT_WORKER_CODEX_MODEL:-gpt-5.6-sol}"', source)
        self.assertIn('WECHAT_WORKER_MIN_EFFORT="${WECHAT_WORKER_MIN_EFFORT:-low}"', source)
        self.assertIn('WECHAT_WORKER_MAX_EFFORT="${WECHAT_WORKER_MAX_EFFORT:-xhigh}"', source)
        self.assertIn('WECHAT_WORKER_TIMEOUT_HIGH_SECONDS="${WECHAT_WORKER_TIMEOUT_HIGH_SECONDS:-21600}"', source)
        self.assertIn('WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS="${WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS:-0}"', source)
        self.assertIn('WECHAT_WORKER_ENV_FILE="$PRIVATE_ENV"', source)

    def test_android_setup_is_wecom_only_and_does_not_bypass_keyguard(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_setup.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('PACKAGE="com.tencent.wework"', source)
        self.assertIn("keyguard_locked", source)
        self.assertNotIn("com.tencent.mm", source)
        self.assertNotIn("wm dismiss-keyguard", source)

    def test_attachment_event_enqueues_source_scoped_transport_task_once(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nsource")
            event = self.sample_event(
                msgtype="image",
                text="What is shown in this image?",
                attachments=[
                    {
                        "kind": "image",
                        "filename": image.name,
                        "path": str(image),
                        "size_bytes": image.stat().st_size,
                        "capture_kind": (
                            "wecom_android_original_media_store_export"
                        ),
                        "fidelity": "native_transmitted_original",
                        "original_resolution_verified": True,
                    }
                ],
            )
            queue = root / "queue.jsonl"
            history = root / "history.sqlite"
            with mock.patch.object(ingest, "record_event"):
                first = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=False)
                second = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=False)
            tasks = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(first["queued"])
        self.assertTrue(second["duplicate"])
        self.assertIn("#daily", first["ack"])
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["source"]["transport"], "wecom")
        self.assertEqual(task["source"]["member_key"], ingest.short_hash(event["sender_userid"]))
        self.assertEqual(task["member_memory"].get("scope"), "exact_member_and_chat")
        self.assertEqual(task["route"]["transport"], "wecom")
        copied = task["transport_preflight"]["wecom_media"]["copied"][0]
        self.assertEqual(copied["task_copy_path"], str(image))
        self.assertEqual(copied["fidelity"], "native_transmitted_original")
        self.assertTrue(copied["original_resolution_verified"])
        self.assertEqual(task["routine"]["id"], "file_intake")

    def test_cli_channel_is_preserved_without_personal_wechat_fallback(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(transport_channel="wecom_cli")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(
                    event,
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=False,
                )
            task = json.loads((root / "queue.jsonl").read_text(encoding="utf-8"))

        self.assertTrue(result["queued"])
        self.assertEqual(task["source"]["wecom_transport_channel"], "wecom_cli")
        self.assertEqual(task["execution_contract"]["transport"], "wecom_cli")
        self.assertEqual(task["route"]["transport_channel"], "wecom_cli")

    def test_gui_channel_is_preserved_without_personal_wechat_fallback(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            account_id="external-gui",
            chat_id="gui:LabAgent",
            transport_channel="wecom_gui",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(
                    event,
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=False,
                )
            task = json.loads((root / "queue.jsonl").read_text(encoding="utf-8"))

        self.assertTrue(result["queued"])
        self.assertEqual(task["source"]["wecom_transport_channel"], "wecom_gui")
        self.assertEqual(task["source"]["wecom_chat_id"], "gui:LabAgent")
        self.assertTrue(task["chat"].startswith("wecom:external-gui:group:"))

    def test_agent_route_can_return_direct_chat_without_queue(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            route = {
                "worker_needed": False,
                "route_kind": "other_worker",
                "response": "Hello. What would you like to build?",
                "task": "",
                "ack": "",
                "public_publish_allowed": False,
            }
            with mock.patch.object(ingest, "route_event", return_value=route), mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(
                    self.sample_event(text="hello"),
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=True,
                )

        self.assertFalse(result["queued"])
        self.assertTrue(result["reply"].startswith(route["response"]))
        self.assertIn("#daily", result["reply"])

    def test_actionable_request_prepends_live_low_quota_warning(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warning = "额度提醒：Codex 当前额度仅剩 3%，低于 5%。"
            with mock.patch.object(
                ingest,
                "quota_warning_for_request",
                return_value=warning,
            ), mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(
                    self.sample_event(text="请设计一个支架"),
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=False,
                )

        self.assertTrue(result["queued"])
        self.assertTrue(result["ack"].startswith(warning))
        self.assertEqual(result["ack"].count(warning), 1)

    def test_quota_probe_failure_never_blocks_request(self) -> None:
        ingest = load_ingest()

        with mock.patch.object(
            ingest,
            "quota_warning_for_request",
            side_effect=RuntimeError("probe unavailable"),
        ):
            result = ingest.prepend_quota_warning("继续处理。", "请继续")

        self.assertEqual(result, "继续处理。")

    def test_legacy_silent_peer_conversation_enters_worker_queue(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": False,
            "route_kind": "other_worker",
            "response": "",
            "task": "",
            "ack": "",
            "message_role": "peer_conversation",
            "reply_mode": "silent",
            "public_publish_allowed": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ingest, "route_event", return_value=route), mock.patch.object(
                ingest, "record_event"
            ):
                result = ingest.ingest_event(
                    self.sample_event(text="师姐你教一下他"),
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=True,
                )
                queue_exists = (root / "queue.jsonl").exists()

        self.assertTrue(result["queued"])
        self.assertTrue(result["ack"])
        self.assertTrue(queue_exists)

    def test_router_prompt_does_not_silence_group_level_experiment_question(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "可以，先把半结构化场景的变量和成功标准收窄，再做第一轮对照实验。",
                    "task": "",
                    "ack": "",
                    "message_role": "ordinary_chat",
                    "reply_mode": "reply",
                    "public_publish_allowed": False,
                }
            ),
        }
        prompts: list[str] = []

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            prompts.append(prompt)
            return response

        with mock.patch.object(ingest, "run_agent_session", side_effect=fake_agent):
            route = ingest.route_event(
                self.sample_event(text="先做半结构化场景的实验设计？", sender_display="megamonster"),
                "先做半结构化场景的实验设计？",
                [{"sender_display": "陈苗", "content": "我们先把实验路线收窄。"}],
            )

        self.assertEqual(route["reply_mode"], "reply")
        self.assertTrue(route["response"])
        self.assertIn("lacks an @ mention", prompts[0])
        self.assertIn("experimental next-step question", prompts[0])

    def test_peer_conversation_prompt_changes_stance_but_still_replies(self) -> None:
        ingest = load_ingest()
        natural_reply = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "这个方向可以继续收窄成可验证的产品假设。",
                    "task": "",
                    "ack": "",
                    "message_role": "peer_conversation",
                    "reply_mode": "reply",
                    "public_publish_allowed": False,
                }
            ),
        }
        request = "比如像味之素公司一样，让类器官生产什么，思考，计算，传感"
        prompts: list[str] = []

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            prompts.append(prompt)
            return natural_reply

        with mock.patch.object(ingest, "run_agent_session", side_effect=fake_agent) as agent:
            route = ingest.route_event(
                self.sample_event(text=request),
                request,
                [{"sender_display": "陈苗", "content": "类器官服务其他行业。"}],
            )

        self.assertFalse(route["worker_needed"])
        self.assertEqual(route["message_role"], "peer_conversation")
        self.assertEqual(route["reply_mode"], "reply")
        self.assertTrue(route["response"])
        self.assertIn("Every genuine inbound contribution", prompts[0])
        self.assertIn("changes only the conversational stance", prompts[0])
        self.assertIn("combined meaning", prompts[0])
        self.assertIn("full recent context", prompts[0])
        self.assertEqual(agent.call_args.kwargs["role"], "route-context-v3")

    def test_named_external_example_requires_grounded_worker_research(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "这个例子可以启发平台化思考。",
                    "task": "",
                    "ack": "",
                    "report_required": False,
                    "external_fact_grounding_required": True,
                    "message_role": "peer_conversation",
                    "reply_mode": "reply",
                    "active_task_relation": "independent",
                    "public_publish_allowed": False,
                }
            ),
        }
        prompts: list[str] = []

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            prompts.append(prompt)
            return response

        request = "比如像某家材料公司一样，把我们的生物能力做成跨行业产品"
        with mock.patch.object(ingest, "run_agent_session", side_effect=fake_agent):
            event = self.sample_event(text=request)
            route = ingest.route_event(
                event,
                request,
                [{"sender_display": "陈苗", "content": "讨论可出售的平台能力。"}],
                memory_context={
                    "preferences": {
                        "pdf_reports": {"preferred_for_substantial_research": True}
                    }
                },
            )
        with tempfile.TemporaryDirectory() as tmp:
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                request,
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "research_or_summary")
        self.assertTrue(route["external_fact_grounding_required"])
        self.assertFalse(route["report_required"])
        self.assertTrue(
            task["instruction_contract"]["verify_named_external_premises_before_analogy"]
        )
        self.assertTrue(
            task["execution_contract"]["research_evidence"][
                "external_fact_grounding_required"
            ]
        )
        self.assertIn("named real-world company", prompts[0])
        self.assertIn("first establish what the named example actually is", prompts[0])

    def test_silent_peer_conversation_gets_agent_only_context_review(self) -> None:
        ingest = load_ingest()
        silent = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "",
                    "task": "",
                    "ack": "",
                    "message_role": "peer_conversation",
                    "reply_mode": "silent",
                    "public_publish_allowed": False,
                }
            ),
        }
        reviewed = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "这里可以把思考、计算和传感拆成三个可验证的产品方向。",
                    "task": "",
                    "ack": "",
                    "report_required": False,
                    "message_role": "peer_conversation",
                    "reply_mode": "reply",
                    "active_task_relation": "independent",
                }
            ),
        }
        prompts: list[str] = []

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            prompts.append(prompt)
            return silent if len(prompts) == 1 else reviewed

        request = "比如像味之素公司一样，让类器官生产什么，思考，计算，传感"
        with mock.patch.object(ingest, "run_agent_session", side_effect=fake_agent) as agent:
            route = ingest.route_event(
                self.sample_event(text=request),
                request,
                [{"sender_display": "陈苗", "content": "让类器官服务其他行业。"}],
            )

        self.assertFalse(route["worker_needed"])
        self.assertEqual(route["message_role"], "peer_conversation")
        self.assertEqual(route["reply_mode"], "reply")
        self.assertTrue(route["response"])
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(
            agent.call_args_list[1].kwargs["role"],
            "peer-context-review-v1",
        )
        self.assertIn("every genuine inbound contribution", prompts[1])
        self.assertIn("never a reason to drop or skip", prompts[1])
        self.assertIn("complete conversation", prompts[1])

    def test_empty_context_only_route_interrupts_active_task_instead_of_silence(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": "",
                    "task": "Use this contribution when continuing the active discussion.",
                    "ack": "",
                    "message_role": "ordinary_chat",
                    "reply_mode": "reply",
                    "active_task_relation": "context_only",
                }
            ),
        }
        active = {
            "id": "wecom-active-context",
            "status": "in_progress",
            "request": "Develop the current research idea.",
        }

        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(
                self.sample_event(text="再把传感这个方向也考虑进去"),
                "再把传感这个方向也考虑进去",
                [{"sender_display": "陈苗", "content": "讨论类器官计算。"}],
                active_task=active,
            )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["reply_mode"], "ack_then_work")
        self.assertEqual(route["active_task_relation"], "interrupt")
        self.assertEqual(route["active_task_id"], "wecom-active-context")

    def test_legacy_silent_message_can_be_reconsidered_without_duplicate_history(self) -> None:
        ingest = load_ingest()
        silent = {
            "worker_needed": False,
            "route_kind": "chat_only",
            "response": "",
            "task": "",
            "ack": "",
            "message_role": "peer_conversation",
            "reply_mode": "silent",
            "public_publish_allowed": False,
        }
        reply = {
            **silent,
            "response": "可以，先收窄变量并定义对照组。",
            "message_role": "ordinary_chat",
            "reply_mode": "reply",
        }
        event = self.sample_event(
            text="先做半结构化场景的实验设计？",
            sender_display="megamonster",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            queue = root / "queue.jsonl"
            with mock.patch.object(
                ingest, "route_event", side_effect=[silent, reply]
            ), mock.patch.object(ingest, "record_event"):
                first = ingest.ingest_event(
                    event,
                    queue=queue,
                    history_db=history,
                    route_with_agent=True,
                )
                second = ingest.ingest_event(
                    event,
                    queue=queue,
                    history_db=history,
                    route_with_agent=True,
                    reconsider_processed=True,
                )
            with sqlite3.connect(history) as conn:
                inbound_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE message_id = ? AND direction = 'inbound'",
                    (event["message_id"],),
                ).fetchone()[0]

        self.assertTrue(first["queued"])
        self.assertEqual(second["reply"], "可以，先收窄变量并定义对照组。")
        self.assertEqual(inbound_count, 1)

    def test_router_preserves_artifact_guidance_role_and_context(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "paper_figure",
                    "response": "",
                    "task": "Use the concept image as a brief, then rebuild an editable BioRender figure.",
                    "ack": "明白，我会按这个两阶段方法调整。",
                    "message_role": "artifact_instruction",
                    "reply_mode": "ack_then_work",
                    "reply_to_senders": ["陈苗", "sunnyyty"],
                    "public_publish_allowed": False,
                }
            ),
        }
        event = self.sample_event(
            text="先生成样本图，再用 BioRender 复刻成可编辑图",
            sender_display="sunnyyty",
            sender_mention="sunnyyty@微信",
        )
        captured: list[str] = []

        def fake_agent(prompt: str, **_kwargs: object) -> dict[str, object]:
            captured.append(prompt)
            return response

        with mock.patch.object(ingest, "run_agent_session", side_effect=fake_agent):
            route = ingest.route_event(
                event,
                ingest.event_request(event),
                [{"sender_display": "陈苗", "content": "这是它调 BioRender 画的图"}],
            )

        self.assertEqual(route["message_role"], "artifact_instruction")
        self.assertEqual(route["reply_mode"], "ack_then_work")
        self.assertEqual(route["reply_to_senders"], ["陈苗", "sunnyyty"])
        self.assertIn("instructions addressed to LabCanvas itself", captured[0])
        self.assertIn("这是它调 BioRender 画的图", captured[0])

    def test_combined_reply_mentions_only_exact_same_chat_senders(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            sender_display="sunnyyty",
            sender_mention="sunnyyty@微信",
        )
        context = [
            {"sender_display": "陈苗", "content": "先学习 NCS 图", "is_self": False},
            {"sender_display": "LabAgent", "content": "old reply", "is_self": True},
        ]
        route = {"reply_to_senders": ["陈苗", "sunnyyty", "not-in-this-chat"]}

        mentions = ingest.route_reply_mentions(event, context, route)

        self.assertEqual(mentions, ["sunnyyty@微信", "陈苗"])

    def test_grant_request_fallback_uses_dedicated_goal_routine(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            text="Write a grant proposal with specific aims, verified references, an editable figure, and PDF."
        )

        route = ingest.fallback_route(event, event["text"])

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "grant_proposal")
        self.assertTrue(route["report_required"])

    def test_presentation_request_fallback_uses_editable_deck_routine(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            text="Prepare a PowerPoint slide deck with editable text and useful figures."
        )

        route = ingest.fallback_route(event, event["text"])

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "presentation_generation")

    def test_backend_outage_fallback_queues_conversation_instead_of_dropping_it(self) -> None:
        ingest = load_ingest()

        route = ingest.fallback_route(
            self.sample_event(text="这个方向我也觉得很有意思"),
            "这个方向我也觉得很有意思",
        )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "other_worker")
        self.assertEqual(route["reply_mode"], "ack_then_work")
        self.assertTrue(route["ack"])

    def test_backend_outage_fallback_still_routes_explicit_design_work(self) -> None:
        ingest = load_ingest()

        route = ingest.fallback_route(
            self.sample_event(text="请设计并渲染一个 C-mount 支架模型"),
            "请设计并渲染一个 C-mount 支架模型",
        )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["route_kind"], "other_worker")
        self.assertEqual(route["reply_mode"], "ack_then_work")

    def test_route_agent_can_bind_cross_sender_update_to_exact_active_task(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "paper_figure",
                    "response": "",
                    "task": "Apply the new figure guidance to the active report.",
                    "ack": "我会把这条建议并入正在进行的图稿。",
                    "report_required": False,
                    "message_role": "artifact_instruction",
                    "reply_mode": "ack_then_work",
                    "active_task_relation": "interrupt",
                    "reply_to_senders": [],
                    "memory_items": [],
                }
            ),
        }
        active = {
            "id": "wecom-active-1",
            "status": "in_progress",
            "route_kind": "paper_figure",
            "sender_display": "Prof Ma",
            "request": "Create the mechanism figure.",
        }
        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(
                self.sample_event(
                    sender_userid="member-two",
                    sender_display="sunnyyty",
                    text="图里把验证实验也画进去",
                ),
                "图里把验证实验也画进去",
                [],
                active_task=active,
            )

        self.assertTrue(route["worker_needed"])
        self.assertEqual(route["active_task_relation"], "interrupt")
        self.assertEqual(route["active_task_id"], "wecom-active-1")

    def test_active_conversation_task_is_exact_chat_and_bounded(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in (
                        {
                            "id": "other",
                            "chat": "wecom:other",
                            "status": "in_progress",
                            "request": "unrelated",
                        },
                        {
                            "id": "active",
                            "chat": "wecom:labagent",
                            "status": "in_progress",
                            "request": "Prepare the current report " + ("x" * 3000),
                            "source": {"sender_display": "Prof Ma"},
                            "route_decision": {"route_kind": "research_or_summary"},
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            active = ingest.active_conversation_task(queue, "wecom:labagent")

        self.assertEqual(active["id"], "active")
        self.assertEqual(active["sender_display"], "Prof Ma")
        self.assertEqual(active["route_kind"], "research_or_summary")
        self.assertLessEqual(len(active["request"]), 1800)

    def test_gui_ingest_suppresses_recent_exact_duplicate_with_changed_sender(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": False,
            "route_kind": "other_worker",
            "response": "收到，明早六点会按计划执行。",
            "task": "",
            "ack": "",
            "daily_topic": "",
            "public_publish_allowed": False,
        }
        first_event = self.sample_event(
            message_id="gui:first",
            account_id="external-gui",
            chat_id="gui:LabAgent",
            transport_channel="wecom_gui",
            sender_userid="external-member:first-ocr-label",
            text="明早六点记得发送日常论文阅读计划",
        )
        duplicate_event = {
            **first_event,
            "message_id": "gui:duplicate",
            "sender_userid": "external-member:changed-ocr-label",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ingest, "route_event", return_value=route) as route_agent, mock.patch.object(
                ingest,
                "record_event",
            ):
                first = ingest.ingest_event(
                    first_event,
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=True,
                )
                duplicate = ingest.ingest_event(
                    duplicate_event,
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=True,
                )

        self.assertTrue(first["reply"].startswith(route["response"]))
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(duplicate["queued"])
        self.assertEqual(duplicate["reply"], "")
        self.assertEqual(duplicate["suppressed"], "recent_exact_wecom_gui_duplicate")
        self.assertEqual(route_agent.call_count, 1)

    def test_android_ingest_suppresses_old_unattributed_history_replay(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": False,
            "route_kind": "other_worker",
            "response": "收到，我会处理。",
            "task": "",
            "ack": "",
            "daily_topic": "",
            "public_publish_allowed": False,
        }
        first_event = self.sample_event(
            message_id="android:original",
            account_id="external-gui",
            chat_id="gui:LabAgent",
            transport_channel="wecom_android",
            sender_userid="android-member:prof-ma",
            sender_display="Prof Ma",
            sender_identity_confidence="visible_row_label",
            text="请做一个研究方案并给我一份PDF。",
        )
        replay_event = {
            **first_event,
            "message_id": "android:history-replay",
            "sender_userid": "android-member:unknown",
            "sender_display": "unknown",
            "sender_identity_confidence": "unattributed_row",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            with mock.patch.object(ingest, "route_event", return_value=route) as route_agent, mock.patch.object(
                ingest,
                "record_event",
            ):
                first = ingest.ingest_event(
                    first_event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )
                old_timestamp = (datetime.now() - timedelta(hours=8)).isoformat(timespec="seconds")
                with sqlite3.connect(history) as conn:
                    conn.execute(
                        "UPDATE messages SET created_at = ?, processed_at = ? "
                        "WHERE message_id = ? AND direction = 'inbound'",
                        (old_timestamp, old_timestamp, first_event["message_id"]),
                    )
                replay = ingest.ingest_event(
                    replay_event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )

        self.assertTrue(first["reply"].startswith(route["response"]))
        self.assertTrue(replay["duplicate"])
        self.assertFalse(replay["queued"])
        self.assertEqual(replay["reply"], "")
        self.assertEqual(replay["suppressed"], "recent_exact_wecom_gui_duplicate")
        self.assertEqual(replay["duplicate_window_seconds"], 24 * 60 * 60)
        self.assertEqual(route_agent.call_count, 1)

    def test_android_ingest_allows_old_repeat_from_attributed_sender(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": False,
            "route_kind": "other_worker",
            "response": "收到，我会处理。",
            "task": "",
            "ack": "",
            "daily_topic": "",
            "public_publish_allowed": False,
        }
        first_event = self.sample_event(
            message_id="android:original-attributed",
            account_id="external-gui",
            chat_id="gui:LabAgent",
            transport_channel="wecom_android",
            sender_userid="android-member:prof-ma",
            sender_display="Prof Ma",
            sender_identity_confidence="visible_row_label",
            text="请再解释一下这个研究方向。",
        )
        later_event = {
            **first_event,
            "message_id": "android:later-attributed",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            with mock.patch.object(ingest, "route_event", return_value=route) as route_agent, mock.patch.object(
                ingest,
                "record_event",
            ):
                first = ingest.ingest_event(
                    first_event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )
                old_timestamp = (datetime.now() - timedelta(hours=8)).isoformat(timespec="seconds")
                with sqlite3.connect(history) as conn:
                    conn.execute(
                        "UPDATE messages SET created_at = ?, processed_at = ? "
                        "WHERE message_id = ? AND direction = 'inbound'",
                        (old_timestamp, old_timestamp, first_event["message_id"]),
                    )
                later = ingest.ingest_event(
                    later_event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )

        self.assertTrue(first["reply"].startswith(route["response"]))
        self.assertFalse(later["duplicate"])
        self.assertTrue(later["reply"].startswith(route["response"]))
        self.assertEqual(route_agent.call_count, 2)

    def test_gui_ingest_retries_same_unprocessed_event_instead_of_suppressing_it(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            message_id="android:stable-message",
            account_id="external-gui",
            chat_id="gui:LabAgent",
            transport_channel="wecom_android",
            sender_userid="android-member:sunnyyty",
            text="@陈喵瞄秒妙 要学习CNS顶刊风格绘图",
        )
        route = {
            "worker_needed": False,
            "route_kind": "other_worker",
            "response": "收到，我会把这条标准用于当前绘图流程。",
            "task": "",
            "ack": "",
            "daily_topic": "",
            "public_publish_allowed": False,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            ingest.init_history_db(history)
            ingest.record_history_message(
                history,
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                direction="inbound",
            )
            with mock.patch.object(ingest, "route_event", return_value=route) as route_agent, mock.patch.object(
                ingest,
                "record_event",
            ):
                result = ingest.ingest_event(
                    event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )

        self.assertFalse(result["duplicate"])
        self.assertTrue(result["reply"].startswith(route["response"]))
        route_agent.assert_called_once()

    def test_daily_directive_queues_one_immediate_report_without_route_turn(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.jsonl"
            history = root / "history.sqlite"
            event = self.sample_event(
                text="#daily sparse event-camera reconstruction",
                authorization_role="owner",
                irreversible_actions_allowed=True,
            )
            with mock.patch.object(ingest, "route_event", side_effect=AssertionError("#daily must not spend a route turn")), mock.patch.object(
                ingest, "record_event"
            ):
                result = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=True)
                duplicate = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=True)
                repeated_topic = ingest.ingest_event(
                    {**event, "message_id": "msg-002"},
                    queue=queue,
                    history_db=history,
                    route_with_agent=True,
                )

            daily = load_daily()
            topics = daily.active_topics(history, ingest.canonical_chat_name(event))
            tasks = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result["queued"])
        self.assertTrue(result["immediate_daily_research"])
        self.assertTrue(result["new_queue_entry"])
        self.assertIn("sparse event-camera reconstruction", result["reply"])
        self.assertIn("已立即进入队列", result["reply"])
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(repeated_topic["queued"])
        self.assertIn("未重复创建任务", repeated_topic["reply"])
        self.assertEqual(topics, ["sparse event-camera reconstruction"])
        self.assertEqual(len(tasks), 1)
        self.assertTrue(tasks[0]["route_decision"]["immediate_daily_research"])
        self.assertFalse(tasks[0]["route_decision"]["scheduled_daily_research"])
        self.assertTrue(tasks[0]["route_decision"]["no_fixed_deadline"])
        self.assertTrue(tasks[0]["daily_research"]["initial_run"])
        self.assertEqual(
            tasks[0]["scheduled_recovery"]["kind"],
            "daily_research",
        )
        self.assertTrue(tasks[0]["scheduled_recovery"]["read_only"])

    def test_interest_directive_queues_immediate_group_inspiration(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.jsonl"
            history = root / "history.sqlite"
            event = self.sample_event(
                text="#interest organoids; speculative bio-design",
                authorization_role="group_member",
            )
            with mock.patch.object(ingest, "route_event", side_effect=AssertionError("interest command must not spend a route turn")), mock.patch.object(
                ingest, "record_event"
            ):
                result = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=True)
                duplicate = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=True)
            tasks = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertFalse(result["queued"])
        self.assertIn("已立即安排", result["reply"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["source"]["local_type"], "scheduled_group_inspiration")
        self.assertIn("organoids", tasks[0]["request"])
        self.assertIn("substantive content", tasks[0]["request"])

    def test_group_inspiration_waits_for_quiet_period_and_is_idempotent(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            event = self.sample_event(text="hello")
            daily.register_group(state, event, chat)
            daily.update_group_inspiration(
                state,
                chat,
                ["organoids", "speculative design"],
                now=datetime(2026, 7, 21, 8, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            captured: list[dict] = []

            def append_once(_queue, task):
                captured.append(task)
                return True

            before = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 10, 59, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=append_once,
            )
            due = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=append_once,
            )
            repeated = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=append_once,
            )

        self.assertEqual(before["actions"], [])
        self.assertEqual(len(due["actions"]), 1)
        self.assertEqual(repeated["actions"], [])
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0]["route_decision"]["scheduled_group_inspiration"])
        self.assertEqual(captured[0]["agent_backend"], "aginti")
        self.assertEqual(
            captured[0]["session_scope"],
            f"{chat}::scheduled-group-inspiration",
        )
        self.assertIn("substantive content", captured[0]["request"])
        recovery = captured[0]["scheduled_recovery"]
        self.assertEqual(recovery["version"], 1)
        self.assertEqual(recovery["kind"], "group_inspiration")
        self.assertTrue(recovery["read_only"])
        self.assertEqual(recovery["max_attempts"], 1)
        self.assertEqual(recovery["delay_seconds"], 300)
        self.assertEqual(recovery["max_age_seconds"], 6 * 60 * 60)

    def test_group_inspiration_uses_only_exact_chat_durable_interests(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            queue = root / "queue.jsonl"
            knowledge = root / "wecom_member_knowledge.sqlite"
            with sqlite3.connect(knowledge) as conn:
                conn.execute(
                    """
                    CREATE TABLE knowledge_items (
                        id TEXT PRIMARY KEY,
                        member_key TEXT,
                        chat TEXT,
                        kind TEXT,
                        title TEXT,
                        content TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO knowledge_items
                    (id, member_key, chat, kind, title, content, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "same",
                            "member-a",
                            "wecom:default:group:labagent",
                            "interest",
                            "Mechanobiology direction",
                            "Connect organoid force maps with optical phenotyping.",
                            "2026-07-28T10:00:00",
                        ),
                        (
                            "stale-question",
                            "member-a",
                            "wecom:default:group:labagent",
                            "question",
                            "Old completed request",
                            "Re-open a paper that was already handled.",
                            "2026-07-28T10:30:00",
                        ),
                        (
                            "old-pdf-preference",
                            "member-a",
                            "wecom:default:group:labagent",
                            "preference",
                            "Old report preference",
                            "Always create a complete PDF for product research.",
                            "2026-07-28T10:45:00",
                        ),
                        (
                            "other",
                            "member-b",
                            "wecom:default:group:other",
                            "note",
                            "Private other-group note",
                            "This must never enter LabAgent context.",
                            "2026-07-28T11:00:00",
                        ),
                    ],
                )
            with mock.patch.dict(
                daily.os.environ,
                {"WECOM_MEMBER_KNOWLEDGE_DB": str(knowledge)},
                clear=False,
            ):
                memory = daily.historical_group_memory(
                    history,
                    "wecom:default:group:labagent",
                    limit=24,
                )
                task = daily.build_group_inspiration_task(
                    chat="wecom:default:group:labagent",
                    account_id="default",
                    chat_id="private-chat",
                    chat_type="group",
                    transport_channel="wecom_bot_websocket",
                    topics=["organoids"],
                    context=[
                        {
                            "direction": "inbound",
                            "content": "Can imaging reveal mechanical transitions?",
                        }
                    ],
                    historical_memory=memory,
                    previous=[],
                    now=datetime(
                        2026,
                        7,
                        29,
                        12,
                        0,
                        tzinfo=ZoneInfo("Asia/Hong_Kong"),
                    ),
                    queue=queue,
                    interval_seconds=10800,
                )

        self.assertEqual(len(memory), 1)
        self.assertIn("mechanical transitions", task["request"])
        self.assertIn("organoid force maps", task["request"])
        self.assertNotIn("Re-open a paper", task["request"])
        self.assertNotIn("complete PDF", task["request"])
        self.assertNotIn("Private other-group note", task["request"])
        self.assertTrue(task["route_decision"]["message_only"])
        self.assertEqual(task["route_decision"]["artifact_delivery"], "forbidden")
        self.assertEqual(task["execution_contract"]["required_artifacts"], [])
        self.assertEqual(task["execution_contract"]["artifact_delivery"], "forbidden")
        self.assertEqual(
            task["group_inspiration"]["historical_memory"][0]["kind"],
            "interest",
        )

    def test_group_inspiration_marks_full_history_as_prior_not_current_request(self) -> None:
        daily = load_daily()
        task = daily.build_group_inspiration_task(
            chat="wecom:default:group:labagent",
            account_id="default",
            chat_id="private-chat",
            chat_type="group",
            transport_channel="wecom_bot_websocket",
            topics=["organoids"],
            context=[{"direction": "inbound", "content": "new question"}],
            historical_memory=[],
            previous=[],
            now=datetime(2026, 7, 29, 12, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            queue=Path("/tmp/queue.jsonl"),
            interval_seconds=10800,
            history_context="old recurring interest",
            history_manifest={"scanned_messages": 400},
        )

        self.assertIn("old recurring interest", task["request"])
        self.assertIn("not a new request", task["request"])
        self.assertIn("must never turn an old completed request", task["request"])
        self.assertEqual(
            task["group_inspiration"]["history_retrieval"]["scanned_messages"],
            400,
        )

    def test_group_inspiration_context_excludes_stale_consumed_and_outbound_messages(self) -> None:
        daily = load_daily()
        timezone = ZoneInfo("Asia/Hong_Kong")
        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone)
        after = datetime(2026, 7, 29, 9, 0, tzinfo=timezone)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            with sqlite3.connect(history) as conn:
                conn.execute(
                    """
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        chat TEXT,
                        direction TEXT,
                        body TEXT,
                        create_time INTEGER,
                        created_at TEXT
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO messages(chat, direction, body, create_time, created_at) VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            "wecom:default:group:labagent",
                            "inbound",
                            "old archive topic",
                            int(datetime(2026, 7, 27, 8, 0, tzinfo=timezone).timestamp()),
                            "2026-07-27T08:00:00+08:00",
                        ),
                        (
                            "wecom:default:group:labagent",
                            "inbound",
                            "already consumed topic",
                            int(datetime(2026, 7, 29, 8, 30, tzinfo=timezone).timestamp()),
                            "2026-07-29T08:30:00+08:00",
                        ),
                        (
                            "wecom:default:group:labagent",
                            "inbound",
                            "new human direction",
                            int(datetime(2026, 7, 29, 10, 0, tzinfo=timezone).timestamp()),
                            "2026-07-29T10:00:00+08:00",
                        ),
                        (
                            "wecom:default:group:labagent",
                            "outbound",
                            "agent answer must not steer the next schedule",
                            int(datetime(2026, 7, 29, 11, 0, tzinfo=timezone).timestamp()),
                            "2026-07-29T11:00:00+08:00",
                        ),
                    ],
                )

            context = daily.recent_group_inspiration_context(
                history,
                "wecom:default:group:labagent",
                now=now,
                after=after,
                max_age_seconds=24 * 3600,
            )

        self.assertEqual([item["content"] for item in context], ["new human direction"])

    def test_daily_context_excludes_stale_and_outbound_scheduler_messages(self) -> None:
        daily = load_daily()
        timezone = ZoneInfo("Asia/Hong_Kong")
        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone)
        chat = "wecom:default:group:labagent"
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            with sqlite3.connect(history) as conn:
                conn.execute(
                    """
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        chat TEXT,
                        direction TEXT,
                        body TEXT,
                        create_time INTEGER,
                        created_at TEXT
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO messages(chat, direction, body, create_time, created_at) VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            chat,
                            "inbound",
                            "stale human request",
                            int(datetime(2026, 7, 25, 8, 0, tzinfo=timezone).timestamp()),
                            "2026-07-25T08:00:00+08:00",
                        ),
                        (
                            chat,
                            "inbound",
                            "current human research direction",
                            int(datetime(2026, 7, 29, 10, 0, tzinfo=timezone).timestamp()),
                            "2026-07-29T10:00:00+08:00",
                        ),
                        (
                            chat,
                            "outbound",
                            "old scheduler report must not be recycled",
                            int(datetime(2026, 7, 29, 11, 0, tzinfo=timezone).timestamp()),
                            "2026-07-29T11:00:00+08:00",
                        ),
                    ],
                )

            context = daily.recent_group_daily_context(
                history,
                chat,
                now=now,
                max_age_seconds=48 * 3600,
            )

        self.assertEqual(
            [item["content"] for item in context],
            ["current human research direction"],
        )

    def test_daily_context_preserves_sender_attribution_when_available(self) -> None:
        daily = load_daily()
        timezone = ZoneInfo("Asia/Hong_Kong")
        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone)
        chat = "wecom:default:group:labagent"
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            with sqlite3.connect(history) as conn:
                conn.execute(
                    """
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        chat TEXT,
                        direction TEXT,
                        sender TEXT,
                        sender_display TEXT,
                        body TEXT,
                        create_time INTEGER,
                        created_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO messages(
                        chat, direction, sender, sender_display, body,
                        create_time, created_at
                    ) VALUES (?, 'inbound', ?, ?, ?, ?, ?)
                    """,
                    (
                        chat,
                        "member-1",
                        "Prof Ma",
                        "Preserve this attribution",
                        int(datetime(2026, 7, 29, 10, 0, tzinfo=timezone).timestamp()),
                        "2026-07-29T10:00:00+08:00",
                    ),
                )

            context = daily.recent_group_daily_context(
                history,
                chat,
                now=now,
                max_age_seconds=48 * 3600,
            )

        self.assertEqual(context[0]["sender_display"], "Prof Ma")

    def test_group_inspiration_defers_while_exact_chat_has_active_work(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            other_chat = "wecom:default:group:other"
            event = self.sample_event(text="hello")
            daily.register_group(state, event, chat)
            daily.update_group_inspiration(
                state,
                chat,
                ["organoids"],
                now=datetime(2026, 7, 21, 8, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            queue.write_text(
                "\n".join(
                    json.dumps(task)
                    for task in (
                        {"id": "same", "chat": chat, "status": "in_progress", "source": {"local_type": "text"}},
                        {"id": "other", "chat": other_chat, "status": "pending", "source": {"local_type": "text"}},
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            captured: list[dict] = []

            blocked = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=lambda _queue, task: captured.append(task) or True,
            )
            queue.write_text(
                json.dumps({"id": "same", "chat": chat, "status": "done", "source": {"local_type": "text"}}) + "\n",
                encoding="utf-8",
            )
            resumed = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 2, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=lambda _queue, task: captured.append(task) or True,
            )

        self.assertEqual(blocked["actions"], [])
        self.assertEqual(blocked["busy_chats"], [chat])
        self.assertEqual(len(resumed["actions"]), 1)
        self.assertEqual(len(captured), 1)

    def test_waiting_confirmation_does_not_disable_idle_inspiration(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            event = self.sample_event(text="hello")
            daily.register_group(state, event, chat)
            daily.update_group_inspiration(
                state,
                chat,
                ["organoids"],
                now=datetime(2026, 7, 21, 8, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            queue.write_text(
                json.dumps(
                    {
                        "id": "confirmation",
                        "chat": chat,
                        "status": "waiting_confirmation",
                        "source": {"local_type": "text"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured: list[dict] = []

            result = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=lambda _queue, task: captured.append(task) or True,
            )

        self.assertEqual(result["busy_chats"], [])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(len(captured), 1)

    def test_waiting_confirmation_inspiration_does_not_block_later_idle_turn(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            event = self.sample_event(text="hello")
            daily.register_group(state, event, chat)
            daily.update_group_inspiration(
                state,
                chat,
                ["organoids"],
                now=datetime(2026, 7, 21, 8, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            queue.write_text(
                json.dumps(
                    {
                        "id": "old-inspiration",
                        "chat": chat,
                        "status": "waiting_confirmation",
                        "source": {"local_type": "scheduled_group_inspiration"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured: list[dict] = []

            result = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=lambda _queue, task: captured.append(task) or True,
            )

        self.assertEqual(result["busy_chats"], [])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["kind"], "inspiration")
        self.assertEqual(len(captured), 1)

    def test_terminal_send_failure_does_not_block_next_group_inspiration(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            event = self.sample_event(text="hello")
            daily.register_group(state, event, chat)
            daily.update_group_inspiration(
                state,
                chat,
                ["organoids"],
                now=datetime(2026, 7, 21, 8, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            queue.write_text(
                json.dumps(
                    {
                        "id": "failed-delivery",
                        "chat": chat,
                        "status": "send_failed",
                        "source": {"local_type": "scheduled_group_inspiration"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured: list[dict] = []

            result = daily.run_inspiration_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 21, 11, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                append_func=lambda _queue, task: captured.append(task) or True,
            )

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["kind"], "inspiration")
        self.assertEqual(len(captured), 1)

    def test_scheduler_heartbeat_contains_only_bounded_health_counts(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scheduler.health.json"
            daily.write_scheduler_heartbeat(
                path,
                status="ok",
                payload={
                    "checked": 2,
                    "actions": [{"chat": "private-chat-id"}],
                    "inspiration": {
                        "checked": 1,
                        "actions": [{"chat": "private-chat-id"}],
                        "busy_chats": ["private-chat-id"],
                    },
                },
            )
            heartbeat = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(heartbeat["status"], "ok")
        self.assertEqual(heartbeat["daily_checked"], 2)
        self.assertEqual(heartbeat["inspiration_checked"], 1)
        self.assertEqual(heartbeat["inspiration_action_count"], 1)
        self.assertNotIn("chat", heartbeat)

    def test_daily_preferences_keep_members_separate_and_support_status_and_off(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            event_a = self.sample_event(
                sender_userid="member-a",
                text="#daily computational microscopy",
                authorization_role="owner",
            )
            event_b = self.sample_event(
                message_id="msg-002",
                sender_userid="member-b",
                text="#daily event-based imaging",
                authorization_role="group_member",
            )
            chat = "wecom:default:group:test"
            daily.handle_daily_directive(state, event_a, chat)
            daily.handle_daily_directive(state, event_b, chat)
            status = daily.handle_daily_directive(state, {**event_b, "text": "#daily status"}, chat)
            off = daily.handle_daily_directive(state, {**event_a, "text": "#daily off"}, chat)
            topics = daily.active_topics(state, chat)

        self.assertIn("computational microscopy", status)
        self.assertIn("event-based imaging", status)
        self.assertIn("其他成员", off)
        self.assertEqual(topics, ["event-based imaging"])

    def test_daily_suffix_accumulates_interests_in_one_member_record(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            event = self.sample_event(
                sender_userid="member-a",
                text="computational microscopy #daily",
                authorization_role="group_member",
            )
            chat = "wecom:default:group:test"
            first = daily.handle_daily_directive(state, event, chat)
            second = daily.handle_daily_directive(
                state,
                {
                    **event,
                    "message_id": "msg-002",
                    "text": "event-camera reconstruction #daily",
                },
                chat,
            )
            duplicate = daily.handle_daily_directive(
                state,
                {
                    **event,
                    "message_id": "msg-003",
                    "text": "computational microscopy #daily",
                },
                chat,
            )
            topics = daily.active_topics(state, chat)
            with sqlite3.connect(state) as conn:
                member_rows = conn.execute(
                    "SELECT COUNT(*) FROM daily_preferences WHERE chat = ?",
                    (chat,),
                ).fetchone()[0]

        self.assertIn("累计 1 项", first)
        self.assertIn("累计 2 项", second)
        self.assertIn("累计 2 项", duplicate)
        self.assertEqual(member_rows, 1)
        self.assertEqual(topics, ["computational microscopy", "event-camera reconstruction"])

    def test_daily_gui_directive_requires_stable_sender_identity(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            event = self.sample_event(
                text="organoid spatial QC #daily",
                transport_channel="wecom_gui",
                sender_identity_confidence="unresolved",
            )

            reply = daily.handle_daily_directive(
                state,
                event,
                "wecom:external-gui:group:test",
            )

        self.assertIn("未能稳定识别", reply)
        self.assertEqual(daily.active_topics(state, "wecom:external-gui:group:test"), [])

    def test_daily_scheduler_enqueues_one_source_scoped_report_per_day(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            event = self.sample_event(
                text="#daily open-source event cameras",
                authorization_role="owner",
                irreversible_actions_allowed=True,
            )
            chat = "wecom:default:group:labagent"
            daily.handle_daily_directive(state, event, chat)
            captured: list[dict] = []

            def append_once(_queue, task):
                captured.append(task)
                return True

            now = datetime(2026, 7, 18, 9, 5, tzinfo=ZoneInfo("Asia/Hong_Kong"))
            first = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=now,
                force=True,
                append_func=append_once,
            )
            second = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=now,
                force=True,
                append_func=append_once,
            )

        self.assertEqual(len(first["actions"]), 1)
        self.assertEqual(second["actions"], [])
        self.assertEqual(len(captured), 1)
        task = captured[0]
        self.assertEqual(task["chat"], chat)
        self.assertEqual(task["source"]["wecom_chat_id"], event["chat_id"])
        self.assertEqual(task["route_decision"]["route_kind"], "research_or_summary")
        self.assertEqual(task["routine"]["id"], "research_summary")
        self.assertFalse(task["route_decision"]["public_publish_allowed"])
        self.assertIn("polished LaTeX source", task["request"])
        self.assertIn("Render and inspect the compiled pages", task["request"])
        self.assertIn("Nature-style", task["request"])
        self.assertIn("not a teaser or status line", task["request"])
        self.assertIn("scientific anchor", task["request"])
        self.assertIn("If the member's topic is about organoids, NCS/CNS papers", task["request"])
        self.assertIn("LLM/agent systems, AI, robotics, sensors, chips", task["request"])
        self.assertIn("private task directory", task["request"])
        self.assertIn("return the polished PDF", task["request"])
        self.assertIn("executive brief", task["request"])
        self.assertIn("materially deeper than the chat message", task["request"])
        self.assertIn("study design or method", task["request"])
        self.assertIn("compare the extracted PDF text", task["request"])
        self.assertIn("Write the PDF for the researcher", task["request"])
        self.assertIn("checksums", task["request"])
        self.assertIn("Never install or upgrade TeX", task["request"])
        evidence = task["execution_contract"]["research_evidence"]
        self.assertTrue(evidence["required"])
        self.assertEqual(evidence["minimum_traceable_sources"], 3)
        self.assertTrue(evidence["include_actionable_next_steps"])
        report_quality = task["execution_contract"]["report_quality"]
        self.assertEqual(report_quality["chat_role"], "executive_summary")
        self.assertEqual(report_quality["pdf_role"], "full_evidence_analysis")
        self.assertTrue(report_quality["materially_deeper_than_chat"])
        self.assertTrue(report_quality["host_compiler_fallback"])
        self.assertIn(
            "source_level_methods_results_and_limitations",
            report_quality["required_dimensions"],
        )
        self.assertIn(
            "reader_facing_narrative_and_local_provenance_separation",
            report_quality["required_dimensions"],
        )
        self.assertIn(
            "no_blank_or_orphan_pages",
            report_quality["required_dimensions"],
        )
        self.assertIn(
            "checksums_and_private_paths",
            report_quality["local_only_provenance"],
        )
        self.assertEqual(
            task["execution_contract"]["required_artifacts"],
            ["markdown_report", "latex_source", "compiled_pdf", "render_audit"],
        )
        self.assertEqual(task["routine"]["default_effort"], "medium")
        self.assertNotIn("transport sends both", task["request"])
        self.assertTrue(task["route_decision"]["no_fixed_deadline"])
        self.assertFalse(task["agent_backend_config"]["agent_fallbacks"]["fallback_on_timeout"])
        self.assertEqual(task["agent_backend"], "aginti")
        recovery = task["scheduled_recovery"]
        self.assertEqual(recovery["version"], 1)
        self.assertEqual(recovery["kind"], "daily_research")
        self.assertTrue(recovery["read_only"])
        self.assertEqual(recovery["max_attempts"], 1)
        self.assertEqual(recovery["delay_seconds"], 300)
        self.assertEqual(recovery["max_age_seconds"], 48 * 60 * 60)

    def test_daily_scheduler_keeps_member_jobs_separate_and_serialized(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            daily.handle_daily_directive(
                state,
                self.sample_event(
                    sender_userid="member-ma",
                    text="Professor Ma external peer papers #daily",
                ),
                chat,
            )
            daily.handle_daily_directive(
                state,
                self.sample_event(
                    message_id="msg-002",
                    sender_userid="member-organoid",
                    text="recent organoid CNS papers #daily",
                ),
                chat,
            )
            captured: list[dict] = []

            def append_once(_queue, task):
                captured.append(task)
                return True

            now = datetime(2026, 7, 20, 6, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
            first = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=now,
                append_func=append_once,
            )
            second = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=now,
                append_func=append_once,
            )

        self.assertEqual(len(first["actions"]), 2)
        self.assertEqual(second["actions"], [])
        self.assertEqual(len(captured), 2)
        self.assertEqual(
            [task["daily_research"]["sequence_index"] for task in captured],
            [1, 2],
        )
        self.assertTrue(all(task["daily_research"]["sequence_total"] == 2 for task in captured))
        self.assertTrue(all(task["daily_research"]["serialized"] for task in captured))
        self.assertCountEqual(
            [task["daily_research"]["topics"][0] for task in captured],
            ["Professor Ma external peer papers", "recent organoid CNS papers"],
        )
        self.assertEqual(
            {task["source"]["member_key"] for task in captured},
            {task["daily_research"]["member_key"] for task in captured},
        )
        self.assertEqual(len({task["source"]["member_key"] for task in captured}), 2)
        self.assertEqual(len({task["id"] for task in captured}), 2)
        self.assertEqual(len({task["session_scope"] for task in captured}), 2)
        self.assertTrue(
            all(
                task["session_scope"].startswith(f"{chat}::daily:")
                for task in captured
            )
        )
        self.assertTrue(
            all(
                task["execution_contract"]["session"]["chat"]
                == task["session_scope"]
                for task in captured
            )
        )

    def test_daily_scheduler_default_report_time_is_six_am(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            daily.os.environ,
            {
                "WECOM_DAILY_RESEARCH_TIME": "06:00",
                "WECOM_DAILY_TIMEZONE": "Asia/Hong_Kong",
            },
            clear=False,
        ):
            state = Path(tmp) / "state.sqlite"
            chat = "wecom:default:group:labagent"
            daily.handle_daily_directive(
                state,
                self.sample_event(text="organoid imaging #daily"),
                chat,
            )
            early = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=Path(tmp) / "queue.jsonl",
                now=datetime(2026, 7, 20, 5, 59, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            due = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=Path(tmp) / "queue.jsonl",
                now=datetime(2026, 7, 20, 6, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )

        self.assertEqual(early["actions"], [])
        self.assertEqual(len(due["actions"]), 1)

    def test_daily_scheduler_runs_at_six_while_periodic_inspiration_sleeps(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            chat = "wecom:default:group:labagent"
            daily.handle_daily_directive(
                state,
                self.sample_event(text="organoid imaging #daily"),
                chat,
            )
            captured: list[dict] = []

            def append_once(_queue, task):
                captured.append(task)
                return True

            now = datetime(2026, 7, 23, 6, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
            with mock.patch.object(daily, "run_inspiration_cycle") as inspiration:
                result = daily.run_scheduler_cycle(
                    state_db=state,
                    history_db=state,
                    queue=queue,
                    now=now,
                    include_inspiration=False,
                    append_func=append_once,
                )

        inspiration.assert_not_called()
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["kind"], "report")
        self.assertEqual(result["inspiration"]["status"], "quiet_hours")
        self.assertEqual(len(captured), 1)

    def test_immediate_daily_run_does_not_consume_the_scheduled_report(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            queue = root / "queue.jsonl"
            event = self.sample_event(
                text="organoid mechanobiology #daily",
                authorization_role="group_member",
            )
            chat = "wecom:default:group:labagent"
            result = daily.handle_daily_directive_result(state, event, chat)
            immediate = daily.enqueue_initial_daily_research(
                state_db=state,
                history_db=state,
                queue=queue,
                event=event,
                chat=chat,
                topic=result["topic"],
                now=datetime(2026, 7, 18, 8, 10, tzinfo=ZoneInfo("Asia/Hong_Kong")),
            )
            scheduled = daily.run_due_cycle(
                state_db=state,
                history_db=state,
                queue=queue,
                now=datetime(2026, 7, 18, 9, 5, tzinfo=ZoneInfo("Asia/Hong_Kong")),
                force=True,
            )
            tasks = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(immediate["queued"])
        self.assertEqual(len(scheduled["actions"]), 1)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(
            {task["source"]["kind"] for task in tasks},
            {"immediate_daily_research", "scheduled_daily_research"},
        )

    def test_daily_scheduler_asks_once_when_an_enrolled_group_has_no_topic(self) -> None:
        daily = load_daily()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.sqlite"
            event = self.sample_event(text="hello", authorization_role="owner")
            chat = "wecom:default:group:labagent"
            daily.register_group(state, event, chat)
            sent: list[tuple[str, str, str]] = []

            def send(chat_id, message, task_id):
                sent.append((chat_id, message, task_id))
                return {"ok": True}

            now = datetime(2026, 7, 18, 9, 5, tzinfo=ZoneInfo("Asia/Hong_Kong"))
            first = daily.run_due_cycle(state_db=state, history_db=state, now=now, force=True, send_func=send)
            second = daily.run_due_cycle(state_db=state, history_db=state, now=now, force=True, send_func=send)

        self.assertEqual(len(first["actions"]), 1)
        self.assertEqual(second["actions"], [])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], event["chat_id"])
        self.assertIn("#daily", sent[0][1])

    def test_labagent_disables_public_publish_even_for_owner(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "publish_video",
                    "response": "",
                    "task": "publish it",
                    "ack": "working",
                    "public_publish_allowed": True,
                }
            ),
        }
        event = self.sample_event(
            text="Publish this video to YouTube",
            authorization_role="owner",
            irreversible_actions_allowed=True,
        )
        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(event, ingest.event_request(event), [])

        self.assertFalse(route["public_publish_allowed"])

    def test_long_direct_wecom_answer_moves_to_lossless_worker_delivery(self) -> None:
        ingest = load_ingest()
        answer = "完整回答。" * 500
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "chat_only",
                    "response": answer,
                    "task": "",
                    "ack": "",
                    "message_role": "ordinary_chat",
                    "public_publish_allowed": False,
                },
                ensure_ascii=False,
            ),
        }
        event = self.sample_event(text="请完整说明。")

        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(event, ingest.event_request(event), [])

        self.assertTrue(route["worker_needed"])
        self.assertTrue(route["long_response_deferred"])
        self.assertEqual(route["route_kind"], "other_worker")
        self.assertEqual(route["response"], "")
        with tempfile.TemporaryDirectory() as tmp:
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )
        self.assertEqual(task["status"], "send_deferred_artifact")
        self.assertEqual(task["result"]["message"], answer)
        self.assertEqual(task["send_deferred_reason"], "long_response_delivery")

    def test_route_report_decision_becomes_required_delivery_contract(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "research_or_summary",
                    "response": "",
                    "task": "Deeply research this question and return a LaTeX PDF.",
                    "ack": "先给初步判断，完整报告正在整理。",
                    "report_required": True,
                    "public_publish_allowed": False,
                }
            ),
        }
        event = self.sample_event(text="这个机制应当如何验证？")
        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(event, ingest.event_request(event), [])
        with tempfile.TemporaryDirectory() as tmp:
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )

        self.assertTrue(route["report_required"])
        self.assertTrue(task["route_decision"]["require_file_delivery"])
        self.assertEqual(task["execution_contract"]["required_artifacts"], ["pdf"])
        evidence = task["execution_contract"]["research_evidence"]
        self.assertEqual(evidence["minimum_traceable_sources"], 2)
        self.assertTrue(evidence["separate_direct_indirect_hypothesis"])

    def test_wecom_task_honors_explicit_backend_override(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "research_or_summary",
                    "response": "",
                    "task": "Research this request.",
                    "ack": "",
                    "report_required": False,
                    "public_publish_allowed": False,
                }
            ),
        }
        event = self.sample_event(text="Research this request.")
        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(event, ingest.event_request(event), [])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {"WECOM_AGENT_BACKEND": "codex"},
        ):
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )

        self.assertEqual(task["agent_backend"], "codex")

    def test_same_member_pdf_preference_upgrades_substantial_research_only(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(text="这个机制的临床价值和验证路径是什么？")
        research_response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "research_or_summary",
                    "response": "",
                    "task": "Research the mechanism and validation path.",
                    "ack": "我先给出初步判断，完整研究在继续。",
                    "report_required": False,
                    "message_role": "research_request",
                    "public_publish_allowed": False,
                }
            ),
        }
        preference = {
            "scope": "exact_member_and_chat",
            "preferences": {
                "pdf_reports": {
                    "preferred_for_substantial_research": True,
                    "explicit_request_count": 2,
                    "completed_report_count": 3,
                }
            },
        }
        with mock.patch.object(ingest, "run_agent_session", return_value=research_response):
            route = ingest.route_event(
                event,
                ingest.event_request(event),
                [],
                memory_context=preference,
            )

        self.assertTrue(route["report_required"])

        chat_response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": False,
                    "route_kind": "other_worker",
                    "response": "早上好。",
                    "task": "",
                    "ack": "",
                    "report_required": False,
                    "message_role": "ordinary_chat",
                    "public_publish_allowed": False,
                }
            ),
        }
        with mock.patch.object(ingest, "run_agent_session", return_value=chat_response):
            chat_route = ingest.route_event(
                self.sample_event(text="早上好"),
                "早上好",
                [],
                memory_context=preference,
            )
        self.assertFalse(chat_route["report_required"])

    def test_explicit_evidence_check_cannot_degrade_to_other_worker(self) -> None:
        ingest = load_ingest()
        response = {
            "ok": True,
            "message": json.dumps(
                {
                    "worker_needed": True,
                    "route_kind": "other_worker",
                    "response": "",
                    "task": "Answer the question.",
                    "ack": "我会核对。",
                    "report_required": False,
                    "message_role": "ordinary_chat",
                    "public_publish_allowed": False,
                }
            ),
        }
        event = self.sample_event(text="帮我调研这个机制是否有研究依据")
        with mock.patch.object(ingest, "run_agent_session", return_value=response):
            route = ingest.route_event(event, ingest.event_request(event), [])
        with tempfile.TemporaryDirectory() as tmp:
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )

        self.assertEqual(route["route_kind"], "research_or_summary")
        self.assertEqual(route["message_role"], "research_request")
        self.assertTrue(task["execution_contract"]["research_evidence"]["required"])
        self.assertEqual(
            task["execution_contract"]["research_evidence"]["minimum_traceable_sources"],
            2,
        )

    def test_wecom_task_preserves_sender_and_exact_chat_response_policy(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            transport_channel="wecom_android",
            sender_userid="android-member:prof-ma",
            sender_display="megamonster",
            sender_mention="megamonster@微信",
            sender_identity_confidence="visible_row_label",
            sender_evidence={"sender_label_bounds": "[80,100][260,130]"},
        )
        route = {
            "worker_needed": True,
            "route_kind": "research_or_summary",
            "response": "",
            "task": "Research the exact question.",
            "ack": "",
            "report_required": True,
            "reply_to_senders": [],
            "public_publish_allowed": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            task = ingest.build_task(
                event,
                ingest.canonical_chat_name(event),
                ingest.event_request(event),
                [],
                route,
                Path(tmp) / "queue.jsonl",
            )

        policy = task["response_policy"]
        self.assertEqual(policy["scope"], "exact_chat_only")
        self.assertFalse(policy["automatic_multilingual"])
        self.assertEqual(policy["language_mode"], "match_requester_language")
        self.assertFalse(policy["cross_chat_context_allowed"])
        self.assertEqual(policy["profile_id"], "labagent")
        self.assertTrue(policy["capability_profile"]["template_profile"])
        self.assertEqual(policy["capability_profile"]["id"], "labagent")
        self.assertNotIn(
            "explicitly_authorized_video_publication",
            policy["capability_profile"]["capabilities"],
        )
        self.assertEqual(task["source"]["sender_display"], "megamonster")
        self.assertEqual(task["source"]["sender_mention"], "megamonster@微信")
        self.assertEqual(task["source"]["sender_identity_confidence"], "visible_row_label")
        self.assertEqual(task["source"]["reply_mentions"], ["megamonster@微信"])

    def test_wecom_history_migrates_and_retains_sender_evidence(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(
            sender_display="sunnyyty",
            sender_mention="sunnyyty@微信",
            sender_identity_confidence="visible_row_label",
            sender_evidence={"sender_candidate_count": "1"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            with sqlite3.connect(history) as conn:
                conn.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, message_id TEXT NOT NULL UNIQUE, "
                    "chat TEXT NOT NULL, direction TEXT NOT NULL, sender TEXT, sender_display TEXT, "
                    "body TEXT NOT NULL, create_time INTEGER, created_at TEXT NOT NULL, processed_at TEXT)"
                )
            ingest.init_history_db(history)
            chat = ingest.canonical_chat_name(event)
            ingest.record_history_message(history, event, chat, event["text"], direction="inbound")
            rows = ingest.recent_history(history, chat, limit=4)

        self.assertEqual(rows[0]["sender_display"], "sunnyyty")
        self.assertEqual(rows[0]["sender_mention"], "sunnyyty@微信")
        self.assertEqual(rows[0]["sender_identity_confidence"], "visible_row_label")
        self.assertEqual(rows[0]["sender_evidence"]["sender_candidate_count"], "1")

    def test_verified_worker_reply_becomes_same_chat_agent_context_once(self) -> None:
        ingest = load_ingest()
        first = self.sample_event(
            text="提出一个类器官产品方向。", create_time=1784300000
        )
        follow_up = self.sample_event(
            text="比如让它承担传感和计算。", create_time=1784300002
        )
        follow_up["message_id"] = "wecom-follow-up-2"
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite"
            ingest.init_history_db(history)
            chat = ingest.canonical_chat_name(first)
            ingest.record_history_message(
                history, first, chat, first["text"], direction="inbound"
            )
            inserted = ingest.record_verified_worker_outbound(
                history,
                task_id="worker-task-1",
                chat=chat,
                body="可以先拆成传感、计算和产品化三个可验证方向。",
                sent_at=datetime.fromtimestamp(1784300001).isoformat(),
            )
            duplicate = ingest.record_verified_worker_outbound(
                history,
                task_id="worker-task-1",
                chat=chat,
                body="可以先拆成传感、计算和产品化三个可验证方向。",
                sent_at=datetime.fromtimestamp(1784300001).isoformat(),
            )
            ingest.record_history_message(
                history,
                follow_up,
                chat,
                follow_up["text"],
                direction="inbound",
            )
            rows = ingest.recent_history(history, chat, limit=5)

        self.assertTrue(inserted)
        self.assertFalse(duplicate)
        self.assertEqual([row["is_self"] for row in rows], [False, True, False])
        self.assertIn("三个可验证方向", rows[1]["content"])

    def test_incomplete_ingest_can_retry_same_message(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": True,
            "route_kind": "other_worker",
            "response": "",
            "task": "complete the task",
            "ack": "working",
            "public_publish_allowed": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.jsonl"
            history = root / "history.sqlite"
            with mock.patch.object(
                ingest,
                "route_event",
                side_effect=[RuntimeError("temporary route failure"), route],
            ), mock.patch.object(ingest, "record_event"):
                with self.assertRaisesRegex(RuntimeError, "temporary route failure"):
                    ingest.ingest_event(self.sample_event(), queue=queue, history_db=history, route_with_agent=True)
                recovered = ingest.ingest_event(
                    self.sample_event(),
                    queue=queue,
                    history_db=history,
                    route_with_agent=True,
                )
                duplicate = ingest.ingest_event(
                    self.sample_event(),
                    queue=queue,
                    history_db=history,
                    route_with_agent=True,
                )

        self.assertTrue(recovered["queued"])
        self.assertFalse(recovered["duplicate"])
        self.assertTrue(duplicate["duplicate"])

    def test_trusted_group_member_can_use_shared_cad_design_routine(self) -> None:
        ingest = load_ingest()
        route = {
            "worker_needed": True,
            "route_kind": "cad_pcb_labcanvas",
            "response": "",
            "task": "Design and render the requested optical holder.",
            "ack": "I will design and return the editable artifacts.",
            "public_publish_allowed": False,
        }
        event = self.sample_event(
            sender_userid="trusted-member",
            authorization_role="group_member",
            irreversible_actions_allowed=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.jsonl"
            history = root / "history.sqlite"
            with mock.patch.object(ingest, "route_event", return_value=route), mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(event, queue=queue, history_db=history, route_with_agent=True)
            task = json.loads(queue.read_text(encoding="utf-8").strip())

        self.assertTrue(result["queued"])
        self.assertEqual(task["routine"]["id"], "labcanvas_cad_pcb")
        self.assertEqual(task["route_decision"]["sender_authorization_role"], "group_member")
        self.assertFalse(task["route_decision"]["public_publish_allowed"])

    def test_router_plan_cannot_replace_exact_user_request(self) -> None:
        ingest = load_ingest()
        exact = "collal 是一个蛋白，研究它对肿瘤的影响并画信号通路图"
        route = {
            "worker_needed": True,
            "route_kind": "research_or_summary",
            "response": "",
            "task": "Do not proceed until the user confirms the spelling.",
            "ack": "我会先核验名称并调研。",
            "daily_topic": "",
            "public_publish_allowed": False,
        }
        event = self.sample_event(text=exact, transport_channel="wecom_gui")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ingest, "route_event", return_value=route), mock.patch.object(
                ingest,
                "record_event",
            ):
                ingest.ingest_event(
                    event,
                    queue=root / "queue.jsonl",
                    history_db=root / "history.sqlite",
                    route_with_agent=True,
                )
            task = json.loads((root / "queue.jsonl").read_text(encoding="utf-8"))

        self.assertEqual(task["request"], exact)
        self.assertEqual(task["original_request"], exact)
        self.assertEqual(task["route_plan"], route["task"])
        self.assertTrue(task["instruction_contract"]["router_plan_is_advisory"])

    def test_worker_uses_wecom_transport_without_resolving_gui_target(self) -> None:
        worker = load_worker()
        task = {
            "id": "wecom-task",
            "chat": "wecom:default:group:abc",
            "source": {
                "transport": "wecom",
                "chat": "wecom:default:group:abc",
                "wecom_chat_id": "private-chat-id",
            },
        }
        result = {"message": "done", "confirmation": "", "files": []}
        with mock.patch.object(worker, "send_result_once_wecom") as send_wecom, mock.patch.object(
            worker, "guarded_send_target", side_effect=AssertionError("GUI target lookup should not run")
        ):
            worker.send_result_once(result, task["chat"], Path("/tmp/missing.json"), task=task)

        send_wecom.assert_called_once_with(result, task["chat"], task)

    def test_legacy_wecom_chat_prefix_cannot_fall_back_to_personal_wechat(self) -> None:
        worker = load_worker()
        task = {
            "id": "legacy-wecom-task",
            "chat": "wecom:external-gui:group:abc",
            "execution_contract": {"required_artifacts": []},
        }
        result = {"message": "done", "confirmation": "", "files": []}

        self.assertEqual(worker.task_transport_kind(task), "wecom")
        contract = worker.worker_execution_contract(task)
        self.assertEqual(contract["transport"], "wecom")
        self.assertEqual(contract["wecom_transport_channel"], "wecom")
        with mock.patch.object(
            worker,
            "send_result_once_wecom",
        ) as send_wecom, mock.patch.object(
            worker,
            "guarded_send_target",
            side_effect=AssertionError("personal WeChat target lookup should not run"),
        ):
            worker.send_result_once(
                result,
                task["chat"],
                Path("/tmp/missing.json"),
                task=task,
            )

        send_wecom.assert_called_once_with(result, task["chat"], task)

    def test_worker_contract_preserves_exact_wecom_transport_channel(self) -> None:
        worker = load_worker()
        task = {
            "chat": "wecom:external-gui:group:abc",
            "source": {
                "transport": "wecom",
                "wecom_transport_channel": "wecom_android",
            },
            "execution_contract": {"required_artifacts": ["pdf"]},
        }

        contract = worker.worker_execution_contract(task)

        self.assertEqual(worker.task_transport_kind(task), "wecom")
        self.assertEqual(worker.task_transport_channel(task), "wecom_android")
        self.assertEqual(contract["transport"], "wecom_android")
        self.assertEqual(contract["wecom_transport_channel"], "wecom_android")
        self.assertEqual(contract["required_artifacts"], ["pdf"])

    def test_worker_selects_separate_cli_delivery_endpoint(self) -> None:
        worker = load_worker()
        task = {"source": {"transport": "wecom", "wecom_transport_channel": "wecom_cli"}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_cli_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 23456, "local_api_token": "private-token"}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root):
                endpoint, token = worker.wecom_transport_settings(task)

        self.assertEqual(endpoint, "http://127.0.0.1:23456")
        self.assertEqual(token, "private-token")

    def test_worker_selects_android_delivery_endpoint(self) -> None:
        worker = load_worker()
        task = {"source": {"transport": "wecom_android", "wecom_transport_channel": "wecom_android"}}
        with mock.patch.object(worker, "ready_wecom_android_transport", return_value=("http://127.0.0.1:19581", "android-token")):
            endpoint, token = worker.wecom_transport_settings(task)

        self.assertEqual(endpoint, "http://127.0.0.1:19581")
        self.assertEqual(token, "android-token")

    def test_worker_selects_separate_gui_delivery_endpoint(self) -> None:
        worker = load_worker()
        task = {"source": {"transport": "wecom", "wecom_transport_channel": "wecom_gui"}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_gui_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 23457, "local_api_token": "gui-token"}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root):
                endpoint, token = worker.wecom_transport_settings(task)

        self.assertEqual(endpoint, "http://127.0.0.1:23457")
        self.assertEqual(token, "gui-token")

    def test_agent_route_can_enroll_natural_daily_topic(self) -> None:
        ingest = load_ingest()
        event = self.sample_event(text="每天整理类器官最前沿研究", transport_channel="wecom_gui")
        route = {
            "worker_needed": True,
            "route_kind": "research_or_summary",
            "task": "Prepare a deep organoid frontier review and PDF.",
            "ack": "我会整理并把 PDF 发回群里。",
            "daily_topic": "类器官最前沿研究",
            "public_publish_allowed": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            with mock.patch.object(ingest, "route_event", return_value=route), mock.patch.object(ingest, "record_event"):
                result = ingest.ingest_event(
                    event,
                    queue=root / "queue.jsonl",
                    history_db=history,
                    route_with_agent=True,
                )
            daily = load_daily()
            status = daily.daily_status(history)

        self.assertTrue(result["queued"])
        self.assertIn("类器官最前沿研究", result["ack"])
        self.assertEqual(status["chats"][0]["topics"], ["类器官最前沿研究"])

    def test_worker_preflight_preserves_exact_wecom_media_and_skips_wechat_resolution(self) -> None:
        worker = load_worker()
        task = {
            "id": "wecom-media-task",
            "chat": "wecom:default:dm:abc",
            "source": {"transport": "wecom", "chat": "wecom:default:dm:abc"},
            "route_decision": {"route_kind": "file_intake"},
            "routine": {"id": "file_intake"},
            "transport_preflight": {
                "wecom_media": {
                    "status": "ready",
                    "copied": [{"task_copy_path": "/tmp/exact.pdf", "status": "ready"}],
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            worker, "prepare_file_intake_preflight", side_effect=AssertionError("personal WeChat intake should not run")
        ):
            preflight = worker.prepare_worker_preflight(task, Path(tmp))

        self.assertEqual(preflight["wecom_media"]["status"], "ready")

    def test_worker_preflight_reads_exact_wecom_pdf_before_agent_turn(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "incoming" / "exact-paper.pdf"
            paper.parent.mkdir()
            paper.write_bytes(b"%PDF-1.4\nexact")
            context = root / "task" / "document_read" / "01-exact-paper" / "agent-context.md"
            context.parent.mkdir(parents=True)
            context.write_text("# Exact paper\n\nReadable evidence.\n", encoding="utf-8")
            task = {
                "id": "wecom-document-task",
                "chat": "wecom:default:group:abc",
                "source": {
                    "transport": "wecom",
                    "wecom_transport_channel": "wecom_android",
                    "chat": "wecom:default:group:abc",
                },
                "route_decision": {"route_kind": "file_intake"},
                "routine": {"id": "file_intake"},
                "transport_preflight": {
                    "wecom_media": {
                        "status": "ready",
                        "copied": [
                            {
                                "kind": "document",
                                "filename": paper.name,
                                "task_copy_path": str(paper),
                                "status": "ready",
                            }
                        ],
                    }
                },
            }
            document_read = {
                "status": "readable",
                "source_path": str(paper),
                "agent_context_path": str(context),
            }
            with mock.patch.object(
                worker,
                "prepare_file_intake_preflight",
                side_effect=AssertionError("personal WeChat intake should not run"),
            ), mock.patch.object(
                worker,
                "analyze_document",
                return_value=document_read,
            ) as analyze:
                preflight = worker.prepare_worker_preflight(task, root / "task")

        copied = preflight["wecom_media"]["copied"][0]
        self.assertEqual(copied["document_read"], document_read)
        analyze.assert_called_once()

    def test_worker_transcribes_exact_official_wecom_voice_without_personal_wechat_resolution(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            voice = root / "inbound" / "voice.amr"
            voice.parent.mkdir()
            voice.write_bytes(b"#!AMR\nvoice")
            agent_context = root / "task" / "audio_intake" / "agent-context.md"
            agent_context.parent.mkdir(parents=True)
            agent_context.write_text("# transcript\n\nexact voice\n", encoding="utf-8")
            task = {
                "id": "wecom-voice-task",
                "chat": "wecom:default:group:abc",
                "source": {
                    "transport": "wecom",
                    "wecom_transport_channel": "wecom_official",
                    "chat": "wecom:default:group:abc",
                    "local_id": 42,
                    "local_type": "voice",
                },
                "route_decision": {"route_kind": "file_intake"},
                "routine": {"id": "file_intake"},
                "transport_preflight": {
                    "wecom_media": {
                        "status": "ready",
                        "copied": [
                            {
                                "kind": "voice",
                                "task_copy_path": str(voice),
                                "status": "ready",
                            }
                        ],
                    }
                },
            }
            expected = {
                "status": "transcribed",
                "input_kind": "local_wechat_media",
                "agent_context_path": str(agent_context),
            }
            with mock.patch.object(
                worker,
                "prepare_file_intake_preflight",
                side_effect=AssertionError("personal WeChat intake should not run"),
            ), mock.patch.object(
                worker,
                "prepare_media_resolution_preflight",
                side_effect=AssertionError("personal WeChat media resolution should not run"),
            ), mock.patch.object(
                worker,
                "run_audio_intake_transcriber",
                return_value=expected,
            ) as transcribe:
                preflight = worker.prepare_worker_preflight(task, root / "task")

            self.assertEqual(preflight["audio_intake"], expected)
            transcribe.assert_called_once_with(
                voice.resolve(), output_dir=root / "task" / "audio_intake", source_local_id=42
            )

    def test_admin_command_reports_launcher_novnc_url(self) -> None:
        wecom_ops = load_wecom_ops()
        reported_url = (
            "http://127.0.0.1:6244/vnc.html?"
            "host=127.0.0.1&port=6244&autoconnect=1&resize=scale"
        )
        completed = mock.Mock(
            returncode=0,
            stdout=f"WeCom admin opened.\nnoVNC: {reported_url}\n",
            stderr="",
        )
        output = io.StringIO()

        with mock.patch.object(wecom_ops.subprocess, "run", return_value=completed), redirect_stdout(output):
            returncode = wecom_ops.cmd_admin(SimpleNamespace(json=True))

        payload = json.loads(output.getvalue())
        self.assertEqual(returncode, 0)
        self.assertEqual(payload["novnc_url"], reported_url)

    def test_windows_client_is_wecom_only_and_isolated(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_windows_client.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("WECOM_CLIENT_WINEPREFIX", source)
        self.assertIn("127.0.0.1", source)
        self.assertIn("WXWork", source)
        self.assertIn("autofit-loop", source)
        self.assertIn("xdotool getdisplaygeometry", source)
        self.assertIn("resize=scale", source)
        self.assertIn("reconnect=1", source)
        self.assertIn("WECOM_CLIENT_LAYERED_NATIVE_GEOMETRY", source)
        self.assertIn("native geometry", source)
        self.assertIn("supervise_client", source)
        self.assertIn("WECOM_CLIENT_RESTART_LIMIT", source)
        self.assertIn("WECOM_CLIENT_RESTART_QUARANTINE_SECONDS", source)
        self.assertIn("login_fallback_due", source)
        self.assertIn("stable_checks >= 4", source)
        self.assertIn("if is_running && wait_for_client_window 4", source)
        self.assertIn("app-login-broker.log", source)
        self.assertIn("show_login_qr()", source)
        start_client = source[source.index("start_client()") : source.index("show_login_qr()")]
        self.assertNotIn("--switch-account", start_client)
        self.assertNotIn("if is_running && login_fallback_due", source)
        self.assertNotIn("com.tencent.mm", source)
        self.assertNotIn("wechat_gui_agent", source)
        self.assertNotIn("xwechat_files", source)

    def test_client_command_reports_isolated_novnc_url(self) -> None:
        wecom_ops = load_wecom_ops()
        reported_url = (
            "http://127.0.0.1:6192/vnc.html?"
            "host=127.0.0.1&port=6192&autoconnect=1&resize=scale"
        )
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "action": "start",
                    "installed": True,
                    "running": True,
                    "novnc_url": reported_url,
                    "error": "",
                }
            ),
            stderr="",
        )
        output = io.StringIO()

        with mock.patch.object(wecom_ops.subprocess, "run", return_value=completed) as run, redirect_stdout(output):
            returncode = wecom_ops.cmd_client(SimpleNamespace(action="start", json=True))

        payload = json.loads(output.getvalue())
        self.assertEqual(returncode, 0)
        self.assertTrue(payload["running"])
        self.assertEqual(payload["novnc_url"], reported_url)
        self.assertEqual(run.call_args.args[0][-2:], ["start", "--json"])

    def test_virtual_desktop_defaults_to_full_scaled_novnc(self) -> None:
        source = (
            ROOT / "agentic_tools" / "virtual_desktop" / "launch_virtual_desktop.sh"
        ).read_text(encoding="utf-8")
        android_source = (
            ROOT / "agentic_tools" / "android_device_agent" / "scripts" / "android_device_desktop.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("/vnc.html?", source)
        self.assertIn("resize=scale", source)
        self.assertIn("display_ready()", source)
        self.assertIn("timeout 3s env DISPLAY=", source)
        self.assertNotIn("vnc_lite.html", source)
        self.assertIn("/vnc.html?", android_source)
        self.assertIn("resize=scale", android_source)
        self.assertIn("reconnect=1", android_source)
        self.assertNotIn("vnc_lite.html", android_source)
        self.assertIn("ANDROID_DEVICE_RETRY_SECONDS", android_source)
        self.assertIn(
            '--app-match "^([^[:space:]]*/)?scrcpy --serial $serial([[:space:]]|$)"',
            android_source,
        )
        self.assertIn("while true; do $command || true", android_source)
        self.assertIn("mirror: waiting for scrcpy retry", android_source)
        self.assertIn(
            "on|off|start|stop|restart|transport-restart|dual-heal|status|dual|single|wechat|wecom",
            android_source,
        )
        self.assertIn("restart_novnc_transport", android_source)
        self.assertIn("heal_dual_layout_once", android_source)
        self.assertIn("ensure_dual_guard", android_source)
        self.assertIn('flock -n 9 || return 0', android_source)
        self.assertIn('tmux respawn-pane -k -t "$SESSION:$DUAL_WINDOW_NAME.0"', android_source)
        self.assertIn(
            "Preserve Xvfb, scrcpy,",
            android_source,
        )
        self.assertIn("--new-display=1080x2160/440", android_source)
        self.assertIn('help_output="$("$1" --help 2>&1)"', android_source)
        self.assertIn("--start-app=+com.tencent.wework", android_source)
        self.assertIn("--render-driver=software", android_source)
        self.assertIn("LabCanvas WeCom Virtual", android_source)
        self.assertIn("Keep WeChat physical and WeCom virtual side by side", android_source)
        self.assertIn("mix2s_dual_setup", android_source)
        self.assertIn(
            "Holding the shared Android lock for",
            android_source,
        )
        self.assertNotIn('--purpose mix2s_dual_review \\', android_source)
        self.assertIn("trap cleanup EXIT HUP INT TERM", android_source)
        self.assertIn('kill -TERM -- "-$child_pid"', android_source)
        self.assertIn("while [[ ", android_source)
        self.assertNotIn("ANDROID_DEVICE_DUAL_REVIEW_SECONDS", android_source)
        self.assertIn("dual_process_live", android_source)
        self.assertIn("dual_activity_state", android_source)
        self.assertIn("waiting for app restore", android_source)
        self.assertIn("com\\.tencent\\.mm", android_source)
        self.assertIn("com\\.tencent\\.wework", android_source)
        self.assertIn("android_control_lease.py", android_source)
        self.assertIn("tail -n 1 || true", android_source)
        self.assertIn("LAYOUT_FILE", android_source)
        self.assertIn('shell svc power stayon false', android_source)
        self.assertIn('shell input keyevent 223', android_source)
        self.assertIn('stop_matching_processes "noVNC relay', android_source)
        self.assertIn('stop_matching_processes "Xvfb display', android_source)
        self.assertIn('echo "mirror: off"', android_source)

        mix2s_wrapper = (ROOT / "scripts" / "mix2s").read_text(encoding="utf-8")
        self.assertIn("android_device_desktop.sh", mix2s_wrapper)
        self.assertIn('exec ', mix2s_wrapper)

    def test_external_cli_exact_group_resolution_is_fail_closed(self) -> None:
        bridge = load_cli_bridge()
        chats = [
            {"chat_id": "one", "chat_name": "AgentTest"},
            {"chat_id": "two", "chat_name": "AgentTest archive"},
            {"chat_id": "three", "chat_name": "Other"},
        ]

        resolved = bridge.resolve_exact_target_chats(chats, ["AgentTest", "Missing"])

        self.assertEqual([item["chat_id"] for item in resolved["AgentTest"]], ["one"])
        self.assertEqual(resolved["Missing"], [])

    def test_external_cli_refuses_changed_chat_identity(self) -> None:
        bridge = load_cli_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            bridge.init_state_db(state)
            self.assertTrue(bridge.remember_target_chat(state, "AgentTest", "raw-one", bridge.short_hash("raw-one")))
            with self.assertRaisesRegex(RuntimeError, "changed identity"):
                bridge.remember_target_chat(state, "AgentTest", "raw-two", bridge.short_hash("raw-two"))

    def test_external_cli_initial_bind_processes_only_latest_message(self) -> None:
        bridge_module = load_cli_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "target_groups": ["AgentTest"],
                "cli_path": str(root / "wecom-cli"),
                "auth_config_dir": str(root / "auth"),
                "tmp_dir": str(root / "tmp"),
                "state_db": str(root / "state.sqlite"),
                "event_root": str(root / "events"),
                "queue": str(root / "queue.jsonl"),
                "initial_backfill": "latest",
                "max_message_age_seconds": 3600,
                "debounce_seconds": 0,
            }
            bridge = bridge_module.WeComCliBridge(config, config_path=root / "config.json")
            now = datetime(2026, 7, 18, 15, 0, 0)
            messages = [
                {"userid": "member", "send_time": "2026-07-18 14:58:00", "msgtype": "text", "text": {"content": "old"}},
                {"userid": "member", "send_time": "2026-07-18 14:59:00", "msgtype": "text", "text": {"content": "new"}},
            ]
            with mock.patch.object(bridge, "invoke_ingest", return_value={"ok": True, "queued": True, "ack": "working"}) as ingest_call, mock.patch.object(
                bridge, "send_text", return_value={"ok": True}
            ) as send_call:
                outcome = bridge.process_chat_messages(
                    target_name="AgentTest",
                    chat_id="raw-chat",
                    chat_hash=bridge_module.short_hash("raw-chat"),
                    messages=messages,
                    now=now,
                    first_resolution=True,
                )
            event_path = Path(ingest_call.call_args.args[0])
            event = json.loads(event_path.read_text(encoding="utf-8"))

        self.assertEqual(outcome["processed"], 1)
        self.assertEqual(outcome["seeded"], 1)
        self.assertEqual(event["text"], "new")
        self.assertEqual(event["transport_channel"], "wecom_cli")
        send_call.assert_called_once()

    def test_external_cli_source_has_no_personal_wechat_runtime_import(self) -> None:
        source = (ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_cli_bridge.py").read_text(encoding="utf-8")

        self.assertNotIn("wechat_gui_agent", source)
        self.assertNotIn("xwechat_files", source)

    def test_external_transport_guard_requires_complete_official_profile(self) -> None:
        guard = load_cli_guard()
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / "auth"
            auth.mkdir()
            config = {"auth_config_dir": str(auth)}
            (auth / "bot.enc").write_text("bot", encoding="utf-8")
            (auth / "mcp_config.enc").write_text("mcp", encoding="utf-8")
            self.assertFalse(guard.profile_ready(config))
            (auth / ".encryption_key").write_text("key", encoding="utf-8")
            self.assertTrue(guard.profile_ready(config))

    def test_external_transport_guard_status_exposes_no_raw_group_identity(self) -> None:
        guard = load_cli_guard()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth"
            auth.mkdir()
            state = root / "status.json"
            state.write_text(
                json.dumps({"state": "waiting_for_qr_scan", "raw_chat_id": "wr-private"}),
                encoding="utf-8",
            )
            status = guard.transport_status(
                {
                    "enabled": True,
                    "auth_config_dir": str(auth),
                    "target_groups": ["AgentTest"],
                },
                state,
            )

        self.assertEqual(status["state"], "waiting_for_qr_scan")
        self.assertEqual(status["target_group_count"], 1)
        self.assertNotIn("raw_chat_id", status)
        self.assertNotIn("AgentTest", json.dumps(status))

    def test_external_transport_guard_never_imports_personal_wechat(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_cli_transport_guard.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("wechat_gui_agent", source)
        self.assertNotIn("xwechat_files", source)

    def test_external_transport_guard_marks_live_bridge_running(self) -> None:
        guard = load_cli_guard()
        process = mock.Mock()
        process.wait.return_value = 0

        with mock.patch.object(guard.subprocess, "Popen", return_value=process), mock.patch.object(
            guard, "write_status"
        ) as write_status:
            result = guard.run_bridge(
                {"_config_path": "/private/external.json"},
                Path("/private/status.json"),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(write_status.call_args_list[0].args[1]["state"], "bridge_starting")
        self.assertEqual(write_status.call_args_list[1].args[1]["state"], "bridge_running")
        self.assertEqual(write_status.call_args_list[2].args[1]["state"], "bridge_stopped")

    def test_external_transport_guard_refuses_false_running_without_message_permission(self) -> None:
        guard = load_cli_guard()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth"
            auth.mkdir()
            for name in ("bot.enc", "mcp_config.enc", ".encryption_key"):
                (auth / name).write_text("private", encoding="utf-8")
            config = {
                "enabled": True,
                "auth_config_dir": str(auth),
                "_config_path": str(root / "external.json"),
            }
            status_path = root / "status.json"
            capability = {
                "ok": False,
                "checks": {"msg_permission": False},
                "error": "current enterprise does not grant message permission",
            }
            with mock.patch.object(guard, "probe_message_capability", return_value=capability), mock.patch.object(
                guard, "run_bridge", side_effect=AssertionError("bridge must not start")
            ):
                result = guard.run_once(config, status_path, 9353)
            persisted = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertFalse(result["ok"])
        self.assertTrue(result["stopped"])
        self.assertEqual(result["state"], "message_permission_unavailable")
        self.assertFalse(result["msg_permission"])
        self.assertTrue(result["gui_fallback_recommended"])
        self.assertEqual(persisted["state"], "message_permission_unavailable")

    def test_external_transport_guard_starts_bridge_only_after_capability_probe(self) -> None:
        guard = load_cli_guard()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = root / "auth"
            auth.mkdir()
            for name in ("bot.enc", "mcp_config.enc", ".encryption_key"):
                (auth / name).write_text("private", encoding="utf-8")
            config = {
                "enabled": True,
                "auth_config_dir": str(auth),
                "_config_path": str(root / "external.json"),
            }
            expected = {"ok": True, "state": "bridge_stopped"}
            with mock.patch.object(
                guard,
                "probe_message_capability",
                return_value={"ok": True, "checks": {"msg_permission": True}},
            ), mock.patch.object(guard, "run_bridge", return_value=expected) as run_bridge:
                result = guard.run_once(config, root / "status.json", 9353)

        self.assertEqual(result, expected)
        run_bridge.assert_called_once()

    def test_external_status_reads_separate_guard(self) -> None:
        wecom_ops = load_wecom_ops()
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "configured": True,
                    "profile_ready": False,
                    "state": "waiting_for_qr_scan",
                    "target_group_count": 1,
                }
            ),
            stderr="",
        )
        output = io.StringIO()

        with mock.patch.object(wecom_ops.subprocess, "run", return_value=completed) as run, redirect_stdout(output):
            returncode = wecom_ops.cmd_external(SimpleNamespace(action="status", json=True))

        payload = json.loads(output.getvalue())
        command = run.call_args.args[0]
        self.assertEqual(returncode, 0)
        self.assertEqual(payload["state"], "waiting_for_qr_scan")
        self.assertIn("wecom_cli_transport_guard.py", " ".join(command))
        self.assertNotIn("wechat_gui_agent", " ".join(command))

    def test_external_authorize_restarts_only_external_window(self) -> None:
        wecom_ops = load_wecom_ops()
        completed = mock.Mock(returncode=0, stdout="ok", stderr="")
        output = io.StringIO()

        with mock.patch.object(
            wecom_ops.subprocess,
            "run",
            side_effect=[completed, completed],
        ) as run, redirect_stdout(output):
            returncode = wecom_ops.cmd_external(
                SimpleNamespace(action="authorize", json=True)
            )

        self.assertEqual(returncode, 0)
        self.assertEqual(run.call_args_list[1].args[0][-1], "external-restart")
        self.assertNotEqual(run.call_args_list[1].args[0][-1], "restart")

    def test_gui_tsv_parser_does_not_merge_quoted_rows(self) -> None:
        bridge = load_gui_bridge()
        value = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t1\t2\t3\t4\t90\t#daily \"topic\"\n"
            "5\t1\t1\t1\t2\t1\t1\t8\t3\t4\t90\tnext message\n"
        )

        rows = bridge.parse_tesseract_tsv(value)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["text"], '#daily "topic"')
        self.assertEqual(rows[1]["text"], "next message")

    def test_gui_bubble_regions_isolate_inbound_message_background(self) -> None:
        bridge = load_gui_bridge()
        if bridge.Image is None:
            self.skipTest("Pillow is an optional WeCom GUI runtime dependency")
        image = bridge.Image.new("RGB", (120, 80), (248, 249, 250))
        for x in range(10, 90):
            for y in range(20, 50):
                image.putpixel((x, y), (228, 231, 235))

        regions = [item for item in bridge.find_color_regions(image, (228, 231, 235), tolerance=8) if item[4] > 300]

        self.assertEqual(regions, [(10, 20, 90, 50, 2400)])

    def test_gui_empty_seed_accepts_first_future_message(self) -> None:
        bridge = load_gui_bridge()

        messages, overlap = bridge.new_message_suffix([], ["new question"])

        self.assertEqual(messages, ["new question"])
        self.assertEqual(overlap, 0)

    def test_gui_ocr_prefers_han_result_over_english_hallucination(self) -> None:
        bridge = load_gui_bridge()

        selected = bridge.choose_ocr_variant("BY LACH", "可以啦")

        self.assertEqual(selected, "可以啦")

    def test_gui_chat_identity_accepts_bounded_visual_ocr_substitution(self) -> None:
        bridge = load_gui_bridge()

        self.assertTrue(bridge.ocr_visual_identity_matches("4gentTest", "AgentTest"))
        self.assertTrue(bridge.ocr_visual_identity_matches("LabAgent", "LabAgent"))
        self.assertFalse(bridge.ocr_visual_identity_matches("AgentBest", "AgentTest"))
        self.assertFalse(bridge.ocr_visual_identity_matches("AgentTest2", "AgentTest"))
        self.assertFalse(bridge.ocr_visual_identity_matches("懒人科研", "LabAgent"))

    def test_gui_config_accumulates_two_groups_and_enables_exact_search_fallback(self) -> None:
        bridge = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "gui.json"
            bridge.initialize_config(config, ["LabAgent"], allow_search_fallback=False)
            payload = bridge.initialize_config(
                config,
                ["AgentTest"],
                allow_search_fallback=True,
            )
            stored = json.loads(config.read_text(encoding="utf-8"))

        self.assertEqual(payload["target_groups"], ["LabAgent", "AgentTest"])
        self.assertTrue(payload["allow_search_fallback"])
        self.assertEqual(stored["target_groups"], ["LabAgent", "AgentTest"])
        self.assertTrue(stored["allow_search_fallback"])
        self.assertTrue(stored["passive_poll_enabled"])
        self.assertEqual(stored["active_rescan_seconds"], 180.0)
        self.assertEqual(stored["auth_quarantine_seconds"], 300.0)
        self.assertEqual(stored["reconnect_stabilization_seconds"], 120.0)
        self.assertEqual(stored["composer_input_backend"], "xdotool")

    def test_gui_guide_and_first_contact_share_one_user_contract(self) -> None:
        bridge = load_gui_bridge()
        ingest = load_ingest()

        message = bridge.labagent_welcome_message()

        self.assertEqual(message, ingest.labagent_welcome_message())
        self.assertIn("请直接发送你想完成的任务", message)
        self.assertIn("#daily", message)
        self.assertIn("CAD/PCB", message)

    def test_gui_ocr_recovers_digit_bearing_scientific_identifier(self) -> None:
        bridge = load_gui_bridge()

        selected = bridge.choose_ocr_variant(
            "collal 帮我调研这个蛋白对肿瘤的影响",
            "collal 帮我调研这个蛋白对肿瘤的影响",
            "COL1A1",
        )

        self.assertEqual(selected, "COL1A1 帮我调研这个蛋白对肿瘤的影响")

    def test_gui_bubble_copy_is_exact_text_source(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.set_clipboard = mock.Mock()
        bridge.right_click = mock.Mock()
        bridge.key = mock.Mock()
        bridge.get_clipboard = mock.Mock(return_value="col1a1 是一个蛋白\r\n")
        window = module.Window("1", 0, 0, 1000, 650)
        bridge.find_window = mock.Mock(return_value=window)
        bridge.dismiss_transient_overlays = mock.Mock()

        with mock.patch.object(module.time, "sleep"):
            copied = bridge.copy_text_bubble(500, 300, probe_id="message-1")

        self.assertEqual(copied, "col1a1 是一个蛋白")
        bridge.right_click.assert_called_once_with(500, 300)
        self.assertEqual(
            bridge.key.call_args_list,
            [mock.call("Home"), mock.call("Return")],
        )
        bridge.dismiss_transient_overlays.assert_called_once_with(window)

    def test_gui_bubble_copy_dismisses_context_menu_after_failure(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.set_clipboard = mock.Mock()
        bridge.right_click = mock.Mock(side_effect=RuntimeError("copy failed"))
        bridge.key = mock.Mock()
        window = module.Window("1", 0, 0, 1000, 650)
        bridge.find_window = mock.Mock(return_value=window)
        bridge.dismiss_transient_overlays = mock.Mock()

        with mock.patch.object(module.time, "sleep"):
            copied = bridge.copy_text_bubble(500, 300, probe_id="message-1")

        self.assertEqual(copied, "")
        bridge.key.assert_not_called()
        bridge.dismiss_transient_overlays.assert_called_once_with(window)

    def test_gui_poll_forces_live_tail_before_reading(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.run_xdotool = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 800)

        with mock.patch.object(module.time, "sleep"):
            bridge.scroll_chat_to_bottom(window)

        command = bridge.run_xdotool.call_args.args[0]
        self.assertEqual(command[:3], ["mousemove", "720", "616"])
        self.assertEqual(command.count("5"), 24)

    def test_gui_visible_chat_keyboard_fallback_uses_relative_rows(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.pause = 0.0
        bridge.runtime_dir = Path("/tmp")
        bridge.capture_screen = mock.Mock(return_value=Path("/tmp/screen.png"))
        bridge.crop = mock.Mock(return_value=Path("/tmp/list.png"))
        bridge.selected_conversation_center_y = mock.Mock(return_value=207.0)
        bridge.find_ocr_line = mock.Mock(return_value={"center_x": 95.0, "center_y": 77.0})
        bridge.run_xdotool = mock.Mock()

        with mock.patch.object(module.time, "sleep"):
            changed = bridge.open_from_visible_list_keyboard(
                module.Window("1", 467, 215, 986, 650),
                "AgentTest",
                "LabAgent",
            )

        self.assertTrue(changed)
        command = bridge.run_xdotool.call_args.args[0]
        self.assertEqual(command[:5], ["mousemove", "651", "552", "click", "1"])
        self.assertEqual(command.count("Up"), 2)
        self.assertEqual(command[-3:], ["key", "--clearmodifiers", "Return"])

    def test_gui_selected_conversation_row_uses_blue_geometry_not_title_ocr(self) -> None:
        module = load_gui_bridge()
        if module.Image is None:
            self.skipTest("Pillow is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conversation-list.png"
            image = module.Image.new("RGB", (240, 320), (240, 243, 247))
            image.paste((51, 133, 243), (0, 110, 240, 176))
            image.save(path)
            bridge = object.__new__(module.WeComGuiBridge)

            center = bridge.selected_conversation_center_y(path)

        self.assertAlmostEqual(center, 142.5)

    def test_gui_clipboard_comparison_normalizes_windows_newlines(self) -> None:
        bridge = load_gui_bridge()

        self.assertEqual(
            bridge.canonical_clipboard_text("first\r\nsecond\x00"),
            "first\nsecond",
        )
        self.assertEqual(
            bridge.canonical_composer_text("first\n\n\n\nsecond"),
            bridge.canonical_composer_text("first\n\nsecond"),
        )

    def test_gui_filename_verifier_accepts_common_one_ell_ocr_confusion(self) -> None:
        bridge = load_gui_bridge()

        self.assertTrue(
            bridge.filename_matches_ocr(
                "col1a1_tumor_report_2026-07-19.pdf",
                "collal_tumor_report_2026-07-19.pdf",
            )
        )

    def test_gui_filename_verifier_accepts_wecom_truncated_attachment_label(self) -> None:
        bridge = load_gui_bridge()

        self.assertTrue(
            bridge.filename_matches_ocr(
                "organoid_cns_briefing_20260719.zh.pdf",
                "organoid_cns_...260719.zh.pdf 169.8KB",
            )
        )

    def test_gui_sender_display_name_produces_stable_private_member_id(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.event_root = Path(temporary)
            bridge.config = {"account_id": "external-gui"}

            first_path = bridge.build_event(
                "LabAgent",
                ["first interest #daily"],
                "image-a",
                sender_label="陈苗 @ WeChat",
                sender_fingerprint="a" * 64,
                sender_confidence="visual_fingerprint",
            )
            second_path = bridge.build_event(
                "LabAgent",
                ["second interest #daily"],
                "image-b",
                sender_label="陈盏@wechat",
                sender_fingerprint="a" * 64,
                sender_confidence="visual_fingerprint",
            )
            first = json.loads(first_path.read_text(encoding="utf-8"))
            second = json.loads(second_path.read_text(encoding="utf-8"))

        self.assertEqual(first["sender_userid"], second["sender_userid"])
        self.assertEqual(first["sender_display"], "陈苗@WeChat")
        self.assertEqual(first["sender_identity_confidence"], "visual_fingerprint")

    def test_gui_poll_checkpoints_ingest_before_uncertain_ack_send(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_db = root / "state.sqlite"
            module.init_state_db(state_db)
            crop = root / "crop.png"
            crop.write_bytes(b"stable-crop")
            screen = root / "screen.png"
            screen.write_bytes(b"screen")
            event_path = root / "events" / "event-one" / "event.json"
            event_path.parent.mkdir(parents=True)
            event_path.write_text("{}", encoding="utf-8")
            records = [
                {
                    "text": "old request",
                    "sender_label": "member",
                    "sender_fingerprint": "a" * 64,
                    "sender_confidence": "visual_fingerprint",
                },
                {
                    "text": "new daily request #daily",
                    "sender_label": "member",
                    "sender_fingerprint": "a" * 64,
                    "sender_confidence": "visual_fingerprint",
                },
            ]
            module.save_snapshot(state_db, "LabAgent", ["old request"], "old-hash")

            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            window = module.Window("1", 0, 0, 1000, 800)
            bridge.ensure_chat = mock.Mock(return_value=window)
            bridge.scroll_chat_to_bottom = mock.Mock()
            bridge.capture_screen = mock.Mock(return_value=screen)
            bridge.extract_inbound_records = mock.Mock(return_value=(records, crop))
            bridge.build_event = mock.Mock(return_value=event_path)
            bridge.invoke_ingest = mock.Mock(
                return_value={"ok": True, "queued": True, "reply": "registered once"}
            )
            bridge.send_text_locked = mock.Mock(side_effect=RuntimeError("uncertain send"))

            with self.assertRaisesRegex(RuntimeError, "uncertain send"):
                bridge.poll_chat("LabAgent")
            checkpoint = module.load_snapshot(state_db, "LabAgent")
            bridge.send_text_locked = mock.Mock()
            second = bridge.poll_chat("LabAgent")

        self.assertEqual(checkpoint[0], ["old request", "new daily request #daily"])
        self.assertEqual(bridge.invoke_ingest.call_count, 1)
        self.assertEqual(second["processed"], 0)
        bridge.send_text_locked.assert_not_called()

    def test_gui_text_delivery_is_not_recorded_when_send_is_unverified(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.pause = 0.0
            bridge.ensure_chat = mock.Mock()
            bridge.find_window = mock.Mock(return_value=module.Window("1", 0, 0, 1000, 800))
            bridge.click = mock.Mock()
            bridge.key = mock.Mock()
            bridge.composer_keys = mock.Mock()
            bridge.set_clipboard = mock.Mock()
            bridge.capture_screen = mock.Mock(return_value=Path(temporary) / "screen.png")
            bridge.composer_text_matches = mock.Mock(return_value=True)
            bridge.composer_is_empty = mock.Mock(return_value=False)

            with mock.patch.object(module, "remember_delivery") as remember:
                with self.assertRaisesRegex(RuntimeError, "did not clear"):
                    bridge.send_text_locked("LabAgent", "hello", task_id="task-1")

        remember.assert_not_called()
        self.assertIn(mock.call(mock.ANY, "alt+s"), bridge.composer_keys.call_args_list)

    def test_gui_text_delivery_restores_composer_focus_after_clipboard_write(self) -> None:
        module = load_gui_bridge()
        events: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.pause = 0.0
            bridge.close_staging_file_managers = mock.Mock()
            bridge.terminate_staging_file_manager_processes = mock.Mock()
            bridge.ensure_chat = mock.Mock()
            bridge.find_window = mock.Mock(return_value=module.Window("1", 0, 0, 1000, 800))
            bridge.composer_keys = mock.Mock(
                side_effect=lambda _window, *values: events.append(f"composer:{','.join(values)}")
            )
            bridge.set_clipboard = mock.Mock(side_effect=lambda _value: events.append("clipboard"))
            bridge.capture_screen = mock.Mock(return_value=Path(temporary) / "screen.png")
            bridge.composer_text_matches = mock.Mock(return_value=False)
            bridge.clear_composer = mock.Mock()

            with self.assertRaisesRegex(RuntimeError, "COMPOSE_UNVERIFIED"):
                bridge.send_text_locked("LabAgent", "hello", task_id="task-1")

        self.assertEqual(
            events[:2],
            ["clipboard", "composer:ctrl+a,ctrl+v"],
        )

    def test_gui_file_delivery_uses_verified_native_picker(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.pdf"
            source.write_bytes(b"report")
            staging_dir = root / "staging"
            staging_dir.mkdir()
            staged = staging_dir / source.name
            staged.write_bytes(source.read_bytes())
            state_db = root / "state.sqlite"
            module.init_state_db(state_db)

            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.pause = 0.0
            window = module.Window("1", 0, 0, 1000, 800)
            bridge.ensure_chat = mock.Mock(return_value=window)
            bridge.find_window = mock.Mock(return_value=window)
            bridge.validate_send_file = mock.Mock(return_value=source)
            bridge.capture_screen = mock.Mock(return_value=root / "screen.png")
            bridge.read_chat_history_text = mock.Mock(return_value="")
            bridge.stage_send_file = mock.Mock(return_value=(staged, staging_dir))
            bridge.composer_contains_filename = mock.Mock(return_value=True)
            bridge.compose_staged_file_with_picker = mock.Mock(
                return_value=root / "picker-selected.png"
            )
            bridge.composer_keys = mock.Mock()
            bridge.click = mock.Mock()
            bridge.wait_for_file_in_history = mock.Mock(return_value=root / "sent.png")

            with mock.patch.object(module, "delivery_done", return_value=False), mock.patch.object(
                module, "remember_delivery"
            ) as remember, mock.patch.object(module, "set_runtime"):
                payload = bridge.send_files_locked("LabAgent", [source], task_id="task-1")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sent_files"], [str(source)])
        bridge.compose_staged_file_with_picker.assert_called_once_with(
            window,
            staged,
            staging_dir,
            mock.ANY,
        )
        self.assertEqual(bridge.ensure_chat.call_count, 2)
        bridge.composer_keys.assert_called_once_with(window, "alt+s")
        remember.assert_called_once()

    def test_gui_file_delivery_never_sends_when_picker_composition_is_unverified(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.pdf"
            source.write_bytes(b"report")
            staging_dir = root / "staging"
            staging_dir.mkdir()
            staged = staging_dir / source.name
            staged.write_bytes(source.read_bytes())
            state_db = root / "state.sqlite"
            module.init_state_db(state_db)

            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.pause = 0.0
            window = module.Window("1", 0, 0, 1000, 800)
            bridge.ensure_chat = mock.Mock(return_value=window)
            bridge.find_window = mock.Mock(return_value=window)
            bridge.validate_send_file = mock.Mock(return_value=source)
            bridge.capture_screen = mock.Mock(return_value=root / "screen.png")
            bridge.read_chat_history_text = mock.Mock(return_value="")
            bridge.stage_send_file = mock.Mock(return_value=(staged, staging_dir))
            bridge.composer_contains_filename = mock.Mock(return_value=False)
            bridge.compose_staged_file_with_picker = mock.Mock(
                return_value=root / "picker-selected.png"
            )
            bridge.composer_keys = mock.Mock()
            bridge.click = mock.Mock()

            with mock.patch.object(module, "delivery_done", return_value=False), mock.patch.object(
                module, "remember_delivery"
            ) as remember:
                payload = bridge.send_files_locked("LabAgent", [source], task_id="task-1")

        self.assertFalse(payload["ok"])
        self.assertIn("COMPOSE_UNVERIFIED", payload["errors"][0]["error"])
        bridge.click.assert_not_called()
        remember.assert_not_called()

    def test_gui_mixed_delivery_sends_files_before_blocked_text_during_device_warning(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {"allow_verified_file_send_during_device_warning": True}
        bridge.target_groups = ["LabAgent"]
        bridge.serialized_gui = mock.MagicMock()
        bridge.security_pause_state = mock.Mock(
            return_value={"auth_blocker": "device_environment_abnormal"}
        )
        report = Path("report.pdf")
        bridge.send_files_locked = mock.Mock(
            return_value={
                "ok": True,
                "sent_messages": [],
                "sent_files": [str(report)],
                "errors": [],
            }
        )
        bridge.send_text_locked = mock.Mock()
        bridge.quarantine_from_send_result = mock.Mock()

        payload = bridge.send("LabAgent", "summary", [report], task_id="task-1")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["sent_files"], [str(report)])
        self.assertIn("WECOM_GUI_AUTH_REQUIRED", payload["errors"][0]["error"])
        bridge.send_files_locked.assert_called_once_with("LabAgent", [report], task_id="task-1")
        bridge.send_text_locked.assert_not_called()

    def test_gui_file_history_wait_reports_late_auth_challenge(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.detect_auth_blocker = mock.Mock(return_value="security_verification_required")
        bridge.capture_screen = mock.Mock()
        bridge.read_chat_history_text = mock.Mock()
        window = module.Window("1", 0, 0, 1000, 800)

        with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 1.0]), mock.patch.object(
            module.time, "sleep"
        ), self.assertRaisesRegex(RuntimeError, "WECOM_GUI_AUTH_REQUIRED: security_verification_required"):
            bridge.wait_for_file_in_history(
                window,
                "report.pdf",
                before_text="",
                delivery_key="delivery-key",
            )

        bridge.capture_screen.assert_not_called()
        bridge.read_chat_history_text.assert_not_called()

    def test_gui_file_history_can_verify_during_device_warning(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {"allow_verified_file_send_during_device_warning": True}
        bridge.detect_auth_blocker = mock.Mock(return_value="device_environment_abnormal")
        bridge.capture_screen = mock.Mock(return_value=Path("sent.png"))
        bridge.read_chat_history_text = mock.Mock(return_value="daily_report_")
        window = module.Window("1", 0, 0, 1000, 800)

        with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 1.0]), mock.patch.object(
            module.time, "sleep"
        ):
            evidence = bridge.wait_for_file_in_history(
                window,
                "daily_report_2026.pdf",
                before_text="",
                delivery_key="delivery-key",
            )

        self.assertEqual(evidence, Path("sent.png"))

    def test_gui_composer_keys_uses_x11_input_by_default(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {}
        bridge.click = mock.Mock()
        bridge.run_win32_input = mock.Mock()
        bridge.run_xdotool = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 800)

        bridge.composer_keys(window, "ctrl+a", "ctrl+v")

        bridge.click.assert_called_once_with(500, 896)
        bridge.run_win32_input.assert_not_called()
        bridge.run_xdotool.assert_called_once_with(
            ["key", "--clearmodifiers", "ctrl+a", "ctrl+v"]
        )

    def test_gui_composer_native_sendinput_requires_explicit_opt_in(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {"composer_input_backend": "native"}
        bridge.click = mock.Mock()
        bridge.run_win32_input = mock.Mock()
        bridge.run_xdotool = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 800)

        bridge.composer_keys(window, "ctrl+a", "ctrl+v")

        self.assertEqual(
            bridge.run_win32_input.call_args_list,
            [mock.call("--clear"), mock.call("--paste")],
        )
        bridge.run_xdotool.assert_not_called()

    def test_gui_composer_keys_keeps_xdotool_fallback_for_unmapped_keys(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {}
        bridge.click = mock.Mock()
        bridge.run_win32_input = mock.Mock()
        bridge.run_xdotool = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 800)

        bridge.composer_keys(window, "ctrl+z")

        bridge.run_win32_input.assert_not_called()
        bridge.run_xdotool.assert_called_once_with(
            ["key", "--clearmodifiers", "ctrl+z"]
        )

    def test_gui_click_uses_x11_input_only(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.run_xdotool = mock.Mock()

        bridge.click(640, 480)

        bridge.run_xdotool.assert_called_once_with(
            ["mousemove", "640", "480", "click", "1"]
        )

    def test_gui_file_picker_navigates_selects_and_stages_exact_file(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging_dir = root / "staging"
            staging_dir.mkdir()
            staged = staging_dir / "report.pdf"
            staged.write_bytes(b"report")
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.pause = 0.0
            bridge.runtime_dir = root
            picker = module.Window("2", 467, 215, 660, 490)
            bridge.find_file_picker = mock.Mock(side_effect=[None, picker, None])
            bridge.wait_for_file_picker = mock.Mock(return_value=picker)
            bridge.windows_path = mock.Mock(return_value=r"C:\\labcanvas_wecom_send\\key")
            bridge.set_clipboard = mock.Mock()
            bridge.run_xdotool = mock.Mock()
            bridge.run_win32_click = mock.Mock()
            bridge.click = mock.Mock()
            bridge.capture_screen = mock.Mock(return_value=root / "picker.png")
            bridge.picker_contains_filename = mock.Mock(return_value=True)
            bridge.picker_filename_field_matches = mock.Mock(return_value=True)
            bridge.close_window = mock.Mock()
            wecom = module.Window("1", 467, 215, 986, 650)

            with mock.patch.object(module.time, "sleep"):
                evidence = bridge.compose_staged_file_with_picker(
                    wecom,
                    staged,
                    staging_dir,
                    "delivery-key",
                )

        self.assertEqual(evidence, root / "picker.png")
        bridge.set_clipboard.assert_called_once_with(r"C:\\labcanvas_wecom_send\\key")
        bridge.run_xdotool.assert_called_once_with(
            ["key", "--clearmodifiers", "ctrl+a", "ctrl+v", "Return"]
        )
        bridge.run_win32_click.assert_called_once_with(1030, 733)
        self.assertEqual(
            bridge.click.call_args_list,
            [
                mock.call(1065, 764),
                mock.call(1244, 766),
                mock.call(836, 660),
                mock.call(704, 278),
                mock.call(1028, 685),
            ],
        )
        bridge.close_window.assert_not_called()

    def test_gui_file_picker_requires_exact_selected_filename_readback(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.pause = 0.0
        bridge.set_clipboard = mock.Mock()
        bridge.click = mock.Mock()
        bridge.run_xdotool = mock.Mock()
        bridge.get_clipboard = mock.Mock(return_value=r"C:\\staging\\report.pdf")
        picker = module.Window("2", 467, 215, 660, 490)

        self.assertTrue(
            bridge.picker_filename_field_matches(
                picker,
                "report.pdf",
                "delivery-key",
            )
        )
        bridge.get_clipboard.return_value = r"C:\\staging\\nearby-report.pdf"
        self.assertFalse(
            bridge.picker_filename_field_matches(
                picker,
                "report.pdf",
                "delivery-key",
            )
        )

    def test_gui_file_picker_fails_closed_before_selecting_wrong_file(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging_dir = root / "staging"
            staging_dir.mkdir()
            staged = staging_dir / "report.pdf"
            staged.write_bytes(b"report")
            picker = module.Window("2", 467, 215, 660, 490)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.pause = 0.0
            bridge.find_file_picker = mock.Mock(side_effect=[None, picker])
            bridge.wait_for_file_picker = mock.Mock(return_value=picker)
            bridge.windows_path = mock.Mock(return_value=r"C:\\staging")
            bridge.set_clipboard = mock.Mock()
            bridge.run_xdotool = mock.Mock()
            bridge.run_win32_click = mock.Mock()
            bridge.click = mock.Mock()
            bridge.picker_contains_filename = mock.Mock(return_value=False)
            bridge.close_window = mock.Mock()

            with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 16.0]), mock.patch.object(
                module.time, "sleep"
            ), self.assertRaisesRegex(RuntimeError, "PICKER_UNVERIFIED"):
                bridge.compose_staged_file_with_picker(
                    module.Window("1", 467, 215, 986, 650),
                    staged,
                    staging_dir,
                    "delivery-key",
                )

        bridge.close_window.assert_called_once_with("2")

    def test_gui_file_picker_accepts_generic_and_document_titles(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        picker = module.Window("2", 467, 215, 660, 490)
        bridge.find_named_window = mock.Mock(side_effect=[None, picker])

        self.assertEqual(bridge.find_file_picker(), picker)
        self.assertEqual(
            bridge.find_named_window.call_args_list,
            [mock.call("Select file/folder"), mock.call("Select file")],
        )

    def test_gui_native_click_recovers_all_stale_wecom_modals(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.pause = 0.0
        bridge.gui_env = mock.Mock(return_value={"DISPLAY": ":92"})
        outcomes = [
            SimpleNamespace(returncode=4, stderr=b"disabled"),
            SimpleNamespace(returncode=0, stderr=b""),
            SimpleNamespace(returncode=0, stderr=b""),
        ]

        with mock.patch.object(module, "ensure_win32_input_helper"), mock.patch.object(
            module.subprocess, "run", side_effect=outcomes
        ) as run, mock.patch.object(module.time, "sleep"):
            bridge.run_win32_click(1030, 733)

        commands = [call.args[0][2:] for call in run.call_args_list]
        self.assertEqual(
            commands,
            [
                ["--click", "1030", "733"],
                ["--close-stale-modals"],
                ["--click", "1030", "733"],
            ],
        )

    def test_gui_poll_cleanup_closes_native_overlay_before_neutral_click(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.close_stale_native_overlays = mock.Mock()
        bridge.click = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 650)

        with mock.patch.object(module.time, "sleep"):
            bridge.dismiss_transient_overlays(window)

        bridge.close_stale_native_overlays.assert_called_once_with()
        bridge.click.assert_called_once_with(680, 252)

    def test_gui_auth_blocker_detects_abnormal_device_before_input(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.runtime_dir = Path(temporary)
            bridge.capture_screen = mock.Mock(return_value=Path(temporary) / "screen.png")
            bridge.crop = mock.Mock(return_value=Path(temporary) / "auth.png")
            bridge.ocr = mock.Mock(
                return_value="The current device environment is abnormal. Scan the QR code."
            )

            blocker = bridge.detect_auth_blocker(module.Window("1", 0, 0, 1000, 650))

        self.assertEqual(blocker, "device_environment_abnormal")

    def test_gui_auth_blocker_enters_durable_input_quarantine(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {
                "auth_quarantine_seconds": 300,
                "allow_verified_file_send_during_device_warning": True,
            }
            bridge.target_groups = ["LabAgent"]
            bridge._client_was_visible = True
            bridge._active_scan_remaining = 2

            with mock.patch.object(module.time, "time", return_value=100.0):
                bridge.activate_auth_quarantine("device_environment_abnormal")
                state = bridge.security_pause_state()
                with self.assertRaisesRegex(RuntimeError, "WECOM_GUI_AUTH_REQUIRED"):
                    bridge.require_gui_input_allowed()
                bridge.require_gui_input_allowed("file")

            self.assertEqual(state["auth_blocker"], "device_environment_abnormal")
            self.assertEqual(state["security_cooldown_remaining_seconds"], 300)
            self.assertEqual(module.get_runtime(state_db, "chat_ready:LabAgent"), "0")
            self.assertFalse(bridge._client_was_visible)
            self.assertEqual(bridge._active_scan_remaining, 0)

    def test_gui_device_warning_file_fallback_is_opt_in(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {}

        self.assertTrue(
            bridge.blocker_prevents_operation("device_environment_abnormal", "file")
        )
        bridge.config["allow_verified_file_send_during_device_warning"] = True
        self.assertFalse(
            bridge.blocker_prevents_operation("device_environment_abnormal", "file")
        )
        self.assertTrue(
            bridge.blocker_prevents_operation("security_verification_required", "file")
        )

    def test_gui_passive_cycle_does_not_touch_unchanged_chat(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            module.set_runtime(state_db, "passive_screen_signature", "stable")
            module.set_runtime(state_db, "last_active_poll_epoch", "100")
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {"active_rescan_seconds": 180}
            bridge.target_groups = ["LabAgent"]
            bridge._client_was_visible = True
            bridge._active_scan_remaining = 0
            window = module.Window("1", 0, 0, 1000, 650)
            bridge.find_window = mock.Mock(return_value=window)
            bridge.serialized_gui = mock.MagicMock()
            bridge.capture_screen = mock.Mock(return_value=Path(temporary) / "screen.png")
            bridge.passive_screen_signature = mock.Mock(return_value="stable")
            bridge.poll_once = mock.Mock()

            with mock.patch.object(module.time, "time", return_value=200.0):
                payload = bridge.poll_cycle()

        self.assertEqual(payload["skipped"], "screen_unchanged")
        bridge.poll_once.assert_not_called()

    def test_gui_send_pacing_waits_locally_instead_of_retrying_gui(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            module.set_runtime(state_db, "last_gui_send_attempt_epoch", "95")
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {"send_min_interval_seconds": 12}

            with mock.patch.object(
                module.time,
                "time",
                side_effect=[100.0, 107.0, 107.0],
            ), mock.patch.object(module.time, "sleep") as sleep:
                bridge.pace_gui_send("text")

            self.assertEqual(
                module.runtime_float(state_db, "last_gui_send_attempt_epoch"),
                107.0,
            )

        sleep.assert_called_once_with(7.0)

    def test_gui_late_file_auth_error_quarantines_followup_sends(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {"auth_quarantine_seconds": 300}
            bridge.target_groups = ["LabAgent"]
            bridge._client_was_visible = True
            bridge._active_scan_remaining = 0

            with mock.patch.object(module.time, "time", return_value=100.0):
                bridge.quarantine_from_send_result(
                    {
                        "errors": [
                            {
                                "error": (
                                    "RuntimeError: WECOM_GUI_AUTH_REQUIRED: "
                                    "device_environment_abnormal"
                                )
                            }
                        ]
                    }
                )

            self.assertEqual(
                module.get_runtime(state_db, "auth_blocker"),
                "device_environment_abnormal",
            )
            self.assertEqual(module.get_runtime(state_db, "chat_ready:LabAgent"), "0")

    def test_gui_health_does_not_expose_allowlisted_chat_names(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.status = mock.Mock(
            return_value={
                "ok": True,
                "api_version": 1,
                "client_visible": True,
                "chat_ready": True,
                "closed_loop_state": "ready",
                "transport": "wecom_gui_only",
                "capabilities": {"text": True},
                "target_groups": ["Private Group"],
            }
        )

        payload = bridge.health()

        self.assertNotIn("target_groups", payload)
        self.assertEqual(payload["transport"], "wecom_gui_only")
        self.assertTrue(payload["chat_ready"])
        self.assertEqual(payload["closed_loop_state"], "ready")

    def test_gui_status_exposes_closed_loop_readiness_not_window_size_alone(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {"enabled": True, "local_api_port": 19580}
            bridge.display = ":92"
            bridge.target_groups = ["LabAgent"]
            bridge.find_window = mock.Mock(return_value=None)
            module.set_runtime(state_db, "chat_ready:LabAgent", "1")
            module.set_runtime(state_db, "last_error", "")

            logged_out = bridge.status()
            bridge.find_window.return_value = module.Window("1", 0, 0, 1000, 650)
            ready = bridge.status()
            module.set_runtime(state_db, "last_error", "title mismatch")
            module.set_runtime(state_db, "chat_ready:LabAgent", "0")
            pending = bridge.status()
            module.set_runtime(state_db, "auth_blocker", "device_environment_abnormal")
            blocked = bridge.status()

        self.assertEqual(logged_out["closed_loop_state"], "login_required")
        self.assertFalse(logged_out["chat_ready"])
        self.assertEqual(ready["closed_loop_state"], "ready")
        self.assertTrue(ready["chat_ready"])
        self.assertEqual(pending["closed_loop_state"], "chat_verification_pending")
        self.assertFalse(pending["chat_ready"])
        self.assertEqual(blocked["closed_loop_state"], "security_verification_required")
        self.assertFalse(blocked["chat_ready"])

    def test_gui_failed_chat_uses_bounded_backoff_without_blocking_other_chat(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.config = {
            "failure_backoff_seconds": 30,
            "max_failure_backoff_seconds": 300,
        }
        bridge.target_groups = ["LabAgent", "AgentTest"]
        bridge._poll_cursor = 0
        bridge._chat_failures = {}
        bridge._chat_retry_at = {}

        with mock.patch.object(module.time, "monotonic", return_value=100.0):
            self.assertEqual(bridge.next_due_chat(), "LabAgent")
            bridge.defer_failed_chat("LabAgent")
            self.assertEqual(bridge.next_due_chat(), "AgentTest")
            self.assertEqual(bridge._chat_retry_at["LabAgent"], 130.0)

        with mock.patch.object(module.time, "monotonic", return_value=131.0):
            self.assertEqual(bridge.next_due_chat(), "LabAgent")

    def test_gui_reconnect_recovery_requeues_only_bounded_wecom_outbox(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_db = root / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.config = {
                "recover_expired_on_reconnect": True,
                "reconnect_recovery_max_age_seconds": 7200,
                "reconnect_recovery_limit": 2,
            }
            bridge.queue = root / "queue.jsonl"
            bridge.state_db = state_db
            completed = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"ok": True, "recovered_count": 1}),
                stderr="",
            )

            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                payload = bridge.recover_expired_outbox()

        self.assertEqual(payload["recovered_count"], 1)
        command = run.call_args.args[0]
        self.assertTrue(command[1].endswith("wecom_reconnect_outbox.py"))
        self.assertIn("--max-age-seconds", command)
        self.assertIn("7200", command)
        self.assertIn("--limit", command)
        self.assertIn("2", command)

    def test_gui_reconnect_waits_for_exact_chat_poll_readiness(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge.config = {"reconnect_stabilization_seconds": 120}
            bridge.target_groups = ["LabAgent"]
            bridge._client_was_visible = False
            bridge.recover_expired_outbox = mock.Mock(
                return_value={"ok": True, "recovered_count": 1}
            )

            transition = bridge.recover_outbox_after_ready_poll(
                client_visible=True,
                poll_result={"ok": False, "error": "chat title not ready"},
            )
            module.set_runtime(state_db, "chat_ready:LabAgent", "1")
            with mock.patch.object(module.time, "time", return_value=100.0):
                stabilizing = bridge.recover_outbox_after_ready_poll(
                    client_visible=True,
                    poll_result={"ok": True, "processed": 0},
                )
            with mock.patch.object(module.time, "time", return_value=221.0):
                ready = bridge.recover_outbox_after_ready_poll(
                    client_visible=True,
                    poll_result={
                        "ok": True,
                        "skipped": "screen_unchanged",
                        "processed": 0,
                    },
                )
                repeated = bridge.recover_outbox_after_ready_poll(
                    client_visible=True,
                    poll_result={"ok": True, "processed": 0},
                )

            self.assertEqual(transition["skipped"], "chat_poll_not_ready")
            self.assertEqual(stabilizing["skipped"], "reconnect_stabilizing")
            self.assertEqual(ready["recovered_count"], 1)
            self.assertEqual(repeated["skipped"], "already_ready")
            bridge.recover_expired_outbox.assert_called_once_with()

    def test_gui_reconnect_readiness_rearms_after_client_disappears(self) -> None:
        module = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            state_db = Path(temporary) / "state.sqlite"
            module.init_state_db(state_db)
            bridge = object.__new__(module.WeComGuiBridge)
            bridge.state_db = state_db
            bridge._client_was_visible = True
            bridge.recover_expired_outbox = mock.Mock()

            payload = bridge.recover_outbox_after_ready_poll(
                client_visible=False,
                poll_result={"ok": False},
            )

            self.assertEqual(payload["skipped"], "client_not_visible")
            self.assertFalse(bridge._client_was_visible)
            bridge.recover_expired_outbox.assert_not_called()

    def test_gui_inbound_ledger_supports_cursor_reads(self) -> None:
        bridge = load_gui_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "state.sqlite"
            event = root / "events" / "event-001" / "event.json"
            event.parent.mkdir(parents=True)
            event.write_text("{}\n", encoding="utf-8")
            bridge.init_state_db(database)

            bridge.record_inbound_messages(
                database,
                "LabAgent",
                ["first question", "second question"],
                event,
                "image-hash",
            )
            bridge.mark_event_ingest(database, event, status="ingested")

            first = bridge.read_inbound_messages(database, "LabAgent", after=0, limit=1)
            second = bridge.read_inbound_messages(
                database,
                "LabAgent",
                after=first[0]["cursor"],
                limit=10,
            )

        self.assertEqual([item["text"] for item in first], ["first question"])
        self.assertEqual([item["text"] for item in second], ["second question"])
        self.assertEqual(first[0]["ingest_status"], "ingested")
        self.assertGreater(second[0]["cursor"], first[0]["cursor"])

    def test_gui_cli_send_accepts_files_without_text(self) -> None:
        wecom_ops = load_wecom_ops()
        completed = mock.Mock(returncode=0, stdout='{"ok": true}\n', stderr="")
        output = io.StringIO()
        with mock.patch.object(wecom_ops.subprocess, "run", return_value=completed) as run, redirect_stdout(output):
            returncode = wecom_ops.cmd_gui(
                SimpleNamespace(
                    action="send",
                    chat="LabAgent",
                    message="",
                    files=["output/report.pdf"],
                    after=0,
                    limit=100,
                    task_id="task-1",
                    live=True,
                    force=False,
                    json=True,
                )
            )

        self.assertEqual(returncode, 0)
        command = run.call_args.args[0]
        self.assertIn("--file", command)
        self.assertIn("output/report.pdf", command)
        self.assertIn("--live", command)

    def test_gui_cli_guide_uses_exact_group_and_live_gate(self) -> None:
        wecom_ops = load_wecom_ops()
        completed = mock.Mock(returncode=0, stdout='{"ok": true}\n', stderr="")
        output = io.StringIO()
        with mock.patch.object(wecom_ops.subprocess, "run", return_value=completed) as run, redirect_stdout(output):
            returncode = wecom_ops.cmd_gui(
                SimpleNamespace(
                    action="guide",
                    chat="AgentTest",
                    message="",
                    files=[],
                    after=0,
                    limit=100,
                    task_id="manual",
                    live=True,
                    force=False,
                    allow_search_fallback=None,
                    json=True,
                )
            )

        self.assertEqual(returncode, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[-5:], ["guide", "--chat", "AgentTest", "--live", "--json"])

    def test_gui_bridge_source_is_allowlisted_and_wecom_only(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_gui_bridge.py"
        ).read_text(encoding="utf-8")
        clipboard = (
            ROOT / "agentic_tools" / "wecom_agent" / "native" / "wecom_clipboard_utf8.c"
        ).read_text(encoding="utf-8")
        win32_input = (
            ROOT / "agentic_tools" / "wecom_agent" / "native" / "wecom_win32_input.c"
        ).read_text(encoding="utf-8")
        tmux_source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_tmux.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("target_groups", source)
        self.assertIn("/v1/chats", source)
        self.assertIn("/v1/messages", source)
        self.assertIn("/v1/send", source)
        self.assertIn("inbound_messages", source)
        self.assertIn("CF_UNICODETEXT", clipboard)
        self.assertIn('strcmp(argv[1], "--read")', clipboard)
        self.assertIn("composer_text_matches", source)
        self.assertIn("composer_is_empty", source)
        self.assertIn("compose_staged_file_with_picker", source)
        self.assertIn('"Select file/folder"', source)
        self.assertIn("wait_for_file_in_history", source)
        self.assertIn('strcmp(argv[1], "--click")', win32_input)
        self.assertIn('strcmp(argv[1], "--close-stale-modals")', win32_input)
        self.assertIn('L"SearchResultWindow2"', win32_input)
        self.assertIn('L"Start Group Chat"', win32_input)
        self.assertNotIn("WeCom remains disabled after closing", win32_input)
        self.assertNotIn("WM_DROPFILES", win32_input)
        self.assertNotIn('"--drag"', win32_input)
        self.assertIn("external-gui", tmux_source)
        self.assertIn("wecom-client", tmux_source)
        self.assertIn("supervise", tmux_source)
        self.assertIn("ensure_core_windows", tmux_source)
        self.assertIn("wecom_member_knowledge.py", tmux_source)
        self.assertIn("window_exists knowledge", tmux_source)
        self.assertIn("codex_quota_status.py", tmux_source)
        self.assertIn("window_exists quota", tmux_source)
        self.assertIn("health_guard_reload_needed", tmux_source)
        self.assertIn("HEALTH_GUARD_SIGNATURE", tmux_source)
        self.assertIn("android_bridge_reload_needed", tmux_source)
        self.assertIn("ANDROID_BRIDGE_SIGNATURE", tmux_source)
        self.assertIn("ANDROID_BRIDGE_RELOAD_STABLE_SECONDS", tmux_source)
        self.assertIn("android_bridge_source_is_stable", tmux_source)
        self.assertIn("android_bridge_outbound_active", tmux_source)
        self.assertIn("reload_android_window_if_idle", tmux_source)
        self.assertIn("wecom_android_outbound.active.json", tmux_source)
        self.assertIn('flock -n "$reload_fd"', tmux_source)
        self.assertIn("missing windows repaired", tmux_source)
        self.assertNotIn("xwechat_files", source)
        self.assertNotIn("wechat_gui_agent", source)

    def test_wecom_autostart_repairs_each_runtime_without_login_actions(self) -> None:
        scripts = ROOT / "agentic_tools" / "wecom_agent" / "scripts"
        autostart = (scripts / "wecom_autostart.sh").read_text(encoding="utf-8")
        installer = (scripts / "install_wecom_autostart.sh").read_text(encoding="utf-8")
        unit = (
            ROOT
            / "agentic_tools"
            / "wecom_agent"
            / "systemd"
            / "labcanvas-wecom-autostart.service.in"
        ).read_text(encoding="utf-8")
        tmux_source = (scripts / "wecom_tmux.sh").read_text(encoding="utf-8")

        self.assertIn('"$TMUX_SUPERVISOR" start', autostart)
        self.assertIn("WECOM_AUTOSTART_INTERVAL_SECONDS", autostart)
        self.assertIn("timeout --signal=TERM", autostart)
        self.assertNotIn("--switch-account", autostart)
        self.assertNotIn(" show_login_qr", autostart)
        self.assertIn("systemctl --user", installer)
        self.assertIn("enable --now", installer)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS", installer)
        self.assertIn("Restart=always", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn("KillMode=process", unit)
        self.assertIn("acquire_mutation_lock", tmux_source)
        self.assertIn("run_with_mutation_lock", tmux_source)
        self.assertIn("flock --close", tmux_source)
        self.assertIn("WECOM_TMUX_LOCK_HELD=1", tmux_source)
        self.assertNotIn('exec 9>"$MUTATION_LOCK"', tmux_source)
        self.assertIn("ensure_gui_client_window", tmux_source)
        self.assertIn("ensure_gui_windows", tmux_source)
        self.assertIn("if ! window_exists external-gui", tmux_source)
        self.assertIn("android_bridge_reload_needed", tmux_source)
        self.assertIn("ANDROID_BRIDGE_SIGNATURE", tmux_source)
        self.assertIn("reload_android_window_if_idle", tmux_source)
        self.assertIn("android_bridge_outbound_active", tmux_source)

    def test_wecom_autostart_docs_define_persisted_profile_boundary(self) -> None:
        readme = (
            ROOT / "agentic_tools" / "wecom_agent" / "README.md"
        ).read_text(encoding="utf-8")
        operations = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "docs"
            / "ROBUST_EFFICIENT_OPERATIONS.md"
        ).read_text(encoding="utf-8")

        self.assertIn("### Reboot and Crash Recovery", readme)
        self.assertIn("labcanvas-wecom-autostart.service", readme)
        self.assertIn("It does not\nswitch accounts", readme)
        self.assertIn("never enter account-switch/QR login", operations)


if __name__ == "__main__":
    unittest.main()

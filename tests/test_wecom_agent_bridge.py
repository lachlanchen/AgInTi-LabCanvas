from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
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
    return load_module(
        "wecom_ingest_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_ingest.py",
    )


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


class WeComAgentBridgeTests(unittest.TestCase):
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

    def test_wecom_worker_disables_personal_wechat_fallbacks(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_worker_loop.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("WECHAT_WORKER_DISABLE_GUI_FILE_DOWNLOAD=1", source)
        self.assertIn("WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT=1", source)
        self.assertIn("WECHAT_WORKER_ANDROID_TEXT_FALLBACK=0", source)
        self.assertIn("WECHAT_WORKER_DISABLE_AUTOPUBLISH_PREFLIGHT=1", source)

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
                attachments=[{"kind": "image", "filename": image.name, "path": str(image), "size_bytes": image.stat().st_size}],
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
        self.assertEqual(task["route"]["transport"], "wecom")
        self.assertEqual(task["transport_preflight"]["wecom_media"]["copied"][0]["task_copy_path"], str(image))
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

    def test_daily_directive_is_private_per_member_and_does_not_invoke_route_agent(self) -> None:
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

            daily = load_daily()
            topics = daily.active_topics(history, ingest.canonical_chat_name(event))

        self.assertFalse(result["queued"])
        self.assertIn("sparse event-camera reconstruction", result["reply"])
        self.assertEqual(topics, ["sparse event-camera reconstruction"])
        self.assertFalse(queue.exists())

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
        self.assertIn("compile a readable PDF", task["request"])

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


if __name__ == "__main__":
    unittest.main()

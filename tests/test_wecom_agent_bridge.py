from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sqlite3
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


def load_gui_bridge():
    return load_module(
        "wecom_gui_bridge_for_tests",
        ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_gui_bridge.py",
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
        self.assertIn('WECHAT_WORKER_CODEX_MODEL="${WECHAT_WORKER_CODEX_MODEL:-gpt-5.6-sol}"', source)
        self.assertIn('WECHAT_WORKER_MIN_EFFORT="${WECHAT_WORKER_MIN_EFFORT:-low}"', source)
        self.assertIn('WECHAT_WORKER_MAX_EFFORT="${WECHAT_WORKER_MAX_EFFORT:-ultra}"', source)
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
        self.assertEqual(tasks[0]["routine"]["id"], "research_summary")
        self.assertEqual(tasks[0]["routine"]["default_effort"], "high")
        self.assertNotIn("expires_at", tasks[0])

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
        self.assertIn("compile a readable PDF", task["request"])
        self.assertIn("Nature-style", task["request"])
        self.assertTrue(task["route_decision"]["no_fixed_deadline"])
        self.assertFalse(task["agent_backend_config"]["agent_fallbacks"]["fallback_on_timeout"])

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
        self.assertEqual(len({task["id"] for task in captured}), 2)

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
        self.assertIn("WECOM_CLIENT_LAYERED_NATIVE_GEOMETRY", source)
        self.assertIn("native geometry", source)
        self.assertIn("supervise_client", source)
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
        self.assertNotIn("vnc_lite.html", android_source)

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

    def test_gui_composer_keys_uses_native_sendinput_for_wine_composer(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
        bridge.click = mock.Mock()
        bridge.run_win32_input = mock.Mock()
        bridge.run_xdotool = mock.Mock()
        window = module.Window("1", 100, 200, 1000, 800)

        bridge.composer_keys(window, "ctrl+a", "ctrl+v")

        bridge.click.assert_called_once_with(500, 896)
        self.assertEqual(
            bridge.run_win32_input.call_args_list,
            [mock.call("--clear"), mock.call("--paste")],
        )
        bridge.run_xdotool.assert_not_called()

    def test_gui_composer_keys_keeps_xdotool_fallback_for_unmapped_keys(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
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
        bridge = object.__new__(module.WeComGuiBridge)
        bridge._client_was_visible = False
        bridge.recover_expired_outbox = mock.Mock(
            return_value={"ok": True, "recovered_count": 1}
        )

        transition = bridge.recover_outbox_after_ready_poll(
            client_visible=True,
            poll_result={"ok": False, "error": "chat title not ready"},
        )

        self.assertEqual(transition["skipped"], "chat_poll_not_ready")
        self.assertFalse(bridge._client_was_visible)
        bridge.recover_expired_outbox.assert_not_called()

        ready = bridge.recover_outbox_after_ready_poll(
            client_visible=True,
            poll_result={"ok": True, "processed": 0},
        )
        repeated = bridge.recover_outbox_after_ready_poll(
            client_visible=True,
            poll_result={"ok": True, "processed": 0},
        )

        self.assertEqual(ready["recovered_count"], 1)
        self.assertEqual(repeated["skipped"], "already_ready")
        bridge.recover_expired_outbox.assert_called_once_with()

    def test_gui_reconnect_readiness_rearms_after_client_disappears(self) -> None:
        module = load_gui_bridge()
        bridge = object.__new__(module.WeComGuiBridge)
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
        self.assertIn("missing windows repaired", tmux_source)
        self.assertNotIn("xwechat_files", source)
        self.assertNotIn("wechat_gui_agent", source)


if __name__ == "__main__":
    unittest.main()

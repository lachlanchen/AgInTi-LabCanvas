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


if __name__ == "__main__":
    unittest.main()

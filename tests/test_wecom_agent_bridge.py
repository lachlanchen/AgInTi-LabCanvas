from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


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
        self.assertEqual(result["reply"], route["response"])

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


if __name__ == "__main__":
    unittest.main()

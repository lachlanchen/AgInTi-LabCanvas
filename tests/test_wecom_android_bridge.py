from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_bridge.py"
)


def load_bridge():
    spec = importlib.util.spec_from_file_location("wecom_android_bridge_for_tests", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_worker():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_task_worker.py"
    spec = importlib.util.spec_from_file_location("wechat_task_worker_for_android_tests", path)
    assert spec and spec.loader
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ingest():
    path = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_ingest.py"
    scripts_dir = str(path.parent)
    shared_dir = str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts")
    for directory in (scripts_dir, shared_dir):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location("wecom_ingest_for_android_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeComAndroidBridgeTests(unittest.TestCase):
    def test_bounds_and_chat_title_are_exact(self) -> None:
        bridge = load_bridge()

        self.assertEqual(bridge.bounds_center("[10,20][110,220]"), (60, 120))
        self.assertTrue(bridge.chat_title_matches("LabAgent(6)", "LabAgent"))
        self.assertTrue(bridge.chat_title_matches("AgentTest", "AgentTest"))
        self.assertFalse(bridge.chat_title_matches("LabAgent archive(6)", "LabAgent"))

    def test_sequence_delta_preserves_repeated_new_message(self) -> None:
        bridge = load_bridge()

        delta, overlap = bridge.sequence_delta(["a", "b"], ["a", "b", "b"])

        self.assertEqual(overlap, 2)
        self.assertEqual(delta, ["b"])

    def test_file_confirmation_requires_exact_chat_file_and_send(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node text="">
              <node text="发送给：" package="com.tencent.wework" />
              <node text="AgentTest" package="com.tencent.wework" />
              <node text="[文件] mobile-transport-test.pdf (607K)" package="com.tencent.wework" />
              <node text="发送" package="com.tencent.wework" clickable="true" bounds="[1,1][2,2]" />
            </node></hierarchy>
            """
        )

        self.assertTrue(
            bridge.validate_file_confirmation(root, "AgentTest", "mobile-transport-test.pdf")
        )
        self.assertFalse(
            bridge.validate_file_confirmation(root, "LabAgent", "mobile-transport-test.pdf")
        )
        self.assertFalse(bridge.validate_file_confirmation(root, "AgentTest", "other.pdf"))

    def test_parse_messages_distinguishes_inbound_and_own_rows(self) -> None:
        bridge = load_bridge()
        xml = """
        <hierarchy><node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="sunnyyty" package="com.tencent.wework" />
            <node text="＠微信" package="com.tencent.wework" />
            <node text="请帮我查论文" resource-id="com.tencent.wework:id/j1l" package="com.tencent.wework" />
          </node>
          <node resource-id="com.tencent.wework:id/eyy" package="com.tencent.wework">
            <node text="报告已发送" resource-id="com.tencent.wework:id/j1l" package="com.tencent.wework" />
          </node>
        </node></hierarchy>
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "serial": "test",
                "target_groups": ["LabAgent"],
                "state_db": str(Path(tmp) / "state.sqlite"),
                "staging_dir": str(Path(tmp) / "staging"),
            }
            runtime = bridge.AndroidBridge(config)
            records = runtime.parse_messages(ET.fromstring(xml))

        self.assertEqual(records[0]["direction"], "inbound")
        self.assertEqual(records[0]["sender"], "sunnyyty")
        self.assertEqual(records[0]["mention_name"], "sunnyyty@微信")
        self.assertEqual(records[0]["body"], "请帮我查论文")
        self.assertEqual(records[1]["direction"], "outbound")

    def test_native_mention_contract_is_exact_and_non_broadcast(self) -> None:
        bridge = load_bridge()
        token = "@\ufff31688857361779939\ufff0"

        self.assertEqual(bridge.validate_mentions(["sunnyyty", "sunnyyty"]), ["sunnyyty"])
        self.assertEqual(bridge.mention_token_count(token + " 请查论文"), 1)
        self.assertEqual(bridge.mention_token_count("\ufff31688857361779939\ufff0 请查论文"), 1)
        self.assertTrue(
            bridge.composer_matches_message(token + " 请查论文", "请查论文", mention_count=1)
        )
        self.assertFalse(
            bridge.composer_matches_message(token + " 其他内容", "请查论文", mention_count=1)
        )
        placeholder = ET.fromstring('<node text="发消息或按住..." />')
        self.assertEqual(bridge.composer_text(placeholder), "")
        with self.assertRaises(bridge.BridgeError):
            bridge.validate_mentions(["所有人"])

    def test_exact_mention_rows_preserve_visible_case_and_spelling(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="sunnyyty@微信" resource-id="com.tencent.wework:id/ic1" package="com.tencent.wework" />
              <node text="Sunnyyty" resource-id="com.tencent.wework:id/ic1" package="com.tencent.wework" />
            </node></hierarchy>
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )

            matches = runtime.exact_mention_rows(root, "sunnyyty")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].attrib["text"], "sunnyyty@微信")

    def test_ingest_preserves_sender_name_as_reply_mention(self) -> None:
        ingest = load_ingest()
        event = {
            "chat_type": "group",
            "sender_display": "sunnyyty",
            "sender_mention": "sunnyyty@微信",
        }

        self.assertEqual(ingest.event_reply_mentions(event), ["sunnyyty@微信"])
        self.assertEqual(
            ingest.event_reply_mentions({"chat_type": "single", "sender_display": "sunnyyty"}),
            [],
        )

    def test_mobile_ingress_sends_prompt_ack_with_source_mention(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            records = [
                {"fingerprint": "old", "direction": "outbound", "sender": "", "body": "old"},
                {
                    "fingerprint": "new",
                    "direction": "inbound",
                    "sender": "sunnyyty",
                    "mention_name": "sunnyyty@微信",
                    "body": "请帮我查论文",
                },
            ]
            with mock.patch.object(runtime, "open_chat", return_value=ET.fromstring("<hierarchy />")), mock.patch.object(
                runtime, "parse_messages", return_value=records
            ), mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "save_snapshot"
            ) as save_snapshot, mock.patch.object(
                runtime, "invoke_ingest", return_value={"queued": True, "ack": "我会查证后回复。"}
            ), mock.patch.object(
                runtime,
                "send_text_locked",
                return_value={"sent_messages": ["我会查证后回复。"]},
            ) as send_text:
                result = runtime.snapshot("LabAgent", enqueue=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["replied"], 1)
        save_snapshot.assert_called_once_with("LabAgent", ["old", "new"])
        send_text.assert_called_once()
        self.assertEqual(send_text.call_args.kwargs["mentions"], ["sunnyyty@微信"])

    def test_config_is_private_and_redacts_token(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "android.local.json"
            result = bridge.initialize_config(
                path,
                ["LabAgent", "AgentTest"],
                serial="device-1",
                force=True,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertNotIn("local_api_token", result)
            self.assertTrue(payload["local_api_token"])
            self.assertEqual(payload["reconcile_seconds"], 20.0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_poll_cycle_reconciles_all_chats_without_unread_badges(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                    "reconcile_seconds": 20,
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime._next_reconcile_at = 0.0
            with mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(runtime, "unread_target_chats", return_value=[]), mock.patch.object(
                runtime,
                "snapshot",
                side_effect=lambda chat, enqueue: {
                    "ok": True,
                    "chat": chat,
                    "processed": 0,
                },
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertTrue(result["ok"])
        self.assertTrue(result["reconciliation"])
        self.assertEqual(result["unread_chats"], [])
        self.assertEqual(result["due_chats"], ["LabAgent", "AgentTest"])
        self.assertEqual(
            [call.args[0] for call in snapshot.call_args_list],
            ["LabAgent", "AgentTest"],
        )

    def test_poll_cycle_uses_unread_only_between_reconciliations(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            runtime._next_reconcile_at = time.monotonic() + 300
            with mock.patch.object(runtime, "load_snapshot", return_value=["old"]), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime, "unread_target_chats", return_value=["AgentTest"]
            ), mock.patch.object(
                runtime,
                "snapshot",
                return_value={"ok": True, "chat": "AgentTest", "processed": 1},
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertTrue(result["ok"])
        self.assertFalse(result["reconciliation"])
        self.assertEqual(result["due_chats"], ["AgentTest"])
        snapshot.assert_called_once_with("AgentTest", enqueue=True)

    def test_one_chat_failure_does_not_block_other_reconciliation(self) -> None:
        bridge = load_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent", "AgentTest"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            runtime.lock_path = Path(tmp) / "bridge.lock"
            with mock.patch.object(runtime, "load_snapshot", return_value=None), mock.patch.object(
                runtime, "open_chat_list", return_value=ET.fromstring("<hierarchy />")
            ), mock.patch.object(
                runtime,
                "snapshot",
                side_effect=[RuntimeError("first chat unavailable"), {"ok": True, "processed": 1}],
            ) as snapshot:
                result = runtime.poll_cycle()

        self.assertFalse(result["ok"])
        self.assertEqual(snapshot.call_count, 2)
        self.assertIn("first chat unavailable", result["results"][0]["error"])
        self.assertEqual(result["processed"], 1)

    def test_worker_prefers_healthy_mobile_send_endpoint(self) -> None:
        worker = load_worker()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "preferred_for_gui_send": True,
                        "local_api_port": 19581,
                        "local_api_token": "private-token",
                    }
                ),
                encoding="utf-8",
            )
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(
                {"ok": True, "device_authorized": True}
            ).encode("utf-8")
            with mock.patch.object(worker, "ROOT", root), mock.patch.object(
                worker.urllib.request, "urlopen", return_value=response
            ):
                endpoint = worker.ready_wecom_android_transport()

        self.assertEqual(endpoint, ("http://127.0.0.1:19581", "private-token"))

    def test_worker_mentions_exact_group_sender_only_on_android(self) -> None:
        worker = load_worker()
        task = {
            "source": {
                "wecom_chat_type": "group",
                "sender_display": "sunnyyty",
                "reply_mentions": ["sunnyyty"],
                "local_type": "text",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 19581}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root):
                android = worker.wecom_native_reply_mentions(task, "http://127.0.0.1:19581")
                desktop = worker.wecom_native_reply_mentions(task, "http://127.0.0.1:19580")

        self.assertEqual(android, ["sunnyyty"])
        self.assertEqual(desktop, [])

    def test_worker_delivery_payload_carries_native_reply_mention(self) -> None:
        worker = load_worker()
        task = {
            "id": "task-mention-1",
            "chat": "wecom:test:group:one",
            "source": {
                "transport": "wecom",
                "wecom_transport_channel": "wecom_android",
                "chat": "wecom:test:group:one",
                "wecom_chat_id": "gui:LabAgent",
                "wecom_chat_type": "group",
                "sender_display": "sunnyyty",
                "reply_mentions": ["sunnyyty"],
                "local_type": "text",
            },
        }
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "ok": True,
                "sent_messages": ["完成。"],
                "sent_files": [],
                "mentioned_users": ["sunnyyty"],
                "errors": [],
            }
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"local_api_port": 19581}), encoding="utf-8")
            with mock.patch.object(worker, "ROOT", root), mock.patch.object(
                worker, "wecom_transport_settings", return_value=("http://127.0.0.1:19581", "token")
            ), mock.patch.object(worker.urllib.request, "urlopen", return_value=response) as urlopen:
                worker.send_result_once_wecom(
                    {"message": "完成。", "confirmation": "", "files": []},
                    "wecom:test:group:one",
                    task,
                )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "gui:LabAgent")
        self.assertEqual(payload["mentions"], ["sunnyyty"])
        self.assertEqual(task["wecom_delivery"]["mentioned_users"], ["sunnyyty"])

    def test_setup_prevents_host_automount_password_dialog(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_setup.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("org.gnome.desktop.media-handling automount false", source)
        self.assertIn("org.gnome.desktop.media-handling automount-open false", source)

        bridge_source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"accelerometer_rotation", "0"', bridge_source)
        self.assertIn('"user_rotation", "0"', bridge_source)


if __name__ == "__main__":
    unittest.main()

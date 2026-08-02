from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_android_bridge.py"
)
INGEST_PATH = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_ingest.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location(
        "wecom_android_bridge_shipinhao_tests", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ingest():
    scripts_dir = str(INGEST_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "wecom_ingest_shipinhao_tests", INGEST_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.quota_warning_for_request = lambda _request: ""
    return module


class WeComShipinhaoCardTests(unittest.TestCase):
    def test_card_is_captured_as_exact_image_evidence(self) -> None:
        bridge = load_bridge()
        root = ET.fromstring(
            """
            <hierarchy><node>
              <node text="LabAgent(6)" resource-id="com.tencent.wework:id/n5i"
                    class="android.widget.TextView" package="com.tencent.wework" />
              <node resource-id="com.tencent.wework:id/eyy"
                    class="android.widget.RelativeLayout" package="com.tencent.wework"
                    bounds="[0,90][120,195]">
                <node resource-id="com.tencent.wework:id/ja3"
                      class="android.widget.ImageView" package="com.tencent.wework"
                      bounds="[2,92][14,104]" />
                <node text="陈苗" class="android.widget.TextView"
                      package="com.tencent.wework" bounds="[18,92][42,102]" />
                <node text="＠微信" class="android.widget.TextView"
                      package="com.tencent.wework" bounds="[44,92][66,102]" />
                <node resource-id="com.tencent.wework:id/og2"
                      class="android.widget.ImageView" package="com.tencent.wework"
                      bounds="[18,106][100,182]" />
                <node text="Nature channel" resource-id="com.tencent.wework:id/og3"
                      class="android.widget.TextView" package="com.tencent.wework"
                      bounds="[20,170][70,180]" />
              </node>
            </node></hierarchy>
            """
        )
        width, height = 120, 200
        rgba = bytearray(b"\xff\xff\xff\xff" * width * height)
        for y in range(106, 182):
            for x in range(18, 100):
                offset = (y * width + x) * 4
                rgba[offset : offset + 4] = bytes(
                    (x * 2 % 256, y % 256, (x + y) % 256, 255)
                )
        screenshot = bridge.RawScreenshot(width, height, bytes(rgba))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(tmp_path / "state.sqlite"),
                    "staging_dir": str(tmp_path / "staging"),
                }
            )
            record = runtime.parse_messages(root, screenshot=screenshot)[0]
            with (
                mock.patch.object(runtime, "open_chat", return_value=root),
                mock.patch.object(
                    runtime, "capture_raw_screenshot", return_value=screenshot
                ),
            ):
                materialized = runtime.materialize_shipinhao_card_record(
                    "LabAgent", record
                )
            event = runtime.build_event("LabAgent", materialized)

        self.assertEqual(record["direction"], "inbound")
        self.assertEqual(record["sender"], "陈苗")
        self.assertEqual(record["source_kind"], bridge.SHIPINHAO_CARD_KIND)
        self.assertIn("Nature channel", record["body"])
        self.assertTrue(record["image_visual_id"])
        self.assertEqual(event["msgtype"], bridge.SHIPINHAO_CARD_KIND)
        self.assertEqual(event["source_metadata"]["kind"], bridge.SHIPINHAO_CARD_KIND)
        self.assertEqual(event["attachments"][0]["kind"], bridge.IMAGE_KIND)
        self.assertEqual(
            event["attachments"][0]["capture_kind"],
            "wecom_android_exact_shipinhao_card_preview",
        )

    def test_card_request_requires_canonical_source_and_exact_paper(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / "card.png"
            preview.write_bytes(b"\x89PNG\r\n\x1a\npreview")
            event = {
                "msgtype": "shipinhao_card",
                "text": "视频号卡片\n<account>Nature channel</account>",
                "quote_text": "",
                "source_metadata": {
                    "kind": "shipinhao_card",
                    "title": "Nature channel",
                },
                "attachments": [
                    {
                        "kind": "image",
                        "filename": preview.name,
                        "path": str(preview),
                    }
                ],
            }
            request = ingest.event_request(event)
            preflight = ingest.wecom_transport_preflight(event)

        self.assertIn("canonical authoritative source", request)
        self.assertIn("distinguish a paper from a podcast", request)
        self.assertIn("label it as related", request)
        self.assertIn("Never substitute a merely topic-similar paper", request)
        self.assertIn(
            "verified lawful paper PDF",
            preflight["wecom_media"]["agent_next_action"],
        )

    def test_card_never_degrades_to_generic_file_intake(self) -> None:
        ingest = load_ingest()
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / "card.png"
            preview.write_bytes(b"\x89PNG\r\n\x1a\npreview")
            event = {
                "chat_id": "gui:LabAgent",
                "chat_name": "LabAgent",
                "chat_type": "group",
                "account_id": "external-gui",
                "message_id": "android:shipinhao-test",
                "sender_userid": "android-member:test",
                "sender_display": "Researcher",
                "create_time": 1,
                "msgtype": "shipinhao_card",
                "text": "视频号卡片",
                "quote_text": "",
                "attachments": [
                    {
                        "kind": "image",
                        "filename": preview.name,
                        "path": str(preview),
                    }
                ],
            }
            response = {
                "ok": True,
                "message": (
                    '{"worker_needed":true,"route_kind":"file_intake",'
                    '"response":"","task":"inspect it","ack":"",'
                    '"report_required":false,"message_role":"ordinary_chat",'
                    '"reply_mode":"ack_then_work","active_task_relation":"independent",'
                    '"reply_to_senders":[],"memory_items":[],"public_publish_allowed":false}'
                ),
            }
            with mock.patch.object(
                ingest, "run_agent_session", return_value=response
            ):
                route = ingest.route_event(event, ingest.event_request(event), [])
            fallback = ingest.fallback_route(event, ingest.event_request(event))

        self.assertEqual(route["route_kind"], "research_or_summary")
        self.assertEqual(route["message_role"], "research_request")
        self.assertTrue(route["worker_needed"])
        self.assertEqual(fallback["route_kind"], "research_or_summary")

    def test_history_scan_does_not_create_bounds_only_media_backlog(self) -> None:
        bridge = load_bridge()
        chat_root = ET.fromstring(
            '<hierarchy><node text="LabAgent(6)" '
            'resource-id="com.tencent.wework:id/n5i" '
            'package="com.tencent.wework" /></hierarchy>'
        )
        image_record = {
            "fingerprint": "bounds-only-image",
            "direction": "inbound",
            "source_kind": bridge.IMAGE_KIND,
            "body": "[图片]",
        }
        card_record = {
            "fingerprint": "bounds-only-card",
            "direction": "inbound",
            "source_kind": bridge.SHIPINHAO_CARD_KIND,
            "body": "视频号卡片",
            "image_bounds": "[10,20][70,90]",
            "image_visual_id": "exact-card-visual-id",
        }
        text_record = {
            "fingerprint": "exact-text",
            "direction": "inbound",
            "source_kind": "text",
            "body": "read this source",
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = bridge.AndroidBridge(
                {
                    "serial": "test",
                    "target_groups": ["LabAgent"],
                    "state_db": str(Path(tmp) / "state.sqlite"),
                    "staging_dir": str(Path(tmp) / "staging"),
                }
            )
            screenshot = bridge.RawScreenshot(
                100, 120, b"\xff\xff\xff\xff" * 100 * 120
            )
            with (
                mock.patch.object(runtime, "adb_shell"),
                mock.patch.object(runtime, "dump_hierarchy", return_value=chat_root),
                mock.patch.object(
                    runtime, "capture_raw_screenshot", return_value=screenshot
                ),
                mock.patch.object(
                    runtime,
                    "parse_messages",
                    return_value=[image_record, card_record, text_record],
                ),
                mock.patch.object(bridge.time, "sleep"),
            ):
                recovered = runtime.scan_older_message_records(
                    "LabAgent", [], max_pages=1
                )
            card_preview_exists = Path(recovered[0]["attachment_path"]).is_file()

        self.assertEqual(
            [record["fingerprint"] for record in recovered],
            ["bounds-only-card", "exact-text"],
        )
        self.assertTrue(card_preview_exists)
        self.assertEqual(
            recovered[0]["attachment_capture_kind"],
            "wecom_android_exact_shipinhao_card_history_preview",
        )


if __name__ == "__main__":
    unittest.main()

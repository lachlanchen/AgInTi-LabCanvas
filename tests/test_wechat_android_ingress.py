from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"


def load_script(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_bridge_installer():
    path = (
        ROOT
        / "agentic_tools"
        / "wechat_gui_agent"
        / "android"
        / "wechat_notification_bridge"
        / "install_bridge.py"
    )
    spec = importlib.util.spec_from_file_location("wechat_bridge_installer_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WechatAndroidIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ingress = load_script("wechat_android_ingress")

    def route(self) -> dict[str, object]:
        return {
            "config_id": "shares.local.json",
            "chat_name": "Shares",
            "message_table": "Msg_shares",
            "is_group": True,
            "aliases": ("Shares", "Shares鏈接"),
        }

    def event(self, *, sequence: int = 1, text: str = "Alice: useful link") -> dict[str, object]:
        return {
            "schema": "labcanvas-wechat-notification-v1",
            "kind": "notification_posted",
            "package": "com.tencent.mm",
            "sequence": sequence,
            "notification_key": "wechat|shares",
            "post_time_ms": 1_750_000_000_000 + sequence,
            "captured_at_ms": 1_750_000_000_000 + sequence,
            "title": "Shares鏈接 (3)",
            "text": text,
            "big_text": "",
            "text_lines": [],
            "messages": [],
        }

    def test_exact_title_maps_but_unrelated_title_does_not(self) -> None:
        route = self.route()
        self.assertEqual(
            self.ingress.match_route(self.event(), [route])["config_id"],
            "shares.local.json",
        )
        unrelated = self.event()
        unrelated["title"] = "Other group"
        self.assertIsNone(self.ingress.match_route(unrelated, [route]))

    def test_consecutive_messaging_style_items_keep_distinct_identity(self) -> None:
        event = self.event()
        event["messages"] = [
            {"sender": "Alice", "text": "first", "timestamp_ms": 101},
            {"sender": "Alice", "text": "second", "timestamp_ms": 102},
        ]
        items = self.ingress.notification_items(event)
        keys = [self.ingress.notification_item_key(event, item) for item in items]

        self.assertEqual([item["text"] for item in items], ["first", "second"])
        self.assertEqual(len(set(keys)), 2)

    def test_first_start_seeds_old_events_then_imports_only_new_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "message_999999.db"
            bridge = self.ingress.AndroidWechatIngress(
                adb="adb",
                serial="device",
                configs=[],
                targets={},
                db_path=db,
            )
            bridge.routes = [self.route()]
            with sqlite3.connect(db) as conn:
                self.ingress.ensure_message_table(conn, "Msg_shares")
            first = self.event(sequence=1, text="Alice: old")
            second = self.event(sequence=2, text="Alice: new")

            with mock.patch.object(self.ingress, "read_device_events", return_value=[first]):
                seeded = bridge.run_once()
            with mock.patch.object(self.ingress, "read_device_events", return_value=[first, second]):
                imported = bridge.run_once()

            self.assertEqual(seeded["seeded"], 1)
            self.assertEqual(seeded["imported"], 0)
            self.assertEqual(imported["imported"], 1)
            with sqlite3.connect(db) as conn:
                row = conn.execute(
                    "SELECT message_content FROM Msg_shares ORDER BY local_id"
                ).fetchone()
            self.assertEqual(row[0], "new")

    def test_repeated_event_is_idempotent_and_sender_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "message_999999.db"
            bridge = self.ingress.AndroidWechatIngress(
                adb="adb",
                serial="device",
                configs=[],
                targets={},
                db_path=db,
            )
            route = self.route()
            bridge.routes = [route]
            with sqlite3.connect(db) as conn:
                self.ingress.ensure_message_table(conn, "Msg_shares")
            bridge.set_meta("initialized", "1")
            event = self.event()

            with mock.patch.object(self.ingress, "read_device_events", return_value=[event]):
                first = bridge.run_once()
                second = bridge.run_once()

            self.assertEqual(first["imported"], 1)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["duplicates"], 1)
            with sqlite3.connect(db) as conn:
                sender, content = conn.execute(
                    "SELECT Name2Id.user_name, Msg_shares.message_content "
                    "FROM Msg_shares JOIN Name2Id ON Name2Id.rowid = Msg_shares.real_sender_id"
                ).fetchone()
            self.assertEqual((sender, content), ("Alice", "useful link"))

    def test_supplemental_android_shard_does_not_replace_desktop_active_shard(self) -> None:
        direct = load_script("wechat_direct_chatops")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "decrypted"
            message_dir = root / "message"
            message_dir.mkdir(parents=True)
            android_db = Path(tmp) / "android" / "message_999999.db"
            android_db.parent.mkdir()
            now = int(time.time())
            for path, rows in (
                (message_dir / "message_4.db", []),
                (android_db, [(1, "android-1", 1, 7, now, 3, "mobile text", None, 0)]),
            ):
                with sqlite3.connect(path) as conn:
                    conn.execute("CREATE TABLE Name2Id (user_name TEXT)")
                    conn.execute("INSERT INTO Name2Id(rowid,user_name) VALUES(7,'friend')")
                    conn.execute(
                        "CREATE TABLE Msg_test (local_id INTEGER, server_id TEXT, local_type INTEGER, "
                        "real_sender_id INTEGER, create_time INTEGER, status INTEGER, "
                        "message_content BLOB, compress_content BLOB, WCDB_CT_message_content INTEGER)"
                    )
                    if rows:
                        conn.executemany("INSERT INTO Msg_test VALUES(?,?,?,?,?,?,?,?,?)", rows)
            config = {"message_table": "Msg_test", "new_message_shard_max_age_seconds": 3600}
            state = {"active_message_db": "message_4.db", "message_db_cursors": {"message_4.db": 0}}

            with mock.patch.object(direct, "DECRYPTED", root), mock.patch.object(
                direct, "DEFAULT_ANDROID_INGRESS_DB", android_db
            ):
                rows = direct.read_new_messages(config, state)

            self.assertEqual([row["content"] for row in rows], ["mobile text"])
            self.assertEqual(rows[0]["_message_db"], "message_999999.db")
            self.assertEqual(state["active_message_db"], "message_4.db")

    def test_android_manifest_limits_capture_to_private_listener_service(self) -> None:
        manifest = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "android"
            / "wechat_notification_bridge"
            / "AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "android"
            / "wechat_notification_bridge"
            / "src"
            / "art"
            / "lazying"
            / "labcanvas"
            / "wechatbridge"
            / "WechatNotificationListener.java"
        ).read_text(encoding="utf-8")

        self.assertIn("BIND_NOTIFICATION_LISTENER_SERVICE", manifest)
        self.assertIn(".BootstrapReceiver", manifest)
        self.assertIn('WECHAT_PACKAGE = "com.tencent.mm"', source)
        self.assertIn("getFilesDir()", source)
        self.assertNotIn("INTERNET", manifest)

    def test_status_rejects_empty_successful_package_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.ingress.AndroidWechatIngress(
                adb="adb",
                serial="device",
                configs=[],
                targets={},
                db_path=Path(tmp) / "message_999999.db",
            )
            probes = [
                mock.Mock(returncode=0, stdout="", stderr=""),
                mock.Mock(returncode=0, stdout="null\n", stderr=""),
                mock.Mock(returncode=1, stdout="", stderr=""),
            ]

            with mock.patch.object(self.ingress.subprocess, "run", side_effect=probes):
                result = bridge.status()

            self.assertFalse(result["ok"])
            self.assertFalse(result["package_installed"])
            self.assertFalse(result["listener_enabled"])
            self.assertFalse(result["listener_live"])

    def test_status_requires_installed_package_and_enabled_listener(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.ingress.AndroidWechatIngress(
                adb="adb",
                serial="device",
                configs=[],
                targets={},
                db_path=Path(tmp) / "message_999999.db",
            )
            bridge.routes = [self.route()]
            probes = [
                mock.Mock(
                    returncode=0,
                    stdout="package:/data/app/bridge/base.apk\n",
                    stderr="",
                ),
                mock.Mock(
                    returncode=0,
                    stdout=(
                        "other/component:"
                        "art.lazying.labcanvas.wechatbridge/"
                        "art.lazying.labcanvas.wechatbridge.WechatNotificationListener\n"
                    ),
                    stderr="",
                ),
                mock.Mock(returncode=0, stdout="4321\n", stderr=""),
            ]

            with mock.patch.object(self.ingress.subprocess, "run", side_effect=probes):
                result = bridge.status()

            self.assertTrue(result["ok"])
            self.assertTrue(result["package_installed"])
            self.assertTrue(result["listener_enabled"])
            self.assertTrue(result["listener_live"])

    def test_miui_install_confirmation_requires_exact_app_identity(self) -> None:
        installer = load_bridge_installer()
        payload = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy>
  <node text='LabCanvas WeChat Bridge' package='com.miui.securitycenter' />
  <node text='Continue' resource-id='android:id/button2'
        class='android.widget.Button' package='com.miui.securitycenter'
        clickable='true' enabled='true' bounds='[80,1896][520,2036]' />
</hierarchy>"""

        self.assertEqual(
            installer.miui_continue_point(payload, "LabCanvas WeChat Bridge"),
            (300, 1966),
        )
        self.assertIsNone(installer.miui_continue_point(payload, "Different App"))

    def test_miui_install_confirmation_rejects_wrong_or_ambiguous_button(self) -> None:
        installer = load_bridge_installer()
        wrong_package = """<hierarchy>
  <node text='LabCanvas WeChat Bridge' />
  <node resource-id='android:id/button2' class='android.widget.Button'
        package='other.package' clickable='true' enabled='true'
        bounds='[80,1896][520,2036]' />
</hierarchy>"""
        duplicate = """<hierarchy>
  <node text='LabCanvas WeChat Bridge' />
  <node resource-id='android:id/button2' class='android.widget.Button'
        package='com.miui.securitycenter' clickable='true' enabled='true'
        bounds='[80,1896][520,2036]' />
  <node resource-id='android:id/button2' class='android.widget.Button'
        package='com.miui.securitycenter' clickable='true' enabled='true'
        bounds='[559,1896][1000,2036]' />
</hierarchy>"""

        self.assertIsNone(
            installer.miui_continue_point(wrong_package, "LabCanvas WeChat Bridge")
        )
        self.assertIsNone(
            installer.miui_continue_point(duplicate, "LabCanvas WeChat Bridge")
        )


if __name__ == "__main__":
    unittest.main()

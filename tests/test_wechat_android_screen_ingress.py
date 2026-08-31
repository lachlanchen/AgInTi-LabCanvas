from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"


def load_screen_ingress():
    for path in (SCRIPTS, ANDROID_SCRIPTS):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    source = SCRIPTS / "wechat_android_screen_ingress.py"
    spec = importlib.util.spec_from_file_location(
        "wechat_android_screen_ingress_for_tests", source
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WechatAndroidScreenIngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_screen_ingress()

    def route(self) -> dict[str, object]:
        return {
            "config_id": "shares.local.json",
            "chat_name": "Shares",
            "message_table": "Msg_shares",
            "is_group": True,
            "aliases": ("Shares", "Shares鏈接"),
            "target": {
                "name": "Shares鏈接",
                "expected_title": "Shares鏈接",
            },
            "self_wxid": "wxid-owner",
        }

    def scanner(self, root: Path):
        config = {
            "config_id": "shares.local.json",
            "chat_name": "Shares",
            "send_target": "Shares鏈接",
            "message_table": "Msg_shares",
            "chatroom_id": "group@chatroom",
            "self_wxid": "wxid-owner",
        }
        targets = {
            "Shares鏈接": {
                "name": "Shares鏈接",
                "expected_title": "Shares鏈接",
            }
        }
        return self.module.AndroidWechatScreenIngress(
            adb="adb",
            serial="device",
            configs=[config],
            targets=targets,
            db_path=root / "message_999999.db",
            send_state_db=root / "send.sqlite",
            output_dir=root / "output",
        )

    def test_green_bubble_detector_returns_only_message_sized_regions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screen.png"
            image = Image.new("RGB", (1080, 2160), (237, 237, 237))
            draw = ImageDraw.Draw(image)
            draw.rectangle((430, 500, 920, 710), fill=self.module.OUTGOING_GREEN)
            draw.rectangle((650, 780, 920, 870), fill=self.module.OUTGOING_GREEN)
            draw.rectangle((980, 2010, 1000, 2030), fill=self.module.OUTGOING_GREEN)
            image.save(path)

            regions = self.module.find_outgoing_bubbles(path)

            self.assertEqual(len(regions), 2)
            self.assertEqual(regions[0][:4], (430, 500, 921, 711))
            self.assertEqual(regions[1][:4], (650, 780, 921, 871))

    def test_visible_suffix_preserves_consecutive_and_repeated_messages(self) -> None:
        self.assertEqual(
            self.module.new_visible_messages(
                ["old one", "same"],
                ["same", "new one", "new two"],
            ),
            ["new one", "new two"],
        )
        self.assertEqual(
            self.module.new_visible_messages(["same"], ["same", "same"]),
            ["same"],
        )

    def test_unseeded_route_is_selected_before_visual_change_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            route = scanner.routes[0]

            selected = scanner.next_route({route["config_id"]: "row-a"})

            self.assertEqual(selected["config_id"], route["config_id"])
            self.assertFalse(scanner.all_routes_seeded())

    def test_deferred_bad_route_does_not_block_another_changed_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            first = scanner.routes[0]
            second = {
                **first,
                "config_id": "memo.local.json",
                "chat_name": "MEMO",
                "message_table": "Msg_memo",
                "aliases": ("MEMO",),
            }
            scanner.routes = [first, second]
            with sqlite3.connect(scanner.db_path) as conn:
                conn.execute(
                    "UPDATE AndroidScreenRoutes SET row_signature='old-a',initialized=1 "
                    "WHERE config_id=?",
                    (first["config_id"],),
                )
                conn.execute(
                    "INSERT INTO AndroidScreenRoutes(config_id,chat_name,row_signature,"
                    "snapshot_json,initialized,updated_at) VALUES(?,?,?,?,?,?)",
                    (
                        second["config_id"],
                        second["chat_name"],
                        "old-b",
                        "[]",
                        1,
                        self.module.utc_now(),
                    ),
                )

            scanner.defer_route(first["config_id"], "new-a")
            selected = scanner.next_route(
                {first["config_id"]: "new-a", second["config_id"]: "new-b"}
            )

            self.assertEqual(selected["config_id"], second["config_id"])
            self.assertEqual(scanner.deferred_route_count({first["config_id"]: "new-a"}), 1)

    def test_new_signature_bypasses_old_route_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            route = scanner.routes[0]
            scanner.defer_route(route["config_id"], "failed-signature")

            self.assertFalse(
                scanner.route_retry_deferred(route["config_id"], "new-signature")
            )

    def test_route_row_prefers_exact_title_over_message_preview(self) -> None:
        route = self.route()
        preview = self.module.OcrLine(
            text="please ask Shares about this",
            left=145,
            top=250,
            right=700,
            bottom=282,
        )
        exact = self.module.OcrLine(
            text="Shares鏈接",
            left=145,
            top=520,
            right=330,
            bottom=568,
        )

        rows = self.module.route_rows_from_lines(
            [preview, exact],
            [route],
            width=1080,
            height=2160,
        )

        self.assertIs(rows[route["config_id"]], exact)

    def test_screen_message_uses_owner_identity_and_existing_message_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            route = scanner.routes[0]

            inserted = scanner.insert_message(route, "full exact command", index=0)

            self.assertTrue(inserted)
            with sqlite3.connect(scanner.db_path) as conn:
                sender, content, status = conn.execute(
                    "SELECT Name2Id.user_name,Msg_shares.message_content,"
                    "AndroidIngressSeen.status FROM Msg_shares "
                    "JOIN Name2Id ON Name2Id.rowid=Msg_shares.real_sender_id "
                    "JOIN AndroidIngressSeen ON Msg_shares.server_id="
                    "'android-screen-' || substr(AndroidIngressSeen.item_key,1,32)"
                ).fetchone()
            self.assertEqual((sender, content, status), (
                "wxid-owner",
                "full exact command",
                "screen_imported",
            ))

    def test_verified_android_outbound_is_consumed_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scanner = self.scanner(root)
            route = scanner.routes[0]
            text = "agent response"
            digest = __import__("hashlib").sha256(text.encode()).hexdigest()
            with sqlite3.connect(scanner.send_state_db) as conn:
                conn.execute(
                    "CREATE TABLE components(component_key TEXT PRIMARY KEY,chat TEXT,"
                    "kind TEXT,value_hash TEXT,status TEXT,updated_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO components VALUES(?,?,?,?,?,?)",
                    ("component-1", "Shares鏈接", "text", digest, "sent", "2026-08-31T06:00:00"),
                )

            self.assertTrue(scanner.recorded_outbound_echo(route, text))
            self.assertFalse(scanner.recorded_outbound_echo(route, text))

    def test_copy_bubble_selects_all_before_copying_selected_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            sender = mock.Mock()
            first_menu = Path(tmp) / "first.png"
            selected_menu = Path(tmp) / "selected.png"
            sender.screenshot.side_effect = [first_menu, selected_menu]
            select_all = self.module.OcrLine("全选", 400, 800, 500, 860)
            copy = self.module.OcrLine("复制", 250, 800, 350, 860)
            with mock.patch.object(
                self.module,
                "serialized_android_clipboard",
                return_value=__import__("contextlib").nullcontext(),
            ), mock.patch.object(self.module, "set_x_clipboard"), mock.patch.object(
                self.module, "dark_menu_box", return_value=(200, 700, 800, 1000)
            ), mock.patch.object(
                self.module, "menu_action", return_value=select_all
            ) as menu_action, mock.patch.object(
                self.module, "copy_action", return_value=copy
            ), mock.patch.object(
                self.module, "get_x_clipboard", return_value="full exact message"
            ), mock.patch.object(self.module.time, "sleep"):
                result = scanner.copy_bubble(
                    sender,
                    (100, 200, 900, 500, 4000),
                    probe_id="selected",
                )

            self.assertEqual(result, "full exact message")
            menu_action.assert_called_once_with(
                first_menu,
                (200, 700, 800, 1000),
                self.module.SELECT_ALL_LABELS,
            )
            self.assertEqual(
                sender.tap.call_args_list,
                [
                    mock.call(select_all.center_x, select_all.center_y),
                    mock.call(copy.center_x, copy.center_y),
                ],
            )

    def test_busy_screen_reader_preempts_only_after_bounded_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            scanner.set_meta("last_success_at", datetime.now(timezone.utc).isoformat())
            with mock.patch.dict(
                self.module.os.environ,
                {"WECHAT_ANDROID_SCREEN_MAX_GAP": "30"},
            ):
                self.assertFalse(scanner.preemption_due())

            scanner.set_meta(
                "last_success_at",
                (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat(),
            )
            with mock.patch.dict(
                self.module.os.environ,
                {"WECHAT_ANDROID_SCREEN_MAX_GAP": "30"},
            ):
                self.assertTrue(scanner.preemption_due())

    def test_busy_screen_reader_catches_up_cooperatively_without_priority_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            navigator = mock.Mock()
            navigator.device_lock_path.return_value = Path(tmp) / "android.lock"
            scanner.set_meta(
                "last_success_at",
                (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat(),
            )
            with mock.patch.object(
                scanner, "sender_for", return_value=navigator
            ), mock.patch.object(
                self.module,
                "passive_android_control",
                side_effect=self.module.AndroidControlBusy("busy"),
            ), mock.patch.object(
                self.module,
                "cooperative_android_control",
                return_value=__import__("contextlib").nullcontext(),
            ) as cooperative, mock.patch.object(
                scanner, "run_with_restore", return_value={"ok": True}
            ):
                result = scanner.run_once()

            self.assertTrue(result["ok"])
            cooperative.assert_called_once()

    def test_status_rejects_fresh_poll_with_stale_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = self.scanner(Path(tmp))
            scanner.set_meta("last_poll_at", datetime.now(timezone.utc).isoformat())
            scanner.set_meta(
                "last_success_at",
                (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
            )

            status = scanner.status()

            self.assertFalse(status["ok"])
            self.assertTrue(status["catchup_overdue"])
            self.assertGreater(status["last_success_age_seconds"], 90)


if __name__ == "__main__":
    unittest.main()

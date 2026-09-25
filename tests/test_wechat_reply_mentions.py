import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))
mentions = importlib.import_module("wechat_reply_mentions")
profiles = importlib.import_module("wechat_chat_profiles")
native = importlib.import_module("wechat_tiny11_bridge")
receipts = importlib.import_module("wechat_native_text_delivery")


class ReplyMentionTests(unittest.TestCase):
    def test_multi_sender_header_keeps_spaces_and_mentions_each_person_once(self):
        names, body, text = mentions.mention_header("@Alice Smith @Bob @Alice Smith\n\nAnswer")
        self.assertEqual(names, ["Alice Smith", "Bob"])
        self.assertEqual(body, "Answer")
        self.assertEqual(text, "@Alice Smith @Bob\nAnswer")

    def test_body_references_and_broadcasts_are_never_native_mentions(self):
        for text in ("Answer mentioning @Alice", "@Alice inline answer", "@all\nAnswer",
                     "@everyone\nAnswer", "@Alice @all\nAnswer", "@Alice\n", "NO_REPLY"):
            self.assertEqual(mentions.mention_header(text), ([], text, text))

    def test_split_reply_keeps_part_marker_without_repeating_mentions(self):
        self.assertEqual(mentions.mention_header("[1/2]\n@Alice\nAnswer"),
                         (["Alice"], "[1/2]\nAnswer", "@Alice\n[1/2]\nAnswer"))
        text = "[2/2]\nThe rest of the answer"
        self.assertEqual(mentions.mention_header(text), ([], text, text))

    def test_rich_mention_padding_normalizes_only_header(self):
        text = "\u2005@Alice Smith\u2005\u2005@Bob\u2005\nAnswer  stays exact"
        self.assertEqual(mentions.mention_header(text),
                         (["Alice Smith", "Bob"], "Answer  stays exact",
                          "@Alice Smith @Bob\nAnswer  stays exact"))

    def test_native_readback_accepts_padding_not_changed_body_or_recipient(self):
        client = object.__new__(native.Tiny11WeChatBridge)
        expected = "@Alice Smith @Bob\nAnswer  stays exact"
        client.get_clipboard = mock.Mock(return_value=
            "\u2005@Alice Smith\u2005\u2005@Bob\u2005\r\nAnswer  stays exact")
        with mock.patch.object(native.Tiny11WeComGuiBridge, "composer_text_matches", return_value=False):
            self.assertTrue(client.composer_text_matches(mock.Mock(), expected, "test"))
            for wrong in ("@Alice Smith @Bob\nAnswer stays exact",
                          "@Alice Other @Bob\nAnswer  stays exact"):
                client.get_clipboard.return_value = wrong
                self.assertFalse(client.composer_text_matches(mock.Mock(), expected, "test"))

    def test_rich_native_echo_matches_pending_send_not_new_inbound(self):
        plain = "@Alice Smith @Bob\nAnswer  stays exact"
        rich = "\u2005@Alice Smith\u2005\u2005@Bob\u2005\r\nAnswer  stays exact"
        self.assertEqual(receipts.normalize_text(rich), plain)
        self.assertNotEqual(receipts.normalize_text(rich.replace("  stays", " stays")), plain)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"self_wxid": "owner", "chat_name": "Team",
                      "send_target": {"name": "Team", "query": "Team"},
                      "message_table": "Msg_" + "a" * 32}
            receipt = {"table": config["message_table"], "sender": "owner",
                       "after": {"message.db": 7}, "started_at": 100}
            receipts.retain_pending_receipt(receipts.pending_receipt_path(config["send_target"], plain, root), receipt)
            row = {"sender": "owner", "local_type": 1, "content": "owner:\n" + rich,
                   "local_id": 8, "create_time": 102, "_message_db": "message.db"}
            self.assertTrue(receipts.pending_outbound_echo(config, row, root))
            self.assertFalse(receipts.pending_outbound_echo(config, {**row, "sender": "someone_else"}, root))

    def test_profile_addresses_answered_members_not_everyone_or_quoted_authors(self):
        for title in ("Team", "Shares", "EchoMind", "LazyResearch"):
            policy = profiles.profile_for_chat(title)["reply_addressing"]
            self.assertIn("not just the last sender", policy)
            self.assertIn("quoted/forwarded authors who did not ask", policy)
            self.assertIn("exactly once", policy)
            self.assertIn("scheduled", policy)
        self.assertEqual(profiles.profile_for_chat("lachlanchan")["reply_addressing"],
                         "No group mentions in a DM.")

    def test_picker_requires_new_small_surface_above_composer(self):
        window = SimpleNamespace(x=0, y=0, width=900, height=900)
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "before.png", Path(tmp) / "after.png"
            before = Image.new("RGB", (900, 900), "white")
            before.save(a)
            before.save(b)
            self.assertIsNone(mentions.mention_picker_box(a, b, window, 226))
            after = before.copy()
            after.paste((160, 160, 160), (190, 650, 360, 750))
            after.save(b)
            self.assertEqual(mentions.mention_picker_box(a, b, window, 226), (230, 650, 130, 100))
            after.paste((100, 100, 100), (882, 540, 890, 750))
            after.save(b)
            self.assertEqual(mentions.mention_picker_box(a, b, window, 226), (230, 650, 130, 100))
            after.paste((100, 100, 100), (126, 400, 890, 750))
            after.save(b)
            self.assertIsNone(mentions.mention_picker_box(a, b, window, 226))

    def native_client(self, folder):
        client = object.__new__(native.Tiny11WeChatBridge)
        client.runtime_dir = Path(folder)
        for method in ("capture_screen", "set_clipboard", "key", "click", "clear_composer", "composer_keys"):
            setattr(client, method, mock.Mock())
        client.capture_screen.return_value = Path(folder) / "screen.png"
        client.crop = mock.Mock(return_value=Path(folder) / "picker.png")
        Image.new("RGB", (150, 100), "white").save(client.crop.return_value)
        client.composer_text_matches = mock.Mock(return_value=True)
        return client

    def test_exact_native_members_are_selected_once_before_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self.native_client(tmp)
            client.find_ocr_line = mock.Mock(side_effect=[
                {"text": "Alice Smith", "center_x": 50, "center_y": 20},
                {"text": "Bob", "center_x": 50, "center_y": 20},
            ])
            window = SimpleNamespace(x=0, y=0, width=900, height=900)
            with mock.patch.object(native, "mention_picker_box", return_value=(200, 600, 150, 100)), \
                    mock.patch.object(native.time, "sleep"):
                selected = client.compose_reply_mentions(window, ["Alice Smith", "Bob"], "Answer",
                                                        "@Alice Smith @Bob\nAnswer", "test")
            self.assertEqual(selected, ["Alice Smith", "Bob"])
            self.assertEqual(client.click.call_count, 2)
            self.assertTrue(all(call.kwargs["full_line_only"] for call in client.find_ocr_line.call_args_list))
            client.clear_composer.assert_not_called()
            client.set_clipboard.assert_called_with("\nAnswer")
            self.assertNotIn(mock.call("Return"), client.key.call_args_list)

    def test_transport_failure_is_not_swallowed_as_a_mention_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self.native_client(tmp)
            client.capture_screen.side_effect = RuntimeError("transport disconnected")
            window = SimpleNamespace(x=0, y=0, width=900, height=900)
            with self.assertRaisesRegex(RuntimeError, "transport disconnected"):
                client.compose_reply_mentions(window, ["Alice"], "Answer", "@Alice\nAnswer", "test")
            client.clear_composer.assert_not_called()

    def test_nearby_member_is_not_tagged_and_plain_name_reply_can_still_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self.native_client(tmp)
            client.find_ocr_line = mock.Mock(return_value={"text": "Alice Other", "center_x": 50, "center_y": 20})
            window = SimpleNamespace(x=0, y=0, width=900, height=900)
            with mock.patch.object(native, "mention_picker_box", return_value=(200, 600, 150, 100)), \
                    mock.patch.object(native.time, "sleep"):
                selected = client.compose_reply_mentions(window, ["Alice"], "Answer", "@Alice\nAnswer", "test")
            self.assertEqual(selected, [])
            client.clear_composer.assert_called_once_with(window)
            client.set_clipboard.assert_called_with("@Alice\nAnswer")
            self.assertEqual(client.click.call_count, 1)  # Close only the owned picker.
            self.assertNotIn(mock.call("Return"), client.key.call_args_list)


if __name__ == "__main__":
    unittest.main()

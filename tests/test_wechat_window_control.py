from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))
import wechat_window_control as control


class WeChatWindowControlTests(unittest.TestCase):
    def test_protected_main_and_invalid_ids_are_rejected_without_x_connection(self):
        self.assertEqual(control.request_close("0x10", display_name=":97",
            protected_window_ids={"16"})["status"], "protected_window")
        self.assertEqual(control.request_close("wrong", display_name=":97")["status"], "invalid_window")
        for value in ("0", "-1", "4294967296"):
            self.assertEqual(control.request_close(value, display_name=":97")["status"], "invalid_window")

    def test_graceful_request_never_destroys_client_window(self):
        try:
            import Xlib.display
        except ImportError:
            self.skipTest("optional python-xlib dependency")
        connection = mock.MagicMock()
        connection.intern_atom.side_effect = lambda name, **kw: {
            "_NET_WM_PID": 1, "WM_DELETE_WINDOW": 2, "WM_PROTOCOLS": 3}[name]
        window = connection.create_resource_object.return_value
        window.get_full_property.return_value = SimpleNamespace(value=[123])
        window.get_wm_protocols.return_value = [2]
        with mock.patch("Xlib.display.Display", return_value=connection), \
             mock.patch.object(Path, "stat", return_value=SimpleNamespace(st_uid=os.getuid())), \
             mock.patch.object(Path, "read_text", return_value="wechat\n"):
            result = control.request_close("20", display_name=":97", protected_window_ids={"16"})
        self.assertEqual(result["status"], "close_requested")
        event = window.send_event.call_args.args[0]
        self.assertEqual(event.client_type, 3)
        self.assertEqual(event.data[1][0], 2)
        window.destroy.assert_not_called()
        connection.close.assert_called_once()

    def test_missing_protocol_or_unrelated_owner_is_not_force_closed(self):
        try:
            import Xlib.display
        except ImportError:
            self.skipTest("optional python-xlib dependency")
        connection = mock.MagicMock()
        connection.intern_atom.return_value = 2
        window = connection.create_resource_object.return_value
        window.get_full_property.return_value = SimpleNamespace(value=[123])
        window.get_wm_protocols.return_value = []
        with mock.patch("Xlib.display.Display", return_value=connection), \
             mock.patch.object(Path, "stat", return_value=SimpleNamespace(st_uid=os.getuid())), \
             mock.patch.object(Path, "read_text", return_value="wechat") as read:
            self.assertEqual(control.request_close("20", display_name=":97")["status"], "close_protocol_unavailable")
            read.return_value = "firefox"
            self.assertEqual(control.request_close("20", display_name=":97")["status"], "not_wechat")
        window.send_event.assert_not_called()
        window.destroy.assert_not_called()


if __name__ == "__main__":
    unittest.main()

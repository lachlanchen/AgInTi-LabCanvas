from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wecom_agent" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

gui = importlib.import_module("wecom_tiny11_gui_bridge")
transport = importlib.import_module("wecom_tiny11_transport")
base = importlib.import_module("wecom_gui_bridge")


def config(**tiny11):
    return {
        "local_api_token": "test-token",
        "tiny11": {
            "ssh_host": "127.0.0.1",
            "ssh_port": 2290,
            "helper_port": 19582,
            "local_port": 19582,
            **tiny11,
        },
    }


class Tiny11WeComTransportTests(unittest.TestCase):
    def test_transport_is_localhost_only(self) -> None:
        client = transport.Tiny11Transport(config())

        self.assertEqual(client.helper_url, "http://127.0.0.1:19582")
        command = client.tunnel_command()
        self.assertIn("127.0.0.1:19582:127.0.0.1:19582", command)
        with self.assertRaisesRegex(transport.Tiny11TransportError, "localhost-only"):
            transport.Tiny11Transport(config(ssh_host="192.0.2.10"))

    def test_transport_requires_private_token(self) -> None:
        with self.assertRaisesRegex(transport.Tiny11TransportError, "token is missing"):
            transport.Tiny11Transport({"tiny11": {"ssh_host": "127.0.0.1"}})

    def test_stage_file_verifies_remote_size_and_sha256(self) -> None:
        client = transport.Tiny11Transport(config())
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "report.pdf"
            source.write_bytes(b"verified artifact")
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            verification = json.dumps({"size": source.stat().st_size, "sha256": expected})
            with mock.patch.object(
                client,
                "powershell",
                side_effect=["", verification],
            ), mock.patch.object(client, "scp_to_guest") as upload:
                remote = client.stage_file(source, "task:one")

        self.assertEqual(remote, r"C:\LabCanvas\WeComBridge\inbox\task_one\report.pdf")
        upload.assert_called_once_with(source.resolve(), remote)

    def test_remove_staged_file_is_confined_to_transport_inbox(self) -> None:
        client = transport.Tiny11Transport(config())
        remote = r"C:\LabCanvas\WeComBridge\inbox\task_one\report.pdf"
        with mock.patch.object(client, "powershell") as powershell:
            client.remove_staged_file(remote)

        self.assertIn(
            r"C:\LabCanvas\WeComBridge\inbox\task_one",
            powershell.call_args.args[0],
        )
        with self.assertRaisesRegex(transport.Tiny11TransportError, "outside"):
            client.remove_staged_file(r"C:\Users\lachlan\Documents\report.pdf")

    def test_native_layout_keeps_fixed_sidebar_when_fullscreen_or_restored(self) -> None:
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        fullscreen = base.Window("full", -2, -2, 1284, 756)
        restored = base.Window("restored", 200, 51, 880, 650)

        self.assertEqual(bridge.content_left(fullscreen), 304)
        self.assertEqual(bridge.content_left(restored), 506)
        self.assertEqual(bridge.conversation_list_box(fullscreen), (60, 48, 244, 698))
        self.assertEqual(bridge.conversation_list_box(restored), (262, 101, 244, 592))

    def test_single_file_clipboard_scalar_is_normalized_as_one_path(self) -> None:
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        source = Path("/tmp/report.pdf")
        remote = r"C:\LabCanvas\WeComBridge\inbox\task\report.pdf"
        bridge.remote_staged_files = {str(source.resolve()): remote}
        bridge.tiny11 = mock.Mock()
        bridge.tiny11.invoke.return_value = remote

        observed = bridge.set_file_clipboard([source])

        self.assertEqual(observed, [remote])

    def test_filename_verifier_tolerates_one_repeated_digit_lost_by_ocr(self) -> None:
        self.assertTrue(
            base.filename_matches_ocr(
                "tiny11-transport-check.txt",
                "tiny 1-transport-check.txt 132B",
            )
        )

    def test_windows_helper_preserves_current_window_geometry(self) -> None:
        source = (
            ROOT / "agentic_tools" / "wecom_agent" / "windows" / "WeComBridge.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("ShowWindow($window.Handle, 5)", source)
        self.assertIn('http://127.0.0.1:$Port/', source)
        self.assertNotIn('http://+:$Port/', source)

    def test_windows_screenshots_do_not_include_adjacent_wechat_monitor(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        self.assertIn('[System.Windows.Forms.Screen]::PrimaryScreen.Bounds', source)
        self.assertNotIn('[System.Windows.Forms.SystemInformation]::VirtualScreen', source)
        self.assertIn('refusing cross-app capture', source)


if __name__ == "__main__":
    unittest.main()

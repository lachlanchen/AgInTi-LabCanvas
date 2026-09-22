from __future__ import annotations

import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError


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
    def test_helper_http_error_retains_login_reason_without_token(self):
        client = transport.Tiny11Transport(config(app='wechat'))
        for operation in (lambda: client.invoke({'action': 'restore'}), client.screenshot):
            body = io.BytesIO(json.dumps({'error': 'WECHAT_ENTRY_REQUIRED: test-token'}).encode())
            exc = HTTPError(client.helper_url, 500, 'error', {}, body)
            with mock.patch.object(transport.request, 'urlopen', side_effect=exc):
                with self.assertRaises(transport.Tiny11TransportError) as caught:
                    operation()
            self.assertIn('HTTP 500: WECHAT_ENTRY_REQUIRED', str(caught.exception))
            self.assertNotIn('test-token', str(caught.exception))
            self.assertTrue(body.closed)

    def test_helper_non_json_error_does_not_expose_proxy_body(self):
        client = transport.Tiny11Transport(config())
        for content in (b'<html>private proxy diagnostics</html>', b'["private"]', b'{"error":42}'):
            exc = HTTPError(client.helper_url, 403, 'Forbidden', {}, io.BytesIO(content))
            with mock.patch.object(transport.request, 'urlopen', side_effect=exc):
                self.assertEqual(client.health(), {'ok': False, 'error': 'Tiny11 helper HTTP 403'})

    def test_logged_out_client_does_not_restart_responding_helper(self):
        client = transport.Tiny11Transport(config(app='wechat'))
        for state in ({'ok': False, 'app': 'wechat', 'session_id': 1},
                      {'ok': False, 'helper_ready': True, 'app': 'wechat', 'client_state': 'entry_required'}):
            with mock.patch.object(client, 'health', return_value=state), \
                    mock.patch.object(client, 'powershell') as start:
                self.assertTrue(client.helper_ready())
                client.start_helper_if_needed()
                start.assert_not_called()

    def test_missing_helper_still_can_be_restarted(self):
        client = transport.Tiny11Transport(config())
        with mock.patch.object(client, 'health', return_value={'ok': False, 'error': 'connection refused'}), \
                mock.patch.object(client, 'powershell') as start:
            client.start_helper_if_needed()
            start.assert_called_once()

    def test_native_login_detection_is_personal_read_only_and_checks_hidden_main_first(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        detector = source.split('function Get-PersonalWeChatState {', 1)[1].split('function Test-NativeWebForeground', 1)[0]
        self.assertLess(detector.index("return 'window_hidden'"), detector.index("return 'entry_required'"))
        self.assertIn('$_.Height -gt $_.Width', detector)
        for forbidden in ('SendWait', 'SetForegroundWindow', 'Start-Process', 'Stop-Process'):
            self.assertNotIn(forbidden, detector)
        restore = source.split("{ $_ -in @('restore', 'activate') }", 1)[1].split('"click"', 1)[0]
        self.assertLess(restore.index('WECHAT_ENTRY_REQUIRED'), restore.index('SendWait'))

    def test_system_dialog_blocks_input_before_focus_and_remains_visible_in_health(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        focus = source.split('function Focus-WeCom {', 1)[1].split('function Invoke-Key {', 1)[0]
        self.assertLess(focus.index('Get-SystemInputBlocker'), focus.index('SetForegroundWindow'))
        self.assertIn('LABCANVAS_GUI_SYSTEM_DIALOG_BLOCKED', focus)
        self.assertIn("$process.Path -ieq $expected", source)
        self.assertIn('input_blocker = $inputBlocker', source)

    def test_personal_focus_recovery_uses_one_native_hotkey_and_rechecks(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        focus = source.split('function Focus-WeCom {', 1)[1].split('function Invoke-Key {', 1)[0]
        self.assertIn("$script:TargetApp -eq 'wechat' -and [LabCanvasWin32]::GetForegroundWindow() -ne $window.Handle", focus)
        self.assertEqual(focus.count("SendWait('^%w')"), 1)
        self.assertLess(focus.index('Get-SystemInputBlocker'), focus.index("SendWait('^%w')"))
        self.assertLess(focus.index("SendWait('^%w')"), focus.index('could not receive focus'))
        for forbidden in ('Stop-Process', 'Start-Process', 'Remove-Item', 'AttachThreadInput'):
            self.assertNotIn(forbidden, focus)

    def test_system_dialog_health_overrides_cached_chat_ready(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.tiny11 = mock.Mock()
        bridge.tiny11.health.return_value = {'ok': True, 'input_blocker': 'windows_system_dialog'}
        with mock.patch.object(base.WeComGuiBridge, 'status', return_value={
            'ok': True, 'chat_ready': True, 'closed_loop_state': 'ready', 'capabilities': {}}):
            state = bridge.status()
            self.assertFalse(state['chat_ready'])
            self.assertEqual(state['closed_loop_state'], 'system_dialog_blocked')
            self.assertFalse(bridge.health()['ok'])

    def test_system_dialog_poll_pauses_without_input_and_recovers_normally(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.state_db = Path('unused')
        bridge.tiny11 = mock.Mock()
        bridge.tiny11.health.return_value = {'ok': True, 'input_blocker': 'windows_system_dialog'}
        with mock.patch.object(gui, 'set_runtime'), \
                mock.patch.object(base.WeComGuiBridge, 'poll_cycle', return_value={'ok': True}) as poll:
            self.assertEqual(bridge.poll_cycle()['skipped'], 'system_dialog_blocked')
            poll.assert_not_called()
            bridge.tiny11.health.return_value = {'ok': True, 'input_blocker': ''}
            self.assertTrue(bridge.poll_cycle()['ok'])
            poll.assert_called_once()

    def test_web_runtime_repair_is_explicit_and_preserves_chat_clients(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Repair-WeChatWebRuntime.ps1').read_text()
        self.assertIn('[switch]$Apply', source)
        self.assertIn('$Apply -and $renderers.Count -ge $MinimumRendererCount', source)
        self.assertIn("$_.ParentProcessId -in $personal.ProcessId", source)
        self.assertIn("\\Tencent\\xwechat\\xplugin\\plugins\\RadiumWMPF\\", source)
        self.assertIn('$current.CreationDate -ne $root.CreationDate', source)
        self.assertIn('taskkill.exe /PID $($root.ProcessId) /T /F', source)
        self.assertIn("throw 'Old web runtime processes remain.'", source)
        self.assertIn("throw 'Client process changed.'", source)
        for forbidden in ('/IM', 'Restart-Computer', 'Remove-Item', 'Start-Process'):
            self.assertNotIn(forbidden, source)

    def test_native_player_focus_requires_app_path_session_and_live_ancestry(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        guard = source.split('function Test-NativeWebForeground {', 1)[1].split('function Focus-WeCom {', 1)[0]
        self.assertIn("$child.Name -ne 'WeChatAppEx.exe'", guard)
        self.assertIn('$child.ExecutablePath -notlike $pathPattern', guard)
        self.assertIn('$parent.CreationDate -gt $child.CreationDate', guard)
        self.assertIn('$parent.SessionId -ne $child.SessionId', guard)
        self.assertIn('$parent.ProcessId -eq $Window.ProcessId', guard)
        self.assertIn('$depth -lt 8', guard)
        self.assertIn('-not (Test-NativeWebForeground $foregroundProcessId $window)', source)

    def test_each_request_scopes_one_app_with_legacy_default(self):
        self.assertEqual(transport.Tiny11Transport(config()).app, 'wecom')
        client = transport.Tiny11Transport(config(app='wechat'))
        with mock.patch.object(client, '_json_request', return_value={'ok': True}) as call:
            client.health()
            self.assertEqual(call.call_args.args[0].get_header('X-labcanvas-app'), 'wechat')
            client.invoke({'action': 'get_clipboard'})
            self.assertEqual(call.call_args.args[0].get_header('X-labcanvas-app'), 'wechat')
        with self.assertRaises(transport.Tiny11TransportError):
            transport.Tiny11Transport(config(app='desktop'))

    def test_native_history_includes_tail_and_composer_excludes_history(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.runtime_dir = Path("/tmp/test-wecom-runtime")
        bridge.crop = mock.Mock(return_value=Path("/tmp/crop.png"))
        bridge.ocr_scaled = mock.Mock(return_value="")
        for height in (800, 1392):
            with self.subTest(height=height):
                window = base.Window("1", 30, 50, 1276, height)
                left, top, width, span = bridge.history_surface(window)
                self.assertEqual(top + span, window.y + height - 160)
                bridge.read_chat_history_text(Path("screen.png"), window, "tail")
                self.assertEqual(bridge.crop.call_args.args[1], (left, top, width, span))
                bridge.composer_contains_filename(Path("screen.png"), window, "report.pdf", "key")
                composer = bridge.crop.call_args.args[1]
                self.assertGreater(composer[1], top + span)
                self.assertLessEqual(composer[1] + composer[3], window.y + height)

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

    def test_browser_repair_only_installs_missing_edge_with_explicit_switch(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Repair-Tiny11Browser.ps1').read_text()
        self.assertIn('if ($InstallMissingEdge -and', source)
        self.assertIn("$_.prog_id -and $_.prog_id -ne 'MSEdgeHTM'", source)
        self.assertIn('install --id Microsoft.Edge --exact --source winget --silent', source)
        for forbidden in ('--ignore-security-hash', '--allow-reboot', 'Restart-Computer',
                          'Stop-Process', 'Set-ItemProperty', 'Remove-ItemProperty'):
            self.assertNotIn(forbidden, source)

    def test_browser_probe_uses_shell_resolution_and_verifies_executable(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Repair-Tiny11Browser.ps1').read_text()
        self.assertIn('AssocQueryString(0x1000, 2, scheme, "open"', source)
        self.assertIn("foreach ($scheme in @('http', 'https'))", source)
        self.assertIn('Test-Path -LiteralPath $exe -PathType Leaf', source)
        self.assertIn("$env:COMPUTERNAME -ne $ExpectedComputer", source)

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

    def test_live_tail_scroll_does_not_click_a_message_card(self) -> None:
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.tiny11 = mock.Mock()
        window = base.Window("shared", 100, 200, 1276, 1392)
        with mock.patch.object(gui.time, "sleep"):
            bridge.scroll_chat_to_bottom(window)
        bridge.tiny11.invoke.assert_called_once_with({
            "action": "macro",
            "actions": [{"action": "wheel", "x": 891, "y": 923, "delta": -720}] * 4,
        })

    def test_already_open_chat_check_does_not_click_to_dismiss_an_absent_menu(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.target_groups = ["LabAgent"]
        window = base.Window("shared", 0, 0, 1276, 1392)
        bridge.find_window = mock.Mock(return_value=window)
        bridge.detect_auth_blocker = mock.Mock(return_value="")
        bridge.current_title_matches = mock.Mock(return_value=True)
        bridge.tiny11 = mock.Mock()

        self.assertEqual(bridge.ensure_chat("LabAgent"), window)
        bridge.tiny11.invoke.assert_not_called()

    def test_menu_cleanup_only_follows_our_right_click_and_uses_title_bar(self):
        for macro in (False, True):
            with self.subTest(macro=macro):
                bridge = object.__new__(gui.Tiny11WeComGuiBridge)
                bridge.tiny11 = mock.Mock()
                window = base.Window("shared", 100, 200, 1276, 1392)
                if macro:
                    bridge.run_xdotool(["mousemove", "500", "400", "click", "3"])
                else:
                    bridge.right_click(500, 400)
                self.assertTrue(bridge._context_menu_cleanup_pending)
                bridge.tiny11.invoke.reset_mock()
                with mock.patch.object(gui.time, "sleep"):
                    bridge.dismiss_transient_overlays(window)
                    bridge.dismiss_transient_overlays(window)
                bridge.tiny11.invoke.assert_called_once_with({
                    "action": "click", "x": 840, "y": 238,
                })
                self.assertFalse(bridge._context_menu_cleanup_pending)

    def test_uncertain_menu_action_and_failed_cleanup_preserve_pending_state(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.tiny11 = mock.Mock()
        bridge.tiny11.invoke.side_effect = transport.Tiny11TransportError("timeout")
        with self.assertRaises(transport.Tiny11TransportError):
            bridge.right_click(500, 400)
        self.assertTrue(bridge._context_menu_cleanup_pending)
        with self.assertRaises(transport.Tiny11TransportError):
            bridge.dismiss_transient_overlays(base.Window("shared", 0, 0, 1276, 1392))
        self.assertTrue(bridge._context_menu_cleanup_pending)

    def test_auth_warning_prevents_pending_menu_cleanup_when_ensuring_chat(self):
        bridge = object.__new__(gui.Tiny11WeComGuiBridge)
        bridge.target_groups = ["LabAgent"]
        bridge._context_menu_cleanup_pending = True
        bridge.find_window = mock.Mock(return_value=base.Window("shared", 0, 0, 1276, 1392))
        bridge.detect_auth_blocker = mock.Mock(return_value="device_environment_abnormal")
        bridge.tiny11 = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "WECOM_GUI_AUTH_REQUIRED"):
            bridge.ensure_chat("LabAgent")
        bridge.tiny11.invoke.assert_not_called()
        self.assertTrue(bridge._context_menu_cleanup_pending)

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

        self.assertNotIn("ShowWindow($window.Handle", source)
        self.assertIn('http://127.0.0.1:$Port/', source)
        self.assertNotIn('http://+:$Port/', source)

    def test_focused_wecom_and_owned_dialogs_do_not_get_refocused(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        focus = source.split('function Focus-WeCom {', 1)[1].split('function Invoke-Key {', 1)[0]
        self.assertIn('$foreground = [LabCanvasWin32]::GetForegroundWindow()', focus)
        self.assertIn('$foreground -ne $window.Handle -and', focus)
        self.assertIn('GetAncestor($foreground, 3) -ne $window.Handle', focus)
        self.assertIn('refusing input into another app', focus)
        screenshot = source.split('function Write-ScreenshotResponse {', 1)[1].split('$listener =', 1)[0]
        self.assertNotIn('Focus-WeCom', screenshot)
        self.assertNotIn('SetForegroundWindow', screenshot)

    def test_windows_screenshots_do_not_include_adjacent_wechat_monitor(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        self.assertIn('[System.Windows.Forms.Screen]::PrimaryScreen.Bounds', source)
        self.assertNotIn('[System.Windows.Forms.SystemInformation]::VirtualScreen', source)
        self.assertIn('refusing cross-app capture', source)

    def test_shared_desktop_capture_masks_everything_except_wecom(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        self.assertIn('$graphics.Clear([System.Drawing.Color]::Black)', source)
        self.assertIn('[System.Drawing.Rectangle]::Intersect($bounds,$rect)', source)
        self.assertIn('$region.IntersectsWith($otherRect)', source)
        self.assertIn('No visible WeCom window; refusing desktop capture.', source)
        self.assertNotIn('CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)', source)

    def test_shared_desktop_layout_is_explicit_and_keeps_dual_mode(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Set-Tiny11AppScreens.ps1').read_text()
        self.assertIn("[ValidateSet('Dual', 'Shared')][string]$Layout = 'Dual'", source)
        self.assertIn("Processes = @('WXWork'); Side = 0", source)
        self.assertIn("Processes = @('WeChat', 'Weixin'); Side = 1", source)
        self.assertIn('$primary.Bounds.Width -lt 2000', source)
        self.assertIn('if ($seen.ContainsKey($key)) { continue }', source)
        self.assertNotIn('Stop-Process', source)
        self.assertNotIn('Restart-Computer', source)

    def test_window_placement_and_capture_exclude_wecom_shadow(self) -> None:
        folder = ROOT / 'agentic_tools/wecom_agent/windows'
        for name in ('WeComBridge.ps1', 'Set-Tiny11AppScreens.ps1'):
            with self.subTest(name=name):
                source = (folder / name).read_text()
                self.assertIn("@('PerryShadowWnd', 'TitleBarWindow')", source)

    def test_logged_in_layout_does_not_reposition_wecom_settings_and_popups(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Set-Tiny11AppScreens.ps1').read_text()
        self.assertIn('Select-AppPlacementWindows -AppName $app.Name', source)
        self.assertIn("$_.ClassName -eq 'WeWorkWindow'", source)
        self.assertIn('if ($main.Count -gt 0) { return $main }', source)

    def test_display_mode_probe_is_read_only_and_session_scoped(self) -> None:
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Get-DesktopModes.ps1').read_text()
        self.assertIn('EnumDisplaySettings', source)
        self.assertIn('SessionId -eq 0', source)
        self.assertIn('Marshal]::SizeOf($mode)', source)
        self.assertNotIn('ChangeDisplaySettings', source)

    def test_persistent_helpers_use_native_value_snapshots_not_uia_providers(self):
        folder = ROOT / 'agentic_tools/wecom_agent/windows'
        for name in ('WeComBridge.ps1', 'Set-Tiny11AppScreens.ps1'):
            source = (folder / name).read_text()
            self.assertIn('NativeWindows.ps1', source)
            self.assertIn('NativeWindows]::Snapshot', source)
            self.assertNotIn('AutomationElement', source)
        source = (folder / 'Set-Tiny11AppScreens.ps1').read_text()
        self.assertIn('$seen.Remove($key)', source)
        self.assertIn('$env:COMPUTERNAME -ne $ExpectedComputer', source)

    def test_install_stages_shared_native_helper_before_restarting_task(self):
        client = transport.Tiny11Transport(config())
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            transport, 'PRIVATE', Path(directory)
        ), mock.patch.object(client, 'ensure_vm'), mock.patch.object(
            client, 'powershell'
        ) as powershell, mock.patch.object(client, 'scp_to_guest') as upload:
            client.install()
        self.assertIn(mock.call(transport.GUEST_HELPER.with_name('NativeWindows.ps1'),
                                client.remote_root + r'\NativeWindows.ps1'), upload.call_args_list)
        registration = powershell.call_args.args[0]
        self.assertIn('$userSid=$identity.User.Value', registration)
        self.assertIn('-UserId $userSid -LogonType Interactive', registration)
        self.assertIn('-AtLogOn -User $userSid', registration)
        self.assertNotIn('-UserId $identity.Name', registration)

    def test_session_probe_is_read_only_and_does_not_claim_app_policy_success(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Test-DesktopSession.ps1').read_text()
        self.assertIn('WTSGetActiveConsoleSessionId', source)
        self.assertIn('GetSystemMetrics(0x1000)', source)
        self.assertIn('GetSystemMetrics(0x2001)', source)
        self.assertIn('proves_wecom_warning_absent = $false', source)
        self.assertIn("if ($session -eq 0)", source)
        for mutation in ('SetCursorPos', 'SendInput', 'SendKeys', 'Stop-Process', 'Restart-Computer'):
            self.assertNotIn(mutation, source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'agentic_tools/wecom_agent/scripts'
sys.path.insert(0, str(SCRIPTS))
views = importlib.import_module('tiny11_display_views')


class SharedConsoleZoomTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the browser geometry unit test')
    def test_login_crop_tracks_shared_layout_without_guest_resize(self):
        module = (SCRIPTS.parent / 'web/tiny11-console.mjs').as_uri()
        result = subprocess.run(
            ['node', '--input-type=module', '-e',
             f"import {{loginCrop}} from {json.dumps(module)}; "
             "console.log(JSON.stringify([loginCrop(2560,1440,'wecom'),"
             "loginCrop(2560,1440,'wechat'),loginCrop(1280,800,'wecom'),"
             "loginCrop(2560,1440,'unknown')]));"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [
            {'x': 478, 'y': 526, 'width': 320, 'height': 340},
            {'x': 1742, 'y': 476, 'width': 360, 'height': 440},
            None, None,
        ])

    def test_enlargement_reuses_one_console_and_disables_input(self):
        folder = SCRIPTS.parent / 'web'
        html = (folder / 'tiny11-console.html').read_text()
        js = (folder / 'tiny11-console.mjs').read_text()
        self.assertEqual(html.count('<iframe '), 1)
        self.assertIn('resize=scale', html)
        self.assertIn("frame.inert = mode !== 'desktop'", js)
        self.assertIn('ctx.drawImage(source,', js)
        self.assertIn("classList.contains('noVNC_connected')", js)
        self.assertNotIn('new WebSocket', js)
        self.assertNotIn('fetch(', js)
        self.assertNotIn('sendKey', js)
        self.assertNotIn('localStorage', js)


class InputLeaseTests(unittest.TestCase):
    def test_control_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.lock'
            first, second = views.InputLease(path), views.InputLease(path)
            try:
                self.assertTrue(first.acquire())
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
            finally:
                first.release()
                second.release()

    def test_lock_is_shared_with_wecom_not_a_separate_browser_lock(self):
        self.assertEqual(views.LOCK, SCRIPTS.parent / '.private/wecom_gui_bridge.lock')

    def test_release_without_acquisition_is_safe(self):
        views.InputLease(Path('/unused')).release()


class DisplaySupervisorTests(unittest.TestCase):
    def test_wecom_uses_original_console_not_guest_input_server(self):
        self.assertEqual(views.PORTS, {'wecom': 5943, 'wechat': 5945})
        source = (SCRIPTS / 'tiny11_displays.sh').read_text()
        self.assertIn('for name in tunnel wechat views;', source)
        self.assertNotIn('ensure_window wecom', source)
        self.assertLess(source.index('ensure_window views'), source.index('ssh -p 2290'))

    def test_retirement_preserves_unknown_legacy_pane(self):
        source = (SCRIPTS / 'tiny11_displays.sh').read_text().split('case "${1:-status}" in')[0]
        stub = '''
tmux() {
    case "$1" in
        list-panes) if [[ "$*" == *pane_pid* ]]; then printf '%s' "$$"; else printf '0'; fi ;;
        *) printf '%s\\n' "$*" ;;
    esac
}
retire_legacy_wecom_reflector
'''
        result = subprocess.run(['bash', '-c', source + stub], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('preserving', result.stderr)
        self.assertNotIn('kill-', result.stdout)

    def test_retirement_removes_only_dead_owned_legacy_pane(self):
        source = (SCRIPTS / 'tiny11_displays.sh').read_text().split('case "${1:-status}" in')[0]
        stub = '''
tmux() {
    case "$1" in
        list-panes) printf '1' ;;
        *) printf '%s\\n' "$*" ;;
    esac
}
retire_legacy_wecom_reflector
'''
        result = subprocess.run(['bash', '-c', source + stub], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'kill-window -t labcanvas-tiny11-displays:wecom')

    def test_only_dead_or_missing_owned_windows_are_restarted(self):
        source = (SCRIPTS / 'tiny11_displays.sh').read_text().split('case "${1:-status}" in')[0]
        for state, expected in [('0', ''), ('1', 'respawn-window'), ('missing', 'new-window')]:
            stub = '''
tmux() {
    case "$1" in
        list-panes) if [[ "$STATE" == missing ]]; then return 1; else printf '%s' "$STATE"; fi ;;
        has-session) return 0 ;;
        *) printf '%s\\n' "$*" ;;
    esac
}
ensure_window wecom 'exec replacement'
'''
            result = subprocess.run(['bash', '-c', source + '\nSTATE=' + state + '\n' + stub],
                                    capture_output=True, text=True, check=True)
            if expected:
                self.assertIn(expected, result.stdout)
                self.assertIn('labcanvas-tiny11-displays', result.stdout)
                self.assertIn('wecom', result.stdout)
            else:
                self.assertEqual(result.stdout, '')
            self.assertNotIn('kill-', result.stdout)


@unittest.skipIf(views.web is None, 'optional display service aiohttp dependency')
class ViewerHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp.test_utils import TestClient, TestServer
        self.client = TestClient(TestServer(views.app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_both_views_exist(self):
        for path in ('/wechat', '/wecom'):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200)
            self.assertIn('Take control', await response.text())

    async def test_unknown_target_fails_closed(self):
        self.assertEqual((await self.client.get('/ws/other')).status, 404)

    async def test_cross_origin_control_is_rejected_before_lock(self):
        response = await self.client.get('/ws/wecom?control=1', headers={'Origin': 'https://example.org'})
        self.assertEqual(response.status, 403)

    async def test_dns_rebinding_host_rejected(self):
        response = await self.client.get('/wechat', headers={'Host': 'example.org'})
        self.assertEqual(response.status, 403)

    async def test_clipboard_requires_current_input_owner(self):
        origin = str(self.client.make_url('/')).rstrip('/')
        response = await self.client.post('/clipboard', headers={'Origin': origin},
                                          json={'lease': 'expired', 'action': 'write', 'text': 'probe'})
        self.assertEqual(response.status, 409)

    async def test_unavailable_upstream_returns_503_and_releases_input(self):
        origin = str(self.client.make_url('/')).rstrip('/')
        with tempfile.TemporaryDirectory() as directory:
            lease = views.InputLease(Path(directory) / 'input.lock')
            for error in (ConnectionRefusedError(), TimeoutError()):
                with mock.patch.object(views, 'InputLease', return_value=lease), mock.patch.object(
                    views.asyncio, 'open_connection', new=mock.AsyncMock(side_effect=error)
                ):
                    response = await self.client.get(
                        '/ws/wecom?control=1&lease=00000000-0000-0000-0000-000000000000',
                        headers={'Origin': origin})
                self.assertEqual(response.status, 503)
                self.assertEqual(response.headers['Retry-After'], '2')
                self.assertEqual(await response.text(), 'Windows display reconnecting')
                self.assertIsNone(lease.handle)
                self.assertEqual(self.client.server.app[views.OWNER_KEY], '')


if __name__ == '__main__':
    unittest.main()

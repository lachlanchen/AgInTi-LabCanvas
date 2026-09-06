from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'agentic_tools/wecom_agent/scripts'
sys.path.insert(0, str(SCRIPTS))
views = importlib.import_module('tiny11_display_views')


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


if __name__ == '__main__':
    unittest.main()

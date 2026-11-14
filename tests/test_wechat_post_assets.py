from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / 'agentic_tools/wechat_gui_agent/scripts'
sys.path.insert(0, str(SCRIPTS))
import wechat_post_assets as assets


class WeChatPostAssetsTests(unittest.TestCase):
    def test_original_dimensions_and_bytes_are_preserved(self):
        data = BytesIO()
        Image.new('RGB', (2151, 3114), 'white').save(data, 'JPEG')
        payload = data.getvalue()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = payload
        opener = mock.Mock()
        opener.open.return_value = response
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, 'build_opener', return_value=opener):
            result = assets.download_post_images(['https://mmbiz.qpic.cn/original'], Path(tmp))[0]
            self.assertEqual(result['status'], 'ready')
            self.assertEqual((result['width'], result['height']), (2151, 3114))
            self.assertEqual(Path(result['path']).read_bytes(), payload)
            self.assertEqual(Path(result['path']).stat().st_mode & 0o777, 0o600)

    def test_untrusted_source_and_redirect_never_fetch_local_resources(self):
        for url in ('http://127.0.0.1/secret', 'file:///etc/passwd', 'https://qpic.cn.attacker.test/image', 'https://user:pass@mmbiz.qpic.cn/asset'):
            with self.subTest(url=url):
                self.assertFalse(assets.trusted_image_url(url))
        with self.assertRaisesRegex(ValueError, 'outside'):
            assets.ImageRedirects().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/secret')

    def test_invalid_images_and_excess_pages_remain_explicitly_unavailable(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'<html>not an image</html>'
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(assets, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            result = assets.download_post_images(['https://mmbiz.qpic.cn/image'] * 13, Path(tmp))
        self.assertTrue(all(item['status'] == 'unavailable' for item in result))
        self.assertIn('budget', result[-1]['error'])
        self.assertEqual(opener.return_value.open.call_count, 12)


if __name__ == '__main__':
    unittest.main()

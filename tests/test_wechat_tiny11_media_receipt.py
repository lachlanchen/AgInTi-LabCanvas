import hashlib
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
media = importlib.import_module('wechat_tiny11_media_receipt')


class VideoReceiptTests(unittest.TestCase):
    def test_native_digest_is_mandatory_before_guest_access(self):
        transport = mock.Mock()
        for attrs in ({}, {'rawmd5': '../bad', 'rawlength': '5'}, {'rawmd5': 'a'*32, 'rawlength': '0'}):
            self.assertIsNone(media.verify_video(transport, 'source', attrs, created_at=1, cache_dir='unused'))
        transport.powershell.assert_not_called()

    def test_cached_native_copy_requires_exact_stream_hashes_not_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            content = b'remuxed container'
            digest = hashlib.md5(content).hexdigest()
            (root / (digest + '.mp4')).write_bytes(content)
            transport = mock.Mock()
            attrs = {'rawmd5': digest, 'rawlength': str(len(content))}
            with mock.patch.object(media, 'stream_hashes', side_effect=[['source'], ['different']]):
                self.assertIsNone(media.verify_video(transport, root/'source.mp4', attrs, created_at=1, cache_dir=root))
            with mock.patch.object(media, 'stream_hashes', return_value=['same audio/video']):
                result = media.verify_video(transport, root/'source.mp4', attrs, created_at=1, cache_dir=root)
            self.assertEqual(result['rawmd5'], digest)
            transport.powershell.assert_not_called()

    def test_empty_or_unreadable_stream_hash_never_verifies(self):
        for text in ('', 'not a media hash', '0,v,SHA256=invalid'):
            with mock.patch.object(media.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=text)), \
                    self.assertRaisesRegex(ValueError, 'stream_hash_unavailable'):
                media.stream_hashes('source.mp4')

    def test_hashes_copy_both_streams_without_reencoding(self):
        text = '0,v,SHA256=' + 'a'*64 + '\n1,a,SHA256=' + 'b'*64 + '\n'
        with mock.patch.object(media.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=text)) as run:
            self.assertEqual(media.stream_hashes('source.mp4'), text.strip().splitlines())
        command = run.call_args.args[0]
        self.assertIn('0:v?', command)
        self.assertIn('0:a?', command)
        self.assertEqual(command[command.index('-c')+1], 'copy')


if __name__ == '__main__':
    unittest.main()

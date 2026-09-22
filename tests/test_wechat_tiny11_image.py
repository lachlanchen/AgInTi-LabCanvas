import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
import wechat_tiny11_image as images

spec = importlib.util.spec_from_file_location('image_export', ROOT / 'agentic_tools/wecom_agent/windows/Export-WeChatImage.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class Tiny11ImageTests(unittest.TestCase):
    def test_progress_queue_update_never_exposes_partial_rows(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            queue = Path(folder) / 'queue.jsonl'
            before = [{'id': 'old', 'status': 'pending'}]
            after = [{'id': 'old', 'status': 'done'}, {'id': 'new', 'status': 'pending'}]
            worker.write_tasks(queue, before)
            replace = worker.os.replace
            def observe_then_replace(source, destination):
                self.assertEqual(worker.read_tasks(queue), before)
                self.assertEqual(worker.read_tasks(Path(source)), after)
                replace(source, destination)
            with mock.patch.object(worker.os, 'replace', side_effect=observe_then_replace):
                worker.write_tasks(queue, after)
            self.assertEqual(worker.read_tasks(queue), after)
            self.assertEqual(queue.stat().st_mode & 0o777, 0o600)
            with mock.patch.object(worker.os, 'replace', side_effect=OSError('replace failed')):
                with self.assertRaises(OSError):
                    worker.write_tasks(queue, before)
            self.assertEqual(worker.read_tasks(queue), after)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_resource_join_is_chat_server_local_time_and_type_bound(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('''CREATE TABLE ChatName2Id(user_name TEXT);
                CREATE TABLE MessageResourceInfo(chat_id, message_local_id, message_svr_id,
                    message_create_time, message_local_type, packed_info);''')
            conn.executemany('INSERT INTO ChatName2Id VALUES (?)', [('our-chat',), ('other-chat',)])
            token = 'a' * 32
            blob = b'\x12\x22\x0a\x20' + token.encode()
            conn.executemany('INSERT INTO MessageResourceInfo VALUES (?,?,?,?,?,?)', [
                (1, 8, 1234, 100, 3, blob),
                (2, 8, 1234, 100, 3, b'\x12\x22\x0a\x20' + b'b' * 32),
                (1, 8, 5678, 101, 3, b'\x12\x22\x0a\x20' + b'c' * 32),
            ])
            request = dict(table='Msg_' + hashlib.md5(b'our-chat').hexdigest(),
                           local_id=8, server_id='1234', create_time=100)
            self.assertEqual(guest.resolve_resource(conn, request), token)
            for changes in ({'local_id': 9}, {'server_id': '99'}, {'create_time': 101}, {'table': 'bad'}):
                with self.assertRaises(ValueError):
                    guest.resolve_resource(conn, dict(request, **changes))

    def test_resource_token_rejects_loose_hash_and_ambiguous_mapping(self):
        for blob in (b'a' * 32, b'', b'\x12\x22\x0a\x20' + b'a' * 32 + b'\x12\x22\x0a\x20' + b'b' * 32):
            with self.assertRaises(ValueError):
                guest.resource_token(blob)

    def test_image_bytes_must_match_source_and_transfer_not_only_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.png'
            Image.new('RGB', (900, 1200), 'white').save(path)
            data = path.read_bytes()
            receipt = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'variant': 'full'}
            attrs = {'md5': hashlib.md5(data).hexdigest(), 'length': str(len(data))}
            self.assertEqual(images.verify_export(path, receipt, attrs), (900, 1200))
            for wrong in ({'md5': '0' * 32}, {'length': str(len(data) + 1)}):
                with self.assertRaises(ValueError):
                    images.verify_export(path, receipt, dict(attrs, **wrong))
            with self.assertRaises(ValueError):
                images.verify_export(path, dict(receipt, sha256='0' * 64), attrs)

    def test_projection_uses_native_id_not_host_synthetic_id(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / 'message_999998.db'
            table = 'Msg_' + 'a' * 32
            with sqlite3.connect(store) as conn:
                conn.executescript(f'''CREATE TABLE {table}(local_id,server_id,create_time,local_type,
                    message_content,compress_content,WCDB_CT_message_content);
                    CREATE TABLE Tiny11Rows(source_id,table_name,local_id);''')
                conn.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?)',
                             (888, '1234', 100, 3, '<msg><img length="99" md5="a"/></msg>', '', 0))
                conn.execute('INSERT INTO Tiny11Rows VALUES (?,?,?)', (7, table, 888))
            config = {'targets': {'Shares': {}}, 'message_tables': [table], 'self_wxid': 'me'}
            task = {'chat': 'Shares', 'source': {'message_table': table, 'message_db': store.name,
                                               'local_id': 888, 'server_id': '1234'}}
            with mock.patch('wechat_native_text_delivery.native_chat_binding', return_value={'table': table}), \
                    mock.patch('wechat_direct_chatops.decode_content', side_effect=lambda a, *rest: a):
                request, attrs = images.image_request(task, config, store)
                self.assertEqual(request['local_id'], 7)
                self.assertEqual(attrs['length'], '99')
                task['source']['server_id'] = 'wrong'
                with self.assertRaises(ValueError):
                    images.image_request(task, config, store)

    def test_worker_uses_windows_images_instead_of_linux_refresh(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'exact.png'
            Image.new('RGB', (2, 2)).save(source)
            candidate = {'mirror_path': str(source), 'original_resolution_verified': True}
            task = {'id': 'test', 'chat': 'Shares', 'source': {'kind': 'image', 'local_type': 3}}
            with mock.patch.object(worker, 'uses_tiny11_wechat', return_value=True), \
                    mock.patch.object(images, 'recover_image', return_value=candidate), \
                    mock.patch.object(worker, 'refresh_media_sync_for_task') as linux, \
                    mock.patch.object(worker, 'resolve_synced_media_from_mirror') as mirror, \
                    mock.patch.object(worker, 'enrich_media_resolution_copies_with_image_read'), \
                    mock.patch.object(worker, 'enrich_copies_with_document_read'):
                result = worker.prepare_media_resolution_preflight(task, root)
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(len(result['copied']), 1)
                linux.assert_not_called()
                mirror.assert_not_called()
                with mock.patch.object(images, 'recover_image', side_effect=ValueError('not_cached')):
                    result = worker.prepare_media_resolution_preflight(task, root)
                    self.assertEqual(result['status'], 'missing')
                    self.assertIn('not_cached', result['refresh']['reason'])
                    mirror.assert_not_called()

    def test_wxgf_retains_exact_bytes_and_is_not_treated_as_a_thumbnail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.wxgf'
            payload = b'wxgf' + bytes(range(64))
            path.write_bytes(payload)
            receipt = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(), 'variant': 'full'}
            attrs = {'length': str(len(payload)), 'md5': hashlib.md5(payload).hexdigest()}
            self.assertIsNone(images.verify_export(path, receipt, attrs))
            with self.assertRaises(ValueError):
                images.decode_wxgf(path, path.with_suffix('.png'))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_wxgf_decodes_native_dimensions_to_png(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.wxgf'
            result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                     'color=c=red:s=128x96', '-frames:v', '1', '-threads', '1',
                                     '-c:v', 'libx265', '-x265-params', 'pools=none:frame-threads=1',
                                     '-f', 'hevc', 'pipe:1'], capture_output=True, timeout=20)
            if result.returncode:
                self.skipTest('ffmpeg has no libx265 encoder')
            path.write_bytes(b'wxgf' + b'\0' * 12 + result.stdout)
            png = path.with_suffix('.png')
            self.assertEqual(images.decode_wxgf(path, png), (128, 96))
            self.assertTrue(png.read_bytes().startswith(b'\x89PNG'))
            self.assertEqual(path.read_bytes()[16:], result.stdout)

    def test_receipt_reconciliation_never_composes_or_changes_chat(self):
        import wechat_tiny11_bridge as bridge
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.target_groups = ['Shares']
        client.config = {'targets': {'Shares': {}}}
        client.state_db = Path('unused')
        client.validate_send_file = mock.Mock(return_value=Path('original.mp4'))
        client.wait_receipt = mock.Mock(return_value={'verified': True})
        client.remember_file_receipt = mock.Mock()
        client.ensure_chat = mock.Mock()
        binding = {'table': 'exact-chat', 'sender': 'owner'}
        with mock.patch.object(bridge, 'delivery_done', return_value=False), \
                mock.patch.object(bridge, 'file_delivery_key', return_value='content-scoped-key'), \
                mock.patch.object(bridge, 'get_runtime', return_value='') as prior, \
                mock.patch.object(bridge, 'native_chat_binding', return_value=binding):
            self.assertFalse(client.reconcile_submitted_file('Other', Path('original.mp4'), task_id='job'))
            self.assertFalse(client.reconcile_submitted_file('Shares', Path('original.mp4'), task_id='job'))
            prior.return_value = json.dumps(dict(binding, table='other-chat'))
            self.assertFalse(client.reconcile_submitted_file('Shares', Path('original.mp4'), task_id='job'))
            client.wait_receipt.assert_not_called()
            prior.return_value = json.dumps(binding)
            self.assertTrue(client.reconcile_submitted_file('Shares', Path('original.mp4'), task_id='job'))
            client.wait_receipt.assert_called_once_with(binding, file=Path('original.mp4'), timeout=0)
            client.remember_file_receipt.assert_called_once()
            client.ensure_chat.assert_not_called()

    def test_pending_video_receipt_releases_only_remaining_delivery(self):
        import wechat_task_worker as worker
        with tempfile.TemporaryDirectory() as folder:
            queue = Path(folder) / 'queue.jsonl'
            file = Path(folder) / 'video.mp4'
            file.write_bytes(b'video')
            task = {'id': 'job', 'chat': 'Shares', 'status': 'send_uncertain',
                    'send_errors': ['WECHAT_GUI_SEND_UNCERTAIN'],
                    'send_deferred_reason': 'gui_postcommit_uncertain',
                    'file_send_errors': [{'path': str(file), 'error': 'WECHAT_GUI_SEND_UNCERTAIN'}]}
            worker.write_tasks(queue, [task])
            with mock.patch.object(worker, 'uses_tiny11_wechat', return_value=True), \
                    mock.patch('wechat_tiny11_bridge.Tiny11WeChatBridge') as cls:
                cls.return_value.reconcile_submitted_file.return_value = False
                self.assertFalse(worker.reconcile_one_uncertain_native_file(queue))
                self.assertEqual(worker.read_tasks(queue)[0]['status'], 'send_uncertain')
                self.assertFalse(worker.reconcile_one_uncertain_native_file(queue))
                self.assertEqual(cls.return_value.reconcile_submitted_file.call_count, 1)
                worker.write_tasks(queue, [dict(task, manual_pause={'reason': 'user'})])
                self.assertFalse(worker.reconcile_one_uncertain_native_file(queue))
                worker.write_tasks(queue, [task])
                cls.return_value.reconcile_submitted_file.return_value = True
                self.assertFalse(worker.reconcile_one_uncertain_native_file(queue, 'Other'))
                self.assertTrue(worker.reconcile_one_uncertain_native_file(queue))
                saved = worker.read_tasks(queue)[0]
                self.assertEqual(saved['status'], worker.SEND_DEFERRED_LOCKED_STATUS)
                self.assertEqual(saved['sent_file_paths'], [str(file)])
                self.assertNotIn('send_errors', saved)
                cls.return_value.send_files_locked.assert_not_called()
                worker.write_tasks(queue, [task])
                def pause_during_read(*args, **kwargs):
                    worker.write_tasks(queue, [dict(task, status='paused_by_user', manual_pause={'reason': 'stop'})])
                    return True
                cls.return_value.reconcile_submitted_file.side_effect = pause_during_read
                self.assertFalse(worker.reconcile_one_uncertain_native_file(queue))
                self.assertEqual(worker.read_tasks(queue)[0]['status'], 'paused_by_user')


if __name__ == '__main__':
    unittest.main()

import base64
import importlib
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/windows'))
bridge = importlib.import_module('wechat_tiny11_bridge')
snapshot = importlib.import_module('wechat_store_snapshot')


class Tiny11WeChatTests(unittest.TestCase):
    def test_real_sqlite_wal_keeps_overflow_pages_and_excludes_uncommitted_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.db'
            conn = sqlite3.connect(source)
            self.addCleanup(conn.close)
            conn.execute('CREATE TABLE evidence(value BLOB)')
            conn.commit()
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA wal_autocheckpoint=0')
            value = b'full original material ' * 1400
            conn.execute('INSERT INTO evidence VALUES (?)', (value,))
            conn.commit()
            conn.execute('INSERT INTO evidence VALUES (?)', (b'not committed' * 1000,))
            workdir = root / 'cache'
            workdir.mkdir()
            db = SimpleNamespace(workdir=workdir, _keys={'message': b'test'},
                                 _db_path=lambda rel: source,
                                 _decrypt_file=lambda src, dst, key: shutil.copyfile(src, dst))
            reader = SimpleNamespace(_decrypt_page=lambda key, page, pgno: page)
            read = snapshot.open_snapshot(db, 'message', reader)
            try:
                self.assertEqual(read.execute('SELECT value FROM evidence').fetchall(), [(value,)])
                self.assertEqual(read.execute('PRAGMA quick_check').fetchall(), [('ok',)])
            finally:
                read.close()
                conn.close()

    def test_damaged_wal_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.wal'
            path.write_bytes(b'x' * 32)
            with self.assertRaises(ValueError):
                snapshot.committed_frames(path)

    def test_store_mirror_retains_raw_bytes_and_deduplicates(self):
        table = 'Msg_' + 'a' * 32
        source = 'message/message_0.db:' + table
        payload = {'account_verified': True, 'tables': [table], 'high_watermarks': {source: 7},
                   'rows': [{'source': source, 'table': table, 'local_id': 7,
                             'server_id': 987, 'local_type': 49, 'sender': 'member',
                             'create_time': 123, 'status': 3, 'message_content': {'base64': base64.b64encode(b'\x00original').decode()},
                             'compress_content': None, 'WCDB_CT_message_content': 4}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'message_999998.db'
            self.assertEqual(bridge.ingest_export(payload, path), 1)
            self.assertEqual(bridge.ingest_export(payload, path), 0)
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute(f'SELECT message_content FROM {table}').fetchone()[0], b'\x00original')
                self.assertEqual(conn.execute('SELECT local_id FROM Tiny11Cursors').fetchone()[0], 7)

    def test_account_failure_never_creates_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.db'
            with self.assertRaises(ValueError):
                bridge.ingest_export({'account_verified': False}, path)
            self.assertFalse(path.exists())

    def test_local_system_rows_can_share_zero_server_id(self):
        table = 'Msg_' + 'b' * 32
        source = 'message/message_0.db:' + table
        rows = [{'source': source, 'table': table, 'local_id': n,
                 'server_id': 0, 'local_type': 10000, 'sender': 'wechat-system',
                 'create_time': n, 'status': 3, 'message_content': 'notice',
                 'compress_content': None, 'WCDB_CT_message_content': 0} for n in (1, 2)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mirror.db'
            payload = {'account_verified': True, 'tables': [table], 'rows': rows,
                       'high_watermarks': {source: 2}}
            self.assertEqual(bridge.ingest_export(payload, path), 2)
            self.assertEqual(bridge.ingest_export(payload, path), 0)

    def test_invalid_table_cannot_create_store(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mirror.db'
            with self.assertRaises(ValueError):
                bridge.ingest_export({'account_verified': True, 'tables': ['not_sql;']}, path)
            self.assertFalse(path.exists())

    def test_disabled_cutover_cannot_send(self):
        with mock.patch.object(bridge, 'Tiny11WeChatBridge') as factory, \
                mock.patch.object(bridge, 'enabled', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'NOT_READY'):
                bridge.send('Shares', message='must not send', task_id='test')
            factory.return_value.send.assert_not_called()

    def test_no_exact_search_result_never_presses_enter(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.target_groups = ['Shares']
        client.config = {'targets': {'Shares': {'query': 'Shares'}}}
        client.runtime_dir = Path('/tmp/test-runtime')
        client.find_window = mock.Mock(return_value=SimpleNamespace(x=100, y=0))
        client.current_title_matches = mock.Mock(return_value=False)
        client.click = mock.Mock()
        client.set_clipboard = mock.Mock()
        client.key = mock.Mock()
        client.capture_screen = mock.Mock()
        client.crop = mock.Mock()
        client.find_ocr_line = mock.Mock(return_value=None)
        with mock.patch.object(bridge.time, 'sleep'), \
                self.assertRaisesRegex(RuntimeError, 'no web search'):
            client.ensure_chat('Shares')
        self.assertNotIn(mock.call('Return'), client.key.call_args_list)

    def test_personal_bridge_cannot_use_wecom_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {'local_api_token': 'test', 'state_db': folder + '/state.db',
                      'event_root': folder + '/events', 'tiny11': {'app': 'wecom'}}
            with self.assertRaisesRegex(ValueError, 'explicitly scoped'):
                bridge.Tiny11WeChatBridge(config)

    def test_input_never_runs_for_unallowlisted_chat(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.target_groups = ['Shares']
        client.config = {'targets': {'Shares': {}}}
        client.find_window = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'allowlisted'):
            client.ensure_chat('LabAgent')
        client.find_window.assert_not_called()

    def test_windows_helper_defaults_to_wecom_and_masks_other_app(self):
        text = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        self.assertIn("$script:TargetApp -notin @('wecom', 'wechat')", text)
        self.assertIn("Headers['X-LabCanvas-App']", text)
        self.assertIn("$other.ClassName -in @('PerryShadowWnd', 'TitleBarWindow')", text)
        self.assertEqual(text.count('Assert-AppPoint $window $Action'), 3)
        self.assertIn('refusing cross-app input', text)
        for forbidden in ('WriteProcessMemory', 'CreateRemoteThread', 'Restart-Computer'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()

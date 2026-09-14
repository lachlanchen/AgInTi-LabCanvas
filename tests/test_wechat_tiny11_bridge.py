import base64
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/windows'))
bridge = importlib.import_module('wechat_tiny11_bridge')
snapshot = importlib.import_module('wechat_store_snapshot')


class Tiny11WeChatTests(unittest.TestCase):
    def test_native_draft_file_roundtrip_requires_exact_single_staged_path(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        staged = Path('/tmp/staged/untruncated-source-name.mp4')
        expected = 'C:/LabCanvas/WeChatDelivery/inbox/exact-task/untruncated-source-name.mp4'
        client.remote_staged_files = {str(staged.resolve()): expected}
        events = []
        client.set_clipboard = mock.Mock(side_effect=lambda _: events.append('clear'))
        client.composer_keys = mock.Mock(side_effect=lambda *args: events.append('copy'))
        client.tiny11 = mock.Mock()
        def read(action):
            events.append('read')
            return expected.replace('/', '\\').upper()
        client.tiny11.invoke.side_effect = read
        window = mock.Mock()
        self.assertTrue(client.composer_file_matches(window, staged, 'key'))
        self.assertEqual(events, ['clear', 'copy', 'read'])
        client.composer_keys.assert_called_once_with(window, 'ctrl+a', 'ctrl+c')
        client.tiny11.invoke.assert_called_once_with({'action': 'get_file_clipboard'})
        client.tiny11.invoke.side_effect = None
        for observed in (None, '', [], [expected, expected],
                         [expected.replace('exact-task', 'another-task')],
                         ['untruncated-source-name.mp4'], {'files': [expected]}):
            with self.subTest(observed=observed):
                client.tiny11.invoke.return_value = observed
                self.assertFalse(client.composer_file_matches(window, staged, 'key'))

    def test_unstaged_file_cannot_pass_composer_check(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.remote_staged_files = {}
        client.set_clipboard = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'verified SFTP'):
            client.composer_file_matches(mock.Mock(), Path('/tmp/unstaged.mp4'), 'key')
        client.set_clipboard.assert_not_called()

    def test_wait_composed_file_uses_native_identity_not_ocr(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.composer_file_matches = mock.Mock(return_value=True)
        client.composer_contains_filename = mock.Mock()
        window = mock.Mock()
        staged = Path('/tmp/staged/source.mp4')
        client.wait_composed_file(window, staged, 'key')
        client.composer_file_matches.assert_called_once_with(window, staged, 'key')
        client.composer_contains_filename.assert_not_called()

    def test_scroll_to_tail_observes_a_stable_viewport(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.history_surface = mock.Mock(return_value=(0, 0, 100, 100))
        client.tiny11 = mock.Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.png'
            Image.new('RGB', (100, 100), 'white').save(path)
            client.capture_screen = mock.Mock(return_value=path)
            with mock.patch.object(bridge.time, 'sleep'):
                client.scroll_chat_to_bottom(mock.Mock())
        self.assertEqual(client.tiny11.invoke.call_count, 2)
        self.assertTrue(all(action['delta'] < 0 for action in client.tiny11.invoke.call_args.args[0]['actions']))

    def test_native_remux_alias_recorded_without_resending(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.state_db = Path('unused')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clip.mp4'; path.write_bytes(b'source')
            client.validate_send_file = mock.Mock(return_value=path)
            client.wait_receipt = mock.Mock(return_value={'verified': True, 'media_proof': {'rawmd5': 'a' * 32}})
            client.ensure_chat = mock.Mock()
            with mock.patch.object(bridge, 'delivery_done', return_value=False), \
                    mock.patch.object(bridge, 'get_runtime', return_value='{}'), \
                    mock.patch.object(bridge, 'remember_delivery'), mock.patch.object(bridge, 'record_event') as record:
                client.send_files_locked('Shares', [path], task_id='same-task')
            client.ensure_chat.assert_not_called()
            identity = record.call_args.kwargs['metadata']['file_identity']
            self.assertEqual(identity['md5_values'], ['a' * 32])
            self.assertIn('sha256', identity)

    def test_file_label_ellipsis_requires_exact_prefix_and_suffix(self):
        self.assertTrue(bridge.composed_filename_matches('sample-episode-transcript.txt', 'sample..…script.txt'))
        self.assertFalse(bridge.composed_filename_matches('different-episode-transcript.txt', 'sample..…script.txt'))
        self.assertFalse(bridge.composed_filename_matches('sample-episode-transcript.mp4', 'sample..…script.txt'))

    def test_single_label_ocr_after_block_ocr_failure(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.runtime_dir = Path('/tmp')
        client.content_left = mock.Mock(return_value=10)
        client.crop = mock.Mock(return_value=Path('/tmp/label.png'))
        client.ocr_scaled = mock.Mock(side_effect=['unreadable icon', 'sample..…script.txt'])
        window = SimpleNamespace(y=0, height=1000)
        self.assertTrue(client.composer_contains_filename(Path('screen.png'), window, 'sample-episode-transcript.txt', 'test'))
        self.assertEqual(client.ocr_scaled.call_args.kwargs, {'scale': 2, 'psm': 7})

    def test_file_chips_are_not_an_empty_draft_but_caret_is(self):
        image = Image.new('RGB', (600, 75), 'white')
        self.assertFalse(bridge.composer_has_visible_content(image))
        image.paste((0, 180, 80), (300, 5, 302, 40))
        self.assertFalse(bridge.composer_has_visible_content(image))
        image.paste((120, 130, 150), (20, 20, 40, 40))
        self.assertTrue(bridge.composer_has_visible_content(image))

    def test_retried_owned_draft_is_not_pasted_again(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.state_db = Path('unused')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clip.mp4'; path.write_bytes(b'source')
            client.validate_send_file = mock.Mock(return_value=path)
            client.ensure_chat = mock.Mock()
            client.composer_is_empty = mock.Mock(return_value=False)
            client.stage_send_file = mock.Mock(return_value=(path, path.parent))
            client.wait_composed_file = mock.Mock(side_effect=RuntimeError('unverified draft'))
            client.compose_staged_file_with_picker = mock.Mock()
            client.composer_keys = mock.Mock()
            client.prepare_native_receipt = mock.Mock()
            with mock.patch.object(bridge, 'delivery_done', return_value=False), \
                    mock.patch.object(bridge, 'get_runtime', side_effect=['', '{"started_at":1}']), \
                    self.assertRaisesRegex(RuntimeError, 'unverified draft'):
                client.send_files_locked('Shares', [path], task_id='same-task')
            client.compose_staged_file_with_picker.assert_not_called()
            client.composer_keys.assert_not_called()
            client.prepare_native_receipt.assert_not_called()

    def test_native_video_receipt_requires_matching_media_proof(self):
        table = 'Msg_' + 'c' * 32
        source = 'message/message_0.db:' + table
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); file = root / 'original.mp4'; file.write_bytes(b'video')
            path = root / 'message_999998.db'
            row = {'source': source, 'table': table, 'local_id': 1, 'server_id': 88,
                   'local_type': 43, 'sender': 'owner', 'create_time': 200, 'status': 2,
                   'message_content': '<msg><videomsg rawmd5="abcdef" rawlength="5"/></msg>',
                   'compress_content': None, 'WCDB_CT_message_content': 0}
            bridge.ingest_export({'account_verified': True, 'tables': [table], 'rows': [row],
                                  'high_watermarks': {source: 1}}, path)
            receipt = {'table': table, 'sender': 'owner', 'started_at': 199, 'after': {path.name: 0}}
            self.assertIsNone(bridge.find_receipt(receipt, file=file, db_path=path))
            verify = mock.Mock(return_value=None)
            self.assertIsNone(bridge.find_receipt(receipt, file=file, db_path=path, video_verifier=verify))
            verify.return_value = {'method': 'verified_stream_hashes'}
            proof = bridge.find_receipt(receipt, file=file, db_path=path, video_verifier=verify)
            self.assertTrue(proof['verified'])
            verify.assert_called_with(file, {'rawmd5': 'abcdef', 'rawlength': '5'}, 200)

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
        client.find_window = mock.Mock(return_value=SimpleNamespace(x=100, y=0, width=835, height=1000))
        client.current_title_matches = mock.Mock(return_value=False)
        client.click = mock.Mock()
        client.set_clipboard = mock.Mock()
        client.key = mock.Mock()
        client.capture_screen = mock.Mock()
        client.crop = mock.Mock()
        client.find_ocr_line = mock.Mock(return_value=None)
        client.native_search_category = mock.Mock(return_value=None)
        with mock.patch.object(bridge.time, 'sleep'), \
                self.assertRaisesRegex(RuntimeError, 'no web search'):
            client.ensure_chat('Shares')
        self.assertNotIn(mock.call('Return'), client.key.call_args_list)

    def test_title_separator_recovery_does_not_alias_chinese_names(self):
        self.assertTrue(bridge.title_matches('MEMO一外语', 'MEMO—外语'))
        self.assertTrue(bridge.title_matches('第一组', '第一组'))
        self.assertFalse(bridge.title_matches('第-组', '第一组'))
        self.assertFalse(bridge.title_matches('MEMO—别组', 'MEMO—外语'))

    def test_layout_watcher_never_moves_native_search_or_channels_popups(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Set-Tiny11AppScreens.ps1').read_text()
        personal = source.split("if ($AppName -eq 'WeChat')", 1)[1].split('return $Windows', 1)[0]
        self.assertIn("$_.Name -in @('Weixin', 'WeChat', '微信')", personal)
        self.assertIn("$_.ClassName -eq 'Qt51514QWindowIcon'", personal)

    def test_native_search_recovers_pale_category_but_never_web_suggestion(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            client = object.__new__(bridge.Tiny11WeChatBridge)
            client.runtime_dir = Path(folder)
            crop = client.runtime_dir / 'search.png'
            Image.new('L', (10, 10), 190).save(crop)
            def find(path, label, **kwargs):
                if path.name == 'wechat-search-categories.png' and label == 'Group Chats':
                    self.assertEqual(Image.open(path).getpixel((0, 0)), 0)
                    return {'similarity': 1.0, 'center_y': 200}
                return None
            client.find_ocr_line = mock.Mock(side_effect=find)
            self.assertEqual(client.native_search_category(crop)['center_y'], 200)
            self.assertNotIn('Internet search results', [call.args[1] for call in client.find_ocr_line.call_args_list])

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

    def test_native_export_uses_shard_sender_index_even_after_upload(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Export-WeChatStore.py').read_text()
        self.assertIn("sender_names = dict(conn.execute('SELECT rowid,user_name FROM Name2Id'))", source)
        self.assertNotIn("record['real_sender_id'] == 2", source)
        self.assertNotIn('SELECT rowid,user_name FROM SenderName2Id', source)

    def test_pending_row_update_keeps_identity_and_native_receipt(self):
        table = 'Msg_' + 'c' * 32
        source = 'message/message_0.db:' + table
        row = {'source': source, 'table': table, 'local_id': 19, 'server_id': 0,
               'local_type': 1, 'sender': 'owner', 'create_time': 200, 'status': 1,
               'message_content': 'owner:\nHello', 'compress_content': None,
               'WCDB_CT_message_content': 0}
        payload = {'account_verified': True, 'tables': [table], 'rows': [row],
                   'high_watermarks': {source: 19}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'message_999998.db'
            receipt = {'table': table, 'sender': 'owner', 'started_at': 199,
                       'after': {path.name: 0}}
            self.assertEqual(bridge.ingest_export(payload, path), 1)
            self.assertIsNone(bridge.find_receipt(receipt, message='Hello', db_path=path))
            row.update(server_id=123456, status=2)
            self.assertEqual(bridge.ingest_export(payload, path), 0)
            proof = bridge.find_receipt(receipt, message='Hello', db_path=path)
            self.assertTrue(proof['verified'])
            self.assertEqual(proof['local_id'], 1)
            self.assertIsNone(bridge.find_receipt(receipt, message='Different', db_path=path))
            self.assertIsNone(bridge.find_receipt({**receipt, 'sender': 'other'}, message='Hello', db_path=path))
            self.assertIsNone(bridge.find_receipt({**receipt, 'after': {path.name: 1}}, message='Hello', db_path=path))
            self.assertIsNone(bridge.find_receipt({**receipt, 'started_at': 201}, message='Hello', db_path=path))

    def test_file_receipt_requires_exact_filename_size_sender_and_new_row(self):
        table = 'Msg_' + 'd' * 32
        source = 'message/message_0.db:' + table
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); file = root / 'report.pdf'; file.write_bytes(b'pdf bytes')
            path = root / 'message_999998.db'
            row = {'source': source, 'table': table, 'local_id': 1, 'server_id': 77,
                   'local_type': (6 << 32) + 49, 'sender': 'owner', 'create_time': 200, 'status': 2,
                   'message_content': 'owner:\n<msg><appmsg><title>report.pdf</title><appattach><totallen>9</totallen></appattach></appmsg></msg>',
                   'compress_content': None, 'WCDB_CT_message_content': 0}
            bridge.ingest_export({'account_verified': True, 'tables': [table], 'rows': [row],
                                  'high_watermarks': {source: 1}}, path)
            receipt = {'table': table, 'sender': 'owner', 'started_at': 199, 'after': {path.name: 0}}
            self.assertTrue(bridge.find_receipt(receipt, file=file, db_path=path)['verified'])
            file.write_bytes(b'different size')
            self.assertIsNone(bridge.find_receipt(receipt, file=file, db_path=path))

    def test_ellipsis_composer_label_is_not_final_delivery_proof(self):
        self.assertTrue(bridge.composed_filename_matches('2026-09-13-recent-items.zh.pdf', '2026-09-13...ems.zh.pdf or'))
        self.assertFalse(bridge.composed_filename_matches('2026-09-14-recent-items.zh.pdf', '2026-09-13...ems.zh.pdf'))
        self.assertFalse(bridge.composed_filename_matches('report.pdf', 'other.pdf'))

    def test_chinese_chat_delivery_ledger_can_be_reconciled(self):
        from wecom_gui_bridge import init_state_db
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'delivery.sqlite'
            init_state_db(path)
            bridge.remember_delivery(path, 'key', '备忘', 'report')
            self.assertTrue(bridge.delivery_done(path, 'key', '备忘'))
            self.assertFalse(bridge.delivery_done(path, 'key', '另一个群'))

    def test_pending_file_intent_uses_existing_echo_suppression_contract(self):
        from wechat_message_policy import recorded_outbound_file_echo
        from wechat_mirror import init_db
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); db = root / 'mirror.sqlite'; file = root / 'report.pdf'
            file.write_bytes(b'pdf bytes'); init_db(db)
            bridge.record_event(chat_name='Memo', action='file_send_intent', direction='outbound',
                                status='sending', db_path=db,
                                metadata={'file_identity': bridge.file_transport_identity(file)})
            xml = '<msg><appmsg><title>report.pdf</title><appattach><totallen>9</totallen></appattach></appmsg></msg>'
            self.assertTrue(recorded_outbound_file_echo(db, 'Memo', xml, source_epoch=bridge.time.time()))
            self.assertFalse(recorded_outbound_file_echo(db, 'Other', xml, source_epoch=bridge.time.time()))

    def test_transport_selection_isolated_for_selftests(self):
        from wechat_transport_selection import tiny11_enabled
        with mock.patch.dict(os.environ, {'WECHAT_TINY11_DISABLE': '1'}):
            self.assertFalse(tiny11_enabled())

    def test_hidden_window_restores_once_without_restarting_client(self):
        client = object.__new__(bridge.Tiny11WeChatBridge)
        client.tiny11 = mock.Mock()
        window = SimpleNamespace(width=1276, height=1392)
        with mock.patch.object(bridge.Tiny11WeComGuiBridge, 'find_window', side_effect=[None, window]):
            self.assertIs(client.find_window(), window)
        client.tiny11.invoke.assert_called_once_with({'action': 'restore'})
        client.tiny11.reset_mock()
        with mock.patch.object(bridge.Tiny11WeComGuiBridge, 'find_window', return_value=window):
            self.assertIs(client.find_window(), window)
        client.tiny11.invoke.assert_not_called()

    def test_native_restore_never_launches_or_terminates_a_chat_process(self):
        script = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        restore = script.split("{ $_ -in @('restore', 'activate') }", 1)[1].split('"click"', 1)[0]
        self.assertIn("$script:TargetApp -ne 'wechat'", restore)
        self.assertIn('$candidates.Count -ne 1', restore)
        self.assertIn("SendWait('^%w')", restore)
        self.assertNotIn('Start-Process', restore)
        self.assertNotIn('Stop-Process', restore)

    def test_native_file_identity_size_parses_xml_and_preserves_hash_checks(self):
        from wechat_message_policy import attachment_transport_identity
        identity = attachment_transport_identity('member:\n<msg><appmsg><title>report.pdf</title>'
                                                  '<appattach><totallen>9</totallen></appattach></appmsg></msg>')
        self.assertEqual(identity['size_bytes'], 9)
        self.assertNotIn('size_bytes', attachment_transport_identity('<msg><appmsg><appattach><totallen>bad</totallen></appattach></appmsg></msg>'))

    def test_windows_monitor_has_own_shard_and_preserves_ubuntu_fallback(self):
        import wechat_direct_chatops as direct
        import wechat_transport_selection as selected
        table = 'Msg_' + 'e' * 32
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'message_999998.db'
            bridge.ingest_export({'account_verified': True, 'tables': [table], 'rows': [],
                                  'high_watermarks': {}}, path)
            with mock.patch.object(selected, 'STORE', path), mock.patch.object(selected, 'tiny11_enabled', return_value=True):
                self.assertEqual(direct.message_db_path(path.name), path)
                self.assertEqual(direct.available_message_db_paths({'message_table': table}), [path])
                self.assertEqual(direct.available_message_db_paths({'message_table': 'Msg_' + 'f' * 32}), [])
            with mock.patch.object(selected, 'tiny11_enabled', return_value=False), \
                    mock.patch.object(direct, 'list_message_db_paths', return_value=[Path('/legacy')]):
                self.assertIn(Path('/legacy'), direct.available_message_db_paths({'message_table': table}))


if __name__ == '__main__':
    unittest.main()

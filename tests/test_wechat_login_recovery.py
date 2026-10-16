import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
bridge = importlib.import_module('wechat_tiny11_bridge')
selection = importlib.import_module('wechat_transport_selection')
TABLE = 'Msg_' + 'a' * 32
SOURCE = 'message/message_0.db:' + TABLE
READY = {'ok': True, 'helper_ready': True, 'app': 'wechat',
         'client_state': 'ready', 'input_ready': True, 'input_blocker': ''}


class LoginRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = self.root / 'message_999998.db'
        self.config = {'enabled': True, 'delivery_verified': True,
                       'message_tables': [TABLE], 'self_wxid': 'test-account', 'targets': {}}
        for module in (bridge, selection):
            patched = mock.patch.object(module, 'STORE', self.store)
            patched.start()
            self.addCleanup(patched.stop)
        config_path = self.root / 'config.json'
        config_path.write_text(json.dumps(self.config))
        patched = mock.patch.object(selection, 'CONFIG', config_path)
        patched.start()
        self.addCleanup(patched.stop)
        self.transport = mock.Mock()
        self.transport.health.return_value = READY
        self.transport.powershell.return_value = json.dumps(
            {'ok': True, 'reader_mode': 'cached_keys_only'})
        self.transport.ssh_port = 1234
        self.transport.user = 'test'
        self.transport.host = 'localhost'
        patched = mock.patch.object(bridge, 'Tiny11Transport', return_value=self.transport)
        patched.start()
        self.addCleanup(patched.stop)

    def payload(self, local_id):
        return {'account_verified': True, 'tables': [TABLE], 'bindings': [],
                'rows': [{'source': SOURCE, 'table': TABLE, 'local_id': local_id,
                          'server_id': str(100 + local_id), 'local_type': 1,
                          'sender': 'test-sender', 'create_time': 500,
                          'status': 4, 'message_content': 'fixture',
                          'compress_content': None, 'WCDB_CT_message_content': 0}],
                'high_watermarks': {SOURCE: local_id}}

    def test_login_pause_preserves_cursor_and_cache_without_remote_export(self):
        bridge.ingest_export(self.payload(1), db_path=self.store)
        old = self.store.read_bytes()
        bridge.record_sync_state({'ok': True, 'client_ready': True,
                                  'client_state': 'ready', 'last_sync_epoch': 1000})
        self.transport.health.return_value = {**READY, 'ok': False,
                                              'client_state': 'entry_required'}
        with mock.patch.object(bridge.subprocess, 'run') as remote:
            result = bridge.sync_once(self.config)
        self.assertEqual(result['sync_deferred'], 'entry_required')
        self.assertFalse(result['client_ready'])
        self.assertFalse(result['automatic_delivery_enabled'])
        self.assertEqual(result['last_sync_epoch'], 1000)
        self.assertEqual(self.store.read_bytes(), old)
        self.transport.scp_to_guest.assert_not_called()
        self.transport.powershell.assert_not_called()
        self.transport.invoke.assert_not_called()
        remote.assert_not_called()
        status = selection.tiny11_health()
        self.assertTrue(status['human_action_required'])
        self.assertGreater(status['store_age_seconds'], 60)

    def test_missing_helper_cannot_reuse_old_login_or_ready_state(self):
        bridge.record_sync_state({'ok': True, 'client_ready': False,
                                  'client_state': 'entry_required'})
        self.transport.health.return_value = {'ok': False, 'error': 'connection refused'}
        result = bridge.sync_once(self.config)
        self.assertEqual(result['client_state'], 'unknown')
        self.assertEqual(result['sync_deferred'], 'helper_unavailable')
        self.assertFalse(selection.tiny11_health()['human_action_required'])
        self.transport.powershell.assert_not_called()

    def test_other_app_health_cannot_authorize_personal_wechat_export(self):
        self.transport.health.return_value = {**READY, 'app': 'wecom'}
        self.assertFalse(bridge.sync_once(self.config)['client_ready'])
        self.transport.powershell.assert_not_called()

    def test_missing_or_hung_client_defers_without_requesting_login(self):
        for state in ('client_unavailable', 'unresponsive'):
            with self.subTest(state=state):
                self.transport.health.return_value = {**READY, 'ok': False, 'client_state': state}
                result = bridge.sync_once(self.config)
                self.assertEqual(result['sync_deferred'], state)
                self.assertFalse(selection.tiny11_health()['human_action_required'])
        self.transport.powershell.assert_not_called()

    def test_relogin_resumes_existing_cursor_without_duplicate_native_rows(self):
        bridge.ingest_export(self.payload(1), db_path=self.store)
        bridge.record_sync_state({'ok': True, 'client_ready': False,
                                  'client_state': 'entry_required', 'sync_deferred': 'entry_required'})
        payload = self.payload(2)
        payload['rows'].insert(0, self.payload(1)['rows'][0])
        def copy_export(*args, **kwargs):
            (self.root / 'export.json').write_text(json.dumps(payload))
        with mock.patch.object(bridge.subprocess, 'run', side_effect=copy_export):
            result = bridge.sync_once(self.config)
        request = json.loads((self.root / 'export-request.json').read_text())
        self.assertEqual(request['cursors'], {SOURCE: 1})
        self.assertEqual(result['inserted'], 1)
        self.assertNotIn('sync_deferred', result)
        self.assertTrue(result['automatic_delivery_enabled'])
        self.assertTrue(selection.tiny11_health()['available'])
        with sqlite3.connect(self.store) as conn:
            self.assertEqual(conn.execute(f'SELECT local_id FROM {TABLE}').fetchall(), [(1,), (2,)])
        self.transport.invoke.assert_not_called()

    def test_login_change_during_export_still_blocks_delivery(self):
        self.transport.health.side_effect = [READY, {**READY, 'ok': False,
                                                    'client_state': 'entry_required'}]
        def copy_export(*args, **kwargs):
            (self.root / 'export.json').write_text(json.dumps(self.payload(1)))
        with mock.patch.object(bridge.subprocess, 'run', side_effect=copy_export):
            result = bridge.sync_once(self.config)
        self.assertFalse(result['automatic_delivery_enabled'])
        self.assertFalse(result['client_ready'])
        self.assertTrue(selection.tiny11_health()['human_action_required'])

    def test_fresh_probe_does_not_make_an_old_store_ready(self):
        bridge.record_sync_state({'ok': True, 'client_ready': True,
                                  'client_state': 'ready', 'last_sync_epoch': 1000})
        self.assertFalse(selection.tiny11_health()['available'])

    def test_transition_history_is_bounded_private_and_not_per_poll(self):
        for index in range(30):
            state = {'ok': True, 'client_state': 'ready' if index % 2 else 'entry_required',
                     'client_ready': bool(index % 2)}
            result = bridge.record_sync_state(state)
            repeated = bridge.record_sync_state(state)
            self.assertEqual(repeated['client_state_changed_at'], result['client_state_changed_at'])
            self.assertEqual(repeated['client_transitions'], result['client_transitions'])
        self.assertLessEqual(len(result['client_transitions']), 16)
        self.assertEqual(result['client_transitions'][-1]['from'], 'entry_required')
        self.assertEqual((self.root / 'status.json').stat().st_mode & 0o777, 0o600)

    def test_loop_logs_transitions_not_every_blocked_poll(self):
        blocked = {'ok': True, 'client_state': 'entry_required', 'client_ready': False,
                   'sync_deferred': 'entry_required', 'inserted': 0}
        ready = {'ok': True, 'client_state': 'ready', 'client_ready': True, 'inserted': 0}
        with mock.patch.object(sys, 'argv', ['bridge', 'sync', '--loop']), \
                mock.patch.object(bridge, 'sync_once', side_effect=[blocked, blocked, ready]), \
                mock.patch.object(bridge.time, 'sleep', side_effect=[None, None, KeyboardInterrupt]) as sleep, \
                mock.patch('builtins.print') as log, self.assertRaises(KeyboardInterrupt):
            bridge.main()
        self.assertEqual(log.call_count, 2)
        self.assertEqual(sleep.call_args_list, [mock.call(10), mock.call(10), mock.call(2)])


if __name__ == '__main__':
    unittest.main()

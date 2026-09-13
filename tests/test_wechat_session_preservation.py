import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/windows'))
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
snapshot = importlib.import_module('wechat_store_snapshot')
selection = importlib.import_module('wechat_transport_selection')
guard = importlib.import_module('wechat_transport_stall_guard')


class ReaderFixture:
    class WeChatDB:
        def __init__(self, **options):
            self.__dict__.update(options)
            self._db_files = [('message', 'message.db', 4096), ('unused', 'unused.db', 4096)]
            self._load_or_extract_keys()

        def _load_or_extract_keys(self, master_key=None):
            raise AssertionError('Upstream constructor must not scan process memory')

        def _key_works(self, rel):
            return self._keys[rel] == bytes.fromhex('aa' * 32)


class WeChatSessionPreservationTests(unittest.TestCase):
    def test_unit_test_entrypoint_disables_live_windows_transport(self):
        source = (ROOT / 'scripts/run-python-tests.js').read_text()
        self.assertIn('WECHAT_TINY11_DISABLE: "1"', source)

    def read_cached(self, folder, payload):
        key_file = Path(folder) / 'keys.json'
        key_file.write_text(json.dumps(payload))
        return snapshot.cached_reader(
            ReaderFixture, db_dir=folder, account='exact-account',
            keys_file=str(key_file), workdir=folder)

    def test_cached_reader_never_enters_upstream_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = {'message': 'aa' * 32, 'other-account-only': 'bb' * 32}
            db = self.read_cached(folder, payload)
            self.assertEqual(db.account, 'exact-account')
            self.assertEqual(db._keys, {'message': bytes.fromhex('aa' * 32)})
            self.assertEqual(db.unkeyed, ['unused'])
            self.assertEqual(json.loads(Path(db.keys_file).read_text()), payload)

    def test_invalid_missing_or_stale_cache_never_falls_back_to_extraction(self):
        for payload in ({}, [], {'message': 'not-a-key'}, {'message': 44},
                        {'message': 'aa' * 31}, {'message': 'bb' * 32}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(RuntimeError, 'explicit provisioning required'):
                    self.read_cached(folder, payload)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'explicit provisioning required'):
                snapshot.cached_reader(ReaderFixture, db_dir=folder, account='exact',
                                       keys_file=folder + '/missing', workdir=folder)

    def test_snapshot_rejects_missing_key_even_if_old_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            db = self.read_cached(folder, {'message': 'aa' * 32})
            with self.assertRaisesRegex(RuntimeError, 'Required WeChat key is not cached'):
                snapshot.open_snapshot(db, 'unused', ReaderFixture)

    def test_exporter_uses_cached_reader_not_automatic_key_extraction(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/Export-WeChatStore.py').read_text()
        self.assertIn('db = cached_reader(reader,', source)
        self.assertNotIn('reader.WeChatDB(', source)
        self.assertIn('"reader_mode": "cached_keys_only"', source)

    def test_fresh_database_cannot_claim_logged_in_without_native_client(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config.json'
            config.write_text(json.dumps({'delivery_verified': True}))
            state = {'ok': True, 'last_sync_epoch': 1000}
            for client_ready in (None, False, True):
                with self.subTest(client_ready=client_ready):
                    (root / 'status.json').write_text(json.dumps({**state, 'client_ready': client_ready}))
                    with mock.patch.object(selection, 'CONFIG', config), \
                         mock.patch.object(selection, 'STORE', root / 'store.db'), \
                         mock.patch.object(selection.time, 'time', return_value=1001):
                        result = selection.tiny11_health()
                    self.assertEqual(result['ok'], client_ready is True)
                    self.assertFalse(result['human_action_required'])
                    self.assertEqual(result['novnc_url'], 'http://127.0.0.1:6143/')

    def test_stale_native_observation_cannot_claim_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config.json'
            config.write_text(json.dumps({'delivery_verified': True}))
            (root / 'status.json').write_text(json.dumps(
                {'ok': True, 'client_ready': True, 'last_sync_epoch': 1000}))
            with mock.patch.object(selection, 'CONFIG', config), \
                 mock.patch.object(selection, 'STORE', root / 'store.db'), \
                 mock.patch.object(selection.time, 'time', return_value=1061):
                self.assertFalse(selection.tiny11_health()['ok'])

    def test_windows_delivery_failure_cannot_restart_ubuntu_fallback(self):
        issue = {'issues': [{'code': 'wechat_gui_delivery_stalled'}]}
        for windows in (True, False):
            with self.subTest(windows=windows), \
                 mock.patch.object(selection, 'tiny11_enabled', return_value=windows), \
                 mock.patch.object(guard, 'repair_due', return_value=True), \
                 mock.patch.object(guard, 'run_repair', return_value={'ok': True}) as repair:
                guard.perform_repairs(issue, {}, consecutive_failures=2,
                                      cooldown_seconds=300, max_sender_seconds=900)
                if windows:
                    repair.assert_not_called()
                else:
                    repair.assert_called_once_with(
                        'wechat_input_stalled', [str(guard.WECHAT_VIRTUAL_DESKTOP), 'restart-client'])


if __name__ == '__main__':
    unittest.main()

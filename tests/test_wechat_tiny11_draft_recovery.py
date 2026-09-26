import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
bridge = importlib.import_module('wechat_tiny11_bridge')
gui = importlib.import_module('wecom_gui_bridge')


class TextDraftRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.client = object.__new__(bridge.Tiny11WeChatBridge)
        self.client.state_db = Path(folder.name) / 'state.db'
        gui.init_state_db(self.client.state_db)
        self.client.config = {'targets': {'Team': {'name': 'Team'}}}
        self.client.tiny11 = mock.Mock()
        self.client.tiny11.invoke.return_value = []
        self.binding = {'table': 'Msg_' + 'a' * 32, 'sender': 'owner'}
        binding_patch = mock.patch.object(bridge, 'native_chat_binding', return_value=self.binding)
        binding_patch.start()
        self.addCleanup(binding_patch.stop)
        self.text = ''
        self.clipboard = ''
        self.sent = []
        self.client.ensure_chat = mock.Mock(return_value='window')
        self.client.composer_is_empty = mock.Mock(side_effect=lambda *args: not self.text)
        self.client.composer_text_matches = mock.Mock(side_effect=lambda w, t, k: self.text == t)
        self.client.clear_composer = mock.Mock(side_effect=lambda w: setattr(self, 'text', ''))
        self.client.set_clipboard = mock.Mock(side_effect=lambda t: setattr(self, 'clipboard', t))
        self.client.composer_keys = mock.Mock(side_effect=self.keys)
        self.client.capture_screen = mock.Mock(return_value=Path(folder.name) / 'screen.png')
        self.client.prepare_native_receipt = mock.Mock(return_value={
            **self.binding, 'after': {'message.db': 0}, 'started_at': 1})
        self.client.wait_receipt = mock.Mock(return_value={'verified': True})
        for name in ('record_event', 'retain_pending_receipt'):
            patch = mock.patch.object(bridge, name)
            patch.start()
            self.addCleanup(patch.stop)

    def keys(self, window, key):
        if key == 'ctrl+v':
            self.text = self.clipboard
        elif key == 'Return':
            self.sent.append(self.text)
            self.text = ''

    def journal(self, **overrides):
        draft = dict(chat='Team', key='owned', text='Acknowledgement', **self.binding)
        draft.update(overrides)
        bridge.set_runtime(self.client.state_db, 'native-text-draft:' + bridge.short_hash('Team'),
                           json.dumps(draft))
        self.text = 'Acknowledgement'
        return draft

    def test_timeout_after_paste_recovers_for_same_or_later_reply(self):
        for replacement in ('Acknowledgement', 'Finished answer'):
            with self.subTest(replacement=replacement):
                self.text = ''
                task_id = 'first-' + replacement
                def timed_out_paste(window, key):
                    self.keys(window, key)
                    raise RuntimeError('helper timeout after accepting paste')
                self.client.composer_keys.side_effect = timed_out_paste
                with self.assertRaisesRegex(RuntimeError, 'helper timeout'):
                    self.client.send_text_locked('Team', 'Acknowledgement', task_id=task_id)
                self.assertEqual(self.text, 'Acknowledgement')
                draft = json.loads(bridge.get_runtime(self.client.state_db,
                                  'native-text-draft:' + bridge.short_hash('Team')))
                self.assertEqual(draft['text'], 'Acknowledgement')
                self.assertFalse(bridge.get_runtime(self.client.state_db, 'native-intent:' + draft['key']))
                self.client.composer_keys.side_effect = self.keys
                result = self.client.send_text_locked('Team', replacement, task_id=task_id)
                self.assertTrue(result['ok'])
                self.assertEqual(self.sent[-1], replacement)
                self.assertFalse(self.text)
                before = list(self.sent)
                self.client.send_text_locked('Team', replacement, task_id=task_id)
                self.assertEqual(self.sent, before)

    def test_unknown_human_draft_is_preserved(self):
        self.text = 'My unfinished message'
        with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
            self.client.send_text_locked('Team', 'Answer', task_id='new')
        self.client.clear_composer.assert_not_called()
        self.client.composer_keys.assert_not_called()

    def test_edited_or_partial_owned_draft_is_preserved(self):
        self.journal()
        for text in ('Ack', 'Acknowledgement plus human edits'):
            self.text = text
            self.assertFalse(self.client.clear_owned_text_draft('window', 'Team'))
        self.client.clear_composer.assert_not_called()

    def test_wrong_chat_or_account_cannot_claim_draft(self):
        for changes in ({'chat': 'Other'}, {'sender': 'other'}, {'table': 'Msg_' + 'b' * 32}):
            self.journal(**changes)
            self.assertFalse(self.client.clear_owned_text_draft('window', 'Team'))
        self.client.clear_composer.assert_not_called()

    def test_added_attachment_is_preserved(self):
        self.journal()
        self.client.tiny11.invoke.return_value = ['C:/user-file.pdf']
        self.assertFalse(self.client.clear_owned_text_draft('window', 'Team'))
        self.client.clear_composer.assert_not_called()

    def test_post_enter_uncertainty_never_discards_or_retries_draft(self):
        self.journal()
        bridge.set_runtime(self.client.state_db, 'native-intent:owned', '{}')
        with self.assertRaisesRegex(RuntimeError, 'WECHAT_GUI_SEND_UNCERTAIN'):
            self.client.clear_owned_text_draft('window', 'Team')
        self.client.clear_composer.assert_not_called()

    def test_corrupt_journal_is_not_ownership(self):
        bridge.set_runtime(self.client.state_db, 'native-text-draft:' + bridge.short_hash('Team'), 'invalid')
        self.assertFalse(self.client.clear_owned_text_draft('window', 'Team'))
        self.client.clear_composer.assert_not_called()


if __name__ == '__main__':
    unittest.main()

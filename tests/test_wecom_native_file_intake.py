import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/scripts'))
import wecom_tiny11_gui_bridge as native
import wecom_gui_bridge as base


class NativeFileIntakeTests(unittest.TestCase):
    def assert_file_card(self, color):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screen = root / 'screen.png'
            image = Image.new('RGB', (600, 600), (246, 248, 251))
            ImageDraw.Draw(image).rectangle((10, 200, 265, 284), fill=color)
            image.save(screen)
            bridge = object.__new__(native.Tiny11WeComGuiBridge)
            bridge.runtime_dir = root
            bridge.history_surface = mock.Mock(return_value=(0, 0, 600, 600))
            bridge.extract_bubble_records = mock.Mock(return_value=[{
                'text': 'Please review my document.', '_screen_y': 100,
                'sender_label': 'Member', 'sender_fingerprint': 'member',
            }])
            bridge.ocr_scaled = mock.Mock(return_value='Research_Proposal.docx\n10.38M')
            bridge.extract_sender_identity = mock.Mock(return_value=('Member', 'member'))
            records, _ = bridge.extract_inbound_records(screen, None, 'LabAgent')
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['text'], 'Please review my document.')
        self.assertIn('Research_Proposal.docx', records[1]['text'])
        self.assertEqual(records[1]['sender_label'], 'Member')
        self.assertIn('native_file_card', records[1])

    def test_native_white_file_card_is_not_lost_behind_text_bubbles(self):
        self.assert_file_card('white')

    def test_selected_file_card_survives_export_retry(self):
        self.assert_file_card((200, 222, 251))

    def test_passive_change_detection_includes_the_newest_native_history_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screen.png'
            bridge = object.__new__(native.Tiny11WeComGuiBridge)
            window = base.Window('1', 0, 0, 1276, 1392)
            image = Image.new('RGB', (2560, 1440), 'white')
            image.save(path)
            original = bridge.passive_screen_signature(path, window)
            ImageDraw.Draw(image).rectangle((330, 1150, 600, 1200), fill='gray')
            image.save(path)
            latest = bridge.passive_screen_signature(path, window)
            self.assertNotEqual(latest, original)
            ImageDraw.Draw(image).rectangle((330, 1290, 600, 1320), fill='black')
            image.save(path)
            self.assertEqual(bridge.passive_screen_signature(path, window), latest)

    def bridge(self, root):
        bridge = object.__new__(native.Tiny11WeComGuiBridge)
        bridge.event_root = root
        bridge.tiny11 = mock.Mock(remote_root=r'C:\LabCanvas\WeComBridge',
                                  ssh_port=2290, user='test', host='127.0.0.1')
        bridge.right_click = mock.Mock()
        bridge.set_clipboard = mock.Mock()
        bridge.click_native_menu_item = mock.Mock()
        bridge.get_clipboard = mock.Mock(return_value='[File: Proposal.docx]')
        bridge.tiny11.invoke.return_value = {'filename': 'Proposal.docx'}
        bridge.tiny11.health.return_value = {'ok': True, 'input_ready': True, 'client_state': 'ready'}
        bridge.find_window = mock.Mock(return_value=None)
        bridge.dismiss_transient_overlays = mock.Mock()
        return bridge

    def test_only_exact_card_export_is_transferred_and_checksum_verified(self):
        content = b'PK-exact-native-file-payload'
        record = {'sender_fingerprint': 'member', 'native_file_card': {
            'x': 100, 'y': 200, 'label': 'Proposal.docx\n10KB'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = self.bridge(root)
            bridge.tiny11.powershell.side_effect = ['', json.dumps({
                'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})]
            def scp(args, **kwargs):
                self.assertEqual(args[0], 'scp')
                Path(args[-1]).write_bytes(content)
            with mock.patch.object(native.subprocess, 'run', side_effect=scp), \
                    mock.patch.object(native.time, 'sleep'):
                attachments = bridge.materialize_inbound_attachments('LabAgent', [record])
                self.assertEqual(Path(attachments[0]['path']).read_bytes(), content)
                self.assertEqual(Path(attachments[0]['path']).stat().st_mode & 0o777, 0o600)
                self.assertEqual(bridge.tiny11.invoke.call_count, 2)
                bridge.get_clipboard.assert_not_called()
                attachments_again = bridge.materialize_inbound_attachments('LabAgent', [record])
                self.assertEqual(attachments_again, attachments)
                self.assertEqual(bridge.tiny11.invoke.call_count, 2)

    def test_different_native_filename_never_substitutes_a_nearby_file(self):
        record = {'native_file_card': {'x': 10, 'y': 20, 'label': 'Other.docx\n10KB'}}
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.bridge(Path(tmp))
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                bridge.materialize_inbound_attachments('LabAgent', [record])
            self.assertNotIn(mock.call({'action': 'save_received_file'}), bridge.tiny11.invoke.mock_calls)
            self.assertEqual(bridge.tiny11.invoke.call_args, mock.call({'action': 'cancel_received_file'}))

    def test_failed_export_is_cancelled_without_advancing_the_message(self):
        record = {'native_file_card': {'x': 10, 'y': 20, 'label': 'Proposal.docx\n10KB'}}
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.bridge(Path(tmp))
            bridge.tiny11.powershell.return_value = ''
            bridge.tiny11.invoke.side_effect = [
                {'filename': 'Proposal.docx'}, RuntimeError('export failed'), {'cancelled': True}]
            with mock.patch.object(native.time, 'sleep'), self.assertRaisesRegex(RuntimeError, 'export failed'):
                bridge.materialize_inbound_attachments('LabAgent', [record])
            self.assertEqual(bridge.tiny11.invoke.call_args, mock.call({'action': 'cancel_received_file'}))
            self.assertEqual(list(Path(tmp).rglob('native-file-export.json')), [])

    def test_completed_guest_export_is_recovered_after_host_crash(self):
        content = b'PK-verified-original'
        record = {'native_file_card': {'x': 10, 'y': 20, 'label': 'Proposal.docx\n10KB'}}
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.bridge(Path(tmp))
            bridge.tiny11.powershell.return_value = json.dumps({
                'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
            with mock.patch.object(native.subprocess, 'run',
                                   side_effect=lambda args, **kw: Path(args[-1]).write_bytes(content)), \
                    mock.patch.object(native.time, 'sleep'):
                files = bridge.materialize_inbound_attachments('LabAgent', [record])
            self.assertEqual(Path(files[0]['path']).read_bytes(), content)
            self.assertEqual([c.args[0]['action'] for c in bridge.tiny11.invoke.call_args_list],
                             ['received_file_name', 'cancel_received_file'])

    def test_attachment_failure_preserves_cursor_and_success_passes_original_to_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / 'state.sqlite'
            base.init_state_db(state)
            base.save_snapshot(state, 'LabAgent', ['previous request'], 'old')
            screen = root / 'screen.png'
            Image.new('RGB', (10, 10), 'white').save(screen)
            event = root / 'event.json'
            event.write_text('{}')
            bridge = object.__new__(base.WeComGuiBridge)
            bridge.state_db = state
            bridge.ensure_chat = mock.Mock(return_value=base.Window('1', 0, 0, 1276, 1392))
            bridge.scroll_chat_to_bottom = mock.Mock()
            bridge.capture_screen = mock.Mock(return_value=screen)
            bridge.extract_inbound_records = mock.Mock(return_value=([
                {'text': 'previous request'}, {'text': '[WeCom file] Proposal.docx'}], screen))
            bridge.materialize_inbound_attachments = mock.Mock(side_effect=RuntimeError('not saved yet'))
            bridge.build_event = mock.Mock(return_value=event)
            bridge.invoke_ingest = mock.Mock(return_value={'queued': True})
            with self.assertRaisesRegex(RuntimeError, 'not saved yet'):
                bridge.poll_chat('LabAgent')
            self.assertEqual(base.load_snapshot(state, 'LabAgent')[0], ['previous request'])
            bridge.build_event.assert_not_called()
            bridge.invoke_ingest.assert_not_called()
            original = {'filename': 'Proposal.docx', 'path': str(root / 'Proposal.docx')}
            bridge.materialize_inbound_attachments.side_effect = None
            bridge.materialize_inbound_attachments.return_value = [original]
            self.assertEqual(bridge.poll_chat('LabAgent')['processed'], 1)
            self.assertEqual(bridge.build_event.call_args.kwargs['attachments'], [original])
            self.assertEqual(base.load_snapshot(state, 'LabAgent')[0][-1], '[WeCom file] Proposal.docx')

    def test_file_export_keeps_standard_dialog_and_private_destination_guards(self):
        source = (ROOT / 'agentic_tools/wecom_agent/windows/WeComBridge.ps1').read_text()
        self.assertIn('save_received_file', source)
        self.assertIn("$_.ClassName -eq '#32770'", source)
        self.assertIn('GetFileNameWithoutExtension', source)
        self.assertIn("Join-Path $BridgeRoot 'intake'", source)
        self.assertIn('UniqueChildControl', source)
        self.assertIn('FocusDialogControl', source)
        self.assertIn("SendWait('^a^v')", source)
        self.assertNotIn('AutomationElement', source)

    def test_native_empty_editor_is_independent_of_selected_history_clipboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screen.png'
            bridge = object.__new__(native.Tiny11WeComGuiBridge)
            bridge.capture_screen = mock.Mock(return_value=path)
            window = base.Window('1', 0, 0, 1276, 1392)
            for content, expected in [('empty', True), ('caret', True), ('draft', False), ('file', False)]:
                with self.subTest(content=content):
                    image = Image.new('RGB', (2560, 1440), 'white')
                    draw = ImageDraw.Draw(image)
                    if content == 'caret':
                        draw.rectangle((330, 1280, 331, 1297), fill='black')
                    elif content == 'draft':
                        draw.text((330, 1280), 'unsent draft', fill='black')
                    elif content == 'file':
                        draw.rectangle((330, 1280, 400, 1330), fill='blue')
                    image.save(path)
                    with mock.patch.object(base.WeComGuiBridge, 'composer_is_empty', return_value=False):
                        self.assertEqual(bridge.composer_is_empty(window, 'test'), expected)


if __name__ == '__main__':
    unittest.main()

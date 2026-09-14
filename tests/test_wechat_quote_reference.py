from __future__ import annotations

import html
from pathlib import Path
import sys
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))

import wechat_direct_chatops as direct
import wechat_quote_reference as quotes
import wechat_source_recovery as recovery
import wechat_task_worker as worker


def card(identity="111", author="Alice", title="First performance"):
    return ('<msg><appmsg><title>Update your WeChat version</title><type>51</type>'
            f'<finderFeed><objectId>{identity}</objectId><nickname>{author}</nickname>'
            f'<desc>{title}</desc></finderFeed></appmsg></msg>')


def reply(body, request="Download this video", reference_type="49"):
    return ('<msg><appmsg><type>57</type><title>' + html.escape(request) + '</title>'
            '<refermsg><type>' + reference_type + '</type><svrid>11111111</svrid>'
            '<displayname>Bob</displayname><content>' + html.escape(body)
            + '</content></refermsg></appmsg></msg>')


def task(body):
    return {'chat': 'Test', 'request': 'Download this video',
            'source': {'chat': 'Test', 'message_db': 'message_1.db', 'local_id': 30,
                       'server_id': '33333333', 'kind': 'quote_reply'},
            'context': [{'chat': 'Test', 'message_db': 'message_1.db', 'local_id': 29,
                         'server_id': '22222222', 'content': card('222', 'Carol', 'Newer video')},
                        {'chat': 'Test', 'message_db': 'message_1.db', 'local_id': 30,
                         'server_id': '33333333', 'content': body}],
            'route_decision': {'route_kind': 'file_download_or_save', 'needs_recent_media': True,
                               'delivery_mode': 'chat_attachment'}}


class QuoteReferenceTests(unittest.TestCase):
    def test_native_escaped_quote_retains_identity_without_original_row(self):
        t = task(reply(card()))
        self.assertEqual(worker.shipinhao_profile_for_task(t)['object_id'], '111')
        self.assertEqual(worker.selected_shipinhao_context_text(t), card())
        self.assertEqual(worker.shipinhao_source_text_for_task(t, {'object_id': '111'}), card())
        self.assertTrue(worker.should_prepare_shipinhao_media_transcript(t))
        self.assertFalse(worker.should_preflight_autopublish(t))
        self.assertFalse(worker.is_video_publish_task(t))
        visible = direct.format_quote_reply_text(t['context'][-1]['content'])
        self.assertIn('quoted Bob', visible)
        self.assertIn('Alice', visible)
        self.assertIn('First performance', visible)
        self.assertNotIn('Newer video', visible)

    def test_consecutive_quotes_do_not_select_previous_quote(self):
        t = task(reply(card('333', 'Dan', 'Second video'), 'Also this'))
        t['request'] = 'Current coalesced request:\n' + reply(card()) + '\nAlso this'
        t['context'].insert(0, {'local_id': 28, 'message_db': 'message_1.db',
                              'content': reply(card())})
        self.assertEqual(worker.shipinhao_profile_for_task(t)['object_id'], '333')

    def test_recent_artifact_shortcut_cannot_override_even_unresolved_quote(self):
        for content in (reply(card()), '<broken quote>'):
            t = task(content)
            self.assertFalse(worker.should_resolve_recent_video_artifact(t))
            with mock.patch.object(worker, 'read_tasks') as read:
                self.assertFalse(worker.resolve_recent_video_artifact_preflight(t)['ok'])
                read.assert_not_called()
            self.assertIsNone(worker.resolved_video_artifact_result(t, {'status': 'recent-artifact-match'}))

    def test_same_local_id_other_shard_or_chat_is_not_source(self):
        for field, value in (('message_db', 'message_2.db'), ('chat', 'Other'),
                             ('server_id', '44444444')):
            t = task(reply(card()))
            t['context'][-1][field] = value
            self.assertIsNone(quotes.task_quote_reference(t))
            self.assertFalse(worker.shipinhao_profile_for_task(t).get('object_id'))
            self.assertEqual(recovery.task_source_text(t), '')

    def test_quote_article_not_replaced_by_adjacent_finder(self):
        article = '<msg><appmsg><type>5</type><url>https://mp.weixin.qq.com/s/EXACT</url></appmsg></msg>'
        t = task(reply(article))
        self.assertIn('/s/EXACT', recovery.task_source_text(t))
        self.assertNotIn('finderFeed', recovery.task_source_text(t))
        self.assertFalse(worker.shipinhao_profile_for_task(t).get('object_id'))

    def test_source_reference_rows_only_include_explicit_refs_and_each_request(self):
        original = {'local_id': 1, 'server_id': '11111111', 'content': card(), 'local_type': 49}
        newer = {'local_id': 2, 'server_id': '22222222', 'content': card('222'), 'local_type': 49}
        row = {'local_id': 3, 'server_id': '33333333', 'content': reply(card()), 'local_type': (57 << 32) | 49}
        self.assertEqual(direct.source_reference_rows({}, row, [original, newer, row]), [original, row])
        self.assertEqual(direct.source_reference_rows({}, row, [newer, row]), [row])

    def test_long_quoted_text_preserves_tail_instructions(self):
        text = 'background ' * 35 + 'Please compare evidence and return a PDF.'
        formatted = direct.format_quote_reply_text(reply(text, reference_type='1'))
        self.assertIn('Please compare evidence and return a PDF.', formatted)

    def test_sanitized_backend_context_preserves_quote_meaning_without_tokens(self):
        payload = card().replace('</finderFeed>', '<mediaUrl>https://secret/?token=SECRET</mediaUrl></finderFeed>')
        output = worker.sanitize_worker_agent_text(reply(payload), max_len=1400)
        self.assertIn('Bob', output)
        self.assertIn('First performance', output)
        self.assertNotIn('SECRET', output)
        self.assertNotIn('<finderFeed>', output)

    def test_whole_envelope_escaped_and_group_prefix(self):
        value = 'member:\n' + html.escape(reply(card()))
        self.assertEqual(quotes.parse_quote_reference(value)['content'], card())


if __name__ == '__main__':
    unittest.main()

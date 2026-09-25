import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agentic_tools/wechat_gui_agent/scripts'))
import wechat_daily_brief as brief


class DailyBriefTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.schedule = dict(id='company', enabled=True, time='19:00', timezone='Asia/Hong_Kong',
                             max_chars=200, instruction='Market insight and practical advice',
                             direct_config=str(self.root / 'config.json'))
        self.config = {'chat_name': 'Company', 'session_scope': 'company-private',
                       'mirror_db': str(self.root / 'mirror.sqlite')}
        self.now = datetime(2026, 9, 25, 19, tzinfo=ZoneInfo('Asia/Hong_Kong'))
        self.content = {'message': '先验证客户是否愿意付费，再扩大产品范围。', 'sources': ['https://example.com/evidence']}
        for name, value in [('load_config', self.config), ('send_gui_message', 'verified receipt')]:
            patcher = mock.patch.object(brief.direct, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(brief, 'generate_brief', return_value=self.content)
        self.generate = patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_clock_timezone_and_daily_deduplication(self):
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now - timedelta(seconds=1))['status'], 'not_due')
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now.astimezone(ZoneInfo('UTC')))['status'], 'sent')
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now + timedelta(hours=2))['status'], 'already_sent')
        self.generate.assert_called_once()
        self.send_gui_message.assert_called_once()

    def test_preview_does_not_consume_evening_delivery(self):
        morning = self.now.replace(hour=8)
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=morning, preview=True)['status'], 'sent')
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=morning, preview=True)['status'], 'already_sent')
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now)['status'], 'sent')
        ids = [c.args[0]['_android_task_id'] for c in self.send_gui_message.call_args_list]
        self.assertNotEqual(ids[0], ids[1])

    def test_delivery_retry_reuses_content_and_id(self):
        self.send_gui_message.side_effect = [RuntimeError('transport unavailable'), 'native receipt']
        with mock.patch.object(brief.time, 'time', return_value=self.now.timestamp()):
            self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now)['status'], 'retry_pending')
            self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now + timedelta(seconds=30))['status'], 'retry_pending')
            self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now + timedelta(minutes=6))['status'], 'sent')
        self.generate.assert_called_once()
        a, b = self.send_gui_message.call_args_list
        self.assertEqual(a.args, b.args)
        self.assertEqual((self.root / 'company/2026-09-25.json').stat().st_mode & 0o777, 0o600)

    def test_restart_after_send_before_state_commit_uses_same_sender_identity(self):
        real_write = brief.write_state
        failed = False
        def crash(path, state):
            nonlocal failed
            if state.get('status') == 'sent' and not failed:
                failed = True
                raise KeyboardInterrupt()
            real_write(path, state)
        with mock.patch.object(brief, 'write_state', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            brief.run_schedule(self.schedule, self.root, now=self.now)
        brief.run_schedule(self.schedule, self.root, now=self.now)
        self.generate.assert_called_once()
        self.assertEqual(*[call.args for call in self.send_gui_message.call_args_list])

    def test_no_receipt_no_success_and_disabled_does_no_work(self):
        self.schedule['enabled'] = False
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now)['status'], 'disabled')
        self.generate.assert_not_called()
        self.schedule['enabled'] = True
        self.send_gui_message.return_value = ''
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=self.now)['status'], 'retry_pending')

    def test_no_previous_day_backlog_replay(self):
        self.send_gui_message.side_effect = [RuntimeError('offline'), 'verified']
        brief.run_schedule(self.schedule, self.root, now=self.now)
        tomorrow = self.now + timedelta(days=1)
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=tomorrow.replace(hour=8))['status'], 'not_due')
        self.assertEqual(brief.run_schedule(self.schedule, self.root, now=tomorrow)['status'], 'sent')
        self.assertEqual(self.generate.call_count, 2)

    def test_character_and_source_contract_never_truncates(self):
        for length in (1, 200):
            data = {**self.content, 'message': '中' * length}
            self.assertEqual(brief.parse_brief(json.dumps(data), 200)['message'], data['message'])
        for data in ({**self.content, 'message': '中' * 201},
                     {**self.content, 'message': 'English only'},
                     {**self.content, 'sources': []},
                     {**self.content, 'sources': ['file:///private']},
                     {**self.content, 'message': '查看/home/user/private'}):
            with self.assertRaises(ValueError):
                brief.parse_brief(json.dumps(data), 200)

    def test_bad_config_fails_closed(self):
        for field, value in [('id', '../other'), ('time', '25:00'), ('max_chars', 0)]:
            with self.assertRaises(ValueError):
                brief.run_schedule({**self.schedule, field: value}, self.root, now=self.now)
        self.generate.assert_not_called()


class BriefGenerationTests(unittest.TestCase):
    def test_research_and_bounded_editor_keep_same_chat_and_sources(self):
        schedule = dict(id='company', instruction='Market advice', max_chars=200)
        config = dict(chat_name='Company only', session_scope='company-private',
                      mirror_db='/tmp/company-test.sqlite', assistant_context={
                          'brief': 'Company evidence', 'reference_paths': ['/private/company.md']})
        data = {'message': '建议先用付费试点验证客户需求。', 'sources': ['https://example.com/source']}
        responses = [dict(ok=True, message=json.dumps({**data, 'message': '中' * 201})),
                     dict(ok=True, message=json.dumps(data), backend='codex', model='test')]
        with mock.patch.object(brief, 'load_wechat_mirror_history', return_value=[]) as history, \
             mock.patch.object(brief, 'build_context_from_messages', return_value={'snapshot': 'same-chat memory'}), \
             mock.patch.object(brief, 'run_agent_session', side_effect=responses) as agent:
            result = brief.generate_brief(schedule, config, datetime.now(ZoneInfo('Asia/Hong_Kong')), 'previous')
        self.assertEqual(result['message'], data['message'])
        self.assertEqual(history.call_args.args[1], ['Company only'])
        self.assertIn('/private/company.md', agent.call_args_list[0].args[0])
        self.assertIn('live web search', agent.call_args_list[0].args[0])
        for call in agent.call_args_list:
            self.assertEqual(call.kwargs['chat_name'], 'company-private')
            self.assertEqual(call.kwargs['sandbox'], 'read-only')
            self.assertTrue(call.kwargs['reuse'])

    def test_backend_error_is_not_sent_as_a_brief(self):
        config = dict(chat_name='Company', mirror_db='/tmp/company-test.sqlite')
        with mock.patch.object(brief, 'load_wechat_mirror_history', return_value=[]), \
             mock.patch.object(brief, 'build_context_from_messages', return_value={}), \
             mock.patch.object(brief, 'run_agent_session', return_value={'ok': False, 'message': 'quota failure'}), \
             self.assertRaises(RuntimeError):
            brief.generate_brief({'id': 'company', 'instruction': 'research', 'max_chars': 200},
                                 config, datetime.now(ZoneInfo('Asia/Hong_Kong')), '')


if __name__ == '__main__':
    unittest.main()

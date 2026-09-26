from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'expired_delivery_guard', ROOT / 'agentic_tools/wechat_gui_agent/scripts/wechat_transport_stall_guard.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class ExpiredDeliveryHealthTests(unittest.TestCase):
    def test_recent_expiry_is_visible_without_requeueing_or_replaying(self):
        task = {'id': 'unsent-answer', 'status': 'send_expired',
                'created_at': '2026-09-25T06:00:00+00:00',
                'last_send_attempt_at': '2026-09-25T06:01:00+00:00',
                'expired_at': '2026-09-26T02:30:00+00:00'}
        now = datetime(2026, 9, 26, 3, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / 'queue.jsonl'
            before = json.dumps(task) + '\n'
            queue.write_text(before)
            result = guard.queue_health(queue, now=now)
            self.assertFalse(result['ok'])
            self.assertEqual(result['deferred_delivery_ids'], ['unsent-answer'])
            self.assertEqual(guard.queue_health_issue('wechat', result)['code'], 'wechat_queue_delivery_pending')
            self.assertEqual(queue.read_text(), before)
            task['status'] = 'done'
            queue.write_text(json.dumps(task) + '\n')
            self.assertTrue(guard.queue_health(queue, now=now)['ok'])

    def test_old_expired_backlog_does_not_trigger_permanent_alerts(self):
        task = {'id': 'historical', 'status': 'send_expired',
                'expired_at': '2026-09-24T02:30:00+00:00'}
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / 'queue.jsonl'
            queue.write_text(json.dumps(task) + '\n')
            result = guard.queue_health(queue, now=datetime(2026, 9, 26, 3, 0, tzinfo=timezone.utc))
            self.assertTrue(result['ok'])
            self.assertEqual(result['deferred_delivery_ids'], [])


if __name__ == '__main__':
    unittest.main()

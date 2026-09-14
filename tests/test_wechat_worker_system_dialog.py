import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agentic_tools/wechat_gui_agent/scripts'))
import wechat_task_worker as worker


class SystemDialogDeliveryTests(unittest.TestCase):
    def test_pre_send_system_dialog_is_deferred_as_gui_busy(self):
        errors = ['LABCANVAS_GUI_SYSTEM_DIALOG_BLOCKED: windows_system_dialog']
        self.assertTrue(worker.send_errors_indicate_deferable(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), 'gui_send_busy')
        self.assertFalse(worker.send_errors_indicate_wecom_auth_required(errors))

    def test_uncertain_submission_is_never_downgraded_to_busy(self):
        errors = ['WECHAT_GUI_SEND_UNCERTAIN: LABCANVAS_GUI_SYSTEM_DIALOG_BLOCKED: windows_system_dialog']
        self.assertFalse(worker.send_errors_indicate_gui_busy(errors))
        self.assertEqual(worker.send_deferred_reason_from_errors(errors), 'gui_postcommit_uncertain')

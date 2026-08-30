from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_retention_module():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_output_retention.py"
    spec = importlib.util.spec_from_file_location("wechat_output_retention_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatOutputRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "output"
        self.root.mkdir()
        self.module = load_retention_module()
        self.module.PRIVATE = Path(self.temp_dir.name) / "private"
        self.now = time.time()

    def run_retention(self):
        return self.module.maintain_output(
            self.root,
            max_log_bytes=100,
            keep_log_bytes=40,
            log_retention_seconds=14 * 86400,
            attempt_retention_seconds=86400,
            sent_retention_seconds=30 * 86400,
            diagnostic_retention_seconds=14 * 86400,
            now=self.now,
        )

    def age(self, path: Path, days: float) -> None:
        timestamp = self.now - days * 86400
        os.utime(path, (timestamp, timestamp))

    def test_trims_active_log_to_recent_complete_lines(self) -> None:
        log = self.root / "supervisor.log"
        log.write_bytes((b"old-line\n" * 20) + b"recent-one\nrecent-two\n")

        result = self.run_retention()

        self.assertEqual(result["trimmed_logs"], 1)
        self.assertLessEqual(log.stat().st_size, 40)
        self.assertTrue(log.read_bytes().endswith(b"recent-two\n"))

    def test_removes_old_logs_and_transient_screenshots_but_keeps_reports(self) -> None:
        old_log = self.root / "old.log"
        old_attempt = self.root / "01-EchoMind-120000-000001-before.png"
        recent_sent = self.root / "01-EchoMind-120001-000002-sent.png"
        old_sent = self.root / "01-EchoMind-120002-000003-sent.png"
        report = self.root / "language-review.pdf"
        for path in (old_log, old_attempt, recent_sent, old_sent, report):
            path.write_bytes(b"evidence")
        self.age(old_log, 15)
        self.age(old_attempt, 2)
        self.age(recent_sent, 2)
        self.age(old_sent, 31)
        self.age(report, 365)

        result = self.run_retention()

        self.assertEqual(result["removed_files"], 3)
        self.assertFalse(old_log.exists())
        self.assertFalse(old_attempt.exists())
        self.assertTrue(recent_sent.exists())
        self.assertFalse(old_sent.exists())
        self.assertTrue(report.exists())

    def test_keeps_open_old_log_and_trims_it_in_place(self) -> None:
        active_log = self.root / "still-open.log"
        active_log.write_bytes((b"old-line\n" * 20) + b"recent-line\n")
        self.age(active_log, 15)

        with active_log.open("ab"):
            result = self.run_retention()

        self.assertTrue(active_log.exists())
        self.assertEqual(result["removed_files"], 0)
        self.assertEqual(result["trimmed_logs"], 1)
        self.assertTrue(active_log.read_bytes().endswith(b"recent-line\n"))

    def test_does_not_delete_unrelated_numbered_project_image(self) -> None:
        unrelated = self.root / "01-mechanism-figure.png"
        unrelated.write_bytes(b"figure")
        self.age(unrelated, 10)

        result = self.run_retention()

        self.assertEqual(result["removed_files"], 0)
        self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()

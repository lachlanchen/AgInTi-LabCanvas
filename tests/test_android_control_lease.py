import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_lease():
    path = ROOT / "agentic_tools" / "android_device_agent" / "scripts" / "android_control_lease.py"
    spec = importlib.util.spec_from_file_location("android_control_lease_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AndroidControlLeaseTests(unittest.TestCase):
    def test_priority_control_writes_claim_while_holding_lock_and_cleans_up(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            lock = root / "android.lock"
            with module.priority_android_control(
                lock_path=lock,
                priority_path=marker,
                purpose="personal_wechat_send",
                timeout_seconds=1,
            ) as claim:
                stored = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual(stored["token"], claim["token"])
                self.assertEqual(stored["purpose"], "personal_wechat_send")
                self.assertEqual(stored["pid"], os.getpid())
            self.assertFalse(marker.exists())

    def test_expired_priority_is_not_active(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "priority.json"
            marker.write_text(
                json.dumps(
                    {
                        "token": "expired",
                        "pid": os.getpid(),
                        "expires_at": 10.0,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(module, "process_is_alive", return_value=True):
                self.assertIsNone(module.read_active_priority(marker, now=11.0))
            self.assertFalse(marker.exists())

    def test_live_foreign_priority_is_active(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "priority.json"
            marker.write_text(
                json.dumps(
                    {
                        "token": "live",
                        "pid": 12345,
                        "purpose": "personal_wechat_send",
                        "expires_at": 20.0,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(module, "process_is_alive", return_value=True):
                active = module.read_active_priority(marker, exclude_pid=999, now=10.0)
            self.assertEqual(active["purpose"], "personal_wechat_send")

    def test_passive_control_yields_to_live_explicit_priority(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            marker.write_text(
                json.dumps(
                    {
                        "token": "live",
                        "pid": 12345,
                        "purpose": "personal_wechat_send",
                        "expires_at": 20.0,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(module, "process_is_alive", return_value=True), mock.patch.object(
                module.time, "time", return_value=10.0
            ):
                with self.assertRaisesRegex(module.AndroidControlBusy, "personal_wechat_send"):
                    with module.passive_android_control(
                        lock_path=root / "android.lock",
                        priority_path=marker,
                        purpose="screen_ingress",
                    ):
                        self.fail("passive work must not acquire the lane")

    def test_passive_control_does_not_create_a_priority_claim(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            with module.passive_android_control(
                lock_path=root / "android.lock",
                priority_path=marker,
                purpose="screen_ingress",
            ) as claim:
                self.assertEqual(claim["purpose"], "screen_ingress")
                self.assertFalse(marker.exists())
            self.assertFalse(marker.exists())

    def test_cooperative_control_waits_without_creating_priority_claim(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            attempts = [BlockingIOError(), None]

            def flock(_handle, _operation):
                outcome = attempts.pop(0) if attempts else None
                if isinstance(outcome, Exception):
                    raise outcome

            with mock.patch.object(module.fcntl, "flock", side_effect=flock), mock.patch.object(
                module.time, "sleep"
            ):
                with module.cooperative_android_control(
                    lock_path=root / "android.lock",
                    priority_path=marker,
                    purpose="screen_ingress",
                    timeout_seconds=1,
                ) as claim:
                    self.assertEqual(claim["purpose"], "screen_ingress")
                    self.assertFalse(marker.exists())

            self.assertFalse(marker.exists())

    def test_cooperative_control_yields_to_explicit_priority(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            marker.write_text(
                json.dumps(
                    {
                        "token": "live",
                        "pid": 12345,
                        "purpose": "artifact_send",
                        "expires_at": 20.0,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(module, "process_is_alive", return_value=True), mock.patch.object(
                module.time, "time", return_value=10.0
            ):
                with self.assertRaisesRegex(module.AndroidControlBusy, "artifact_send"):
                    with module.cooperative_android_control(
                        lock_path=root / "android.lock",
                        priority_path=marker,
                        purpose="screen_ingress",
                        timeout_seconds=1,
                    ):
                        self.fail("cooperative work must yield to explicit work")

    def test_run_cli_returns_child_status_and_cleans_priority_marker(self):
        module = load_lease()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "priority.json"
            lock = root / "android.lock"
            argv = [
                "android_control_lease.py",
                "run",
                "--lock-path",
                str(lock),
                "--priority-path",
                str(marker),
                "--purpose",
                "dual-review-test",
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ]
            with mock.patch.object(sys, "argv", argv):
                returncode = module.main()

            self.assertEqual(returncode, 7)
            self.assertFalse(marker.exists())

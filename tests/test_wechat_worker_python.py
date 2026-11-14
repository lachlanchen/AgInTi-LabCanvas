import os
from pathlib import Path
import subprocess
import tempfile
import unittest


WRAPPER = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts/wechat_worker_guarded_loop.sh"


class WeChatWorkerPythonTests(unittest.TestCase):
    def test_configured_interpreter_is_used_and_inherited_by_child_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            interpreter = root / "worker-python"
            interpreter.write_text('#!/bin/sh\nprintf "%s\\n" "$0" "$PATH" "$@"\n')
            interpreter.chmod(0o700)
            config = root / "worker.env"
            config.write_text(f'export WECHAT_WORKER_PYTHON="{interpreter}"\n')
            env = {**os.environ, "WECHAT_WORKER_ENV_FILE": str(config),
                   "WECHAT_WORKER_SKIP_SELFTEST": "1"}
            result = subprocess.run(["bash", str(WRAPPER), "--help"], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(lines[0], str(interpreter))
            self.assertEqual(lines[1].split(os.pathsep)[0], str(root))
            self.assertEqual(lines[2], "-u")
            self.assertTrue(lines[3].endswith("wechat_task_worker.py"))

    def test_missing_explicit_interpreter_does_not_silently_switch_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "WECHAT_WORKER_ENV_FILE": str(Path(tmp) / "absent.env"),
                   "WECHAT_WORKER_SKIP_SELFTEST": "1", "WECHAT_WORKER_PYTHON": "/missing/worker-python"}
            result = subprocess.run(["bash", str(WRAPPER), "--help"], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

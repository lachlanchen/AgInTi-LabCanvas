import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh"
COMPAT = ROOT / "agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh"


class JlcBrowserStackTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str, env=None):
        return subprocess.run(
            [str(script), *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_config_is_dedicated_and_non_launching(self):
        result = self.run_script(STACK, "config", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["display"], ":104")
        self.assertEqual(config["vnc_port"], 5924)
        self.assertEqual(config["novnc_port"], 6124)
        self.assertEqual(config["cdp_port"], 49237)
        self.assertIn("jlcpcb-order-shared", config["profile"])
        self.assertNotEqual(config["cdp_port"], 9344)
        self.assertNotEqual(config["novnc_port"], 6099)
        self.assertNotIn("xyq-chrome", config["profile"])

    def test_status_does_not_require_or_start_browser(self):
        result = self.run_script(STACK, "status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertIn("ready", status)
        self.assertEqual(status["cdp_port"], 49237)
        self.assertEqual(status["novnc_port"], 6124)

    def test_compatibility_launcher_rejects_cross_browser_tab_target(self):
        env = os.environ.copy()
        env["JLCPCB_TAB_CDP_PORT"] = "9344"
        result = self.run_script(COMPAT, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no longer supported", result.stderr)
        self.assertIn("XYQ profile is left untouched", result.stderr)


if __name__ == "__main__":
    unittest.main()

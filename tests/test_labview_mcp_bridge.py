import subprocess
import sys
import unittest
from pathlib import Path


class LabVIEWMcpBridgeTests(unittest.TestCase):
    def test_bridge_smoke_script(self):
        script = Path("agentic_tools/labview_mcp_agent/scripts/test_mcp_bridge.py")
        result = subprocess.run(
            [sys.executable, str(script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MCP bridge smoke test passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

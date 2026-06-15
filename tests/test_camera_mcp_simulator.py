import os
import subprocess
import sys
import unittest
from pathlib import Path


class CameraMcpSimulatorTests(unittest.TestCase):
    def test_camera_mcp_simulator_smoke_script(self):
        script = Path("agentic_tools/labview_mcp_agent/scripts/test_camera_mcp_simulator.py")
        result = subprocess.run(
            [sys.executable, str(script)],
            env={**os.environ, "LABCANVAS_CAMERA_NO_PIL": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Camera MCP simulator smoke test passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

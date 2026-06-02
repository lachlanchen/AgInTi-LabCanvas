import io
from contextlib import redirect_stdout
import tempfile
from pathlib import Path
import unittest

from agenticapp.cli import main


class CliTests(unittest.TestCase):
    def test_list_reads_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "targets.json"
            config.write_text(
                '{"targets":[{"name":"unreal","kind":"unreal","transport":{"type":"noop"}}]}',
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["--config", str(config), "list"])

        self.assertEqual(code, 0)
        self.assertIn("unreal", stdout.getvalue())

    def test_mcp_config_filters_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "targets.json"
            config.write_text(
                '{"targets":[{"name":"blender","kind":"blender","mcp":{"command":"uvx","args":["blender-mcp"]}},'
                '{"name":"unity","kind":"unity","mcp":{"command":"uvx","args":["unity-mcp"]}}]}',
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["--config", str(config), "mcp-config", "--only", "unity"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("unity-mcp", output)
        self.assertNotIn("blender-mcp", output)


if __name__ == "__main__":
    unittest.main()

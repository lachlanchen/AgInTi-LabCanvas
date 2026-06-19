import json
import os
from pathlib import Path
import stat
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NpmPackageTests(unittest.TestCase):
    def test_package_manifest_exposes_cli_bins(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["name"], "@lazyingart/labcanvas")
        self.assertEqual(package["bin"]["labcanvas"], "bin/labcanvas.js")
        self.assertEqual(package["bin"]["app-auto-action"], "bin/app-auto-action.js")
        self.assertEqual(package["bin"]["agenticapp"], "bin/agenticapp.js")
        self.assertIn("src/agenticapp/**/*.py", package["files"])
        self.assertIn("src/agenticapp/web/static/*", package["files"])
        self.assertIn("agentic_tools/wechat_gui_agent/scripts/*.py", package["files"])
        self.assertIn("agentic_tools/wechat_gui_agent/scripts/*.sh", package["files"])
        self.assertIn("agentic_tools/virtual_desktop/", package["files"])
        self.assertIn("configs/", package["files"])
        self.assertIn("examples/", package["files"])
        self.assertEqual(package["scripts"]["wechat:start"], "labcanvas wechat stack start")

    def test_npm_bin_wrappers_are_executable_and_set_pythonpath(self):
        wrapper = ROOT / "bin" / "labcanvas.js"
        mode = wrapper.stat().st_mode
        text = wrapper.read_text(encoding="utf-8")

        if os.name == "nt":
            self.assertTrue(text.startswith("#!/usr/bin/env node"))
        else:
            self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(text.startswith("#!/usr/bin/env node"))
        self.assertIn("PYTHONPATH", text)
        self.assertIn("agenticapp", text)


if __name__ == "__main__":
    unittest.main()

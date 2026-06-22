from pathlib import Path
import os
import stat
import unittest

from agenticapp.config import load_config


ROOT = Path(__file__).resolve().parents[1]


class BlenderBridgeTests(unittest.TestCase):
    def test_local_blender_config_uses_command_wrapper(self):
        config = load_config(ROOT / "configs" / "blender-local-command.example.json")
        target = config.get_target("blender")

        self.assertEqual(target.transport["type"], "local_command")
        self.assertEqual(target.transport["command"], ["./bridges/codex_exec_blender.sh"])

    def test_wrapper_is_executable(self):
        wrapper = ROOT / "bridges" / "codex_exec_blender.sh"
        mode = wrapper.stat().st_mode

        if os.name == "nt":
            self.assertTrue(wrapper.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash"))
        else:
            self.assertTrue(mode & stat.S_IXUSR)

    def test_blender_bridge_script_exists(self):
        script = ROOT / "bridges" / "blender_building_bridge.py"

        self.assertIn("create_building_scene", script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

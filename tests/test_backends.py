import tempfile
from pathlib import Path
import unittest

from agenticapp.backends import default_backend_settings, load_backend_settings, save_backend_settings


class BackendSettingsTests(unittest.TestCase):
    def test_default_toolchain_exposes_studio_tools(self):
        settings = default_backend_settings()

        self.assertEqual(settings["agent"]["backend"], "codex")
        self.assertEqual(settings["agent"]["model"], "gpt-5.6-sol")
        self.assertEqual(settings["model_policy"]["primary_backend"], "codex")
        self.assertEqual(settings["model_policy"]["aginti"]["provider_chain"], ["deepseek", "localllm"])
        self.assertTrue(settings["agent"]["dynamic_routing"])
        self.assertTrue(settings["toolchain"]["cad"])
        self.assertTrue(settings["toolchain"]["kicad"])
        self.assertTrue(settings["toolchain"]["tex"])
        self.assertTrue(settings["toolchain"]["wechat"])
        self.assertTrue(settings["toolchain"]["labview"])
        self.assertTrue(settings["toolchain"]["blender"])
        self.assertTrue(settings["toolchain"]["openscad"])
        self.assertTrue(settings["toolchain"]["aginti_image"])
        self.assertTrue(settings["toolchain"]["target_registry"])
        self.assertEqual(settings["writing"]["provider"], "deepseek")
        self.assertEqual(settings["writing"]["api_key_env"], "DEEPSEEK_API_KEY")

    def test_saved_settings_merge_new_toolchain_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_backend_settings(path, {"toolchain": {"biorender": True}})
            settings = load_backend_settings(path)

        self.assertTrue(settings["toolchain"]["biorender"])
        self.assertTrue(settings["toolchain"]["aginti_image"])
        self.assertEqual(settings["writing"]["model"], "deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()

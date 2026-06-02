import tempfile
from pathlib import Path
import unittest

from agenticapp.backends import default_backend_settings, load_backend_settings, save_backend_settings


class BackendSettingsTests(unittest.TestCase):
    def test_default_toolchain_exposes_studio_tools(self):
        settings = default_backend_settings()

        self.assertTrue(settings["toolchain"]["blender"])
        self.assertTrue(settings["toolchain"]["openscad"])
        self.assertTrue(settings["toolchain"]["aginti_image"])
        self.assertTrue(settings["toolchain"]["target_registry"])

    def test_saved_settings_merge_new_toolchain_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_backend_settings(path, {"toolchain": {"biorender": True}})
            settings = load_backend_settings(path)

        self.assertTrue(settings["toolchain"]["biorender"])
        self.assertTrue(settings["toolchain"]["aginti_image"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_gui_audio_capture.py"
    spec = importlib.util.spec_from_file_location("shipinhao_gui_audio_capture_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ShipinhaoGuiAudioCaptureTests(unittest.TestCase):
    def test_identity_terms_prefer_book_title_hashtags_and_author(self) -> None:
        module = load_module()

        terms = module.derive_identity_terms(
            "蒋勋开讲《寒食帖》#寒食帖#苏东坡书法",
            "我是大熊熊.",
        )

        self.assertIn("寒食帖", terms)
        self.assertIn("苏东坡书法", terms)
        self.assertIn("我是大熊熊", terms)

    def test_pipewire_stream_is_limited_to_wechat_and_display(self) -> None:
        module = load_module()
        payload = [
            {
                "id": 10,
                "info": {
                    "props": {
                        "media.class": "Stream/Output/Audio",
                        "application.process.binary": "firefox",
                        "object.serial": 100,
                        "window.x11.display": ":97",
                    }
                },
            },
            {
                "id": 68,
                "info": {
                    "props": {
                        "media.class": "Stream/Output/Audio",
                        "application.process.binary": "WeChatAppEx",
                        "application.process.id": 899390,
                        "object.serial": 644,
                        "window.x11.display": ":97",
                    }
                },
            },
        ]
        completed = mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(module, "run", return_value=completed):
            stream = module.find_wechat_audio_stream(":97")

        self.assertEqual(stream, {"node_id": 68, "serial": 644, "process_id": 899390})


if __name__ == "__main__":
    unittest.main()

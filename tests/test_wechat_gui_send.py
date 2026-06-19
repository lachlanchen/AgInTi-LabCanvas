import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_gui_send():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"
    spec = importlib.util.spec_from_file_location("wechat_gui_send_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatGuiSendTests(unittest.TestCase):
    def test_target_fallback_clicks_preserve_order_without_duplicates(self):
        module = load_wechat_gui_send()

        target = module.target_from_raw(
            {
                "name": "EchoMind",
                "query": "EchoMind",
                "expected_title": "EchoMind",
                "result_click": [165, 100],
                "fallback_clicks": [[165, 100], [240, 335], [165, 170]],
            }
        )

        self.assertEqual(target.fallback_clicks, ((165, 100), (240, 335), (165, 170)))
        self.assertEqual(
            module.target_click_candidates(target),
            [
                ("result_click", (165, 100)),
                ("fallback_click_2", (240, 335)),
                ("fallback_click_3", (165, 170)),
            ],
        )


if __name__ == "__main__":
    unittest.main()

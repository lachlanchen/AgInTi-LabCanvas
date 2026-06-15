import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from urllib import request

from agenticapp.webapp import chat_update, create_server, default_scene_spec, dispatch_web_target, plan_web_scene, run_web_lab_task, target_list_response

ROOT = Path(__file__).resolve().parents[1]


class WebAppTests(unittest.TestCase):
    def test_chat_update_mutates_scene(self):
        spec = default_scene_spec()
        result = chat_update(spec, 'Make it a V-SPICE experiment setup and vivid')

        self.assertTrue(result["ok"])
        self.assertEqual(result["spec"]["title"], "V-SPICE experiment setup")
        self.assertIn("beam", result["spec"]["materials"])

    def test_chat_update_places_extra_optics_in_open_slots(self):
        result = chat_update(default_scene_spec(), "Make it a V-SPICE experiment setup, brighter and vivid, add lens and add filter")
        spec = result["spec"]
        x_positions = [
            float(element["x"])
            for element in spec["elements"]
            if element.get("type") in {"led_source", "optic", "lcd_light_valve", "event_camera"} and "x" in element
        ]

        self.assertEqual(spec["render"]["world_color"], [0.90, 0.93, 0.96])
        self.assertIn("Lens", {element.get("label") for element in spec["elements"]})
        self.assertIn("Filter", {element.get("label") for element in spec["elements"]})
        self.assertTrue(all(abs(a - b) >= 24 for index, a in enumerate(x_positions) for b in x_positions[index + 1 :]))

    def test_plan_web_scene_is_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = plan_web_scene(default_scene_spec(), Path(tmp))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "dry-run")
        self.assertTrue(result["plan"]["png"].endswith(".png"))

    def test_server_health_endpoint(self):
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with request.urlopen(f"http://{host}:{port}/api/health", timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        self.assertTrue(data["ok"])

    def test_server_serves_static_logo_svg(self):
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with request.urlopen(f"http://{host}:{port}/static/labcanvas-logo.svg", timeout=3) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["Content-Type"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        self.assertIn("image/svg+xml", content_type)
        self.assertIn("<svg", body)

    def test_webapp_language_selector_has_profile_locales(self):
        html = (ROOT / "src" / "agenticapp" / "web" / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "src" / "agenticapp" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        expected = ["en", "ar", "es", "fr", "ja", "ko", "vi", "zh-Hans", "zh-Hant", "de", "ru"]

        self.assertIn('id="localeSelect"', html)
        self.assertNotIn(">Language</", html)
        self.assertIn('src="/static/labcanvas-logo.svg"', html)
        self.assertIn("Powered by", html)
        self.assertIn("LazyingArt LLC", html)
        for locale in expected:
            self.assertIn(f'value="{locale}"', html)
        for key in set(re.findall(r'data-i18n(?:-[a-z]+)?="([^"]+)"', html)):
            self.assertIn(f'"{key}"', script)

    def test_target_dispatch_registers_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            targets = target_list_response()
            target_name = targets["targets"][0]["name"]
            result = dispatch_web_target(
                {
                    "target": target_name,
                    "instruction": "Prepare a paper figure workflow",
                    "dry_run": True,
                },
                Path(tmp),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["dispatch"]["status"], "dry-run")
        self.assertEqual(result["artifact"]["kind"], "json")

    def test_web_lab_task_registers_plan_and_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_web_lab_task(
                {
                    "prompt": "Prepare the Lumileds no-resistor PCB and C-mount reflector CAD task",
                    "mode": "auto",
                },
                Path(tmp),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["task"]["kind"], "mixed")
        self.assertTrue(any(item["source"] == "lab-task" for item in result["artifacts"]["items"]))

    def test_chat_update_routes_board_cad_prompt_to_lab_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = chat_update(
                default_scene_spec(),
                "Prepare the Lumileds no-resistor PCB and C-mount reflector CAD task",
                storage_dir=Path(tmp),
                settings={},
            )

        self.assertTrue(result["ok"])
        self.assertIn("reusable", result["reply"])
        self.assertIn("artifacts", result)


if __name__ == "__main__":
    unittest.main()

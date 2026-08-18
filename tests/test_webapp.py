import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from urllib import request

from agenticapp.backends import default_backend_settings
from agenticapp.webapp import (
    LabCanvasHandler,
    build_next_paragraph_messages,
    chat_update,
    create_server,
    default_scene_spec,
    dispatch_web_target,
    plan_web_scene,
    run_web_agent_chat,
    run_web_lab_task,
    run_web_next_paragraph,
    sanitize_next_paragraph,
    target_list_response,
)

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

    def test_server_serves_room_surface_and_room_api(self):
        previous_storage = LabCanvasHandler.storage_dir
        with tempfile.TemporaryDirectory() as tmp:
            LabCanvasHandler.storage_dir = Path(tmp)
            server = create_server("127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with request.urlopen(f"http://{host}:{port}/rooms", timeout=3) as response:
                    html = response.read().decode("utf-8")
                with request.urlopen(f"http://{host}:{port}/api/rooms", timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                LabCanvasHandler.storage_dir = previous_storage

        self.assertIn('data-testid="rooms-app"', html)
        self.assertIn('src="/static/rooms.js"', html)
        self.assertEqual([room["id"] for room in payload["rooms"]], ["agenttest", "labagent"])

    def test_webapp_language_selector_has_profile_locales(self):
        html = (ROOT / "src" / "agenticapp" / "web" / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "src" / "agenticapp" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        expected = ["en", "ar", "es", "fr", "ja", "ko", "vi", "zh-Hans", "zh-Hant", "de", "ru"]

        self.assertIn('id="localeSelect"', html)
        self.assertNotIn(">Language</", html)
        self.assertIn('src="/static/labcanvas-logo.svg"', html)
        self.assertIn("Powered by", html)
        self.assertIn("LazyingArt LLC", html)
        self.assertIn('id="agentModelSelect"', html)
        self.assertIn('id="agentEffortSelect"', html)
        self.assertIn('id="agentModeSelect"', html)
        self.assertIn('data-testid="labcanvas-app"', html)
        self.assertIn('data-testid="chat-input"', html)
        self.assertIn('data-testid="chat-send"', html)
        self.assertIn('data-testid="artifact-list"', html)
        self.assertIn('data-agent-status="ready"', html)
        self.assertIn("setAgentTaskState(task.id", script)
        self.assertIn('item.dataset.testid = `chat-message-${role}`', script)
        self.assertIn('id="artifactOpenLink"', html)
        self.assertIn('id="writingFullText"', html)
        self.assertIn('id="writeNextBtn"', html)
        self.assertIn("GPT-5.6 SOL", html)
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

    def test_web_agent_chat_dry_run_uses_workspace_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_web_agent_chat(
                {
                    "message": "Design and render a KiCad PCB and a C-mount holder",
                    "conversation_id": "web-test",
                    "dry_run": True,
                },
                Path(tmp),
                settings=default_backend_settings(),
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["policy"]["backend"], "aginti")
        self.assertEqual(result["policy"]["model"], "provider-default")
        self.assertEqual(result["policy"]["reasoning_effort"], "medium")
        self.assertIn("WeChat", result["prompt"])

    def test_next_paragraph_prompt_contains_complete_context(self):
        messages = build_next_paragraph_messages(
            {
                "full_text": "第一段。",
                "setting": "近未来城市",
                "characters": "阿青，工程师",
                "materials": "参考资料 A",
                "goal": "写出压迫感",
                "direction": "转到钱的问题",
                "previous_draft": "旧草稿。",
                "action": "adjust",
            }
        )
        prompt = messages[-1]["content"]

        self.assertIn("只输出一个自然段", messages[0]["content"])
        self.assertIn("【全文】\n第一段。", prompt)
        self.assertIn("【设定】\n近未来城市", prompt)
        self.assertIn("【人物】\n阿青，工程师", prompt)
        self.assertIn("【资料】\n参考资料 A", prompt)
        self.assertIn("【写作目标】\n写出压迫感", prompt)
        self.assertIn("【本轮方向】\n转到钱的问题", prompt)
        self.assertIn("【上一版草稿】\n旧草稿。", prompt)

    def test_next_paragraph_response_is_clamped_to_one_paragraph(self):
        result = run_web_next_paragraph(
            {"full_text": "前文。", "goal": "继续", "action": "next"},
            settings=default_backend_settings(),
            deepseek_runner=lambda messages, settings: "下一段：他终于意识到，钱不是远方的问题，而是今天晚饭前就会敲门的问题。\n\n第二段不应出现。",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["paragraph"], "他终于意识到，钱不是远方的问题，而是今天晚饭前就会敲门的问题。")
        self.assertEqual(sanitize_next_paragraph("草稿：只留这一段。\n\n不要这段。"), "只留这一段。")


if __name__ == "__main__":
    unittest.main()

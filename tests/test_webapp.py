import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import request

from agenticapp.webapp import chat_update, create_server, default_scene_spec, dispatch_web_target, plan_web_scene, target_list_response


class WebAppTests(unittest.TestCase):
    def test_chat_update_mutates_scene(self):
        spec = default_scene_spec()
        result = chat_update(spec, 'Make it a V-SPICE experiment setup and vivid')

        self.assertTrue(result["ok"])
        self.assertEqual(result["spec"]["title"], "V-SPICE experiment setup")
        self.assertIn("beam", result["spec"]["materials"])

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


if __name__ == "__main__":
    unittest.main()

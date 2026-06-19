import io
import json
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

    def test_studio_targets_json(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = main(["studio", "targets", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("blender", [target["name"] for target in payload["targets"]])

    def test_studio_figure_grid_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["studio", "figure-grid", "optics icons", "--rows", "1", "--cols", "2", "--storage-dir", tmp, "--json"])

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["figure_url"].endswith(".svg"))
        self.assertEqual(payload["rows"], 1)
        self.assertEqual(payload["cols"], 2)

    def test_studio_dispatch_dry_run_registers_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(
                    [
                        "studio",
                        "dispatch",
                        "blender",
                        "Prepare an editable paper figure",
                        "--storage-dir",
                        tmp,
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["dispatch"]["status"], "dry-run")
        self.assertEqual(payload["artifact"]["kind"], "json")

    def test_studio_lab_task_registers_board_and_cad_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(
                    [
                        "studio",
                        "lab-task",
                        "prepare",
                        "lumileds",
                        "pcb",
                        "and",
                        "cmount",
                        "reflector",
                        "cad",
                        "--storage-dir",
                        tmp,
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["task"]["kind"], "mixed")
        self.assertGreaterEqual(len(payload["task"]["steps"]), 2)
        self.assertTrue(any(item["source"] == "lab-task" for item in payload["artifacts"]["items"]))

    def test_wechat_status_json_has_reusable_command_surface(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            code = main(["wechat", "--json", "status"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertIn("desktop", payload)
        self.assertIn("sessions", payload)
        self.assertIn("queue", payload)
        self.assertIn("mirror", payload)
        self.assertIn("external_backend", payload)
        self.assertTrue(payload["external_backend"]["private_paths_redacted"])
        self.assertIn("codex_sessions", payload)
        self.assertIn("novnc_url", payload)

    def test_wechat_queue_json_reads_private_queue_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps({"id": "1", "chat": "demo", "request": "render a device", "status": "pending"}) + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["wechat", "queue", "--queue", str(queue), "--json"])

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["counts"]["pending"], 1)
        self.assertEqual(payload["recent"][0]["request"], "render a device")

    def test_wechat_approve_promotes_newest_waiting_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "old", "chat": "demo", "request": "old task", "status": "waiting_confirmation"}),
                        json.dumps({"id": "new", "chat": "demo", "request": "new task", "status": "waiting_confirmation"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["wechat", "approve", "--queue", str(queue), "--note", "go ahead", "--json"])

            payload = json.loads(stdout.getvalue())
            rows = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(code, 0)
        self.assertEqual(payload["task"]["id"], "new")
        self.assertEqual(rows[0]["status"], "waiting_confirmation")
        self.assertEqual(rows[1]["status"], "pending")
        self.assertIn("go ahead", rows[1]["request"])

    def test_wechat_reject_cancels_named_waiting_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps({"id": "task-1", "chat": "demo", "request": "submit order", "status": "waiting_confirmation"}) + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["wechat", "reject", "task-1", "--queue", str(queue), "--note", "not now", "--json"])

            payload = json.loads(stdout.getvalue())
            row = json.loads(queue.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(code, 0)
        self.assertEqual(payload["task"]["status"], "canceled")
        self.assertEqual(row["status"], "canceled")
        self.assertEqual(row["cancel_note"], "not now")


if __name__ == "__main__":
    unittest.main()

import base64
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from agenticapp.biorender_figures import build_nature_figure_prompt, run_biorender_figure
from agenticapp.cli import main


def png(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return signature + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class FakeBioRenderClient:
    def __init__(self) -> None:
        self.calls = []

    def initialize(self):
        self.calls.append(("initialize", {}))
        return {"result": {}}

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "custom-figure-create-session":
            return {"result": {"structuredContent": {"sessionId": "session-1", "jobId": "job-1"}}}
        if name == "custom-figure-get-preview-job":
            return {"result": {"structuredContent": {"job": {"status": "completed"}}}}
        if name == "custom-figure-get-session":
            return {
                "result": {
                    "structuredContent": {
                        "session": {"id": "session-1", "status": "completed"},
                        "figure": {"figureId": "figure-1", "url": "https://app.biorender.com/illustrations/figure-1"},
                    },
                    "content": [
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(png(1600, 900)).decode("ascii"),
                        }
                    ],
                }
            }
        if name == "custom-figure-confirm-preview":
            return {"result": {"structuredContent": {"confirmed": True}}}
        raise AssertionError(name)


class BioRenderFigureTests(unittest.TestCase):
    def test_prompt_encodes_alignment_editability_and_scientific_guardrails(self):
        prompt = build_nature_figure_prompt(
            {
                "title": "Neurovascular integration",
                "prompt": "Distinguish integration failure from active rejection.",
                "panels": ["A: Failure modes", "B: Diagnostic decision tree"],
            }
        )

        self.assertIn("strict aligned grid", prompt)
        self.assertIn("equal outer margins", prompt)
        self.assertIn("editable BioRender objects", prompt)
        self.assertIn("Do not imply experimental results", prompt)
        self.assertIn("Panel A", prompt)
        self.assertIn("Panel B", prompt)

    def test_dry_run_writes_atomic_manifest_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_biorender_figure(
                {
                    "prompt": "Brain organoid vascularization roadmap",
                    "title": "Neurovascular roadmap",
                    "panels": ["A: Failure modes", "B: Readouts"],
                    "run_id": "test-run",
                },
                Path(tmp),
            )
            manifest = Path(tmp) / result["manifest_artifact"]["path"]
            data = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual([panel["id"] for panel in data["panels"]], ["A", "B"])
        self.assertTrue(data["layout_contract"]["grid_aligned"])

    def test_live_run_saves_preview_confirms_handshake_and_registers_artifact(self):
        client = FakeBioRenderClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = run_biorender_figure(
                {
                    "prompt": "Brain organoid vascularization roadmap",
                    "title": "Neurovascular roadmap",
                    "panels": ["A: Failure modes", "B: Intervention pipeline"],
                    "run_id": "live-test",
                    "template_id": "template-1",
                    "live": True,
                    "cdp_export": False,
                },
                Path(tmp),
                client=client,
                sleep=lambda _seconds: None,
            )
            image = Path(tmp) / result["artifact"]["path"]

        self.assertEqual(result["status"], "completed")
        self.assertTrue(image.name.endswith(".png"))
        self.assertEqual(result["figure"]["quality"]["width"], 1600)
        self.assertIn(("custom-figure-confirm-preview", {"jobId": "job-1"}), client.calls)
        create = next(args for name, args in client.calls if name == "custom-figure-create-session")
        self.assertEqual(create["canvasContext"]["templateId"], "template-1")

    def test_cli_exposes_biorender_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "studio",
                        "biorender-figure",
                        "brain",
                        "organoid",
                        "workflow",
                        "--title",
                        "Brain organoid workflow",
                        "--panel",
                        "A:Failure modes",
                        "--storage-dir",
                        tmp,
                        "--run-id",
                        "cli-test",
                        "--json",
                    ]
                )
            result = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["figure"]["panels"][0]["id"], "A")


if __name__ == "__main__":
    unittest.main()

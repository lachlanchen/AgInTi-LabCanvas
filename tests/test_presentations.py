from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from agenticapp.presentations import (
    build_presentation,
    default_manifest,
    initialize_presentation_workspace,
    validate_manifest,
)


class PresentationTests(unittest.TestCase):
    def test_workspace_starts_with_bright_theme_and_interruptible_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = initialize_presentation_workspace(
                tmp,
                title="Optical research roadmap",
                objective="Explain the evidence and next experiment",
            )
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(manifest["theme"], "bright_scientific")
        self.assertTrue(manifest["interaction"]["start_immediately"])
        self.assertIn("send", manifest["interaction"]["progress_message"].lower())
        self.assertTrue(manifest["image_generation_policy"]["forbid_full_slide_generation"])

    def test_generated_full_slide_asset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "asset.png"
            image.write_bytes(b"placeholder")
            manifest = default_manifest("Generated asset guard")
            manifest["slides"][1]["assets"] = [
                {
                    "path": "asset.png",
                    "role": "full_slide",
                    "box": {"x": 0, "y": 0, "w": 13.333, "h": 7.5},
                    "provenance": {
                        "kind": "image_generation",
                        "prompt": "Generate the entire slide",
                        "contains_text": False,
                    },
                }
            ]

            result = validate_manifest(manifest, root)

        self.assertFalse(result["ok"])
        self.assertTrue(any("cannot use generated imagery" in item for item in result["errors"]))
        self.assertTrue(any("supporting material" in item for item in result["errors"]))

    def test_generated_text_requires_transcript_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "asset.png"
            image.write_bytes(b"placeholder")
            manifest = default_manifest("Generated text guard")
            manifest["slides"][1]["assets"] = [
                {
                    "path": "asset.png",
                    "role": "supporting_visual",
                    "provenance": {
                        "kind": "image_generation",
                        "prompt": "A small labeled concept illustration",
                        "contains_text": True,
                    },
                }
            ]

            result = validate_manifest(manifest, root)

        self.assertFalse(result["ok"])
        self.assertTrue(any("text_transcript" in item for item in result["errors"]))
        self.assertTrue(any("text_reviewed" in item for item in result["errors"]))

    def test_asset_box_must_stay_inside_slide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "asset.png"
            image.write_bytes(b"placeholder")
            manifest = default_manifest("Asset boundary guard")
            manifest["slides"][1]["assets"] = [
                {
                    "path": "asset.png",
                    "role": "supporting_visual",
                    "box": {"x": 12.5, "y": 1.0, "w": 2.0, "h": 2.0},
                }
            ]

            result = validate_manifest(manifest, root)

        self.assertFalse(result["ok"])
        self.assertTrue(any("beyond the slide boundary" in item for item in result["errors"]))

    @unittest.skipUnless(importlib.util.find_spec("pptx"), "python-pptx is not installed")
    def test_build_creates_editable_pptx_with_expected_slide_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = initialize_presentation_workspace(root, title="Editable deck")

            result = build_presentation(workspace["manifest"], output_dir=root / "build")

            self.assertTrue(result["ok"])
            self.assertEqual(result["package_check"]["slide_count"], 4)
            self.assertTrue(Path(result["pptx"]).is_file())

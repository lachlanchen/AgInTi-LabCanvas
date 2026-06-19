from pathlib import Path
import tempfile
import unittest

from agenticapp.artifacts import ArtifactStore
from agenticapp.openscad_export import export_scene_to_openscad
from agenticapp.paper_figures import generate_icon_grid, parse_grid_size
from agenticapp.webapp import default_scene_spec, generate_web_figure_grid, register_aginti_outputs


class PaperFigureTests(unittest.TestCase):
    def test_parse_grid_size(self):
        self.assertEqual(parse_grid_size("make a 3x4 figure grid"), (3, 4))
        self.assertEqual(parse_grid_size("rows 5 cols 2"), (5, 2))

    def test_generate_icon_grid_writes_exact_svg_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_icon_grid("optical experiment icons", tmp, rows=2, cols=3, cell_size=200, border=4)
            text = result.path.read_text(encoding="utf-8")

        self.assertIn('width="604"', text)
        self.assertIn('height="404"', text)
        self.assertEqual(text.count('stroke="#000"'), 7)

    def test_artifact_store_registers_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_icon_grid("cell assay icons", Path(tmp) / "figures", rows=1, cols=2)
            store = ArtifactStore(Path(tmp))
            item = store.register(result.path, title="Grid", kind="image")

        self.assertEqual(item["kind"], "image")
        self.assertTrue(item["url"].endswith(".svg"))

    def test_openscad_export_writes_scene_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = export_scene_to_openscad(default_scene_spec(), tmp)
            text = result.path.read_text(encoding="utf-8")

        self.assertIn("OpenSCAD export", text)
        self.assertIn("optical rails", text)

    def test_web_figure_grid_returns_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = {
                "aginti": {"enabled": False},
                "figure": {"rows": 2, "cols": 3, "cell_size": 180, "border": 4},
            }
            result = generate_web_figure_grid({"prompt": "device 2x2 icon grid"}, Path(tmp), settings)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["cols"], 2)
        self.assertGreaterEqual(len(result["artifacts"]["items"]), 1)

    def test_register_aginti_outputs_includes_live_image_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "aginti-output.png"
            image.write_bytes(b"png")
            store = ArtifactStore(root)

            register_aginti_outputs(store, {"imagePaths": [str(image)], "summary": "live image"})
            bundle = store.bundle()

        self.assertEqual(bundle["items"][0]["kind"], "image")
        self.assertEqual(bundle["items"][0]["source"], "aginti")


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/openhi_vertical_multimodal_microscope_setup"


class OpenHIPublicationRenderTests(unittest.TestCase):
    def setUp(self):
        self.pointer = json.loads((DESIGN / "artifacts/publication_latest.json").read_text())

    def local(self):
        path = ROOT / self.pointer["manifest"]
        if not path.is_file():
            self.skipTest("Local publication render run is not present")
        return path.parent, json.loads(path.read_text())

    def test_render_only_run(self):
        self.assertFalse(self.pointer["cad_geometry_changed"])
        self.assertNotEqual(self.pointer["run_dir"], self.pointer["source_run"])

    def test_assemblies_are_byte_identical(self):
        run, data = self.local()
        source = ROOT / data["source_run"]
        self.assertFalse(data["cad_geometry_changed"])
        for entry in data["variants"].values():
            for parent in (run, source):
                self.assertEqual(hashlib.sha256((parent / entry["assembly_step"]).read_bytes()).hexdigest(), entry["sha256"])

    def test_source_meshes_untouched(self):
        _, data = self.local()
        for entry in data["variants"].values():
            for row in entry["render_components"]:
                self.assertEqual(hashlib.sha256((ROOT / row["source_mesh"]).read_bytes()).hexdigest(), row["sha256"])

    def test_raytraced_cpu_studio(self):
        _, data = self.local()
        settings = data["render_settings"]
        self.assertEqual(settings["engine"], "CYCLES")
        self.assertEqual(settings["device"], "CPU")
        self.assertLessEqual(settings["threads"], 6)
        self.assertTrue(settings["denoise"])
        self.assertEqual(settings["source_mm_to_scene_m"], 0.001)

    def test_every_configuration_and_detail_is_uncropped(self):
        run, _ = self.local()
        rows = json.loads((run / "renders/camera_validation.json").read_text())
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(row["name"].endswith("_overview") for row in rows), 3)
        for row in rows:
            self.assertEqual(row["engine"], "CYCLES")
            self.assertEqual(row["device"], "CPU")
            b = row["projected_bounds"]
            self.assertGreaterEqual(b["xmin"], 0.079)
            self.assertLessEqual(b["xmax"], 0.921)
            self.assertGreaterEqual(b["ymin"], 0.079)
            self.assertLessEqual(b["ymax"], 0.921)
            if row["name"].endswith("_overview"):
                names = set(row["visible_components"])
                self.assertIn("GT090101_lower", names)
                self.assertIn("GT090101_upper", names)
                self.assertIn("frame_camera_body", names)
                self.assertIn("c12880_board", names)
                if row["variant"] != "single_4f":
                    self.assertIn("event_camera_body", names)

    def test_rendered_pixels_are_nonblank_on_white(self):
        run, _ = self.local()
        from PIL import Image
        import numpy as np
        for file in (run / "renders").glob("*.png"):
            pixels = np.asarray(Image.open(file).convert("RGB"))
            content = np.min(pixels, axis=2) < 230
            self.assertGreater(float(content.mean()), 0.02, file.name)
            self.assertLess(float(content.mean()), 0.8, file.name)
            for corner in (pixels[:8, :8], pixels[:8, -8:], pixels[-8:, :8], pixels[-8:, -8:]):
                self.assertGreaterEqual(int(corner.min()), 248, file.name)

    def test_labels_and_aspect_ratios_fit(self):
        run, _ = self.local()
        layouts = json.loads((run / "figures/layout_validation.json").read_text())
        self.assertEqual(len(layouts), 3)
        for layout in layouts:
            for panel in layout["panels"]:
                _, _, w, h = panel["rectangle"]
                iw, ih = panel["image_size"]
                self.assertAlmostEqual(w * 7.2 / (h * 7.8), iw / ih)
            for text in layout["text_bounds"]:
                x0, y0, x1, y1 = text["bounds_fraction"]
                self.assertGreaterEqual(x0, 0)
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(x1, 1)
                self.assertLessEqual(y1, 1)
            for ext in ("pdf", "png", "svg"):
                self.assertTrue((run / f"figures/Figure_{layout['variant']}_publication.{ext}").is_file())

    def test_nutstore_files_match(self):
        run, _ = self.local()
        target = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN.name / run.name
        if not target.exists():
            self.skipTest("Nutstore copy is not mounted")
        files = json.loads((run / "sync_manifest.json").read_text())
        for relative, digest in files.items():
            self.assertEqual(hashlib.sha256((target / relative).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()

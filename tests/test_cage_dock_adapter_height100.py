import hashlib
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/cage_dock_m10_to_m6_adapter_20_50"


class CageDockAdapterHeight100Tests(unittest.TestCase):
    def setUp(self):
        path = DESIGN / "artifacts/height100_manifest.json"
        if not path.exists():
            self.skipTest("100 mm adapter has not been built")
        self.data = json.loads(path.read_text())
        self.run = DESIGN / "runs" / self.data["run_name"]

    def test_height_only_extension_uses_original_fit(self):
        p = self.data["parameters_mm"]
        self.assertEqual((p["lower_diameter"], p["lower_length"]), (9.8, 20))
        self.assertEqual((p["upper_diameter"], p["upper_length"]), (6, 80))
        self.assertEqual(p["total_height"], 100)
        self.assertEqual(p["added_upper_length"], 30)
        self.assertEqual(p["top_chamfer"], 0.35)
        self.assertEqual(p["bottom_chamfer"], 0.35)
        self.assertEqual(p["grid_pitch"], 24)

    def test_geometry_preservation_and_added_volume(self):
        g = self.data["geometry_checks"]
        for name in ("baseline_reconstruction_difference_mm3", "lower_insert_difference_mm3", "translated_top_difference_mm3"):
            self.assertLess(g[name], 1e-5)
        self.assertAlmostEqual(g["added_volume_mm3"], math.pi * 9 * 30, places=5)

    def test_single_and_four_part_prints(self):
        for name, count in (("single", 1), ("2x2", 4)):
            p = self.data["print_packages"][name]
            self.assertEqual(p["solid_count"], count)
            self.assertEqual(p["mesh_components"], count)
            self.assertTrue(p["step_valid"])
            self.assertTrue(p["watertight"])
            self.assertTrue(all(p["first_layer_nonempty_each_part"]))
            self.assertTrue(all(abs(z) < 1e-6 for z in p["min_z_each_part_mm"]))
            self.assertEqual(p["three_mf_build_items"], 1)
            self.assertEqual(p["three_mf_units"], "millimeter")
            self.assertAlmostEqual(p["bounds_mm"][5], 100)

    def test_original_source_not_overwritten(self):
        record = self.data["source"]
        for path_key, hash_key in (("path", "sha256"), ("generator", "generator_sha256")):
            path = ROOT / record[path_key]
            if not path.exists():
                self.skipTest("Local original CAD source is absent")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record[hash_key])

    def test_render_margins(self):
        path = self.run / "renders/camera_validation.json"
        if not path.exists():
            self.skipTest("CAD renders are local artifacts")
        rows = json.loads(path.read_text())
        self.assertEqual(len(rows), 2)
        for row in rows:
            b = row["projected_bounds"]
            self.assertGreaterEqual(b["xmin"], 0.079)
            self.assertLessEqual(b["xmax"], 0.921)
            self.assertGreaterEqual(b["ymin"], 0.079)
            self.assertLessEqual(b["ymax"], 0.921)


if __name__ == "__main__":
    unittest.main()

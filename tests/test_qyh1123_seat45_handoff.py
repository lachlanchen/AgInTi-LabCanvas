import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/qyh1123_light_valve_centered_clearance_cage_holder"


class Qyh1123Seat45Tests(unittest.TestCase):
    def setUp(self):
        p = DESIGN / "artifacts/seat45_manifest.json"
        if not p.exists():
            self.skipTest("QYH1123 pair has not been built")
        self.summary = json.loads(p.read_text())

    def local_data(self):
        for key, row in self.summary["variants"].items():
            path = ROOT / row["manifest"]
            if not path.exists():
                self.skipTest("Local CAD run is not present")
            yield key, json.loads(path.read_text()), path.parent

    def test_both_requested_variants(self):
        self.assertEqual(set(self.summary["variants"]), {"0deg", "45deg"})
        self.assertTrue(self.summary["accepted_sources_unchanged"])

    def test_exact_original_copy(self):
        key, data, run = next(self.local_data())
        self.assertEqual(key, "0deg")
        self.assertTrue(data["original_holder_byte_copy"])
        self.assertTrue(data["original_assembly_byte_copy"])
        self.assertEqual(hashlib.sha256((run / "holder.step").read_bytes()).hexdigest(), data["source_identity"]["holder_step"]["sha256"])

    def test_fit_and_cage_values_not_changed(self):
        for key, data, run in self.local_data():
            self.assertEqual(data["seat_rotation_deg"], 0 if key == "0deg" else 45)
            p = data["parameters"]
            self.assertEqual((p["body_width_mm"], p["body_height_mm"], p["body_thickness_mm"]), (42, 42, 8))
            self.assertEqual(p["cage_rod_pitch_mm"], 30)
            self.assertEqual(p["cage_rod_clearance_diameter_mm"], 6.4)
            self.assertEqual(p["valve_pocket_clearance_mm"], 0.6)
            self.assertEqual(p["valve_pocket_depth_mm"], 2.2)
            self.assertEqual(p["pin_exit_relief_width_mm"], 6.6)

    def test_geometry_and_print_packages(self):
        for _, data, run in self.local_data():
            for name, value in data["geometry_checks"].items():
                if name.endswith("_mm3"):
                    self.assertLess(value, 1e-5, name)
            self.assertTrue(data["geometry_checks"]["holder_valid"])
            self.assertTrue(data["geometry_checks"]["assembly_valid"])
            p = data["print_validation"]
            self.assertEqual(p["solid_count"], 1)
            self.assertTrue(p["watertight"])
            self.assertEqual(p["mesh_components"], 1)
            self.assertAlmostEqual(p["min_z_mm"], 0)
            self.assertTrue(p["first_layer_nonempty"])
            self.assertEqual(p["three_mf_build_items"], 1)
            self.assertFalse(p["ears_added"])

    def test_uncropped_renders(self):
        for _, data, run in self.local_data():
            path = run / "renders/camera_validation.json"
            if not path.exists():
                self.skipTest("Renders are not present")
            rows = json.loads(path.read_text())
            self.assertEqual(len(rows), 3)
            for row in rows:
                b = row["projected_bounds"]
                self.assertGreaterEqual(b["xmin"], 0.079)
                self.assertLessEqual(b["xmax"], 0.921)
                self.assertGreaterEqual(b["ymin"], 0.079)
                self.assertLessEqual(b["ymax"], 0.921)


if __name__ == "__main__":
    unittest.main()

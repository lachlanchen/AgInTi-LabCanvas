import json
import unittest
from pathlib import Path


DESIGN = Path(__file__).resolve().parents[1] / "cad/designs/yxra100_servo_analyzer_breadboard_mount"


class Yxra100AnalyzerMountTests(unittest.TestCase):
    def setUp(self):
        path = DESIGN / "artifacts/manifest.json"
        if not path.exists():
            self.skipTest("Local CAD artifacts not built")
        self.data = json.loads(path.read_text())

    def test_purchased_variant_and_source_holes(self):
        self.assertEqual(self.data["selected_motor"], "40 mm / 100 W servo")
        expected = sorted(self.data["stationary_base_holes_mm"])
        self.assertEqual(sorted(self.data["measured_source_holes_mm"]), expected)
        self.assertEqual(len(expected), 3)

    def test_breadboard_and_cage_datums(self):
        for x, y in self.data["breadboard_holes_mm"]:
            self.assertAlmostEqual(x % 25, 0)
            self.assertAlmostEqual(y % 25, 0)
        self.assertEqual(self.data["cage_pin_centers_mm"], [[-15, -15], [-15, 15], [15, -15], [15, 15]])

    def test_no_unwanted_overlap(self):
        self.assertTrue(self.data["assembly_step_round_trip_valid"])
        for value in self.data["interference_volume_mm3"].values():
            self.assertLessEqual(value, 0.01)
        self.assertLessEqual(self.data["rotating_assembly_max_interference_mm3_15deg_samples"], 0.01)

    def test_print_contract(self):
        self.assertEqual(len(self.data["print_validation"]), 3)
        for record in self.data["print_validation"].values():
            self.assertEqual(record["solids"], 1)
            self.assertTrue(record["watertight"])
            self.assertEqual(record["mesh_components"], 1)
            self.assertAlmostEqual(record["min_z_mm"], 0)
            self.assertTrue(record["first_layer_nonempty"])
            self.assertEqual(record["three_mf_build_items"], 1)

    def test_optical_limit_not_misrepresented(self):
        optical = self.data["optical_constraints"]
        self.assertFalse(optical["focus_validated"])
        self.assertEqual(optical["vertical_gap_mm"], 5)
        self.assertAlmostEqual(optical["required_microscope_upshift_mm"], 61, places=5)

    def test_cameras_do_not_crop(self):
        path = DESIGN / "artifacts/renders/camera_validation.json"
        if not path.exists():
            self.skipTest("Renders not generated")
        for row in json.loads(path.read_text()):
            bounds = row["projected_bounds"]
            self.assertGreater(bounds["xmin"], 0.03)
            self.assertLess(bounds["xmax"], 0.97)
            self.assertGreater(bounds["ymin"], 0.03)
            self.assertLess(bounds["ymax"], 0.97)


if __name__ == "__main__":
    unittest.main()

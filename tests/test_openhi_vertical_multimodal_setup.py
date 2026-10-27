import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/openhi_vertical_multimodal_microscope_setup"


class OpenHIVerticalMultimodalSetupTests(unittest.TestCase):
    def setUp(self):
        self.manifest_path = DESIGN / "artifacts/manifest.json"
        final_step = DESIGN / "USE_THIS_openhi_vertical_multimodal_microscope_setup_single_4f.step"
        if not self.manifest_path.exists() or not final_step.exists():
            self.skipTest("CAD assembly has not been built")
        self.manifest = json.loads(self.manifest_path.read_text())

    def test_stack_order_and_cage_contract(self):
        stack = self.manifest["stack_sequence"]
        self.assertLess(stack.index("tungsten lamp on Lumileds PCB holder"), stack.index("QYH1123 LCD with one lower adhered polarizer proxy"))
        self.assertLess(stack.index("two-piece slide/petri sample holder"), stack.index("Hengyang GT090101 analyzer"))
        self.assertEqual(self.manifest["parameters"]["cage_pitch_mm"], 30.0)
        self.assertTrue(self.manifest["checks"]["all_cage_centers_share_xy_origin"])

    def test_variants_have_expected_detector_topology(self):
        single = self.manifest["variants"]["single_4f"]
        dual = self.manifest["variants"]["dual_4f"]
        self.assertIsNone(single["secondary_4f"])
        self.assertIsNotNone(dual["secondary_4f"])
        self.assertIn("frame camera", single["detector_contract"]["straight_port"])
        self.assertIn("C12880MA", single["detector_contract"]["split_port"])
        self.assertIn("event camera", dual["detector_contract"]["second_split_port"])
        self.assertIn("C12880MA", dual["detector_contract"]["second_straight_port"])

    def test_cascade_interface_and_outputs_are_valid(self):
        dual = self.manifest["variants"]["dual_4f"]
        primary_c = dual["datums_mm"]["primary_c_output_x"]
        secondary_a = dual["secondary_4f"]["a_input_x_mm"]
        expected_gap = self.manifest["parameters"]["cascade_input_gap_mm"]
        self.assertAlmostEqual(secondary_a - primary_c, expected_gap, places=6)
        self.assertTrue(self.manifest["checks"]["all_step_round_trips_valid"])
        self.assertTrue(self.manifest["variants"]["single_4f"]["validation"]["step_round_trip_valid"])
        self.assertTrue(dual["validation"]["step_round_trip_valid"])

    def test_sources_and_final_steps_exist(self):
        for record in self.manifest["source_identity"].values():
            source = ROOT / record["path"]
            self.assertTrue(source.exists(), source)
        for variant in self.manifest["variants"].values():
            self.assertTrue((ROOT / variant["assembly_step"]).exists())
            self.assertTrue((ROOT / variant["use_this_step"]).exists())

    def test_vertical_cascade_aligns_actual_b_axis(self):
        vertical = self.manifest["variants"]["dual_4f_vertical"]
        second = vertical["secondary_4f"]
        self.assertAlmostEqual(second["a_input_z_mm"] - vertical["datums_mm"]["primary_b_output_z"], 3)
        self.assertAlmostEqual(second["a_input_x_mm"], -0.367)
        self.assertAlmostEqual(second["b_output_x_mm"], -0.734)
        self.assertEqual(second["rotation_y_deg"], 0)
        self.assertIn("frame camera", vertical["detector_contract"]["first_split_port"])
        self.assertIn("event camera", vertical["detector_contract"]["second_straight_port"])
        self.assertIn("C12880MA", vertical["detector_contract"]["second_split_port"])

    def test_complete_cameras_have_safe_margins(self):
        path = DESIGN / "artifacts/renders/camera_validation.json"
        if not path.exists():
            self.skipTest("Full-frame renders not generated")
        records = json.loads(path.read_text())
        self.assertEqual(len(records), 5)
        for record in records:
            bounds = record["projected_bounds"]
            self.assertGreaterEqual(bounds["xmin"], 0.079)
            self.assertLessEqual(bounds["xmax"], 0.921)
            self.assertGreaterEqual(bounds["ymin"], 0.079)
            self.assertLessEqual(bounds["ymax"], 0.921)


if __name__ == "__main__":
    unittest.main()

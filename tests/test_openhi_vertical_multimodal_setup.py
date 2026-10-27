import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/openhi_vertical_multimodal_microscope_setup"


class OpenHIVerticalMultimodalSetupTests(unittest.TestCase):
    def setUp(self):
        self.manifest_path = DESIGN / "artifacts/manifest.json"
        if not self.manifest_path.exists():
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


if __name__ == "__main__":
    unittest.main()

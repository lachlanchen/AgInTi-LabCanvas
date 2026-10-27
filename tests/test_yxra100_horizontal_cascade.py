import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/yxra100_servo_analyzer_breadboard_mount"


class Yxra100HorizontalCascadeTests(unittest.TestCase):
    def setUp(self):
        path = DESIGN / "artifacts/manifest.json"
        if not path.exists():
            self.skipTest("Horizontal rotary CAD has not been built")
        self.data = json.loads(path.read_text())
        if self.data.get("configuration") != "horizontal_dual_4f_rotary_analyzer":
            self.skipTest("Current assembly is a different configuration")
        self.run = DESIGN / "runs" / self.data["run_name"]

    def test_lateral_cascade_datums(self):
        c = self.data["cascade"]
        self.assertEqual(c["source_variant"], "dual_4f")
        self.assertFalse(c["vertical_cascade"])
        self.assertEqual(c["secondary_4f"]["rotation_y_deg"], 90)
        self.assertAlmostEqual(c["interface_gap_mm"], 3)
        self.assertAlmostEqual(c["datums_mm"]["primary_bs_z"], 606.2)
        self.assertEqual(c["secondary_4f"]["beam_splitter_center_mm"], [207.6, 0, 606.2])
        self.assertAlmostEqual(c["secondary_4f"]["c_output_z_mm"], 501.8)
        self.assertAlmostEqual(c["source_b_axis_shift_mm"], -0.367)

    def test_three_detectors_and_accepted_relays(self):
        names = {row["name"] for row in self.data["render_components"]}
        self.assertTrue({"primary_openhi_4f", "secondary_openhi_4f", "frame_camera_body", "event_camera_body", "c12880_sensor"}.issubset(names))
        self.assertEqual(len(names), 52)
        self.assertEqual(len(self.data["new_components"]), 8)
        for row in self.data["render_components"]:
            if row["origin"] == "horizontal_relay_run_2":
                self.assertAlmostEqual(row["source_translation_mm"][2], 61, places=5)

    def test_accepted_base_preserved(self):
        kept = self.data["preserved_base_components"]
        self.assertEqual(len(kept), 44)
        self.assertTrue({"YXRA100_servo_vendor", "GT090101_analyzer", "motor_yoke_stand_foot", "motor_yoke_top_bridge", "bridge_M3_screw_1", "lamp_holder", "qyh1123_lcd", "sample_holder_and_cap"}.issubset(kept))
        self.assertTrue(self.data["assembly_step_round_trip_valid"])
        self.assertLessEqual(self.data["new_vs_retained_max_interference_mm3"], 0.01)
        for row in self.data["step_component_round_trip"].values():
            self.assertTrue(row["valid"])
            self.assertTrue(row["solid_shell_face_counts_match"])
            self.assertLess(row["bounds_max_error_mm"], 1e-4)

    def test_archived_inputs_unchanged(self):
        for row in self.data["frozen_sources"].values():
            path = ROOT / row["path"]
            if not path.exists():
                self.skipTest("Local CAD archive is not present")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])

    def test_detail_is_explanatory_not_fake_crop(self):
        detail = self.data["detail_view"]
        names = set(detail["included_components"])
        self.assertEqual(detail["geometry_transform"], "none")
        self.assertTrue({"lamp_holder", "lcd_holder", "sample_holder_and_cap", "tungsten_bulb", "petri_dish"}.issubset(names))
        self.assertFalse(names.intersection({"YXRA100_servo_vendor", "gusseted_L_support", "breadboard_foot", "motor_yoke_stand_foot"}))
        self.assertEqual(names.intersection(detail["omitted_components"]), set())

    def test_no_historical_measurement_claim(self):
        self.assertFalse(self.data["historical_measurements_motorized"])
        self.assertFalse(self.data["optical_constraints"]["focus_validated"])
        self.assertIn("earlier four-angle measurements did not use motorized rotation", " ".join(self.data["limitations"]))

    def test_all_rendered_objects_fit(self):
        path = self.run / "renders/camera_validation.json"
        if not path.exists():
            self.skipTest("Run has not been rendered")
        records = json.loads(path.read_text())
        self.assertEqual(len(records), 3)
        for row in records:
            b = row["projected_bounds"]
            self.assertGreaterEqual(b["xmin"], 0.079)
            self.assertLessEqual(b["xmax"], 0.921)
            self.assertGreaterEqual(b["ymin"], 0.079)
            self.assertLessEqual(b["ymax"], 0.921)
        self.assertEqual(records[0]["object_count"], 52)


if __name__ == "__main__":
    unittest.main()

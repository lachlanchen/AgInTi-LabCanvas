import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/openhi_vertical_multimodal_microscope_setup"


class OpenHIDualLCDStackTests(unittest.TestCase):
    def setUp(self):
        self.latest = json.loads((DESIGN / "artifacts/dual_lcd_stack_latest.json").read_text())

    def local_run(self):
        path = ROOT / self.latest["manifest"]
        if not path.is_file():
            self.skipTest("Local generated apparatus run is not present")
        return path.parent, json.loads(path.read_text())

    def test_all_three_layouts(self):
        self.assertEqual(set(self.latest["variants"]), {"single_4f", "dual_4f", "dual_4f_vertical"})
        self.assertEqual(self.latest["configuration"], "fixed_dual_GT090101_dual_QYH1123_stack")

    def test_new_sequence_and_separated_layers(self):
        _, data = self.local_run()
        self.assertEqual(data["stack_sequence"][:8], [
            "dock", "lamp and PCB", "lower GT090101", "lower QYH1123 LCD holder",
            "sample holder, dish and cap", "upper QYH1123 LCD holder", "upper GT090101", "microscope",
        ])
        layers = data["axial_layers"]
        self.assertEqual(len(layers), 7)
        for a, b in zip(layers, layers[1:]):
            self.assertEqual(b["bottom_mm"] - a["top_mm"], 5)
        self.assertEqual(data["parameters"]["microscope_bottom_z_mm"] - layers[-1]["top_mm"], 8)
        self.assertFalse(data["parameters"]["axial_placement_is_measured"])

    def test_two_accepted_lcd_holders_and_no_rotary_hardware(self):
        _, data = self.local_run()
        for entry in data["variants"].values():
            parts = {row["name"]: row for row in entry["components"]}
            self.assertTrue({"GT090101_lower", "GT090101_upper", "LCD_lower_holder", "LCD_upper_holder"}.issubset(parts))
            for position in ("lower", "upper"):
                self.assertIn("run-4-45deg-full-through-pin-dupont", parts[f"LCD_{position}_holder"]["placement"]["source"])
            self.assertFalse(any("YXRA" in name or "motor_yoke" in name for name in parts))
            self.assertEqual(set(entry["lower_detail_components"]), set(data["variants"]["single_4f"]["lower_detail_components"]))

    def test_cage_rod_centers_and_diameters(self):
        _, data = self.local_run()
        self.assertEqual(data["parameters"]["cage_pitch_mm"], 30)
        for entry in data["variants"].values():
            rods = [row for row in entry["components"] if row["name"].startswith("cage_rod_")]
            self.assertEqual(len(rods), 8)
            for row in rods:
                b = row["geometry"]["bounds_mm"]
                self.assertAlmostEqual(abs((b[0] + b[3]) / 2), 15, places=5)
                self.assertAlmostEqual(abs((b[1] + b[4]) / 2), 15, places=5)
                self.assertAlmostEqual(b[3] - b[0], 6, places=5)
                self.assertAlmostEqual(b[4] - b[1], 6, places=5)

    def test_pins_clear_adjacent_bodies(self):
        _, data = self.local_run()
        self.assertEqual(set(data["lower_pin_intersections_mm3"]), {"LCD_lower_pins", "LCD_upper_pins"})
        for neighbours in data["lower_pin_intersections_mm3"].values():
            for overlap in neighbours.values():
                self.assertLess(abs(overlap), 1e-5)

    def test_named_step_parts_and_upper_geometry_preserved(self):
        run, data = self.local_run()
        for name, entry in data["variants"].items():
            self.assertTrue((run / entry["assembly_step"]).is_file())
            self.assertTrue(entry["all_step_round_trips_valid"])
            self.assertEqual(len(entry["step_round_trip"]), len(entry["components"]))
            for check in entry["step_round_trip"].values():
                self.assertTrue(check["valid"])
                self.assertTrue(check["solid_shell_face_counts_match"])
                self.assertLess(check["bounds_max_error_mm"], 1e-4)
            self.assertIn("primary_openhi_4f", entry["preserved_upper_parts"])
            self.assertEqual("secondary_openhi_4f" in entry["preserved_upper_parts"], name != "single_4f")

    def test_cascade_gaps_and_beam_splitter_offsets(self):
        _, data = self.local_run()
        horizontal = data["variants"]["dual_4f"]
        second = horizontal["secondary_4f"]
        self.assertEqual(second["rotation_y_deg"], 90)
        self.assertAlmostEqual(second["a_input_x_mm"] - horizontal["datums_mm"]["primary_c_output_x"], 3)
        vertical = data["variants"]["dual_4f_vertical"]
        second = vertical["secondary_4f"]
        self.assertEqual(second["rotation_y_deg"], 0)
        self.assertAlmostEqual(second["a_input_z_mm"] - vertical["datums_mm"]["primary_b_output_z"], 3)
        self.assertAlmostEqual(second["a_input_x_mm"], -0.367)
        self.assertAlmostEqual(second["b_output_x_mm"], -0.734)

    def test_all_sources_unchanged(self):
        _, data = self.local_run()
        for record in data["source_identity"].values():
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_complete_framing_and_detail_visibility(self):
        run, data = self.local_run()
        rows = json.loads((run / "renders/camera_validation.json").read_text())
        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(row["file"].endswith("overview.png") for row in rows), 3)
        for row in rows:
            b = row["projected_bounds"]
            self.assertGreaterEqual(b["xmin"], 0.079)
            self.assertLessEqual(b["xmax"], 0.921)
            self.assertGreaterEqual(b["ymin"], 0.079)
            self.assertLessEqual(b["ymax"], 0.921)
            names = set(row["visible_components"])
            if "overview" in row["file"]:
                self.assertTrue({"GT090101_lower", "GT090101_upper", "LCD_lower_holder", "LCD_upper_holder", "openhi_microscope"}.issubset(names))
                self.assertIn("frame_camera_body", names)
                if row["variant"] != "single_4f":
                    self.assertIn("event_camera_body", names)
            if "lower_optical_stack" in row["file"]:
                self.assertEqual(names, set(data["variants"]["single_4f"]["lower_detail_components"]))
                self.assertNotIn("openhi_microscope", names)

    def test_nutstore_copy_is_verified(self):
        nutstore = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
        if not nutstore.is_dir():
            self.skipTest("Local Nutstore is not mounted")
        run, _ = self.local_run()
        target = nutstore / DESIGN.name / run.name
        checksums = json.loads((run / "sync_manifest.json").read_text())
        self.assertIn("figures/Figure_updated_dual_LCD_optical_setup.pdf", checksums)
        for relative, expected in checksums.items():
            self.assertEqual(hashlib.sha256((target / relative).read_bytes()).hexdigest(), expected)

    def test_publication_panels_retain_all_nonwhite_content(self):
        run, _ = self.local_run()
        panels = json.loads((run / "figures/panel_layout.json").read_text())
        self.assertEqual(len(panels), 4)
        for panel in panels:
            x0, y0, x1, y1 = panel["white_margin_crop_px"]
            bx0, by0, bx1, by1 = panel["nonwhite_content_bounds_px"]
            self.assertLessEqual(x0, bx0)
            self.assertLessEqual(y0, by0)
            self.assertGreaterEqual(x1, bx1)
            self.assertGreaterEqual(y1, by1)
            self.assertFalse(panel["apparatus_geometry_changed"])
        for suffix in ("png", "pdf", "svg"):
            self.assertTrue((run / f"figures/Figure_updated_dual_LCD_optical_setup.{suffix}").is_file())


if __name__ == "__main__":
    unittest.main()

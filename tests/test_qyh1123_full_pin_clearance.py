import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/qyh1123_light_valve_centered_clearance_cage_holder"


class Qyh1123FullPinClearanceTests(unittest.TestCase):
    def setUp(self):
        self.summary = json.loads(
            (DESIGN / "artifacts/pin_clearance_manifest.json").read_text()
        )

    def local_data(self):
        rows = []
        for key, row in self.summary["variants"].items():
            path = ROOT / row["manifest"]
            if not path.is_file():
                self.skipTest("Local generated CAD runs are not present")
            rows.append((key, json.loads(path.read_text()), path.parent))
        return rows

    def test_both_orientations_and_connected_window(self):
        self.assertEqual(set(self.summary["variants"]), {"0deg", "45deg"})
        p = self.summary["pin_clearance"]
        self.assertEqual(p["window_width_mm"], 12)
        self.assertEqual(p["window_length_mm"], 9)
        self.assertEqual(p["body_thickness_mm"], 8)
        self.assertEqual(
            (p["window_inner_y_mm"] + p["window_outer_y_mm"]) / 2,
            p["window_center_y_mm"],
        )
        self.assertEqual(
            p["optical_window_edge_y_mm"] - p["window_inner_y_mm"],
            p["remaining_optical_ledge_mm"],
        )
        self.assertEqual(p["remaining_optical_ledge_mm"], 1)

    def test_preserved_source_and_fit(self):
        for key, data, _ in self.local_data():
            with self.subTest(variant=key):
                source = ROOT / data["source"]["path"]
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    data["source"]["sha256"],
                )
                self.assertEqual(data["seat_rotation_deg"], 0 if key == "0deg" else 45)
                p = data["parameters"]
                self.assertEqual(
                    (p["body_width_mm"], p["body_height_mm"], p["body_thickness_mm"]),
                    (42, 42, 8),
                )
                self.assertEqual(p["cage_rod_pitch_mm"], 30)
                self.assertEqual(p["cage_rod_clearance_diameter_mm"], 6.4)
                self.assertEqual(p["valve_pocket_clearance_mm"], 0.6)
                self.assertEqual(p["valve_pocket_depth_mm"], 2.2)
                self.assertEqual(data["pin_clearance"], self.summary["pin_clearance"])

    def test_clearance_and_no_unrelated_geometry_change(self):
        for key, data, _ in self.local_data():
            checks = data["geometry_checks"]
            for name in (
                "full_window_obstruction_mm3",
                "material_added_mm3",
                "outside_window_changed_mm3",
                "protected_cage_collars_changed_mm3",
                "pin_envelope_obstruction_mm3",
                "plug_envelope_obstruction_mm3",
                "pins_vs_rods_mm3",
                "plug_vs_rods_mm3",
                "round_trip_changed_mm3",
            ):
                with self.subTest(variant=key, check=name):
                    self.assertLess(abs(checks[name]), 1e-5)
            self.assertEqual(checks["holder_solid_count"], 1)
            self.assertTrue(checks["holder_valid"])
            self.assertTrue(checks["assembly_valid"])

    def test_grounded_holder_only_print_packages(self):
        for key, data, run in self.local_data():
            with self.subTest(variant=key):
                p = data["print_validation"]
                self.assertEqual(p["solid_count"], 1)
                self.assertTrue(p["step_valid"])
                self.assertTrue(p["watertight"])
                self.assertEqual(p["mesh_components"], 1)
                self.assertAlmostEqual(p["min_z_mm"], 0)
                self.assertTrue(p["first_layer_nonempty"])
                self.assertEqual(p["three_mf_build_items"], 1)
                self.assertEqual(p["three_mf_units"], "millimeter")
                self.assertFalse(p["ears_added"])
                for ext in ("step", "stl", "3mf"):
                    self.assertTrue((run / (p["stem"] + "." + ext)).is_file())

    def test_front_rear_and_print_renders_are_uncropped(self):
        for key, _, run in self.local_data():
            rows = json.loads((run / "renders/camera_validation.json").read_text())
            self.assertEqual(
                {row["file"] for row in rows},
                {
                    "LCD_face_top.png",
                    "rear_through_clearance.png",
                    "rear_connector_envelope_reference.png",
                    "direct_print.png",
                },
            )
            for row in rows:
                with self.subTest(variant=key, view=row["file"]):
                    self.assertTrue((run / "renders" / row["file"]).is_file())
                    b = row["projected_bounds"]
                    self.assertGreaterEqual(b["xmin"], 0.079)
                    self.assertLessEqual(b["xmax"], 0.921)
                    self.assertGreaterEqual(b["ymin"], 0.079)
                    self.assertLessEqual(b["ymax"], 0.921)
                    if row["file"] == "direct_print.png":
                        self.assertEqual(row["visible_objects"], ["print_holder_only"])

    def test_reference_geometry_is_explicitly_not_a_flush_enclosure(self):
        for _, data, _ in self.local_data():
            limitations = " ".join(data["limitations"])
            self.assertIn("not measured Dupont", limitations)
            self.assertIn("may project beyond", limitations)
            self.assertIn("not a closed flush", limitations)
            self.assertIn("rear -Z", data["coordinate_rule"])

    def test_synced_files_match_run_checksums(self):
        nutstore = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
        if not nutstore.is_dir():
            self.skipTest("Local Nutstore is not mounted")
        for key, _, run in self.local_data():
            destination = nutstore / DESIGN.name / run.name
            records = json.loads((run / "sync_manifest.json").read_text())
            self.assertGreaterEqual(len(records), 28)
            for relative, digest in records.items():
                with self.subTest(variant=key, file=relative):
                    for folder in (run, destination):
                        self.assertEqual(
                            hashlib.sha256((folder / relative).read_bytes()).hexdigest(),
                            digest,
                        )


if __name__ == "__main__":
    unittest.main()

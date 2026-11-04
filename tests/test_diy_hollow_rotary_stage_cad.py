"""Lightweight source contracts plus optional local generated-artifact checks."""

import ast
import hashlib
import json
import math
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/diy_hollow_rotary_stage_openhi_nema17"
TREE = ast.parse((DESIGN / "build_stage.py").read_text())
PARAMETERS = next(
    ast.literal_eval(node.value)
    for node in TREE.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "P" for t in node.targets)
)


class RotaryStageSourceTests(unittest.TestCase):
    def test_exact_openhi_motor_dimensions(self):
        self.assertEqual(PARAMETERS["motor_body_mm"], [42, 42, 40])
        self.assertEqual(PARAMETERS["motor_hole_pitch_mm"], 31)
        self.assertEqual(PARAMETERS["motor_shaft_diameter_mm"], 5)
        self.assertEqual(PARAMETERS["motor_shaft_length_from_face_mm"], 22)

    def test_exact_open_belt_length(self):
        function = next(
            n
            for n in TREE.body
            if isinstance(n, ast.FunctionDef) and n.name == "center_distance"
        )
        context = {"P": PARAMETERS, "math": math}
        exec(
            compile(
                ast.Module(body=[function], type_ignores=[]),
                "<center_distance>",
                "exec",
            ),
            context,
        )
        center, length, big, small = context["center_distance"]()
        self.assertAlmostEqual(center, 83.8848853054856, places=8)
        self.assertAlmostEqual(length, 320, places=9)
        self.assertAlmostEqual(big / small, 6)

    def test_clearance_is_not_a_global_scale(self):
        self.assertEqual(PARAMETERS["motor_body_clearance_each_side_mm"], 0.2)
        self.assertAlmostEqual(
            PARAMETERS["rotor_bearing_seat_mm"] - PARAMETERS["bearing_od_mm"], 0.1
        )
        self.assertAlmostEqual(
            PARAMETERS["bearing_id_mm"] - PARAMETERS["fixed_inner_journal_mm"], 0.1
        )
        self.assertEqual(PARAMETERS["clear_bore_mm"], 30)
        self.assertEqual(PARAMETERS["polarizer_insert_clear_aperture_mm"], 24)

    def test_height_and_table_grid_are_explicit(self):
        self.assertEqual(PARAMETERS["tray_underside_z_mm"], 85)
        self.assertEqual(PARAMETERS["stationary_carrier_underside_z_mm"], 75)
        self.assertEqual(PARAMETERS["lowest_rotating_cup_z_mm"], 79)
        for x, y in PARAMETERS["breadboard_screw_centers_mm"]:
            self.assertEqual(x % 25, 0)
            self.assertEqual(y % 25, 0)


class RotaryStageGeneratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pointer = DESIGN / "artifacts/latest.json"
        if not pointer.exists():
            raise unittest.SkipTest("Local CAD run is not present")
        cls.run_dir = ROOT / json.loads(pointer.read_text())["run_dir"]
        if not (cls.run_dir / "manifest.json").exists():
            raise unittest.SkipTest(
                "Generated CAD files are intentionally not stored in git"
            )
        cls.data = json.loads((cls.run_dir / "manifest.json").read_text())

    def test_collision_and_fastener_gates(self):
        checks = self.data["checks"]
        self.assertEqual(checks["empty_stage_bore_obstruction_mm3"], 0)
        for name in (
            "moving_vs_fixed_intersections_mm3",
            "full_rotation_envelope_intersections_mm3",
            "belt_to_motor_screw_intersections_mm3",
            "motor_tension_extremes_vs_carrier_mm3",
        ):
            self.assertTrue(checks[name])
            self.assertLessEqual(max(checks[name].values()), 1e-5)
        self.assertTrue(checks["assembly_step_valid"])
        self.assertGreaterEqual(checks["motor_screw_head_to_belt_vertical_gap_mm"], 0.7)
        self.assertEqual(checks["motor_mount_screw_engagement_mm"], 3)
        self.assertAlmostEqual(
            checks["measured_main_flange_underside_z_mm"], 85, places=6
        )
        self.assertGreater(checks["M4_stand_screw_bottom_clearance_mm"], 0)

    def test_every_print_is_one_grounded_object(self):
        records = {**self.data["print_validation"], **self.data["fit_coupons"]}
        self.assertEqual(len(records), 15)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        for name, row in records.items():
            with self.subTest(part=name):
                self.assertTrue(
                    row["step_valid"]
                    and row["watertight"]
                    and row["first_layer_nonempty"]
                )
                self.assertEqual(row["solids"], 1)
                self.assertEqual(row["mesh_components"], 1)
                self.assertAlmostEqual(row["min_z_mm"], 0, places=5)
                for extension in (".stl", ".step", ".3mf"):
                    self.assertTrue(
                        (self.run_dir / (row["stem"] + extension)).is_file()
                    )
                with zipfile.ZipFile(self.run_dir / (row["stem"] + ".3mf")) as z:
                    model = ET.fromstring(z.read("3D/3dmodel.model"))
                self.assertEqual(model.attrib["unit"], "millimeter")
                self.assertEqual(len(model.findall("m:build/m:item", ns)), 1)
                vertices = model.findall(
                    "m:resources/m:object/m:mesh/m:vertices/m:vertex", ns
                )
                self.assertAlmostEqual(
                    min(float(v.attrib["z"]) for v in vertices), 0, places=5
                )

    def test_motor_source_is_traceable(self):
        source = self.data["source_motor"]
        self.assertTrue(source["selected_label"].endswith("/42 stepper motor"))
        path = ROOT / source["step"]
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(), source["sha256"]
        )

    def test_render_camera_margins(self):
        path = self.run_dir / "render_checks.json"
        if not path.exists():
            self.skipTest("Rendering has not completed")
        rows = json.loads(path.read_text())
        self.assertTrue(rows["cpu_only"])
        self.assertEqual(len(rows["renders"]), 19)
        for record in rows["renders"]:
            b = record["camera_bounds"]
            self.assertGreaterEqual(min(b["xmin"], b["ymin"]), 0.079)
            self.assertLessEqual(max(b["xmax"], b["ymax"]), 0.921)
            self.assertTrue((self.run_dir / record["path"]).is_file())

    def test_synced_assets_match(self):
        path = DESIGN / "artifacts/sync.json"
        if not path.exists():
            self.skipTest("Nutstore packaging has not completed")
        record = json.loads(path.read_text())
        if record["run_dir"] != str(self.run_dir.relative_to(ROOT)):
            self.skipTest("Current run has not been synced")
        destination = Path(record["nutstore_run"])
        for name, expected in json.loads(
            (self.run_dir / "checksums.json").read_text()
        ).items():
            self.assertEqual(
                hashlib.sha256((destination / name).read_bytes()).hexdigest(),
                expected,
                name,
            )


if __name__ == "__main__":
    unittest.main()

"""Fast source contracts for the measured GSP25 floating-retainer variants."""

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "cad/designs/diy_hollow_rotary_stage_openhi_nema17"
TREE = ast.parse((DESIGN / "build_polarizer_variants.py").read_text())
FIT = next(
    ast.literal_eval(n.value)
    for n in TREE.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "FIT" for t in n.targets)
)
FUNC = next(
    n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "datums"
)
NAMESPACE = {"FIT": FIT}
exec(  # noqa: S102 - only the repository-owned pure datums function is compiled.
    compile(ast.Module(body=[FUNC], type_ignores=[]), "<polarizer datums>", "exec"),
    NAMESPACE,
)


class PolarizerSourceTests(unittest.TestCase):
    def test_measured_optic_overrides_catalog_thickness(self):
        self.assertEqual(FIT["optic_thickness_mm"], 4.5)
        self.assertEqual(FIT["optic_diameter_mm"], 25.4)
        self.assertEqual(FIT["pocket_diameter_mm"], 25.7)

    def test_intentionally_shallow_split_pockets(self):
        d = NAMESPACE["datums"]()
        self.assertEqual(FIT["pocket_depth_each_mm"], 2)
        self.assertAlmostEqual(d["bare_glass_seam_gap"], 0.5)
        self.assertAlmostEqual(d["seam_gap"], 0.7)
        self.assertGreater(d["cap_bottom"], d["base_top"])
        self.assertAlmostEqual(d["glass_bottom"] - d["base_bottom"], 1.7)

    def test_direct_pilot_and_nut_roof_are_not_interchangeable(self):
        self.assertEqual(FIT["direct_M3_pilot_mm"], 2.5)
        d = NAMESPACE["datums"]()
        self.assertGreaterEqual(d["part_body_height"] - FIT["nut_pocket_depth_mm"], 1)

    def test_screws_do_not_hit_the_rotor(self):
        d = NAMESPACE["datums"]()
        tip = (
            d["cap_top"]
            + FIT["cap_screw_washer_mm"]
            - FIT["cap_screw_length_mm"]
            - d["base_bottom"]
        )
        self.assertAlmostEqual(tip, 0.4)
        self.assertGreaterEqual(FIT["nut_pocket_depth_mm"] - tip, 2)
        self.assertGreaterEqual(d["part_body_height"] - tip, 3)

    def test_generated_print_and_collision_records(self):
        pointer = DESIGN / "artifacts/polarizer_variant.json"
        if not pointer.exists():
            self.skipTest("Local generated run is optional")
        run = ROOT / json.loads(pointer.read_text())["run_dir"]
        if not (run / "manifest.json").exists():
            self.skipTest("Generated files are local")
        data = json.loads((run / "manifest.json").read_text())
        self.assertEqual(set(data["variants"]), {"direct_pilot", "captive_nut"})
        self.assertFalse(data["promoted_to_default"])
        for entry in data["variants"].values():
            self.assertLessEqual(max(entry["checks_mm3"].values()), 1e-5)
            for row in entry["print_validation"].values():
                self.assertTrue(row["watertight"] and row["step_valid"])
                self.assertEqual(row["mesh_components"], 1)
                self.assertEqual(row["3mf_build_items"], 1)
                self.assertAlmostEqual(row["min_z_mm"], 0, places=5)


if __name__ == "__main__":
    unittest.main()

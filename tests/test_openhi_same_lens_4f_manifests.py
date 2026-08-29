import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = ROOT / "cad" / "designs"
DESIGN_NAMES = (
    "openhi_4f_gla11_025_025_same_lens",
    "openhi_4f_gla11_025_050_same_lens",
    "openhi_4f_jh036_same_lens",
    "openhi_4f_jh042_same_lens",
)


class OpenHISameLens4fManifestTests(unittest.TestCase):
    def load_manifest(self, design_name):
        path = DESIGN_ROOT / design_name / "artifacts" / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_complete_paths_and_b_axis_match_source_contract(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                optical = manifest["optical_layout"]
                expected_path = 4.0 * optical["catalog_efl_mm"] + 4.6

                self.assertAlmostEqual(
                    optical["expected_end_path_4f_plus_seat_mm"],
                    expected_path,
                    places=7,
                )
                self.assertAlmostEqual(
                    optical["measured_end_path_mm"]["A_to_B"],
                    expected_path,
                    places=7,
                )
                self.assertAlmostEqual(
                    optical["measured_end_path_mm"]["A_to_C"],
                    expected_path,
                    places=7,
                )
                self.assertAlmostEqual(optical["b_axis_x_mm"], 254.633, places=7)
                self.assertAlmostEqual(
                    optical["b_axis_shift_from_a_mm"], -0.367, places=7
                )
                self.assertTrue(
                    all(
                        math.isclose(error, 0.0, abs_tol=1e-8)
                        for error in optical["b_axis_chain_error_mm"].values()
                    )
                )

    def test_committed_geometry_gates_all_pass(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                self.assertTrue(manifest["checks"])
                self.assertTrue(all(manifest["checks"].values()))
                self.assertEqual(set(manifest["parts"]), {
                    "A",
                    "A_C_BS",
                    "B",
                    "C",
                    "Lens_B_holder",
                    "Lens_C_holder",
                })


if __name__ == "__main__":
    unittest.main()

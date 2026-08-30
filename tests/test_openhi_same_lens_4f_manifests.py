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

    def test_thread_interface_map_preserves_tight_fit_variants(self):
        expected = {
            "a_c_bs_lower_a_female": ("pivot_mm", 29.8, "groove_mm", 30.6),
            "a_c_bs_side_c_female": ("pivot_mm", 29.6, "groove_mm", 30.4),
            "lens_b_holder_lens_side_female": (
                "pivot_mm", 29.8, "groove_mm", 30.6
            ),
            "lens_c_holder_lens_side_female": (
                "pivot_mm", 29.8, "groove_mm", 30.6
            ),
            "lens_c_holder_beam_splitter_side_male": (
                "root_mm", 29.8, "crest_mm", 30.6
            ),
        }
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                interfaces = self.load_manifest(design_name)["thread_interfaces"]
                for name, (root_key, root, crest_key, crest) in expected.items():
                    self.assertAlmostEqual(interfaces[name][root_key], root, places=7)
                    self.assertAlmostEqual(interfaces[name][crest_key], crest, places=7)

    def test_final_lens_fit_and_chamfer_audit(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                audit = manifest["final_dimensional_audit"]
                lens_fit = audit["lens_fit"]
                chamfers = audit["receiver_chamfers"]

                self.assertAlmostEqual(
                    lens_fit["radial_clearance_each_side_mm"], 0.125, places=7
                )
                self.assertGreaterEqual(
                    lens_fit["holder_support_land_radial_mm"], 0.875
                )
                self.assertGreaterEqual(
                    lens_fit["cap_retainer_land_radial_mm"], 0.75
                )
                self.assertGreater(lens_fit["minimum_holder_wall_radial_mm"], 7.0)
                self.assertAlmostEqual(
                    chamfers["lens_pocket_to_female_pivot"]["angle_deg"],
                    45.0,
                    places=7,
                )
                self.assertGreaterEqual(
                    chamfers["male_retainer_to_lens"]["angle_deg"], 44.5
                )
                self.assertLessEqual(
                    chamfers["male_retainer_to_lens"]["angle_deg"], 45.5
                )

    def test_thread_clearance_and_source_tight_fit_are_explicit(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                audit = self.load_manifest(design_name)["final_dimensional_audit"]
                retainer = audit["lens_retainer_thread_fit"]
                central = audit["central_c_source_style_fit"]
                camera = audit["camera_output_thread"]

                self.assertAlmostEqual(retainer["root_radial_clearance_mm"], 0.1)
                self.assertAlmostEqual(retainer["crest_radial_clearance_mm"], 0.1)
                self.assertAlmostEqual(retainer["bounded_length_mm"], 7.75)
                self.assertTrue(retainer["runout_clipped_to_parent_length"])
                self.assertAlmostEqual(
                    central["nominal_diametric_interference_mm"], 0.2
                )
                self.assertIn("not a CAD clearance fit", central["classification"])
                self.assertEqual(
                    camera["classification"],
                    "source OpenHI printed C-mount-like profile",
                )

    def test_optical_distance_chain_preserves_source_seat_allowances(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                focal_length = manifest["lens"]["focal_length_mm"]
                chain = manifest["final_dimensional_audit"]["optical_distance_chain"]

                self.assertAlmostEqual(
                    chain["beam_splitter_to_nominal_seat_mm"], focal_length
                )
                self.assertAlmostEqual(
                    chain["a_to_b_nominal_seat_spacing_2f_mm"], 2 * focal_length
                )
                self.assertAlmostEqual(
                    chain["a_to_c_nominal_seat_spacing_2f_mm"], 2 * focal_length
                )
                self.assertAlmostEqual(
                    chain["a_seat_to_outer_end_mm"], focal_length + 0.2
                )
                self.assertAlmostEqual(
                    chain["b_seat_to_outer_end_mm"], focal_length + 4.4
                )
                self.assertAlmostEqual(
                    chain["c_seat_to_outer_end_mm"], focal_length + 4.4
                )
                self.assertAlmostEqual(
                    chain["a_outer_end_to_beam_splitter_mm"],
                    2 * focal_length + 0.2,
                )
                self.assertAlmostEqual(
                    chain["beam_splitter_to_b_outer_end_mm"],
                    2 * focal_length + 4.4,
                )
                self.assertAlmostEqual(
                    chain["beam_splitter_to_c_outer_end_mm"],
                    2 * focal_length + 4.4,
                )
                self.assertAlmostEqual(
                    chain["a_to_b_complete_outer_end_path_mm"],
                    4 * focal_length + 4.6,
                )
                self.assertAlmostEqual(
                    chain["a_to_c_complete_outer_end_path_mm"],
                    4 * focal_length + 4.6,
                )

    def test_lens_models_use_analytic_surfaces(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                self.assertTrue(manifest["lens_model"]["analytic_spherical_faces"])
                self.assertLessEqual(
                    manifest["lens_outputs"]["step_validation"]["face_count"], 6
                )

                if manifest["lens"]["kind"] == "plano_convex":
                    model = manifest["lens_model"]
                    self.assertLess(
                        abs(model["manufacturer_edge_consistency_error_mm"]),
                        0.05,
                    )
                    self.assertAlmostEqual(model["bevel_mm"], 0.2)
                    self.assertLess(
                        model["modeled_edge_thickness_mm"],
                        model["unbeveled_edge_thickness_mm"],
                    )


if __name__ == "__main__":
    unittest.main()

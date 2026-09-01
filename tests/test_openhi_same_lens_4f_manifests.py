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
AC_BS_MANIFEST = (
    DESIGN_ROOT
    / "openhi_a_c_bs_dual_female_29p6_pivot"
    / "artifacts"
    / "manifest.json"
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
                inward_support = manifest["lens_model"][
                    "mechanical_inward_contact_z_mm"
                ]
                chain = manifest["final_dimensional_audit"]["optical_distance_chain"]

                self.assertAlmostEqual(
                    chain["beam_splitter_to_inward_axis_vertex_mm"],
                    focal_length,
                )
                self.assertAlmostEqual(
                    chain["beam_splitter_to_annular_support_plane_mm"],
                    focal_length + inward_support,
                )
                self.assertAlmostEqual(
                    chain["a_to_b_inward_vertex_spacing_2f_mm"],
                    2 * focal_length,
                )
                self.assertAlmostEqual(
                    chain["a_to_c_inward_vertex_path_2f_mm"],
                    2 * focal_length,
                )
                self.assertAlmostEqual(
                    chain["a_seat_to_outer_end_mm"],
                    focal_length + 0.2 - inward_support,
                )
                self.assertAlmostEqual(
                    chain["b_seat_to_outer_end_mm"],
                    focal_length + 4.4 - inward_support,
                )
                self.assertAlmostEqual(
                    chain["c_seat_to_outer_end_mm"],
                    focal_length + 4.4 - inward_support,
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

    def test_fully_inserted_pairs_preserve_real_lens_cavity(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                model = manifest["lens_model"]
                required = (
                    model["mechanical_outward_contact_z_mm"]
                    - model["mechanical_inward_contact_z_mm"]
                )
                cavities = manifest["final_dimensional_audit"][
                    "fully_inserted_lens_cavities"
                ]
                self.assertEqual(set(cavities), {"A", "B", "C"})
                for cavity in cavities.values():
                    self.assertAlmostEqual(
                        cavity["lens_required_axial_envelope_mm"],
                        required,
                    )
                    self.assertAlmostEqual(
                        cavity["fully_inserted_available_cavity_mm"],
                        required + 0.2,
                    )
                    self.assertAlmostEqual(
                        cavity["fully_inserted_axial_clearance_mm"],
                        0.2,
                    )
                    self.assertAlmostEqual(
                        cavity["full_thread_engagement_mm"],
                        7.75,
                    )

                brep_audit = manifest["optical_layout"][
                    "lens_axis_brep_audit"
                ]
                self.assertEqual(set(brep_audit), {"A", "B", "C"})
                for measured in brep_audit.values():
                    self.assertAlmostEqual(
                        measured["inward_vertex_error_mm"],
                        0.0,
                    )
                    self.assertAlmostEqual(
                        measured["outward_vertex_error_mm"],
                        0.0,
                    )

    def test_a_input_receiver_is_exact_source_geometry_inside_arm(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                receiver = manifest["a_input_receiver_audit"]
                self.assertTrue(receiver["receiver_is_exact_source_brep"])
                self.assertTrue(receiver["thread_relief_is_present"])
                self.assertTrue(receiver["insertion_depth_is_internal_to_4f_arm"])
                self.assertAlmostEqual(
                    receiver["receiver_depth_mm"],
                    12.474,
                    places=5,
                )
                self.assertAlmostEqual(receiver["pilot_diameter_mm"], 25.0)
                self.assertAlmostEqual(
                    receiver["groove_envelope_diameter_mm"],
                    25.8,
                )
                self.assertAlmostEqual(receiver["missing_source_void_mm3"], 0.0)
                self.assertAlmostEqual(receiver["excess_void_mm3"], 0.0)
                self.assertGreater(
                    receiver["source_thread_relief_outside_smooth_pilot_mm3"],
                    1.0,
                )
                self.assertGreaterEqual(
                    receiver["minimum_radial_wall_inside_lens_thread_root_mm"],
                    1.5,
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

    def test_complete_axes_and_mechanical_optical_cores_are_clear(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                optical = self.load_manifest(design_name)["optical_layout"]
                self.assertTrue(
                    all(
                        math.isclose(error, 0.0, abs_tol=1e-8)
                        for error in optical[
                            "complete_axis_chain_error_mm"
                        ].values()
                    )
                )
                audit = optical["mechanical_optical_path_audit"]
                self.assertAlmostEqual(
                    audit["minimum_verified_core_diameter_mm"], 4.0
                )
                self.assertEqual(set(audit["paths"]), {"A", "B", "C"})
                for path in audit["paths"].values():
                    self.assertAlmostEqual(path["total_overlap_mm3"], 0.0)
                membrane = audit["c_receiver_membrane_probe"]
                self.assertAlmostEqual(
                    membrane["generated_a_c_bs_overlap_mm3"], 0.0
                )
                self.assertAlmostEqual(
                    membrane["source_a_c_bs_overlap_mm3"], 0.0
                )

    def test_thread_construction_and_print_artifacts_are_bounded(self):
        for design_name in DESIGN_NAMES:
            with self.subTest(design=design_name):
                manifest = self.load_manifest(design_name)
                thread_audit = manifest["thread_construction_audit"]
                self.assertTrue(
                    thread_audit["all_samples_clipped_to_parent_interval"]
                )
                self.assertTrue(
                    all(
                        sample["clipped_to_parent_interval"]
                        for sample in thread_audit["samples"].values()
                    )
                )
                for name, part in manifest["parts"].items():
                    self.assertEqual(part["step_validation"]["solid_count"], 1)
                    mesh_validation = part["mesh_validation"]
                    self.assertAlmostEqual(
                        mesh_validation["minimum_z_mm"], 0.0, places=5
                    )
                    self.assertGreater(
                        mesh_validation["first_layer_triangle_count"], 0
                    )
                    validation = part["3mf_validation"]
                    self.assertEqual(validation["unit"], "millimeter")
                    self.assertEqual(validation["mesh_object_count"], 1)
                    self.assertEqual(validation["build_item_count"], 1)
                    self.assertTrue(
                        validation["build_items_reference_mesh_objects"]
                    )
                    self.assertEqual(validation["components"], 1)
                    self.assertTrue(validation["indices_valid"])
                    self.assertTrue(validation["watertight"])
                    self.assertTrue(validation["winding_consistent"])
                    self.assertTrue(validation["bounds_match_stl"])
                    self.assertAlmostEqual(
                        validation["minimum_z_mm"], 0.0, places=5
                    )
                    self.assertGreater(
                        validation["first_layer_triangle_count"], 0
                    )
                    if name in {"C", "Lens_B_holder", "Lens_C_holder"}:
                        self.assertIn("rotate", part["print_orientation"])

    def test_fixed_a_c_bs_source_has_no_c_receiver_membrane(self):
        manifest = json.loads(AC_BS_MANIFEST.read_text(encoding="utf-8"))
        validation = manifest["validation"]
        self.assertTrue(validation["checks"]["all_pass"])
        self.assertTrue(
            validation["checks"]["beam_splitter_to_C_centerline_is_clear"]
        )
        self.assertTrue(validation["checks"]["C_receiver_has_no_fusion_membrane"])
        probes = validation["optical_bore_probes"]
        self.assertAlmostEqual(
            probes["beam_splitter_to_c_core"]["solid_overlap_mm3"], 0.0
        )
        self.assertAlmostEqual(
            probes["c_receiver_smooth_core"]["solid_overlap_mm3"], 0.0
        )


if __name__ == "__main__":
    unittest.main()

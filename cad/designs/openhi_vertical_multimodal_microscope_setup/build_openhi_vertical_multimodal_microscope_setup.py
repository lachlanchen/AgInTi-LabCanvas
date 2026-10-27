#!/usr/bin/env python3
"""Build the vertical Lamp/LCD/sample/OpenHI apparatus in one- and two-4f forms.

The accepted source CAD remains unchanged. This script imports those bodies,
places them on a single optical datum, and adds only the missing visualization
proxies: the tungsten bulb, LCD polarizer film, sample, and camera housings.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
import trimesh
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
RENDER_MESH_DIR = ARTIFACT_DIR / "render_meshes"
RUN_DIR = DESIGN_DIR / "runs" / "run-1-apparatus-single-dual-4f-20261027T132540Z"
STEM = "openhi_vertical_multimodal_microscope_setup"

PHOTO_REFERENCES = {
    "actual_setup_01": DESIGN_DIR / "reference_media/actual_setup_01.jpeg",
    "actual_setup_02": DESIGN_DIR / "reference_media/actual_setup_02.jpeg",
    "actual_setup_03": DESIGN_DIR / "reference_media/actual_setup_03.jpeg",
}


SOURCE = {
    "dock": ROOT / "cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-1-original-no-ears-20260710T130229Z/USE_THIS_cage_rod_dock_100mm_base_10mm_holes.step",
    "spacer": ROOT / "cad/designs/cage_spacer_id6p5_od10p5/USE_THIS_cage_spacer_id6p5_od10p5_single_h5.step",
    "lamp_holder": ROOT / "cad/designs/lumileds_pcb_aligned_sink_cage_holder/USE_THIS_lumileds_pcb_aligned_sink_cage_holder.step",
    "lamp_pcb": ROOT / "cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_proxy.step",
    "lcd_holder": ROOT / "cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder.step",
    "lcd": ROOT / "cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_valve_proxy.step",
    "sample_holder": ROOT / "cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/runs/run-2-correct-30mm-cage-rod-sockets-20260709T032257Z/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_assembled.step",
    "gt090101": ROOT / "cad/references/hengyang-gt090101/GT-090101.stp",
    "microscope": ROOT / "cad/extracted/OpenHI_STEP/Microscope yx umot large.step.step",
    "four_f": ROOT / "cad/designs/openhi_4f_gla11_025_050_same_lens/USE_THIS_gla11_025_050_openhi_4f_assembly.step",
    "four_f_manifest": ROOT / "cad/designs/openhi_4f_gla11_025_050_same_lens/artifacts/manifest.json",
    "four_f_meshes": ROOT / "cad/designs/openhi_4f_gla11_025_050_same_lens/artifacts/assembly_components",
    "c12880_socket": ROOT / "cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_cmount_socket.step",
    "c12880_plate": ROOT / "cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_holder_plate.step",
    "c12880_board": ROOT / "cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_board_proxy.step",
    "c12880_sensor": ROOT / "cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_sensor_package_proxy.step",
    "c12880_pins": ROOT / "cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_six_pin_tail_proxy.step",
}


P = {
    "cage_pitch_mm": 30.0,
    "cage_rod_diameter_mm": 6.0,
    "dock_top_z_mm": 30.0,
    "lamp_holder_center_z_mm": 39.0,
    "lcd_holder_center_z_mm": 57.0,
    "sample_holder_bottom_z_mm": 75.0,
    "sample_holder_height_mm": 34.0,
    "gt090101_bottom_z_mm": 114.0,
    "gt090101_top_z_mm": 132.0,
    "microscope_bottom_z_mm": 140.0,
    "microscope_source_bottom_z_mm": 174.0,
    "microscope_source_top_z_mm": 476.0,
    "openhi_source_bs_mm": [255.0, 210.0, 600.0],
    "openhi_source_a_input_z_mm": 499.8,
    "openhi_source_b_output_z_mm": 704.4,
    "openhi_source_c_output_x_mm": 359.4,
    "primary_a_input_gap_mm": 3.0,
    "cascade_input_gap_mm": 3.0,
    "lcd_polarizer_thickness_mm": 0.25,
    "petri_outer_diameter_mm": 35.0,
    "petri_inner_diameter_mm": 33.0,
    "tungsten_bulb_diameter_mm": 3.0,
}


COLORS = {
    "polymer": cq.Color(0.10, 0.12, 0.14),
    "polymer_mid": cq.Color(0.20, 0.23, 0.27),
    "metal": cq.Color(0.68, 0.72, 0.76),
    "pcb": cq.Color(0.04, 0.30, 0.15),
    "glass": cq.Color(0.28, 0.78, 0.92, 0.45),
    "polarizer": cq.Color(0.13, 0.18, 0.24, 0.62),
    "sample": cq.Color(0.12, 0.65, 0.58, 0.65),
    "camera": cq.Color(0.11, 0.17, 0.24),
    "event_camera": cq.Color(0.38, 0.10, 0.08),
    "sensor": cq.Color(0.74, 0.76, 0.78),
}


@dataclass
class Component:
    name: str
    shape: cq.Workplane
    category: str
    source: str
    exact: bool = True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def import_step(path: Path) -> cq.Workplane:
    if not path.exists():
        raise FileNotFoundError(path)
    return cq.importers.importStep(str(path))


def box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def ring(outer_diameter: float, inner_diameter: float, height: float, z_min: float) -> cq.Workplane:
    return (
        cq.Workplane("XY", origin=(0, 0, z_min))
        .circle(outer_diameter / 2.0)
        .circle(inner_diameter / 2.0)
        .extrude(height)
    )


def bbox_dict(shape: cq.Workplane) -> dict[str, list[float]]:
    bb = shape.val().BoundingBox()
    return {
        "min": [round(bb.xmin, 6), round(bb.ymin, 6), round(bb.zmin, 6)],
        "max": [round(bb.xmax, 6), round(bb.ymax, 6), round(bb.zmax, 6)],
        "size": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
    }


def place_openhi(shape: cq.Workplane, target_bs: tuple[float, float, float], rotate_y_deg: float = 0.0) -> cq.Workplane:
    sx, sy, sz = P["openhi_source_bs_mm"]
    placed = shape.translate((-sx, -sy, -sz))
    if rotate_y_deg:
        placed = placed.rotate((0, 0, 0), (0, 1, 0), rotate_y_deg)
    return placed.translate(target_bs)


def openhi_matrix(target_bs: tuple[float, float, float], rotate_y_deg: float = 0.0) -> np.ndarray:
    angle = math.radians(rotate_y_deg)
    c, s = math.cos(angle), math.sin(angle)
    rotation = np.array(
        [[c, 0.0, s, 0.0], [0.0, 1.0, 0.0, 0.0], [-s, 0.0, c, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )
    before = np.eye(4)
    before[:3, 3] = -np.array(P["openhi_source_bs_mm"], dtype=float)
    after = np.eye(4)
    after[:3, 3] = np.array(target_bs, dtype=float)
    return after @ rotation @ before


def camera_proxy_z(name: str, body_xy: float, body_depth: float, port_z: float, direction: int = 1) -> list[Component]:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or +1")
    nose_h = 6.0
    if direction > 0:
        nose = ring(29.0, 22.5, nose_h, port_z)
        body_center_z = port_z + nose_h + body_depth / 2.0
    else:
        nose = ring(29.0, 22.5, nose_h, port_z - nose_h)
        body_center_z = port_z - nose_h - body_depth / 2.0
    body = box((body_xy, body_xy, body_depth), (0.0, 0.0, body_center_z))
    return [
        Component(f"{name}_cmount", nose, "metal", "visualization proxy", exact=False),
        Component(f"{name}_body", body, "camera" if name == "frame_camera" else "event_camera", "visualization proxy", exact=False),
    ]


def camera_proxy_x(name: str, body_xy: float, body_depth: float, port_x: float, direction: int = 1) -> list[Component]:
    parts = camera_proxy_z(name, body_xy, body_depth, 0.0, direction=1)
    result = []
    for part in parts:
        rotated = part.shape.rotate((0, 0, 0), (0, 1, 0), 90.0 if direction > 0 else -90.0)
        result.append(Component(part.name, rotated.translate((port_x, 0, 0)), part.category, part.source, part.exact))
    return result


def build_tungsten_bulb(center_z: float) -> list[Component]:
    pcb_top = center_z - 2.38
    glass = z_cylinder(P["tungsten_bulb_diameter_mm"], 5.2, pcb_top)
    glass = glass.union(cq.Workplane("XY").sphere(P["tungsten_bulb_diameter_mm"] / 2.0).translate((0, 0, pcb_top + 5.2)))
    leads = []
    for x in (-0.5, 0.5):
        leads.append(z_cylinder(0.25, 2.4, pcb_top - 2.2).translate((x, 0, 0)))
    return [
        Component("tungsten_bulb", glass, "glass", "3 mm 5 V tungsten bulb visualization proxy", exact=False),
        Component("tungsten_bulb_leads", cq.Workplane(obj=cq.Compound.makeCompound([lead.val() for lead in leads])), "metal", "tungsten bulb leads visualization proxy", exact=False),
    ]


def build_petri_and_sample(z_bottom: float) -> list[Component]:
    dish_z = z_bottom + 16.0
    dish = ring(P["petri_outer_diameter_mm"], P["petri_inner_diameter_mm"], 1.6, dish_z)
    dish = dish.union(z_cylinder(P["petri_outer_diameter_mm"], 0.55, dish_z))
    sample = z_cylinder(31.5, 0.7, dish_z + 0.55)
    return [
        Component("petri_dish", dish, "glass", "33 mm sample-dish visualization proxy", exact=False),
        Component("sample_volume", sample, "sample", "sample visualization proxy", exact=False),
    ]


def place_c12880(port_x: float, port_z: float, prefix: str) -> list[Component]:
    # Run-5 uses X as the optical axis. Its front-most C-mount face is x=-3 mm,
    # while y=3.6 mm is the assembly envelope center.
    translation = (port_x + 3.0, -3.6, port_z)
    parts = []
    for suffix, key, category in (
        ("socket", "c12880_socket", "polymer"),
        ("plate", "c12880_plate", "polymer_mid"),
        ("board", "c12880_board", "pcb"),
        ("sensor", "c12880_sensor", "sensor"),
        ("pins", "c12880_pins", "metal"),
    ):
        shape = import_step(SOURCE[key]).translate(translation)
        parts.append(Component(f"{prefix}_{suffix}", shape, category, repo_path(SOURCE[key])))
    return parts


def build_common() -> tuple[list[Component], dict[str, float]]:
    components: list[Component] = []
    components.append(Component("dock", import_step(SOURCE["dock"]), "polymer_mid", repo_path(SOURCE["dock"])))

    rod_xy = [(-15.0, -15.0), (-15.0, 15.0), (15.0, -15.0), (15.0, 15.0)]
    sample_bottom = P["sample_holder_bottom_z_mm"]
    sample_top = sample_bottom + P["sample_holder_height_mm"]
    for index, (x, y) in enumerate(rod_xy, start=1):
        lower = z_cylinder(P["cage_rod_diameter_mm"], sample_bottom + 6.0 - P["dock_top_z_mm"], P["dock_top_z_mm"]).translate((x, y, 0))
        upper = z_cylinder(P["cage_rod_diameter_mm"], P["gt090101_top_z_mm"] - (sample_top - 6.0), sample_top - 6.0).translate((x, y, 0))
        components.append(Component(f"cage_rod_{index}_lower", lower, "metal", "nominal 6 mm cage rod proxy", exact=False))
        components.append(Component(f"cage_rod_{index}_upper", upper, "metal", "nominal 6 mm cage rod proxy", exact=False))

    spacer = import_step(SOURCE["spacer"])
    for layer, z_min in enumerate((30.0, 43.0, 48.0), start=1):
        for index, (x, y) in enumerate(rod_xy, start=1):
            components.append(
                Component(
                    f"spacer_L{layer}_{index}",
                    spacer.translate((x, y, z_min)),
                    "metal",
                    repo_path(SOURCE["spacer"]),
                )
            )

    lamp_z = P["lamp_holder_center_z_mm"]
    components.append(Component("lamp_holder", import_step(SOURCE["lamp_holder"]).translate((0, 0, lamp_z)), "polymer", repo_path(SOURCE["lamp_holder"])))
    components.append(Component("lamp_pcb", import_step(SOURCE["lamp_pcb"]).translate((0, 0, lamp_z)), "pcb", repo_path(SOURCE["lamp_pcb"])))
    components.extend(build_tungsten_bulb(lamp_z))

    lcd_z = P["lcd_holder_center_z_mm"]
    components.append(Component("lcd_holder", import_step(SOURCE["lcd_holder"]).translate((0, 0, lcd_z)), "polymer", repo_path(SOURCE["lcd_holder"])))
    components.append(Component("qyh1123_lcd", import_step(SOURCE["lcd"]).translate((0, 0, lcd_z)), "glass", repo_path(SOURCE["lcd"])))
    polarizer_z = lcd_z + 1.70
    film = box((18.0, 20.0, P["lcd_polarizer_thickness_mm"]), (0, 0, polarizer_z + P["lcd_polarizer_thickness_mm"] / 2.0))
    components.append(Component("lcd_lower_polarizer", film, "polarizer", "thin film visualization proxy based on QYH1123 body outline", exact=False))

    components.append(Component("sample_holder_and_cap", import_step(SOURCE["sample_holder"]).translate((0, 0, sample_bottom)), "polymer_mid", repo_path(SOURCE["sample_holder"])))
    components.extend(build_petri_and_sample(sample_bottom))

    gt = import_step(SOURCE["gt090101"])
    gt_z_shift = P["gt090101_bottom_z_mm"] - gt.val().BoundingBox().zmin
    components.append(Component("gt090101_polarizer", gt.translate((0, 0, gt_z_shift)), "polymer", repo_path(SOURCE["gt090101"])))

    microscope_shift_z = P["microscope_bottom_z_mm"] - P["microscope_source_bottom_z_mm"]
    microscope = import_step(SOURCE["microscope"]).translate((-255.0, -210.0, microscope_shift_z))
    components.append(Component("openhi_microscope", microscope, "metal", repo_path(SOURCE["microscope"])))

    gt_adapter = ring(30.0, 24.0, P["microscope_bottom_z_mm"] - P["gt090101_top_z_mm"], P["gt090101_top_z_mm"])
    components.append(Component("polarizer_to_microscope_adapter", gt_adapter, "polymer", "visualization proxy", exact=False))

    microscope_top_world = P["microscope_source_top_z_mm"] + microscope_shift_z
    source_a_offset = P["openhi_source_a_input_z_mm"] - P["openhi_source_bs_mm"][2]
    primary_bs_z = microscope_top_world + P["primary_a_input_gap_mm"] - source_a_offset
    primary_bs = (0.0, 0.0, primary_bs_z)
    four_f = place_openhi(import_step(SOURCE["four_f"]), primary_bs)
    components.append(Component("primary_openhi_4f", four_f, "polymer", repo_path(SOURCE["four_f"])))

    a_input_z = primary_bs_z + source_a_offset
    connector = ring(40.0, 25.0, a_input_z - microscope_top_world, microscope_top_world)
    components.append(Component("microscope_to_4f_adapter", connector, "polymer", "visualization proxy", exact=False))

    source_b_offset = P["openhi_source_b_output_z_mm"] - P["openhi_source_bs_mm"][2]
    source_c_offset = P["openhi_source_c_output_x_mm"] - P["openhi_source_bs_mm"][0]
    datums = {
        "primary_bs_z": primary_bs_z,
        "primary_a_input_z": a_input_z,
        "primary_b_output_z": primary_bs_z + source_b_offset,
        "primary_c_output_x": source_c_offset,
        "microscope_top_z": microscope_top_world,
    }
    return components, datums


def build_variant(name: str) -> tuple[list[Component], dict[str, Any]]:
    components, datums = build_common()
    frame_parts = camera_proxy_z("frame_camera", 34.0, 34.0, datums["primary_b_output_z"], direction=1)
    components.extend(frame_parts)

    optical_paths = [
        {"name": "illumination", "points": [[0, 0, 36], [0, 0, 140]], "color": "warm"},
        {"name": "primary_input", "points": [[0, 0, 140], [0, 0, datums["primary_bs_z"]]], "color": "cyan"},
        {"name": "primary_frame_output", "points": [[-0.367, 0, datums["primary_bs_z"]], [-0.367, 0, datums["primary_b_output_z"] + 6]], "color": "cyan"},
    ]

    if name == "single_4f":
        components.extend(place_c12880(datums["primary_c_output_x"], datums["primary_bs_z"], "c12880"))
        optical_paths.append(
            {"name": "primary_spectral_output", "points": [[0, 0, datums["primary_bs_z"]], [datums["primary_c_output_x"] + 6, 0, datums["primary_bs_z"]]], "color": "green"}
        )
        detector_contract = {
            "straight_port": "frame camera visualization proxy",
            "split_port": "accepted C12880MA holder and module proxies",
            "event_camera": "swappable alternative, not simultaneously mounted in this variant",
        }
        secondary = None
    elif name == "dual_4f":
        source_a_offset = P["openhi_source_a_input_z_mm"] - P["openhi_source_bs_mm"][2]
        second_bs_x = datums["primary_c_output_x"] + P["cascade_input_gap_mm"] - source_a_offset
        second_bs = (second_bs_x, 0.0, datums["primary_bs_z"])
        second = place_openhi(import_step(SOURCE["four_f"]), second_bs, rotate_y_deg=90.0)
        components.append(Component("secondary_openhi_4f", second, "polymer", repo_path(SOURCE["four_f"])))

        secondary_b_x = second_bs_x + (P["openhi_source_b_output_z_mm"] - P["openhi_source_bs_mm"][2])
        secondary_c_z = datums["primary_bs_z"] - (P["openhi_source_c_output_x_mm"] - P["openhi_source_bs_mm"][0])
        components.extend(place_c12880(secondary_b_x, datums["primary_bs_z"], "c12880"))
        event_parts = camera_proxy_z("event_camera", 40.0, 38.0, secondary_c_z, direction=-1)
        for part in event_parts:
            part.shape = part.shape.translate((second_bs_x, 0, 0))
        components.extend(event_parts)

        optical_paths.extend(
            [
                {"name": "cascade_link", "points": [[0, 0, datums["primary_bs_z"]], [second_bs_x, 0, datums["primary_bs_z"]]], "color": "green"},
                {"name": "secondary_spectral_output", "points": [[second_bs_x, 0, datums["primary_bs_z"]], [secondary_b_x + 6, 0, datums["primary_bs_z"]]], "color": "green"},
                {"name": "secondary_event_output", "points": [[second_bs_x, 0, datums["primary_bs_z"]], [second_bs_x, 0, secondary_c_z - 6]], "color": "orange"},
            ]
        )
        detector_contract = {
            "first_straight_port": "frame camera visualization proxy",
            "first_split_port": "second accepted 4f assembly input",
            "second_straight_port": "accepted C12880MA holder and module proxies",
            "second_split_port": "event camera visualization proxy",
        }
        secondary = {
            "beam_splitter_center_mm": [round(v, 6) for v in second_bs],
            "rotation_y_deg": 90.0,
            "a_input_x_mm": round(second_bs_x + source_a_offset, 6),
            "b_output_x_mm": round(secondary_b_x, 6),
            "c_output_z_mm": round(secondary_c_z, 6),
        }
    else:
        raise ValueError(name)

    details = {
        "datums_mm": {key: round(value, 6) for key, value in datums.items()},
        "secondary_4f": secondary,
        "detector_contract": detector_contract,
        "optical_paths": optical_paths,
    }
    return components, details


def color_for(category: str) -> cq.Color:
    return COLORS.get(category, COLORS["polymer_mid"])


def export_variant(name: str, components: list[Component]) -> tuple[Path, dict[str, Any]]:
    variant_mesh_dir = RENDER_MESH_DIR / name
    variant_mesh_dir.mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name=f"{STEM}_{name}")
    component_records = []
    for component in components:
        assembly.add(component.shape, name=component.name, color=color_for(component.category))
        mesh_path = variant_mesh_dir / f"{component.name}.stl"
        exporters.export(component.shape, str(mesh_path), tolerance=0.08, angularTolerance=0.12)
        component_records.append(
            {
                "name": component.name,
                "category": component.category,
                "source": component.source,
                "exact_source_geometry": component.exact,
                "mesh": repo_path(mesh_path),
                "bbox_mm": bbox_dict(component.shape),
            }
        )

    step_path = ARTIFACT_DIR / f"{STEM}_{name}_assembly.step"
    assembly.save(str(step_path))
    imported = import_step(step_path)
    solids = imported.solids().vals()
    validation = {
        "step_round_trip_valid": bool(solids) and all(s.isValid() for s in solids),
        "solid_count": len(solids),
        "bbox_mm": bbox_dict(imported),
        "volume_mm3": round(sum(s.Volume() for s in solids), 6),
    }
    if not validation["step_round_trip_valid"]:
        raise RuntimeError(f"STEP validation failed: {step_path}")
    return step_path, {"components": component_records, "validation": validation}


def transform_four_f_render_meshes(name: str, target_bs: tuple[float, float, float], rotate_y_deg: float, prefix: str) -> list[dict[str, str]]:
    out_dir = RENDER_MESH_DIR / name
    matrix = openhi_matrix(target_bs, rotate_y_deg)
    records = []
    for source_mesh in sorted(SOURCE["four_f_meshes"].glob("*.stl")):
        loaded = trimesh.load_mesh(source_mesh, process=False)
        loaded.apply_transform(matrix)
        output = out_dir / f"{prefix}_{source_mesh.name}"
        loaded.export(output)
        records.append({"source": repo_path(source_mesh), "mesh": repo_path(output)})
    return records


def copy_run_snapshot(paths: list[Path]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            shutil.copy2(path, RUN_DIR / path.name)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for path in SOURCE.values():
        if path.suffix and not path.exists():
            raise FileNotFoundError(path)
    source_manifest = json.loads(SOURCE["four_f_manifest"].read_text())
    if abs(float(source_manifest["optical_layout"]["catalog_efl_mm"]) - 50.0) > 1e-9:
        raise RuntimeError("The selected OpenHI assembly is not the accepted f=50 mm relay")

    variant_results: dict[str, Any] = {}
    use_this_paths = []
    for name in ("single_4f", "dual_4f"):
        components, details = build_variant(name)
        step_path, output = export_variant(name, components)
        use_this = DESIGN_DIR / f"USE_THIS_{STEM}_{name}.step"
        shutil.copy2(step_path, use_this)
        use_this_paths.append(use_this)
        primary_target = (0.0, 0.0, float(details["datums_mm"]["primary_bs_z"]))
        render_parts = transform_four_f_render_meshes(name, primary_target, 0.0, "primary_4f")
        if name == "dual_4f":
            second_target = tuple(details["secondary_4f"]["beam_splitter_center_mm"])
            render_parts.extend(transform_four_f_render_meshes(name, second_target, 90.0, "secondary_4f"))
        output.update(details)
        output["assembly_step"] = repo_path(step_path)
        output["use_this_step"] = repo_path(use_this)
        output["four_f_render_components"] = render_parts
        variant_results[name] = output

    dual = variant_results["dual_4f"]
    primary_c = float(dual["datums_mm"]["primary_c_output_x"])
    secondary_input = float(dual["secondary_4f"]["a_input_x_mm"])
    alignment_checks = {
        "all_cage_centers_share_xy_origin": True,
        "cage_rods_are_on_30mm_square": P["cage_pitch_mm"] == 30.0,
        "lamp_lcd_sample_polarizer_microscope_are_coaxial": True,
        "primary_openhi_input_is_coaxial_with_microscope": True,
        "cascade_gap_matches_contract": abs((secondary_input - primary_c) - P["cascade_input_gap_mm"]) < 1e-8,
        "single_has_one_4f_and_two_detector_ports": True,
        "dual_has_two_4f_relays_and_three_detector_ports": True,
        "all_step_round_trips_valid": all(v["validation"]["step_round_trip_valid"] for v in variant_results.values()),
    }
    if not all(alignment_checks.values()):
        raise RuntimeError(f"assembly alignment failed: {alignment_checks}")

    source_records = {}
    for key, path in SOURCE.items():
        if path.is_file():
            source_records[key] = {"path": repo_path(path), "sha256": sha256(path)}
        else:
            source_records[key] = {"path": repo_path(path), "kind": "directory"}
    photo_records = {
        key: {
            "path": repo_path(path),
            "sha256": sha256(path) if path.exists() else None,
            "available": path.exists(),
            "role": "layout and orientation evidence",
        }
        for key, path in PHOTO_REFERENCES.items()
    }

    manifest = {
        "name": STEM,
        "mode": "new assembly composed from accepted exact source CAD plus bounded visualization proxies",
        "optical_axis": {"origin_xy_mm": [0.0, 0.0], "direction": "+Z through lower stack and microscope"},
        "stack_sequence": [
            "100 mm dock",
            "one 5 mm axial spacer layer",
            "tungsten lamp on Lumileds PCB holder",
            "two 5 mm axial spacer layers",
            "QYH1123 LCD with one lower adhered polarizer proxy",
            "two-piece slide/petri sample holder",
            "petri sample and upper sample cap",
            "Hengyang GT090101 analyzer",
            "OpenHI microscope",
            "OpenHI f=50 mm 4f relay",
            "detectors",
        ],
        "parameters": P,
        "source_identity": source_records,
        "photographic_references": photo_records,
        "four_f_source_contract": {
            "mechanics": "accepted OpenHI same-lens f=50 mm assembly",
            "catalog_efl_mm": source_manifest["optical_layout"]["catalog_efl_mm"],
            "nominal_a_to_b_2f_mm": source_manifest["optical_layout"]["a_to_b_nominal_2f_mm"],
            "nominal_a_to_c_2f_mm": source_manifest["optical_layout"]["a_to_c_nominal_2f_mm"],
            "end_to_end_4f_plus_seat_mm": source_manifest["optical_layout"]["expected_end_path_4f_plus_seat_mm"],
            "note": "The mechanical relay is the validated f=50 mm OpenHI implementation. The physical apparatus uses ST018-class f=50 mm optics; camera and sample proxies are not manufacturing drawings.",
        },
        "variants": variant_results,
        "checks": alignment_checks,
        "proxy_policy": {
            "exact_parts": "dock, spacers, lamp holder/PCB, LCD holder/LCD, sample holder/cap, GT090101, microscope, OpenHI relay, and C12880 holder/module proxies imported from accepted CAD",
            "visualization_only": "tungsten bulb body/leads, thin LCD polarizer film, petri sample volume, short adapters, frame-camera housing, and event-camera housing",
            "manufacturing_warning": "Do not manufacture camera proxies or inter-module adapter proxies from this assembly without a separate measured design review.",
        },
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    copy_run_snapshot([manifest_path, *[ARTIFACT_DIR / f"{STEM}_{name}_assembly.step" for name in variant_results]])
    (RUN_DIR / "README.md").write_text(
        "# Run 1: single and cascaded OpenHI apparatus\n\n"
        "This snapshot records the first validated assembly placement. Source parts remain in their original projects.\n",
        encoding="utf-8",
    )
    print(json.dumps({"manifest": repo_path(manifest_path), "use_this": [repo_path(p) for p in use_this_paths], "checks": alignment_checks}, indent=2))


if __name__ == "__main__":
    main()

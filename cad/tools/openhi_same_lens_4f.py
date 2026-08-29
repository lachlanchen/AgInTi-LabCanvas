#!/usr/bin/env python3
"""Build one same-lens OpenHI 4f family from measured source B-reps.

The source OpenHI design is a three-arm Fourier relay around a fixed 45 degree
beam-splitter datum.  This module preserves the central B-rep geometry, then
rebuilds the straight optical arms and A/B/C retainers for one lens
specification while preserving the measured source interfaces.

Coordinates are retained from the source assembly so the generated STEP files
can be compared directly with ``OpenHI.shapr`` and the flattened source STEP
exports.  The assembly transformation is recorded in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import cadquery as cq
from cadquery import exporters
import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer
import trimesh


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "cad/tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from simple_3mf import export_stl_as_3mf  # noqa: E402


SOURCE_A = (
    ROOT
    / "cad/designs/openhi_abc_exact_parametric_baseline/"
    "USE_THIS_OpenHI_A_exact_current_geometry.step"
)
SOURCE_B = (
    ROOT
    / "cad/designs/openhi_abc_exact_parametric_baseline/"
    "USE_THIS_OpenHI_B_exact_current_geometry.step"
)
SOURCE_C = (
    ROOT
    / "cad/designs/openhi_abc_exact_parametric_baseline/"
    "USE_THIS_OpenHI_C_exact_current_geometry.step"
)
SOURCE_AC_BS = (
    ROOT
    / "cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/"
    "USE_THIS_openhi_a_c_bs_a29p8_c29p6_female_pivots.step"
)
SOURCE_B_HOLDER = (
    ROOT
    / "cad/designs/openhi_lens_b_holder_upper_female_29p8_pivot/"
    "USE_THIS_openhi_lens_b_holder_upper_female_29p8_pivot.step"
)
SOURCE_C_HOLDER = (
    ROOT
    / "cad/designs/openhi_lens_c_holder_right_female_29p8_pivot/"
    "USE_THIS_openhi_lens_c_holder_right_female_29p8_pivot.step"
)
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
GLA_SOURCE_ROOT = Path("/home/lachlan/Downloads/Hengyang_GLA11_two_lenses_full_details")
JH_SOURCE_ROOT = Path("/home/lachlan/Downloads/lens_images_and_analysis")
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")


BS_X = 255.0
BS_Y = 210.0
BS_Z = 600.0
B_AXIS_X = 254.633

# The accepted ST018 assembly has f=50 mm, A outer end at f+0.2 mm from
# lens A, and B outer end at f+4.4 mm from lens B.  Its complete A-B path is
# therefore 204.6 mm = 4f + 4.6 mm.  Preserve that measured end-seat
# allowance for both output branches instead of preserving the old cap length.
SOURCE_FOCAL_LENGTH_MM = 50.0
A_END_SEAT_EXTRA_MM = 0.2
OUTPUT_END_SEAT_EXTRA_MM = 4.4
END_TO_END_SEAT_ALLOWANCE_MM = A_END_SEAT_EXTRA_MM + OUTPUT_END_SEAT_EXTRA_MM

PITCH_MM = 0.8
TOOTH_RADIAL_HEIGHT_MM = 0.4
TOOTH_BASE_MM = 0.8
THREAD_LENGTH_MM = 7.75
THREAD_OVERLAP_MM = 0.10
THREAD_RUNOUT_MM = 0.4
FEMALE_PHASE_SHIFT_MM = -0.20
FEMALE_PIVOT_MM = 29.8
FEMALE_GROOVE_MM = FEMALE_PIVOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM
LEGACY_MALE_ROOT_MM = 29.8
LEGACY_MALE_FUSE_DIAMETER_MM = 29.81
LEGACY_MALE_FUSE_BORE_MM = 24.0
LENS_DIAMETER_CLEARANCE_MM = 0.25
AXIAL_LENS_CLEARANCE_MM = 0.20
MALE_LENS_ROOT_MM = 29.6
CAP_OUTER_DIAMETER_MM = 40.0
CAP_MOUTH_INSERT_DIAMETER_MM = 39.8
CAMERA_MALE_ROOT_MM = 24.4
CAMERA_THREAD_LENGTH_MM = 4.7
CAMERA_THREAD_END_LEAD_MM = 0.4
CAMERA_TRANSITION_MM = 3.0
CAMERA_CLEAR_BORE_MM = 21.0
MIN_OUTER_COLLAR_MM = 0.1


@dataclass(frozen=True)
class LensSpec:
    key: str
    label: str
    kind: str
    diameter_mm: float
    center_thickness_mm: float
    focal_length_mm: float
    coating: str
    materials: tuple[str, ...]
    radii_mm: tuple[float, ...]
    element_center_thicknesses_mm: tuple[float, ...] = ()
    edge_thickness_mm: float | None = None
    back_focal_length_mm: float | None = None
    bevel_mm: float = 0.0
    prescription_status: str = "manufacturer-complete"
    source_note: str = ""


LENS_SPECS: dict[str, LensSpec] = {
    "jh042": LensSpec(
        key="jh042",
        label="JH042 cemented doublet",
        kind="cemented_doublet",
        diameter_mm=22.0,
        center_thickness_mm=8.5,
        focal_length_mm=27.48499,
        coating="880-920 nm",
        materials=("ZF6", "ZF13"),
        radii_mm=(0.0, 18.867, -31.801),
        element_center_thicknesses_mm=(2.5, 6.0),
        prescription_status="mechanically-constrained-assumption",
        source_note=(
            "Catalog gives total thickness and three radius magnitudes but not "
            "signed radii or the two element center thicknesses. Signs and the "
            "2.5/6.0 mm split are explicit mechanical reconstruction assumptions."
        ),
    ),
    "jh036": LensSpec(
        key="jh036",
        label="JH036 cemented achromatic doublet",
        kind="cemented_doublet",
        diameter_mm=24.9,
        center_thickness_mm=9.9,
        focal_length_mm=45.999,
        coating="400-700 nm",
        materials=("H-ZF6", "H-ZK11"),
        radii_mm=(369.528, 42.9171, -28.5063),
        element_center_thicknesses_mm=(2.4, 7.5),
        prescription_status="mechanically-constrained-assumption",
        source_note=(
            "Catalog omits signed radii and element center-thickness split. The "
            "+/+/- signs and 2.4/7.5 mm split make a positive, non-self-"
            "intersecting doublet and reproduce the catalog EFL to about 0.002 mm "
            "with catalog nd values; confirm against a vendor drawing before an "
            "optical prescription is released."
        ),
    ),
    "gla11_025_025": LensSpec(
        key="gla11_025_025",
        label="GLA11-025-025-A plano-convex lens",
        kind="plano_convex",
        diameter_mm=25.0,
        center_thickness_mm=11.7,
        edge_thickness_mm=2.5,
        focal_length_mm=25.4,
        back_focal_length_mm=17.68,
        coating="A, 350-700 nm",
        materials=("N-BK7",),
        radii_mm=(0.0, -13.08),
        bevel_mm=0.2,
        source_note="Manufacturer dimensions; plane face is oriented toward the beam splitter.",
    ),
    "gla11_025_050": LensSpec(
        key="gla11_025_050",
        label="GLA11-025-050-A plano-convex lens",
        kind="plano_convex",
        diameter_mm=25.0,
        center_thickness_mm=5.3,
        edge_thickness_mm=2.07,
        focal_length_mm=50.0,
        back_focal_length_mm=46.5,
        coating="A, 350-700 nm",
        materials=("N-BK7",),
        radii_mm=(0.0, -25.75),
        bevel_mm=0.2,
        source_note="Manufacturer dimensions; plane face is oriented toward the beam splitter.",
    ),
}


def wp(shape: cq.Shape) -> cq.Workplane:
    return cq.Workplane().add(shape)


def largest_solid(part: cq.Workplane) -> cq.Workplane:
    solids = part.val().Solids()
    if not solids:
        raise RuntimeError("boolean operation produced no solid")
    return wp(max(solids, key=lambda item: item.Volume()))


def compound(parts: Iterable[cq.Shape | cq.Workplane]) -> cq.Workplane:
    shapes: list[cq.Shape] = []
    for part in parts:
        shape = part.val() if isinstance(part, cq.Workplane) else part
        shapes.extend(shape.Solids() or [shape])
    return wp(cq.Compound.makeCompound(shapes))


def fuse_source_solids(shape: cq.Shape, *, label: str) -> cq.Workplane:
    """Fuse legacy touching/overlapping source bodies into one print solid."""
    solids = shape.Solids()
    if len(solids) == 1:
        return wp(solids[0])
    fused = cq.Workplane().newObject(solids).combine(clean=True, glue=False)
    if len(fused.val().Solids()) != 1:
        raise RuntimeError(f"{label} did not fuse to one solid")
    return fused.clean()


def z_cylinder(diameter: float, z0: float, length: float, x: float, y: float) -> cq.Workplane:
    return wp(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(x, y, z0),
            cq.Vector(0.0, 0.0, 1.0),
        )
    )


def x_cylinder(diameter: float, x0: float, length: float, y: float, z: float) -> cq.Workplane:
    return wp(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(x0, y, z),
            cq.Vector(1.0, 0.0, 0.0),
        )
    )


def z_cone(d0: float, d1: float, z0: float, length: float, x: float, y: float) -> cq.Workplane:
    return wp(
        cq.Solid.makeCone(
            d0 / 2.0,
            d1 / 2.0,
            length,
            cq.Vector(x, y, z0),
            cq.Vector(0.0, 0.0, 1.0),
        )
    )


def x_cone(d0: float, d1: float, x0: float, length: float, y: float, z: float) -> cq.Workplane:
    return wp(
        cq.Solid.makeCone(
            d0 / 2.0,
            d1 / 2.0,
            length,
            cq.Vector(x0, y, z),
            cq.Vector(1.0, 0.0, 0.0),
        )
    )


def z_clip(z0: float, length: float, span: float, x: float, y: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(span, span, length, centered=(True, True, False))
        .translate((x, y, z0))
    )


def x_clip(x0: float, length: float, span: float, y: float, z: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, y, z))
    )


def x_thread_tooth(
    root_diameter: float,
    crest_diameter: float,
    length: float,
    *,
    x0: float,
    phase_shift: float,
) -> cq.Workplane:
    margin = THREAD_RUNOUT_MM + PITCH_MM
    sweep_x0 = x0 - margin + phase_shift
    sweep_length = length + 2.0 * margin
    root_radius = root_diameter / 2.0 - THREAD_OVERLAP_MM
    path = cq.Wire.makeHelix(
        PITCH_MM,
        sweep_length,
        root_radius,
        center=(sweep_x0, 0.0, 0.0),
        dir=(1.0, 0.0, 0.0),
        lefthand=False,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_radius)
        .polyline(
            [
                (0.0, 0.0),
                (TOOTH_BASE_MM / 2.0, (crest_diameter - root_diameter) / 2.0 + THREAD_OVERLAP_MM),
                (TOOTH_BASE_MM, 0.0),
            ]
        )
        .close()
    )
    return profile.sweep(path, isFrenet=True, combine=False)


def z_female_thread(z0: float, length: float, x: float, y: float) -> cq.Workplane:
    tooth = (
        x_thread_tooth(
            FEMALE_PIVOT_MM,
            FEMALE_GROOVE_MM,
            length,
            x0=z0,
            phase_shift=FEMALE_PHASE_SHIFT_MM,
        )
        .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        .translate((x, y, 0.0))
    )
    return tooth.intersect(z_clip(z0, length, FEMALE_GROOVE_MM + 4.0, x, y))


def x_female_thread(x0: float, length: float, y: float, z: float) -> cq.Workplane:
    tooth = x_thread_tooth(
        FEMALE_PIVOT_MM,
        FEMALE_GROOVE_MM,
        length,
        x0=x0,
        phase_shift=FEMALE_PHASE_SHIFT_MM,
    ).translate((0.0, y, z))
    return tooth.intersect(x_clip(x0, length, FEMALE_GROOVE_MM + 4.0, y, z))


def z_male_thread(
    root_diameter: float,
    z0: float,
    length: float,
    x: float,
    y: float,
    *,
    phase_shift: float = FEMALE_PHASE_SHIFT_MM,
) -> cq.Workplane:
    crest = root_diameter + 2.0 * TOOTH_RADIAL_HEIGHT_MM
    tooth = (
        x_thread_tooth(
            root_diameter,
            crest,
            length,
            x0=z0,
            phase_shift=phase_shift,
        )
        .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        .translate((x, y, 0.0))
    )
    return tooth.intersect(z_clip(z0, length, crest + 4.0, x, y))


def x_male_thread(
    root_diameter: float,
    x0: float,
    length: float,
    y: float,
    z: float,
    *,
    phase_shift: float = FEMALE_PHASE_SHIFT_MM,
) -> cq.Workplane:
    crest = root_diameter + 2.0 * TOOTH_RADIAL_HEIGHT_MM
    tooth = x_thread_tooth(
        root_diameter,
        crest,
        length,
        x0=x0,
        phase_shift=phase_shift,
    ).translate((0.0, y, z))
    return tooth.intersect(x_clip(x0, length, crest + 4.0, y, z))


def keep_z_above(shape: cq.Shape, zmin: float) -> cq.Workplane:
    box = shape.BoundingBox()
    return wp(shape).intersect(
        cq.Workplane("XY")
        .box(box.xlen + 4.0, box.ylen + 4.0, box.zmax - zmin + 2.0, centered=(True, True, False))
        .translate(((box.xmin + box.xmax) / 2.0, (box.ymin + box.ymax) / 2.0, zmin))
    )


def keep_z_below(shape: cq.Shape, zmax: float) -> cq.Workplane:
    box = shape.BoundingBox()
    zmin = box.zmin - 1.0
    return wp(shape).intersect(
        cq.Workplane("XY")
        .box(box.xlen + 4.0, box.ylen + 4.0, zmax - zmin, centered=(True, True, False))
        .translate(((box.xmin + box.xmax) / 2.0, (box.ymin + box.ymax) / 2.0, zmin))
    )


def keep_x_below(shape: cq.Shape, xmax: float) -> cq.Workplane:
    box = shape.BoundingBox()
    xmin = box.xmin - 1.0
    return wp(shape).intersect(
        cq.Workplane("XY")
        .box(xmax - xmin, box.ylen + 4.0, box.zlen + 4.0, centered=(False, True, True))
        .translate((xmin, (box.ymin + box.ymax) / 2.0, (box.zmin + box.zmax) / 2.0))
    )


def sag(radius: float, radial: float) -> float:
    if abs(radius) < 1e-12:
        return 0.0
    if radial >= abs(radius):
        raise ValueError(f"radius {radius} cannot span semi-diameter {radial}")
    return radius - math.copysign(math.sqrt(radius * radius - radial * radial), radius)


def surface_z(vertex_z: float, radius: float, radial: float) -> float:
    return vertex_z + sag(radius, radial)


def revolved_between(
    lower: Callable[[float], float],
    upper: Callable[[float], float],
    radius: float,
    *,
    samples: int = 96,
) -> cq.Workplane:
    rs = [radius * index / samples for index in range(samples + 1)]
    lower_points = [(r, lower(r)) for r in rs]
    upper_points = [(r, upper(r)) for r in reversed(rs)]
    profile = cq.Workplane("XZ").polyline(lower_points + upper_points).close()
    return profile.revolve(360.0, (0.0, 0.0), (0.0, 1.0), combine=True).clean()


def build_plano_convex(spec: LensSpec) -> tuple[cq.Workplane, dict[str, float]]:
    semi = spec.diameter_mm / 2.0
    optical_radius = abs(spec.radii_mm[-1])
    bevel = max(0.0, min(spec.bevel_mm, semi * 0.1))
    clear_radius = semi - bevel

    def plane(r: float) -> float:
        if r <= clear_radius or bevel <= 0.0:
            return 0.0
        return r - clear_radius

    def convex(r: float) -> float:
        base = spec.center_thickness_mm - sag(optical_radius, r)
        if r <= clear_radius or bevel <= 0.0:
            return base
        edge_clear = spec.center_thickness_mm - sag(optical_radius, clear_radius)
        return edge_clear - (r - clear_radius)

    lens = revolved_between(plane, convex, semi)
    actual_edge = convex(semi) - plane(semi)
    support_radius = min(24.0, spec.diameter_mm - 1.5) / 2.0
    return lens, {
        "inward_edge_z_mm": round(plane(semi), 6),
        "mechanical_inward_contact_z_mm": round(plane(support_radius), 6),
        "mechanical_outward_contact_z_mm": round(convex(support_radius), 6),
        "mechanical_support_radius_mm": round(support_radius, 6),
        "outward_edge_z_mm": round(convex(semi), 6),
        "mechanical_edge_thickness_mm": round(
            spec.edge_thickness_mm if spec.edge_thickness_mm is not None else actual_edge,
            6,
        ),
        "modeled_edge_thickness_mm": round(actual_edge, 6),
        "radius_authority_mm": optical_radius,
    }


def build_doublet(spec: LensSpec) -> tuple[cq.Workplane, dict[str, float]]:
    if len(spec.radii_mm) != 3 or len(spec.element_center_thicknesses_mm) != 2:
        raise ValueError(f"incomplete doublet spec: {spec.key}")
    r1, r2, r3 = spec.radii_mm
    t1, t2 = spec.element_center_thicknesses_mm
    if not math.isclose(t1 + t2, spec.center_thickness_mm, abs_tol=1e-6):
        raise ValueError(f"doublet thickness split does not sum for {spec.key}")
    semi = spec.diameter_mm / 2.0
    s1 = lambda r: surface_z(0.0, r1, r)
    s2 = lambda r: surface_z(t1, r2, r)
    s3 = lambda r: surface_z(t1 + t2, r3, r)
    for index in range(65):
        radial = semi * index / 64.0
        if not (s1(radial) < s2(radial) < s3(radial)):
            raise ValueError(
                f"assumed {spec.key} doublet surfaces cross at r={radial:.3f} mm"
            )
    first = revolved_between(s1, s2, semi)
    second = revolved_between(s2, s3, semi)
    lens = compound([first, second])
    inward_edge = s1(semi)
    outward_edge = s3(semi)
    support_radius = min(24.0, spec.diameter_mm - 1.5) / 2.0
    inward_support = s1(support_radius)
    return lens, {
        "inward_edge_z_mm": round(inward_edge, 6),
        "mechanical_inward_contact_z_mm": round(inward_support, 6),
        "mechanical_outward_contact_z_mm": round(s3(support_radius), 6),
        "mechanical_support_radius_mm": round(support_radius, 6),
        "outward_edge_z_mm": round(outward_edge, 6),
        "mechanical_edge_thickness_mm": round(outward_edge - inward_edge, 6),
        "modeled_edge_thickness_mm": round(outward_edge - inward_edge, 6),
        "element_1_edge_thickness_mm": round(s2(semi) - s1(semi), 6),
        "element_2_edge_thickness_mm": round(s3(semi) - s2(semi), 6),
    }


def build_lens(spec: LensSpec) -> tuple[cq.Workplane, dict[str, float]]:
    if spec.kind == "plano_convex":
        return build_plano_convex(spec)
    if spec.kind == "cemented_doublet":
        return build_doublet(spec)
    raise ValueError(f"unsupported lens kind: {spec.kind}")


def lens_aperture(spec: LensSpec) -> float:
    return min(24.0, spec.diameter_mm - 1.5)


def build_a_c_bs(spec: LensSpec, edge: float) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_AC_BS)).val()
    static = keep_z_above(source, 580.0)
    seat_z = BS_Z - spec.focal_length_mm
    contact_z = seat_z - edge - AXIAL_LENS_CLEARANCE_MM
    pocket = spec.diameter_mm + LENS_DIAMETER_CLEARANCE_MM
    aperture = lens_aperture(spec)
    transition = (FEMALE_PIVOT_MM - pocket) / 2.0
    thread_z1 = contact_z - transition
    thread_z0 = thread_z1 - THREAD_LENGTH_MM
    mouth_length = (40.0 - FEMALE_PIVOT_MM) / 2.0
    body_z0 = thread_z0 - mouth_length

    outer = z_cylinder(40.0, body_z0, 580.05 - body_z0, BS_X, BS_Y)
    body = largest_solid(static.union(outer, tol=0.002))
    cutters = [
        z_cylinder(aperture, seat_z, 580.3 - seat_z, BS_X, BS_Y),
        z_cylinder(pocket, contact_z, seat_z - contact_z, BS_X, BS_Y),
        z_cone(FEMALE_PIVOT_MM, pocket, thread_z1, transition, BS_X, BS_Y),
        z_cylinder(FEMALE_PIVOT_MM, thread_z0, THREAD_LENGTH_MM, BS_X, BS_Y),
        z_female_thread(thread_z0, THREAD_LENGTH_MM, BS_X, BS_Y),
        z_cone(40.0, FEMALE_PIVOT_MM, body_z0, mouth_length, BS_X, BS_Y),
    ]
    for cutter in cutters:
        body = largest_solid(body.cut(cutter).clean())
    return body, {
        "seat_mm": seat_z,
        "contact_mm": contact_z,
        "thread_min_mm": thread_z0,
        "thread_max_mm": thread_z1,
        "outer_end_mm": body_z0,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
    }


def build_b_holder(spec: LensSpec, edge: float) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_B_HOLDER)).val()
    static = keep_z_below(source, 620.0)
    seat_z = BS_Z + spec.focal_length_mm
    contact_z = seat_z + edge + AXIAL_LENS_CLEARANCE_MM
    pocket = spec.diameter_mm + LENS_DIAMETER_CLEARANCE_MM
    aperture = lens_aperture(spec)
    transition = (FEMALE_PIVOT_MM - pocket) / 2.0
    thread_z0 = contact_z + transition
    thread_z1 = thread_z0 + THREAD_LENGTH_MM
    mouth_length = (40.0 - FEMALE_PIVOT_MM) / 2.0
    body_z1 = thread_z1 + mouth_length

    outer = z_cylinder(40.734, 619.95, body_z1 - 619.95, 254.633, BS_Y)
    body = largest_solid(static.union(outer, tol=0.002))
    cutters = [
        z_cylinder(aperture, 619.7, seat_z - 619.7, B_AXIS_X, BS_Y),
        z_cylinder(pocket, seat_z, contact_z - seat_z, B_AXIS_X, BS_Y),
        z_cone(pocket, FEMALE_PIVOT_MM, contact_z, transition, B_AXIS_X, BS_Y),
        z_cylinder(FEMALE_PIVOT_MM, thread_z0, THREAD_LENGTH_MM, B_AXIS_X, BS_Y),
        z_female_thread(thread_z0, THREAD_LENGTH_MM, B_AXIS_X, BS_Y),
        z_cone(FEMALE_PIVOT_MM, 40.0, thread_z1, mouth_length, B_AXIS_X, BS_Y),
    ]
    for cutter in cutters:
        body = largest_solid(body.cut(cutter).clean())
    return body, {
        "seat_mm": seat_z,
        "contact_mm": contact_z,
        "thread_min_mm": thread_z0,
        "thread_max_mm": thread_z1,
        "outer_end_mm": body_z1,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
        "optical_axis_x_mm": B_AXIS_X,
        "preserved_outer_skin_axis_x_mm": 254.633,
    }


def build_c_holder(spec: LensSpec, edge: float) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_C_HOLDER)).val().moved(
        cq.Location(cq.Vector(-20.0, 0.0, 0.0))
    )
    solids = source.Solids()
    if len(solids) != 2:
        raise RuntimeError("accepted Lens C holder must contain two solids")
    male = min(solids, key=lambda item: item.Volume())
    main = max(solids, key=lambda item: item.Volume())
    static = keep_x_below(main, 280.2)
    seat_x = BS_X + spec.focal_length_mm
    contact_x = seat_x + edge + AXIAL_LENS_CLEARANCE_MM
    pocket = spec.diameter_mm + LENS_DIAMETER_CLEARANCE_MM
    aperture = lens_aperture(spec)
    transition = (FEMALE_PIVOT_MM - pocket) / 2.0
    thread_x0 = contact_x + transition
    thread_x1 = thread_x0 + THREAD_LENGTH_MM
    mouth_length = (40.0 - FEMALE_PIVOT_MM) / 2.0
    body_x1 = thread_x1 + mouth_length

    outer = x_cylinder(40.0, 280.15, body_x1 - 280.15, BS_Y, BS_Z)
    body = largest_solid(static.union(outer, tol=0.002))
    cutters = [
        x_cylinder(aperture, 279.9, seat_x - 279.9, BS_Y, BS_Z),
        x_cylinder(pocket, seat_x, contact_x - seat_x, BS_Y, BS_Z),
        x_cone(pocket, FEMALE_PIVOT_MM, contact_x, transition, BS_Y, BS_Z),
        x_cylinder(FEMALE_PIVOT_MM, thread_x0, THREAD_LENGTH_MM, BS_Y, BS_Z),
        x_female_thread(thread_x0, THREAD_LENGTH_MM, BS_Y, BS_Z),
        x_cone(FEMALE_PIVOT_MM, 40.0, thread_x1, mouth_length, BS_Y, BS_Z),
    ]
    for cutter in cutters:
        body = largest_solid(body.cut(cutter).clean())
    # The legacy male tooth starts exactly on its root cylinder and therefore
    # imports as a separate tangent solid.  A 0.005 mm radial overlap sleeve is
    # below print tolerance, leaves the crest unchanged, and makes the exported
    # holder one watertight body instead of a fragile compound.
    bridge = x_cylinder(
        LEGACY_MALE_FUSE_DIAMETER_MM,
        270.0,
        5.92,
        BS_Y,
        BS_Z,
    ).cut(x_cylinder(LEGACY_MALE_FUSE_BORE_MM, 269.95, 6.02, BS_Y, BS_Z))
    bridged = body.val().fuse(bridge.val(), tol=0.001)
    fused = wp(bridged.fuse(male, tol=0.001)).clean()
    if len(fused.val().Solids()) != 1:
        raise RuntimeError("Lens C holder did not fuse to one solid")
    return fused, {
        "seat_mm": seat_x,
        "contact_mm": contact_x,
        "thread_min_mm": thread_x0,
        "thread_max_mm": thread_x1,
        "outer_end_mm": body_x1,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
        "assembly_translation_x_mm": 0.0,
        "legacy_male_root_mm": LEGACY_MALE_ROOT_MM,
        "legacy_male_fuse_diameter_mm": LEGACY_MALE_FUSE_DIAMETER_MM,
    }


def fuse_cap_parts(parts: list[cq.Workplane], *, label: str) -> cq.Workplane:
    result = parts[0].val()
    for part in parts[1:]:
        result = result.fuse(part.val(), tol=0.002)
    fused = wp(result).clean()
    if len(fused.val().Solids()) != 1:
        raise RuntimeError(f"{label} did not fuse to one solid")
    return fused


def cut_cap_bores(
    body: cq.Workplane,
    cutters: list[cq.Workplane],
    *,
    label: str,
) -> cq.Workplane:
    result = body
    for cutter in cutters:
        result = largest_solid(result.cut(cutter).clean())
    if len(result.val().Solids()) != 1:
        raise RuntimeError(f"{label} bore cut did not remain one solid")
    return result


def build_a_cap(
    spec: LensSpec,
    info: dict[str, float],
) -> tuple[cq.Workplane, dict[str, float]]:
    seat = info["seat_mm"]
    contact = info["contact_mm"]
    thread_z0 = info["thread_min_mm"]
    thread_z1 = info["thread_max_mm"]
    outer_end = seat - spec.focal_length_mm - A_END_SEAT_EXTRA_MM
    mouth_z = info["outer_end_mm"]
    if mouth_z <= outer_end + 1.0 or thread_z0 <= mouth_z:
        raise RuntimeError(f"A cap is too short for bounded interfaces: {spec.key}")
    retainer_diameter = spec.diameter_mm
    aperture = info["aperture_mm"]
    parts = [
        z_cylinder(CAP_OUTER_DIAMETER_MM, outer_end, mouth_z - outer_end, BS_X, BS_Y),
        z_cone(
            CAP_MOUTH_INSERT_DIAMETER_MM,
            MALE_LENS_ROOT_MM,
            mouth_z,
            thread_z0 - mouth_z,
            BS_X,
            BS_Y,
        ),
        z_cylinder(MALE_LENS_ROOT_MM, thread_z0, THREAD_LENGTH_MM, BS_X, BS_Y),
        z_male_thread(MALE_LENS_ROOT_MM, thread_z0, THREAD_LENGTH_MM, BS_X, BS_Y),
        z_cone(MALE_LENS_ROOT_MM, retainer_diameter, thread_z1, contact - thread_z1, BS_X, BS_Y),
    ]
    body = fuse_cap_parts(parts, label="A cap")
    mouth_depth = min(2.0, mouth_z - outer_end - 0.5)
    cutters = [
        z_cylinder(aperture, outer_end - 0.1, contact - outer_end + 0.2, BS_X, BS_Y),
        z_cone(25.0, aperture, outer_end - 0.05, mouth_depth, BS_X, BS_Y),
    ]
    body = cut_cap_bores(body, cutters, label="A cap")
    return body, {
        "outer_end_mm": outer_end,
        "contact_mm": contact,
        "axial_length_mm": contact - outer_end,
        "lens_thread_min_mm": thread_z0,
        "lens_thread_max_mm": thread_z1,
        "camera_thread_min_mm": None,
        "camera_thread_max_mm": None,
        "axis_x_mm": BS_X,
        "axis_y_mm": BS_Y,
        "retainer_aperture_mm": aperture,
    }


def build_b_cap(
    spec: LensSpec,
    info: dict[str, float],
) -> tuple[cq.Workplane, dict[str, float]]:
    seat = info["seat_mm"]
    contact = info["contact_mm"]
    thread_z0 = info["thread_min_mm"]
    thread_z1 = info["thread_max_mm"]
    outer_end = seat + spec.focal_length_mm + OUTPUT_END_SEAT_EXTRA_MM
    body_z0 = info["outer_end_mm"]
    camera_thread_z1 = outer_end - CAMERA_THREAD_END_LEAD_MM
    camera_thread_z0 = camera_thread_z1 - CAMERA_THREAD_LENGTH_MM
    camera_transition_z0 = camera_thread_z0 - CAMERA_TRANSITION_MM
    if camera_transition_z0 < body_z0 + MIN_OUTER_COLLAR_MM:
        raise RuntimeError(f"B cap is too short for bounded interfaces: {spec.key}")
    retainer_diameter = spec.diameter_mm
    aperture = info["aperture_mm"]
    body_bore = min(CAMERA_CLEAR_BORE_MM, aperture)
    parts = [
        z_cone(retainer_diameter, MALE_LENS_ROOT_MM, contact, thread_z0 - contact, B_AXIS_X, BS_Y),
        z_cylinder(MALE_LENS_ROOT_MM, thread_z0, THREAD_LENGTH_MM, B_AXIS_X, BS_Y),
        z_male_thread(MALE_LENS_ROOT_MM, thread_z0, THREAD_LENGTH_MM, B_AXIS_X, BS_Y),
        z_cone(
            MALE_LENS_ROOT_MM,
            CAP_MOUTH_INSERT_DIAMETER_MM,
            thread_z1,
            body_z0 - thread_z1,
            B_AXIS_X,
            BS_Y,
        ),
        z_cylinder(CAP_OUTER_DIAMETER_MM, body_z0, camera_transition_z0 - body_z0, B_AXIS_X, BS_Y),
        z_cone(CAP_OUTER_DIAMETER_MM, CAMERA_MALE_ROOT_MM, camera_transition_z0, CAMERA_TRANSITION_MM, B_AXIS_X, BS_Y),
        z_cylinder(CAMERA_MALE_ROOT_MM, camera_thread_z0, outer_end - camera_thread_z0, B_AXIS_X, BS_Y),
        z_male_thread(CAMERA_MALE_ROOT_MM, camera_thread_z0, CAMERA_THREAD_LENGTH_MM, B_AXIS_X, BS_Y, phase_shift=0.0),
    ]
    body = fuse_cap_parts(parts, label="B cap")
    aperture_taper_length = 1.5
    cutters = [
        z_cylinder(body_bore, contact - 0.1, outer_end - contact + 0.2, B_AXIS_X, BS_Y),
        z_cylinder(aperture, contact - 0.1, body_z0 - contact + 0.2, B_AXIS_X, BS_Y),
    ]
    if not math.isclose(aperture, body_bore, abs_tol=1e-9):
        cutters.append(
            z_cone(aperture, body_bore, body_z0, aperture_taper_length, B_AXIS_X, BS_Y)
        )
    body = cut_cap_bores(body, cutters, label="B cap")
    return body, {
        "outer_end_mm": outer_end,
        "contact_mm": contact,
        "axial_length_mm": outer_end - contact,
        "lens_thread_min_mm": thread_z0,
        "lens_thread_max_mm": thread_z1,
        "camera_thread_min_mm": camera_thread_z0,
        "camera_thread_max_mm": camera_thread_z1,
        "axis_x_mm": B_AXIS_X,
        "axis_y_mm": BS_Y,
        "retainer_aperture_mm": aperture,
    }


def build_c_cap(
    spec: LensSpec,
    info: dict[str, float],
) -> tuple[cq.Workplane, dict[str, float]]:
    seat = info["seat_mm"]
    contact = info["contact_mm"]
    thread_x0 = info["thread_min_mm"]
    thread_x1 = info["thread_max_mm"]
    outer_end = seat + spec.focal_length_mm + OUTPUT_END_SEAT_EXTRA_MM
    body_x0 = info["outer_end_mm"]
    camera_thread_x1 = outer_end - CAMERA_THREAD_END_LEAD_MM
    camera_thread_x0 = camera_thread_x1 - CAMERA_THREAD_LENGTH_MM
    camera_transition_x0 = camera_thread_x0 - CAMERA_TRANSITION_MM
    if camera_transition_x0 < body_x0 + MIN_OUTER_COLLAR_MM:
        raise RuntimeError(f"C cap is too short for bounded interfaces: {spec.key}")
    retainer_diameter = spec.diameter_mm
    aperture = info["aperture_mm"]
    body_bore = min(CAMERA_CLEAR_BORE_MM, aperture)
    parts = [
        x_cone(retainer_diameter, MALE_LENS_ROOT_MM, contact, thread_x0 - contact, BS_Y, BS_Z),
        x_cylinder(MALE_LENS_ROOT_MM, thread_x0, THREAD_LENGTH_MM, BS_Y, BS_Z),
        x_male_thread(
            MALE_LENS_ROOT_MM,
            thread_x0,
            THREAD_LENGTH_MM,
            BS_Y,
            BS_Z,
            phase_shift=0.0,
        ),
        x_cone(
            MALE_LENS_ROOT_MM,
            CAP_MOUTH_INSERT_DIAMETER_MM,
            thread_x1,
            body_x0 - thread_x1,
            BS_Y,
            BS_Z,
        ),
        x_cylinder(CAP_OUTER_DIAMETER_MM, body_x0, camera_transition_x0 - body_x0, BS_Y, BS_Z),
        x_cone(CAP_OUTER_DIAMETER_MM, CAMERA_MALE_ROOT_MM, camera_transition_x0, CAMERA_TRANSITION_MM, BS_Y, BS_Z),
        x_cylinder(CAMERA_MALE_ROOT_MM, camera_thread_x0, outer_end - camera_thread_x0, BS_Y, BS_Z),
        x_male_thread(CAMERA_MALE_ROOT_MM, camera_thread_x0, CAMERA_THREAD_LENGTH_MM, BS_Y, BS_Z, phase_shift=0.0),
    ]
    body = fuse_cap_parts(parts, label="C cap")
    aperture_taper_length = 1.5
    cutters = [
        x_cylinder(body_bore, contact - 0.1, outer_end - contact + 0.2, BS_Y, BS_Z),
        x_cylinder(aperture, contact - 0.1, body_x0 - contact + 0.2, BS_Y, BS_Z),
    ]
    if not math.isclose(aperture, body_bore, abs_tol=1e-9):
        cutters.append(
            x_cone(aperture, body_bore, body_x0, aperture_taper_length, BS_Y, BS_Z)
        )
    body = cut_cap_bores(body, cutters, label="C cap")
    return body, {
        "outer_end_mm": outer_end,
        "contact_mm": contact,
        "axial_length_mm": outer_end - contact,
        "lens_thread_min_mm": thread_x0,
        "lens_thread_max_mm": thread_x1,
        "camera_thread_min_mm": camera_thread_x0,
        "camera_thread_max_mm": camera_thread_x1,
        "axis_y_mm": BS_Y,
        "axis_z_mm": BS_Z,
        "retainer_aperture_mm": aperture,
    }


def build_caps(
    spec: LensSpec,
    arm_info: dict[str, dict[str, float]],
) -> tuple[dict[str, cq.Workplane], dict[str, dict[str, float]]]:
    a, a_info = build_a_cap(spec, arm_info["A"])
    b, b_info = build_b_cap(spec, arm_info["B"])
    c, c_info = build_c_cap(spec, arm_info["C"])
    return {"A": a, "B": b, "C": c}, {"A": a_info, "B": b_info, "C": c_info}


def place_lens(lens: cq.Workplane, seat: float, arm: str, inward_edge: float) -> cq.Workplane:
    shifted = lens.translate((0.0, 0.0, -inward_edge))
    if arm == "A":
        return shifted.rotate((0, 0, 0), (0, 1, 0), 180).translate((BS_X, BS_Y, seat))
    if arm == "B":
        return shifted.translate((B_AXIS_X, BS_Y, seat))
    if arm == "C":
        return shifted.rotate((0, 0, 0), (0, 1, 0), 90).translate((seat, BS_Y, BS_Z))
    raise ValueError(arm)


def make_bs_proxy() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(25.0, 25.0, 1.0, centered=(True, True, True))
        .rotate((0, 0, 0), (0, 1, 0), 45.0)
        .translate((BS_X, BS_Y, BS_Z))
    )


def bbox(shape: cq.Shape) -> dict[str, list[float]]:
    box = shape.BoundingBox()
    return {
        "min": [round(box.xmin, 6), round(box.ymin, 6), round(box.zmin, 6)],
        "max": [round(box.xmax, 6), round(box.ymax, 6), round(box.zmax, 6)],
        "size": [round(box.xlen, 6), round(box.ylen, 6), round(box.zlen, 6)],
    }


def step_summary(path: Path) -> dict[str, Any]:
    shape = cq.importers.importStep(str(path)).val()
    return {
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "bbox": bbox(shape),
        "volume_mm3": round(shape.Volume(), 6),
        "occt_valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
    }


def mesh_summary(path: Path) -> dict[str, Any]:
    loaded = trimesh.load_mesh(path, force="mesh", process=True)
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"cannot load mesh {path}")
    parent = list(range(len(loaded.vertices)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    referenced: set[int] = set()
    for first, second, third in loaded.faces:
        indices = (int(first), int(second), int(third))
        referenced.update(indices)
        union(indices[0], indices[1])
        union(indices[1], indices[2])
    components = len({find(index) for index in referenced})

    return {
        "vertices": int(len(loaded.vertices)),
        "faces": int(len(loaded.faces)),
        "watertight": bool(loaded.is_watertight),
        "winding_consistent": bool(loaded.is_winding_consistent),
        "components": int(components),
        "bounds_mm": [[round(float(v), 6) for v in row] for row in loaded.bounds],
    }


def sanitize_stl(path: Path) -> None:
    """Remove tessellation-only degenerate faces without changing the B-rep."""
    mesh = trimesh.load_mesh(path, force="mesh", process=True)
    if isinstance(mesh, trimesh.Scene):
        meshes = [item for item in mesh.geometry.values() if isinstance(item, trimesh.Trimesh)]
        mesh = trimesh.util.concatenate(meshes)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"cannot sanitize mesh {path}")
    mesh.update_faces(mesh.nondegenerate_faces(height=1e-10))
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight:
        counts = np.bincount(mesh.edges_unique_inverse)
        boundary_edges = mesh.edges_unique[counts == 1]
        boundary_vertices = sorted({int(value) for edge in boundary_edges for value in edge})
        if len(boundary_edges) == 3 and len(boundary_vertices) == 3:
            for candidate in itertools.permutations(boundary_vertices):
                trial = trimesh.Trimesh(
                    vertices=mesh.vertices.copy(),
                    faces=np.vstack([mesh.faces, candidate]),
                    process=False,
                )
                if trial.is_watertight and trial.is_winding_consistent:
                    mesh = trial
                    break
    mesh.export(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_evidence(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    return [
        {
            "path": str(path),
            "relative_path": str(path.relative_to(root)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def localize_for_print(shape: cq.Workplane) -> cq.Workplane:
    box = shape.val().BoundingBox()
    return shape.translate((-box.xmin, -box.ymin, -box.zmin))


def overlap_length(first: tuple[float, float], second: tuple[float, float]) -> float:
    return max(0.0, min(first[1], second[1]) - max(first[0], second[0]))


def export_shape_set(
    shapes: dict[str, cq.Workplane],
    artifact_dir: Path,
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    parts_dir = artifact_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for name, shape in shapes.items():
        stem = f"openhi_{name}"
        step = parts_dir / f"{stem}.step"
        stl = parts_dir / f"{stem}.stl"
        threemf = parts_dir / f"{stem}.3mf"
        exporters.export(shape, str(step))
        exporters.export(
            localize_for_print(shape),
            str(stl),
            tolerance=0.035,
            angularTolerance=0.10,
        )
        sanitize_stl(stl)
        export_stl_as_3mf(stl, threemf, title=stem)
        outputs[name] = {
            "step": str(step.relative_to(ROOT)),
            "stl": str(stl.relative_to(ROOT)),
            "3mf": str(threemf.relative_to(ROOT)),
            "step_validation": step_summary(step),
            "mesh_validation": mesh_summary(stl),
            "sha256": {p.suffix.lstrip("."): sha256(p) for p in (step, stl, threemf)},
        }
    return outputs


def write_readme(
    design_dir: Path,
    spec: LensSpec,
    lens_info: dict[str, float],
    arm_info: dict[str, dict[str, float]],
) -> None:
    bfl_note = (
        f" Manufacturer BFL: `{spec.back_focal_length_mm:.3f} mm`."
        if spec.back_focal_length_mm is not None
        else " The catalog does not provide BFL/principal-plane locations."
    )
    complete_end_path = 4.0 * spec.focal_length_mm + END_TO_END_SEAT_ALLOWANCE_MM
    content = f"""# OpenHI Same-Lens 4f System: {spec.label}

## Use This

- `USE_THIS_{spec.key}_openhi_4f_assembly.step`: six mechanical parts plus three lens copies and a beam-splitter reference.
- `artifacts/parts/`: separate STEP, STL, and 3MF files for A, A+C+BS, B, C, Lens B holder, and Lens C holder.
- `artifacts/{spec.key}_lens.step`: standalone lens model.
- `artifacts/manifest.json`: dimensions, source identity, assembly transforms, focal datums, and validation.

## Optical Layout

All three arms use the same `{spec.label}` lens. The beam-splitter center is the fixed datum `(255, 210, 600) mm`. The CAD places the A, B, and C holder contact planes one catalog EFL from that datum: `{spec.focal_length_mm:.5f} mm`. Therefore A-B and A-C nominal principal-plane separations are `2f = {2.0 * spec.focal_length_mm:.5f} mm` under the source OpenHI thin-lens convention.{bfl_note}

The complete physical A-to-B and A-to-C outer-end paths are both `{complete_end_path:.5f} mm = 4f + {END_TO_END_SEAT_ALLOWANCE_MM:.1f} mm`. The `4.6 mm` allowance is measured from the accepted ST018 assembly, not guessed: the A outer end contributes `f + {A_END_SEAT_EXTRA_MM:.1f} mm` and each output end contributes `f + {OUTPUT_END_SEAT_EXTRA_MM:.1f} mm`. Thread length overlaps its receiver and is not added again to this path.

For the plano-convex variants, all plane faces point inward toward the beam splitter, as requested. The manifest records the BFL-versus-EFL difference so a bench test can tune the final axial position rather than hiding a thick-lens assumption.

## Lens Fit

- nominal lens diameter: `{spec.diameter_mm:.3f} mm`;
- holder pocket: `{arm_info['A']['pocket_mm']:.3f} mm`;
- clear aperture: `{arm_info['A']['aperture_mm']:.3f} mm`;
- modeled mechanical edge thickness: `{lens_info['mechanical_edge_thickness_mm']:.3f} mm`;
- retaining axial envelope at the actual support radius: `{lens_info['holder_axial_envelope_mm']:.3f} mm`;
- axial pocket allowance: `{AXIAL_LENS_CLEARANCE_MM:.3f} mm`;
- female threads: `{FEMALE_PIVOT_MM:.1f}/{FEMALE_GROOVE_MM:.1f} mm`, pitch `{PITCH_MM:.1f} mm`, `{THREAD_LENGTH_MM:.2f} mm` bounded engagement;
- matching male lens threads: `{MALE_LENS_ROOT_MM:.1f}/{MALE_LENS_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM:.1f} mm` root/crest;
- B optical axis: `X = {B_AXIS_X:.3f} mm`, intentionally `{B_AXIS_X - BS_X:.3f} mm` from the A/beam-splitter datum.

The holder side supplies the flat locating shoulder. A/B/C retain from the opposite side. The 45-degree diameter transition is on the A/B/C-facing receiver side, preserving the original OpenHI design philosophy.

The A and C axes use the beam-splitter datum. The complete B chain, including holder bore, pocket, lens, retainer, and camera thread, preserves the accepted source axis at `X = {B_AXIS_X:.3f} mm`; it must not be recentered to `255 mm`.

## Prescription Status

`{spec.prescription_status}`. {spec.source_note}

This is a mechanically buildable CAD reconstruction. JH042/JH036 require a vendor optical drawing before the internal cemented interface can be certified as an exact optical prescription.

## Rebuild

```bash
cad/.conda/cad-python/bin/python {design_dir.relative_to(ROOT)}/build_{spec.key}_openhi_4f.py
blender --background --python cad/tools/render_openhi_same_lens_4f.py -- --design-dir {design_dir.relative_to(ROOT)}
```
"""
    (design_dir / "README.md").write_text(content, encoding="utf-8")


def sync_outputs(design_dir: Path, spec: LensSpec) -> Path:
    artifact_dir = design_dir / "artifacts"
    target = NUTSTORE_ROOT / design_dir.name
    target.mkdir(parents=True, exist_ok=True)
    direct_files = [
        design_dir / f"USE_THIS_{spec.key}_openhi_4f_assembly.step",
        design_dir / "README.md",
        artifact_dir / "manifest.json",
        artifact_dir / f"{spec.key}_lens.step",
        artifact_dir / f"{spec.key}_lens.stl",
        artifact_dir / f"{spec.key}_lens.3mf",
        artifact_dir / f"{spec.key}_openhi_4f_assembly.step",
    ]
    for source in direct_files:
        if source.exists():
            shutil.copy2(source, target / source.name)
    for subdir in ("parts", "renders"):
        source_dir = artifact_dir / subdir
        if not source_dir.exists():
            continue
        target_dir = target / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_dir.glob("*")):
            if source.is_file():
                shutil.copy2(source, target_dir / source.name)
    return target


def build_system(spec_key: str, design_dir: Path, *, sync: bool = True) -> dict[str, Any]:
    spec = LENS_SPECS[spec_key]
    design_dir = design_dir.resolve()
    artifact_dir = design_dir / "artifacts"
    components_dir = artifact_dir / "assembly_components"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    components_dir.mkdir(parents=True, exist_ok=True)

    lens, lens_info = build_lens(spec)
    edge = max(
        float(lens_info["mechanical_edge_thickness_mm"]),
        float(lens_info["mechanical_outward_contact_z_mm"])
        - float(lens_info["mechanical_inward_contact_z_mm"]),
    )
    lens_info["holder_axial_envelope_mm"] = round(edge, 6)
    ac_bs, a_info = build_a_c_bs(spec, edge)
    b_holder, b_info = build_b_holder(spec, edge)
    c_holder, c_info = build_c_holder(spec, edge)
    arm_info = {"A": a_info, "B": b_info, "C": c_info}
    caps, cap_info = build_caps(spec, arm_info)
    parts = {
        "A": caps["A"],
        "A_C_BS": ac_bs,
        "B": caps["B"],
        "C": caps["C"],
        "Lens_B_holder": b_holder,
        "Lens_C_holder": c_holder,
    }
    part_outputs = export_shape_set(parts, artifact_dir)

    lens_step = artifact_dir / f"{spec.key}_lens.step"
    lens_stl = artifact_dir / f"{spec.key}_lens.stl"
    lens_3mf = artifact_dir / f"{spec.key}_lens.3mf"
    exporters.export(lens, str(lens_step))
    lens_mesh_shape = fuse_source_solids(lens.val(), label=f"{spec.key} lens mesh")
    exporters.export(localize_for_print(lens_mesh_shape), str(lens_stl), tolerance=0.015, angularTolerance=0.05)
    sanitize_stl(lens_stl)
    export_stl_as_3mf(lens_stl, lens_3mf, title=f"{spec.key}_lens")

    lens_contact = lens_info["mechanical_inward_contact_z_mm"]
    lens_a = place_lens(lens, a_info["seat_mm"], "A", lens_contact)
    lens_b = place_lens(lens, b_info["seat_mm"], "B", lens_contact)
    lens_c = place_lens(lens, c_info["seat_mm"], "C", lens_contact)
    lens_b_box = lens_b.val().BoundingBox()
    lens_b_axis_x = (lens_b_box.xmin + lens_b_box.xmax) / 2.0
    assembly_parts = {
        "A": caps["A"],
        "A_C_BS": ac_bs,
        "B": caps["B"],
        "C": caps["C"],
        "Lens_B_holder": b_holder,
        "Lens_C_holder": c_holder,
        "lens_A": lens_a,
        "lens_B": lens_b,
        "lens_C": lens_c,
        "beam_splitter_reference": make_bs_proxy(),
    }
    lens_interference_mm3 = {
        "A_holder": lens_a.val().intersect(ac_bs.val()).Volume(),
        "A_cap": lens_a.val().intersect(assembly_parts["A"].val()).Volume(),
        "B_holder": lens_b.val().intersect(b_holder.val()).Volume(),
        "B_cap": lens_b.val().intersect(assembly_parts["B"].val()).Volume(),
        "C_holder": lens_c.val().intersect(assembly_parts["Lens_C_holder"].val()).Volume(),
        "C_cap": lens_c.val().intersect(assembly_parts["C"].val()).Volume(),
    }
    mating_interference_mm3 = {
        "A": caps["A"].val().intersect(ac_bs.val()).Volume(),
        "B": caps["B"].val().intersect(b_holder.val()).Volume(),
        "C": caps["C"].val().intersect(c_holder.val()).Volume(),
    }
    thread_engagement_mm = {
        "A": overlap_length(
            (a_info["thread_min_mm"], a_info["thread_max_mm"]),
            (cap_info["A"]["lens_thread_min_mm"], cap_info["A"]["lens_thread_max_mm"]),
        ),
        "B": overlap_length(
            (b_info["thread_min_mm"], b_info["thread_max_mm"]),
            (cap_info["B"]["lens_thread_min_mm"], cap_info["B"]["lens_thread_max_mm"]),
        ),
        "C": overlap_length(
            (c_info["thread_min_mm"], c_info["thread_max_mm"]),
            (cap_info["C"]["lens_thread_min_mm"], cap_info["C"]["lens_thread_max_mm"]),
        ),
    }
    source_bs = cq.importers.importStep(str(SOURCE_AC_BS)).val()
    protected_source_bs = keep_z_above(source_bs, 580.1).val()
    protected_generated_bs = keep_z_above(ac_bs.val(), 580.1).val()
    protected_bs_difference_mm3 = (
        protected_source_bs.cut(protected_generated_bs).Volume()
        + protected_generated_bs.cut(protected_source_bs).Volume()
    )
    focal_datum_error_mm = {
        "A_to_B_2f": abs((b_info["seat_mm"] - a_info["seat_mm"]) - 2.0 * spec.focal_length_mm),
        "BS_to_A_f": abs((BS_Z - a_info["seat_mm"]) - spec.focal_length_mm),
        "BS_to_B_f": abs((b_info["seat_mm"] - BS_Z) - spec.focal_length_mm),
        "BS_to_C_f": abs((c_info["seat_mm"] - BS_X) - spec.focal_length_mm),
    }
    expected_end_path_mm = 4.0 * spec.focal_length_mm + END_TO_END_SEAT_ALLOWANCE_MM
    end_path_mm = {
        "A_to_B": (BS_Z - cap_info["A"]["outer_end_mm"]) + (cap_info["B"]["outer_end_mm"] - BS_Z),
        "A_to_C": (BS_Z - cap_info["A"]["outer_end_mm"]) + (cap_info["C"]["outer_end_mm"] - BS_X),
    }
    end_path_error_mm = {
        name: abs(value - expected_end_path_mm) for name, value in end_path_mm.items()
    }
    b_axis_chain_error_mm = {
        "holder_declared_axis": abs(b_info["optical_axis_x_mm"] - B_AXIS_X),
        "cap_declared_axis": abs(cap_info["B"]["axis_x_mm"] - B_AXIS_X),
        "lens_measured_bbox_axis": abs(lens_b_axis_x - B_AXIS_X),
    }
    for name, shape in assembly_parts.items():
        export_shape = (
            fuse_source_solids(shape.val(), label=f"{name} assembly mesh")
            if name.startswith("lens_")
            else shape
        )
        component_stl = components_dir / f"{name}.stl"
        exporters.export(export_shape, str(component_stl), tolerance=0.035, angularTolerance=0.10)
        sanitize_stl(component_stl)

    assembly = compound(assembly_parts.values())
    assembly_step = artifact_dir / f"{spec.key}_openhi_4f_assembly.step"
    exporters.export(assembly, str(assembly_step))
    use_this = design_dir / f"USE_THIS_{spec.key}_openhi_4f_assembly.step"
    shutil.copy2(assembly_step, use_this)

    optical = {
        "beam_splitter_center_mm": [BS_X, BS_Y, BS_Z],
        "catalog_efl_mm": spec.focal_length_mm,
        "a_holder_contact_plane_z_mm": a_info["seat_mm"],
        "b_holder_contact_plane_z_mm": b_info["seat_mm"],
        "c_holder_contact_plane_x_assembly_mm": c_info["seat_mm"],
        "a_to_b_nominal_2f_mm": 2.0 * spec.focal_length_mm,
        "a_to_c_nominal_2f_mm": 2.0 * spec.focal_length_mm,
        "plano_faces_toward_beam_splitter": spec.kind == "plano_convex",
        "manufacturer_bfl_mm": spec.back_focal_length_mm,
        "thick_lens_bfl_minus_efl_mm": (
            spec.back_focal_length_mm - spec.focal_length_mm
            if spec.back_focal_length_mm is not None
            else None
        ),
        "datum_policy": (
            "Catalog EFL is used as the source-compatible holder contact distance. "
            "Manufacturer BFL is retained as a physical tuning datum for thick plano-convex lenses."
        ),
        "lens_to_mechanical_interference_mm3": {
            key: round(value, 9) for key, value in lens_interference_mm3.items()
        },
        "mating_part_interference_mm3": {
            key: round(value, 9) for key, value in mating_interference_mm3.items()
        },
        "thread_engagement_mm": {
            key: round(value, 6) for key, value in thread_engagement_mm.items()
        },
        "focal_datum_error_mm": {
            key: round(value, 9) for key, value in focal_datum_error_mm.items()
        },
        "protected_beam_splitter_region_difference_mm3": round(
            protected_bs_difference_mm3, 9
        ),
        "b_axis_x_mm": B_AXIS_X,
        "b_axis_shift_from_a_mm": round(B_AXIS_X - BS_X, 6),
        "b_axis_chain_error_mm": {
            key: round(value, 9) for key, value in b_axis_chain_error_mm.items()
        },
        "source_st018_focal_length_mm": SOURCE_FOCAL_LENGTH_MM,
        "end_to_end_seat_allowance_mm": END_TO_END_SEAT_ALLOWANCE_MM,
        "expected_end_path_4f_plus_seat_mm": round(expected_end_path_mm, 9),
        "measured_end_path_mm": {key: round(value, 9) for key, value in end_path_mm.items()},
        "end_path_error_mm": {key: round(value, 9) for key, value in end_path_error_mm.items()},
    }
    lens_mesh_validation = mesh_summary(lens_stl)
    checks = {
        "all_part_steps_valid": all(row["step_validation"]["occt_valid"] for row in part_outputs.values()),
        "all_part_meshes_watertight": all(row["mesh_validation"]["watertight"] for row in part_outputs.values()),
        "lens_step_valid": step_summary(lens_step)["occt_valid"],
        "lens_mesh_watertight": lens_mesh_validation["watertight"],
        "assembly_step_valid": step_summary(assembly_step)["occt_valid"],
        "three_identical_lens_copies": True,
        "nominal_4f_spacing_matches_catalog_efl": max(focal_datum_error_mm.values()) <= 1e-8,
        "source_beam_splitter_geometry_preserved": protected_bs_difference_mm3 <= 1e-6,
        "lens_to_mechanical_interference_is_zero": all(
            value <= 1e-6 for value in lens_interference_mm3.values()
        ),
        "mating_part_interference_is_zero": all(
            value <= 1e-6 for value in mating_interference_mm3.values()
        ),
        "minimum_thread_engagement_is_at_least_5mm": min(thread_engagement_mm.values()) >= 5.0,
        "end_paths_equal_4f_plus_measured_seat": max(end_path_error_mm.values()) <= 1e-8,
        "b_axis_shift_preserved": max(b_axis_chain_error_mm.values()) <= 1e-8,
    }
    manifest = {
        "design": design_dir.name,
        "lens": asdict(spec),
        "lens_model": lens_info,
        "optical_layout": optical,
        "arms": {"A": a_info, "B": b_info, "C": c_info},
        "caps": cap_info,
        "source_files": {
            path.name: {"path": str(path), "sha256": sha256(path)}
            for path in (SOURCE_A, SOURCE_B, SOURCE_C, SOURCE_AC_BS, SOURCE_B_HOLDER, SOURCE_C_HOLDER, SOURCE_SHAPR)
            if path.exists()
        },
        "lens_source_evidence": source_evidence(
            GLA_SOURCE_ROOT if spec.key.startswith("gla11") else JH_SOURCE_ROOT
        ),
        "parts": part_outputs,
        "lens_outputs": {
            "step": str(lens_step.relative_to(ROOT)),
            "stl": str(lens_stl.relative_to(ROOT)),
            "3mf": str(lens_3mf.relative_to(ROOT)),
            "step_validation": step_summary(lens_step),
            "mesh_validation": lens_mesh_validation,
        },
        "assembly": {
            "step": str(assembly_step.relative_to(ROOT)),
            "use_this_step": str(use_this.relative_to(ROOT)),
            "validation": step_summary(assembly_step),
        },
        "checks": checks,
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(design_dir, spec, lens_info, {"A": a_info, "B": b_info, "C": c_info})

    if not all(checks.values()):
        raise RuntimeError(f"validation failed for {spec.key}: {checks}")

    if sync:
        sync_outputs(design_dir, spec)

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", choices=sorted(LENS_SPECS))
    parser.add_argument("--design-dir", required=True, type=Path)
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--sync-only", action="store_true")
    args = parser.parse_args()
    if args.sync_only:
        target = sync_outputs(args.design_dir.resolve(), LENS_SPECS[args.spec])
        print(json.dumps({"design": args.design_dir.name, "synced_to": str(target)}, indent=2))
        return
    manifest = build_system(args.spec, args.design_dir, sync=not args.no_sync)
    print(json.dumps({"design": manifest["design"], "checks": manifest["checks"]}, indent=2))


def run_design_cli(spec_key: str, design_dir: Path) -> None:
    """Run a fixed-lens convenience wrapper without hiding sync behavior."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--sync-only", action="store_true")
    args = parser.parse_args()
    spec = LENS_SPECS[spec_key]
    design_dir = design_dir.resolve()
    if args.sync_only:
        target = sync_outputs(design_dir, spec)
        print(json.dumps({"design": design_dir.name, "synced_to": str(target)}, indent=2))
        return
    manifest = build_system(spec_key, design_dir, sync=not args.no_sync)
    print(json.dumps({"design": manifest["design"], "checks": manifest["checks"]}, indent=2))


if __name__ == "__main__":
    main()

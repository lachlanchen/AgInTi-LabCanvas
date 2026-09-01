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
from collections import Counter
import hashlib
import itertools
import json
import math
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

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
SOURCE_A_INPUT_RECEIVER = ROOT / "cad/extracted/OpenHI_STEP/A.step"
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
# The original A part has a source-authored internal OpenHI/C-mount-like
# receiver at its lower end.  Preserve that B-rep cavity instead of replacing
# it with a plain lead-in cone.  The receiver is internal to the A optical-arm
# envelope: a mating flange seats at the A outer face, so its insertion depth
# is not added a second time to the 4f distance chain.
A_INPUT_RECEIVER_DOMAIN_DIAMETER_MM = 30.0
A_INPUT_RECEIVER_PILOT_DIAMETER_MM = 25.0
A_INPUT_RECEIVER_GROOVE_DIAMETER_MM = 25.8
A_INPUT_RECEIVER_DEPTH_MM = 12.474
A_INPUT_RECEIVER_BORE_TRANSITION_ANGLE_DEG = 45.0
OPTICAL_CORE_PROBE_DIAMETER_MM = 4.0
C_RECEIVER_MEMBRANE_PROBE_DIAMETER_MM = 29.4
C_RECEIVER_PROBE_X0 = 269.91
C_RECEIVER_PROBE_X1 = 274.95
OPTICAL_PATH_END_MARGIN_MM = 0.05
BREP_BOUND_TOLERANCE_MM = 1e-6
PRINT_RELEASE_RUN_NAME = (
    "run-4-a-input-receiver-optical-vertex-lens-clearance-"
    "print-ready-20260901T040031Z"
)


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


def a_input_receiver_cavity(
    outer_end_mm: float,
) -> tuple[cq.Workplane, dict[str, float]]:
    """Return the exact lower internal receiver void from the source A B-rep."""

    source = cq.importers.importStep(str(SOURCE_A_INPUT_RECEIVER)).val()
    lower = min(source.Solids(), key=lambda item: item.BoundingBox().zmin)
    box = lower.BoundingBox()
    depth = box.zmax - box.zmin
    if not math.isclose(depth, A_INPUT_RECEIVER_DEPTH_MM, abs_tol=1e-5):
        raise RuntimeError(
            "source A input receiver depth changed: "
            f"expected {A_INPUT_RECEIVER_DEPTH_MM}, measured {depth}"
        )
    domain = z_cylinder(
        A_INPUT_RECEIVER_DOMAIN_DIAMETER_MM,
        box.zmin,
        depth,
        BS_X,
        BS_Y,
    )
    cavity = largest_solid(domain.cut(wp(lower)).clean())
    cavity_box = cavity.val().BoundingBox()
    if not math.isclose(
        max(cavity_box.xlen, cavity_box.ylen),
        A_INPUT_RECEIVER_GROOVE_DIAMETER_MM,
        abs_tol=1e-5,
    ):
        raise RuntimeError("source A input receiver groove envelope changed")
    translated = cavity.translate((0.0, 0.0, outer_end_mm - box.zmin))
    return translated, {
        "source_min_mm": box.zmin,
        "source_max_mm": box.zmax,
        "depth_mm": depth,
        "min_mm": outer_end_mm,
        "max_mm": outer_end_mm + depth,
        "pilot_diameter_mm": A_INPUT_RECEIVER_PILOT_DIAMETER_MM,
        "groove_diameter_mm": A_INPUT_RECEIVER_GROOVE_DIAMETER_MM,
        "domain_diameter_mm": A_INPUT_RECEIVER_DOMAIN_DIAMETER_MM,
        "source_cavity_volume_mm3": cavity.val().Volume(),
    }


def sag(radius: float, radial: float) -> float:
    if abs(radius) < 1e-12:
        return 0.0
    if radial >= abs(radius):
        raise ValueError(f"radius {radius} cannot span semi-diameter {radial}")
    return radius - math.copysign(math.sqrt(radius * radius - radial * radial), radius)


def surface_z(vertex_z: float, radius: float, radial: float) -> float:
    return vertex_z + sag(radius, radial)


def revolved_between_spherical_surfaces(
    lower_vertex_z: float,
    lower_radius: float,
    upper_vertex_z: float,
    upper_radius: float,
    semi_diameter: float,
) -> cq.Workplane:
    """Revolve an exact meridional section bounded by planes or circular arcs."""

    def append_surface(
        profile: cq.Workplane,
        vertex_z: float,
        radius: float,
        *,
        outward: bool,
    ) -> cq.Workplane:
        edge = (semi_diameter, surface_z(vertex_z, radius, semi_diameter))
        axis = (0.0, surface_z(vertex_z, radius, 0.0))
        if abs(radius) < 1e-12:
            return profile.lineTo(*(edge if outward else axis))
        midpoint = (
            semi_diameter / 2.0,
            surface_z(vertex_z, radius, semi_diameter / 2.0),
        )
        return profile.threePointArc(midpoint, edge if outward else axis)

    profile = cq.Workplane("XZ").moveTo(
        0.0,
        surface_z(lower_vertex_z, lower_radius, 0.0),
    )
    profile = append_surface(
        profile,
        lower_vertex_z,
        lower_radius,
        outward=True,
    )
    profile = profile.lineTo(
        semi_diameter,
        surface_z(upper_vertex_z, upper_radius, semi_diameter),
    )
    profile = append_surface(
        profile,
        upper_vertex_z,
        upper_radius,
        outward=False,
    )
    return profile.close().revolve(
        360.0,
        (0.0, 0.0),
        (0.0, 1.0),
        combine=True,
    ).clean()


def build_plano_convex(spec: LensSpec) -> tuple[cq.Workplane, dict[str, Any]]:
    semi = spec.diameter_mm / 2.0
    optical_radius = abs(spec.radii_mm[-1])
    bevel = max(0.0, min(spec.bevel_mm, semi * 0.1))
    cylinder = cq.Workplane("XY").circle(semi).extrude(spec.center_thickness_mm)
    sphere = cq.Workplane("XY").sphere(optical_radius).translate(
        (0.0, 0.0, spec.center_thickness_mm - optical_radius)
    )
    lens = cylinder.intersect(sphere).clean()
    theoretical_edge = spec.center_thickness_mm - sag(optical_radius, semi)
    if bevel > 0.0:
        rim_edges = [
            edge
            for edge in lens.val().Edges()
            if edge.BoundingBox().zlen < 1e-7
            and math.isclose(
                edge.Length(),
                math.pi * spec.diameter_mm,
                abs_tol=1e-5,
            )
        ]
        if len(rim_edges) != 2:
            raise RuntimeError(f"could not identify two rim edges for {spec.key}")
        lens = (
            cq.Workplane(obj=lens.val())
            .newObject(rim_edges)
            .chamfer(bevel)
            .clean()
        )
    modeled_edge_land = max(0.0, theoretical_edge - 2.0 * bevel)
    support_radius = min(24.0, spec.diameter_mm - 1.5) / 2.0
    outward_support = spec.center_thickness_mm - sag(optical_radius, support_radius)
    return lens, {
        "inward_edge_z_mm": round(bevel, 6),
        "mechanical_inward_contact_z_mm": 0.0,
        "mechanical_outward_contact_z_mm": round(outward_support, 6),
        "mechanical_support_radius_mm": round(support_radius, 6),
        "outward_edge_z_mm": round(theoretical_edge - bevel, 6),
        "mechanical_edge_thickness_mm": round(modeled_edge_land, 6),
        "modeled_edge_thickness_mm": round(modeled_edge_land, 6),
        "unbeveled_edge_thickness_mm": round(theoretical_edge, 6),
        "manufacturer_edge_thickness_mm": spec.edge_thickness_mm,
        "manufacturer_edge_consistency_error_mm": round(
            theoretical_edge - spec.edge_thickness_mm,
            6,
        )
        if spec.edge_thickness_mm is not None
        else None,
        "bevel_mm": round(bevel, 6),
        "analytic_spherical_faces": True,
        "radius_authority_mm": optical_radius,
    }


def build_doublet(spec: LensSpec) -> tuple[cq.Workplane, dict[str, Any]]:
    if len(spec.radii_mm) != 3 or len(spec.element_center_thicknesses_mm) != 2:
        raise ValueError(f"incomplete doublet spec: {spec.key}")
    r1, r2, r3 = spec.radii_mm
    t1, t2 = spec.element_center_thicknesses_mm
    if not math.isclose(t1 + t2, spec.center_thickness_mm, abs_tol=1e-6):
        raise ValueError(f"doublet thickness split does not sum for {spec.key}")
    semi = spec.diameter_mm / 2.0
    def s1(radial: float) -> float:
        return surface_z(0.0, r1, radial)

    def s2(radial: float) -> float:
        return surface_z(t1, r2, radial)

    def s3(radial: float) -> float:
        return surface_z(t1 + t2, r3, radial)

    for index in range(65):
        radial = semi * index / 64.0
        if not (s1(radial) < s2(radial) < s3(radial)):
            raise ValueError(
                f"assumed {spec.key} doublet surfaces cross at r={radial:.3f} mm"
            )
    first = revolved_between_spherical_surfaces(0.0, r1, t1, r2, semi)
    second = revolved_between_spherical_surfaces(t1, r2, t1 + t2, r3, semi)
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
        "analytic_spherical_faces": True,
    }


def build_lens(spec: LensSpec) -> tuple[cq.Workplane, dict[str, Any]]:
    if spec.kind == "plano_convex":
        return build_plano_convex(spec)
    if spec.kind == "cemented_doublet":
        return build_doublet(spec)
    raise ValueError(f"unsupported lens kind: {spec.kind}")


def lens_aperture(spec: LensSpec) -> float:
    return min(24.0, spec.diameter_mm - 1.5)


def build_a_c_bs(
    spec: LensSpec,
    edge: float,
    inward_contact: float,
) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_AC_BS)).val()
    static = keep_z_above(source, 580.0)
    optical_vertex_z = BS_Z - spec.focal_length_mm
    seat_z = optical_vertex_z - inward_contact
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
        "optical_vertex_mm": optical_vertex_z,
        "seat_mm": seat_z,
        "contact_mm": contact_z,
        "thread_min_mm": thread_z0,
        "thread_max_mm": thread_z1,
        "outer_end_mm": body_z0,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
        "optical_axis_x_mm": BS_X,
        "optical_axis_y_mm": BS_Y,
        "inward_support_offset_mm": inward_contact,
        "lens_axial_envelope_mm": edge,
        "available_lens_cavity_mm": seat_z - contact_z,
    }


def build_b_holder(
    spec: LensSpec,
    edge: float,
    inward_contact: float,
) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_B_HOLDER)).val()
    static = keep_z_below(source, 620.0)
    optical_vertex_z = BS_Z + spec.focal_length_mm
    seat_z = optical_vertex_z + inward_contact
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
        "optical_vertex_mm": optical_vertex_z,
        "seat_mm": seat_z,
        "contact_mm": contact_z,
        "thread_min_mm": thread_z0,
        "thread_max_mm": thread_z1,
        "outer_end_mm": body_z1,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
        "optical_axis_x_mm": B_AXIS_X,
        "optical_axis_y_mm": BS_Y,
        "preserved_outer_skin_axis_x_mm": 254.633,
        "inward_support_offset_mm": inward_contact,
        "lens_axial_envelope_mm": edge,
        "available_lens_cavity_mm": contact_z - seat_z,
    }


def build_c_holder(
    spec: LensSpec,
    edge: float,
    inward_contact: float,
) -> tuple[cq.Workplane, dict[str, float]]:
    source = cq.importers.importStep(str(SOURCE_C_HOLDER)).val().moved(
        cq.Location(cq.Vector(-20.0, 0.0, 0.0))
    )
    solids = source.Solids()
    if len(solids) != 2:
        raise RuntimeError("accepted Lens C holder must contain two solids")
    male = min(solids, key=lambda item: item.Volume())
    main = max(solids, key=lambda item: item.Volume())
    static = keep_x_below(main, 280.2)
    optical_vertex_x = BS_X + spec.focal_length_mm
    seat_x = optical_vertex_x + inward_contact
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
        "optical_vertex_mm": optical_vertex_x,
        "seat_mm": seat_x,
        "contact_mm": contact_x,
        "thread_min_mm": thread_x0,
        "thread_max_mm": thread_x1,
        "outer_end_mm": body_x1,
        "aperture_mm": aperture,
        "pocket_mm": pocket,
        "assembly_translation_x_mm": 0.0,
        "optical_axis_y_mm": BS_Y,
        "optical_axis_z_mm": BS_Z,
        "legacy_male_root_mm": LEGACY_MALE_ROOT_MM,
        "legacy_male_fuse_diameter_mm": LEGACY_MALE_FUSE_DIAMETER_MM,
        "inward_support_offset_mm": inward_contact,
        "lens_axial_envelope_mm": edge,
        "available_lens_cavity_mm": contact_x - seat_x,
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
    contact = info["contact_mm"]
    thread_z0 = info["thread_min_mm"]
    thread_z1 = info["thread_max_mm"]
    optical_vertex = info["optical_vertex_mm"]
    outer_end = optical_vertex - spec.focal_length_mm - A_END_SEAT_EXTRA_MM
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
    receiver, receiver_info = a_input_receiver_cavity(outer_end)
    transition_length = (
        A_INPUT_RECEIVER_PILOT_DIAMETER_MM - aperture
    ) / 2.0
    if transition_length < 0.0:
        raise RuntimeError(f"A aperture exceeds source receiver pilot: {spec.key}")
    transition_z0 = receiver_info["max_mm"]
    transition_z1 = transition_z0 + transition_length
    if transition_z1 >= contact - 0.5:
        raise RuntimeError(
            f"A receiver/optical transition leaves no support land: {spec.key}"
        )
    cutters = [
        receiver,
        z_cone(
            A_INPUT_RECEIVER_PILOT_DIAMETER_MM,
            aperture,
            transition_z0,
            transition_length,
            BS_X,
            BS_Y,
        ),
        z_cylinder(
            aperture,
            transition_z1 - 0.05,
            contact - transition_z1 + 0.15,
            BS_X,
            BS_Y,
        ),
    ]
    body = cut_cap_bores(body, cutters, label="A cap")
    return body, {
        "optical_vertex_mm": optical_vertex,
        "outer_end_mm": outer_end,
        "contact_mm": contact,
        "axial_length_mm": contact - outer_end,
        "lens_thread_min_mm": thread_z0,
        "lens_thread_max_mm": thread_z1,
        "input_receiver_min_mm": receiver_info["min_mm"],
        "input_receiver_max_mm": receiver_info["max_mm"],
        "input_receiver_depth_mm": receiver_info["depth_mm"],
        "input_receiver_pilot_diameter_mm": receiver_info["pilot_diameter_mm"],
        "input_receiver_groove_diameter_mm": receiver_info["groove_diameter_mm"],
        "input_receiver_source_cavity_volume_mm3": receiver_info[
            "source_cavity_volume_mm3"
        ],
        "input_receiver_transition_min_mm": transition_z0,
        "input_receiver_transition_max_mm": transition_z1,
        "input_receiver_transition_length_mm": transition_length,
        "input_receiver_flange_seat_mm": outer_end,
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
    contact = info["contact_mm"]
    thread_z0 = info["thread_min_mm"]
    thread_z1 = info["thread_max_mm"]
    optical_vertex = info["optical_vertex_mm"]
    outer_end = optical_vertex + spec.focal_length_mm + OUTPUT_END_SEAT_EXTRA_MM
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
        "optical_vertex_mm": optical_vertex,
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
    contact = info["contact_mm"]
    thread_x0 = info["thread_min_mm"]
    thread_x1 = info["thread_max_mm"]
    optical_vertex = info["optical_vertex_mm"]
    outer_end = optical_vertex + spec.focal_length_mm + OUTPUT_END_SEAT_EXTRA_MM
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
        "optical_vertex_mm": optical_vertex,
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


def place_lens(
    lens: cq.Workplane,
    optical_vertex: float,
    arm: str,
) -> cq.Workplane:
    """Place local lens z=0, the inward optical-axis vertex, exactly at f."""

    if arm == "A":
        return lens.rotate((0, 0, 0), (0, 1, 0), 180).translate(
            (BS_X, BS_Y, optical_vertex)
        )
    if arm == "B":
        return lens.translate((B_AXIS_X, BS_Y, optical_vertex))
    if arm == "C":
        return lens.rotate((0, 0, 0), (0, 1, 0), 90).translate(
            (optical_vertex, BS_Y, BS_Z)
        )
    raise ValueError(arm)


def measure_lens_axis_interval(
    placed_lens: cq.Workplane,
    spec: LensSpec,
    optical_vertex: float,
    arm: str,
) -> dict[str, float | str]:
    """Measure the placed B-rep on its optical axis, not only its transform."""

    margin = 1.0
    if arm == "A":
        probe = z_cylinder(
            0.2,
            optical_vertex - spec.center_thickness_mm - margin,
            spec.center_thickness_mm + 2.0 * margin,
            BS_X,
            BS_Y,
        )
        box = placed_lens.val().intersect(probe.val()).BoundingBox()
        measured_inward = box.zmax
        measured_outward = box.zmin
        expected_outward = optical_vertex - spec.center_thickness_mm
        axis = "Z"
    elif arm == "B":
        probe = z_cylinder(
            0.2,
            optical_vertex - margin,
            spec.center_thickness_mm + 2.0 * margin,
            B_AXIS_X,
            BS_Y,
        )
        box = placed_lens.val().intersect(probe.val()).BoundingBox()
        measured_inward = box.zmin
        measured_outward = box.zmax
        expected_outward = optical_vertex + spec.center_thickness_mm
        axis = "Z"
    elif arm == "C":
        probe = x_cylinder(
            0.2,
            optical_vertex - margin,
            spec.center_thickness_mm + 2.0 * margin,
            BS_Y,
            BS_Z,
        )
        box = placed_lens.val().intersect(probe.val()).BoundingBox()
        measured_inward = box.xmin
        measured_outward = box.xmax
        expected_outward = optical_vertex + spec.center_thickness_mm
        axis = "X"
    else:
        raise ValueError(arm)
    return {
        "axis": axis,
        "expected_inward_vertex_mm": optical_vertex,
        "measured_inward_vertex_mm": round(measured_inward, 9),
        "inward_vertex_error_mm": round(abs(measured_inward - optical_vertex), 9),
        "expected_outward_vertex_mm": expected_outward,
        "measured_outward_vertex_mm": round(measured_outward, 9),
        "outward_vertex_error_mm": round(
            abs(measured_outward - expected_outward),
            9,
        ),
    }


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

    minimum_z = float(loaded.bounds[0][2])
    face_z = loaded.vertices[loaded.faces][:, :, 2]
    first_layer_height_mm = 0.20
    first_layer_z = minimum_z + first_layer_height_mm
    first_layer_triangle_count = int(
        np.count_nonzero(
            (face_z.min(axis=1) <= first_layer_z)
            & (face_z.max(axis=1) >= first_layer_z)
            & (loaded.area_faces > 1e-10)
        )
    )
    base_face_count = int(
        np.count_nonzero(
            np.all(np.abs(face_z - minimum_z) <= 1e-4, axis=1)
            & (loaded.area_faces > 1e-10)
        )
    )

    return {
        "vertices": int(len(loaded.vertices)),
        "faces": int(len(loaded.faces)),
        "watertight": bool(loaded.is_watertight),
        "winding_consistent": bool(loaded.is_winding_consistent),
        "components": int(components),
        "bounds_mm": [[round(float(v), 6) for v in row] for row in loaded.bounds],
        "minimum_z_mm": round(minimum_z, 6),
        "first_layer_height_mm": first_layer_height_mm,
        "first_layer_triangle_count": first_layer_triangle_count,
        "base_face_count": base_face_count,
    }


def three_mf_summary(path: Path) -> dict[str, Any]:
    """Validate the native 3MF mesh without relying on optional graph packages."""
    with zipfile.ZipFile(path) as archive:
        model_name = next(
            name for name in archive.namelist() if name.lower().endswith(".model")
        )
        root = ElementTree.fromstring(archive.read(model_name))

    namespace_uri = root.tag.split("}", 1)[0].lstrip("{")
    namespace = {"m": namespace_uri}
    mesh_objects = root.findall(".//m:resources/m:object[m:mesh]", namespace)
    meshes = [item.find("./m:mesh", namespace) for item in mesh_objects]
    if len(meshes) != 1:
        raise RuntimeError(f"expected one 3MF mesh object in {path}, found {len(meshes)}")
    mesh = meshes[0]
    if mesh is None:
        raise RuntimeError(f"3MF mesh object has no mesh payload: {path}")
    vertices = [
        (
            float(vertex.attrib["x"]),
            float(vertex.attrib["y"]),
            float(vertex.attrib["z"]),
        )
        for vertex in mesh.findall("./m:vertices/m:vertex", namespace)
    ]
    triangles = [
        (
            int(triangle.attrib["v1"]),
            int(triangle.attrib["v2"]),
            int(triangle.attrib["v3"]),
        )
        for triangle in mesh.findall("./m:triangles/m:triangle", namespace)
    ]
    if not vertices or not triangles:
        raise RuntimeError(f"3MF contains no usable mesh: {path}")

    parent = list(range(len(vertices)))

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

    edge_counts: Counter[tuple[int, int]] = Counter()
    edge_orientation: Counter[tuple[int, int]] = Counter()
    referenced: set[int] = set()
    indices_valid = True
    for triangle in triangles:
        if any(index < 0 or index >= len(vertices) for index in triangle):
            indices_valid = False
            continue
        referenced.update(triangle)
        union(triangle[0], triangle[1])
        union(triangle[1], triangle[2])
        for start, end in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge = (min(start, end), max(start, end))
            edge_counts[edge] += 1
            edge_orientation[edge] += 1 if start < end else -1

    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    base_face_count = sum(
        1
        for triangle in triangles
        if indices_valid
        and all(abs(vertices[index][2] - minimum[2]) <= 1e-4 for index in triangle)
    )
    first_layer_height_mm = 0.20
    first_layer_z = minimum[2] + first_layer_height_mm
    first_layer_triangle_count = sum(
        1
        for triangle in triangles
        if indices_valid
        and min(vertices[index][2] for index in triangle) <= first_layer_z
        and max(vertices[index][2] for index in triangle) >= first_layer_z
    )
    build_items = root.findall("./m:build/m:item", namespace)
    mesh_object_ids = {item.attrib.get("id") for item in mesh_objects}
    build_object_ids = [item.attrib.get("objectid") for item in build_items]
    return {
        "unit": root.attrib.get("unit"),
        "mesh_object_count": len(meshes),
        "build_item_count": len(build_items),
        "build_items_reference_mesh_objects": all(
            object_id in mesh_object_ids for object_id in build_object_ids
        ),
        "vertices": len(vertices),
        "faces": len(triangles),
        "components": len({find(index) for index in referenced}),
        "indices_valid": indices_valid,
        "watertight": bool(edge_counts)
        and all(count == 2 for count in edge_counts.values()),
        "winding_consistent": bool(edge_orientation)
        and all(orientation == 0 for orientation in edge_orientation.values()),
        "bounds_mm": [
            [round(value, 6) for value in minimum],
            [round(value, 6) for value in maximum],
        ],
        "minimum_z_mm": round(minimum[2], 6),
        "first_layer_height_mm": first_layer_height_mm,
        "first_layer_triangle_count": first_layer_triangle_count,
        "base_face_count": base_face_count,
    }


def bounds_match(
    first: list[list[float]],
    second: list[list[float]],
    *,
    tolerance: float = 1e-5,
) -> bool:
    return all(
        math.isclose(left, right, abs_tol=tolerance)
        for first_row, second_row in zip(first, second)
        for left, right in zip(first_row, second_row)
    )


def sanitize_stl(path: Path, *, normalize_z: bool = False) -> None:
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
    if normalize_z:
        mesh.apply_translation((0.0, 0.0, -float(mesh.bounds[0][2])))
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


def orient_for_print(name: str, shape: cq.Workplane) -> tuple[cq.Workplane, str]:
    """Keep thread axes vertical while preserving STEP assembly coordinates."""
    if name == "C":
        oriented = shape.rotate((0, 0, 0), (0, 1, 0), -90.0)
        note = "rotate -90 degrees about Y; lens-retainer end on build plate"
    elif name == "Lens_B_holder":
        oriented = shape.rotate((0, 0, 0), (0, 1, 0), 180.0)
        note = "rotate 180 degrees about Y; outer lens-retainer end on build plate"
    elif name == "Lens_C_holder":
        oriented = shape.rotate((0, 0, 0), (0, 1, 0), -90.0)
        note = "rotate -90 degrees about Y; broad central mating end on build plate"
    else:
        oriented = shape
        note = "preserve assembly orientation; translate minimum Z to build plate"
    return localize_for_print(oriented), note


def overlap_length(first: tuple[float, float], second: tuple[float, float]) -> float:
    return max(0.0, min(first[1], second[1]) - max(first[0], second[0]))


def mechanical_path_probe(
    parts: dict[str, cq.Workplane],
    probe: cq.Workplane,
    *,
    axis: str,
    axial_range_mm: tuple[float, float],
    center_mm: tuple[float, float],
) -> dict[str, Any]:
    overlaps = {
        name: round(abs(shape.val().intersect(probe.val()).Volume()), 9)
        for name, shape in parts.items()
    }
    return {
        "axis": axis,
        "diameter_mm": OPTICAL_CORE_PROBE_DIAMETER_MM,
        "axial_range_mm": [round(value, 6) for value in axial_range_mm],
        "center_mm": [round(value, 6) for value in center_mm],
        "part_overlap_mm3": overlaps,
        "total_overlap_mm3": round(sum(overlaps.values()), 9),
    }


def build_optical_path_audit(
    parts: dict[str, cq.Workplane],
    cap_info: dict[str, dict[str, float]],
) -> dict[str, Any]:
    margin = OPTICAL_PATH_END_MARGIN_MM
    a_range = (cap_info["A"]["outer_end_mm"] + margin, BS_Z - margin)
    b_range = (BS_Z + margin, cap_info["B"]["outer_end_mm"] - margin)
    c_range = (BS_X + margin, cap_info["C"]["outer_end_mm"] - margin)
    paths = {
        "A": mechanical_path_probe(
            parts,
            z_cylinder(
                OPTICAL_CORE_PROBE_DIAMETER_MM,
                a_range[0],
                a_range[1] - a_range[0],
                BS_X,
                BS_Y,
            ),
            axis="Z",
            axial_range_mm=a_range,
            center_mm=(BS_X, BS_Y),
        ),
        "B": mechanical_path_probe(
            parts,
            z_cylinder(
                OPTICAL_CORE_PROBE_DIAMETER_MM,
                b_range[0],
                b_range[1] - b_range[0],
                B_AXIS_X,
                BS_Y,
            ),
            axis="Z",
            axial_range_mm=b_range,
            center_mm=(B_AXIS_X, BS_Y),
        ),
        "C": mechanical_path_probe(
            parts,
            x_cylinder(
                OPTICAL_CORE_PROBE_DIAMETER_MM,
                c_range[0],
                c_range[1] - c_range[0],
                BS_Y,
                BS_Z,
            ),
            axis="X",
            axial_range_mm=c_range,
            center_mm=(BS_Y, BS_Z),
        ),
    }
    c_receiver_probe = x_cylinder(
        C_RECEIVER_MEMBRANE_PROBE_DIAMETER_MM,
        C_RECEIVER_PROBE_X0,
        C_RECEIVER_PROBE_X1 - C_RECEIVER_PROBE_X0,
        BS_Y,
        BS_Z,
    )
    c_receiver_overlap = abs(
        parts["A_C_BS"].val().intersect(c_receiver_probe.val()).Volume()
    )
    source = cq.importers.importStep(str(SOURCE_AC_BS)).val()
    source_c_receiver_overlap = abs(source.intersect(c_receiver_probe.val()).Volume())
    return {
        "minimum_verified_core_diameter_mm": OPTICAL_CORE_PROBE_DIAMETER_MM,
        "paths": paths,
        "c_receiver_membrane_probe": {
            "diameter_mm": C_RECEIVER_MEMBRANE_PROBE_DIAMETER_MM,
            "x_range_mm": [C_RECEIVER_PROBE_X0, C_RECEIVER_PROBE_X1],
            "generated_a_c_bs_overlap_mm3": round(c_receiver_overlap, 9),
            "source_a_c_bs_overlap_mm3": round(source_c_receiver_overlap, 9),
        },
    }


def build_thread_construction_audit() -> dict[str, Any]:
    samples = {
        "female_lens_z": (z_female_thread(0.0, THREAD_LENGTH_MM, 0.0, 0.0), "z", THREAD_LENGTH_MM),
        "female_lens_x": (x_female_thread(0.0, THREAD_LENGTH_MM, 0.0, 0.0), "x", THREAD_LENGTH_MM),
        "male_lens_z": (
            z_male_thread(MALE_LENS_ROOT_MM, 0.0, THREAD_LENGTH_MM, 0.0, 0.0),
            "z",
            THREAD_LENGTH_MM,
        ),
        "male_lens_x": (
            x_male_thread(MALE_LENS_ROOT_MM, 0.0, THREAD_LENGTH_MM, 0.0, 0.0),
            "x",
            THREAD_LENGTH_MM,
        ),
        "male_camera_z": (
            z_male_thread(
                CAMERA_MALE_ROOT_MM,
                0.0,
                CAMERA_THREAD_LENGTH_MM,
                0.0,
                0.0,
                phase_shift=0.0,
            ),
            "z",
            CAMERA_THREAD_LENGTH_MM,
        ),
    }
    records: dict[str, dict[str, Any]] = {}
    for name, (shape, axis, expected_length) in samples.items():
        box = shape.val().BoundingBox()
        minimum = box.xmin if axis == "x" else box.zmin
        maximum = box.xmax if axis == "x" else box.zmax
        records[name] = {
            "axis": axis.upper(),
            "expected_bounds_mm": [0.0, expected_length],
            "measured_bounds_mm": [round(minimum, 9), round(maximum, 9)],
            "start_error_mm": round(abs(minimum), 9),
            "end_error_mm": round(abs(maximum - expected_length), 9),
            "clipped_to_parent_interval": (
                abs(minimum) <= BREP_BOUND_TOLERANCE_MM
                and abs(maximum - expected_length) <= BREP_BOUND_TOLERANCE_MM
            ),
        }
    return {
        "pitch_mm": PITCH_MM,
        "radial_tooth_height_mm": TOOTH_RADIAL_HEIGHT_MM,
        "construction_runout_mm": THREAD_RUNOUT_MM,
        "samples": records,
        "all_samples_clipped_to_parent_interval": all(
            record["clipped_to_parent_interval"] for record in records.values()
        ),
    }


def build_a_input_receiver_audit(
    a_cap: cq.Workplane,
    cap_info: dict[str, float],
) -> dict[str, Any]:
    expected, receiver_info = a_input_receiver_cavity(
        cap_info["input_receiver_flange_seat_mm"]
    )
    domain = z_cylinder(
        A_INPUT_RECEIVER_DOMAIN_DIAMETER_MM,
        receiver_info["min_mm"],
        receiver_info["depth_mm"],
        BS_X,
        BS_Y,
    )
    actual = largest_solid(domain.cut(a_cap).clean())
    missing_void = expected.val().cut(actual.val()).Volume()
    excess_void = actual.val().cut(expected.val()).Volume()
    smooth_pilot = z_cylinder(
        A_INPUT_RECEIVER_PILOT_DIAMETER_MM,
        receiver_info["min_mm"],
        receiver_info["depth_mm"],
        BS_X,
        BS_Y,
    )
    source_thread_relief = expected.val().cut(smooth_pilot.val()).Volume()
    return {
        "source_path": str(SOURCE_A_INPUT_RECEIVER),
        "flange_seat_mm": receiver_info["min_mm"],
        "receiver_depth_mm": receiver_info["depth_mm"],
        "pilot_diameter_mm": receiver_info["pilot_diameter_mm"],
        "groove_envelope_diameter_mm": receiver_info["groove_diameter_mm"],
        "source_cavity_volume_mm3": round(expected.val().Volume(), 9),
        "actual_cavity_volume_mm3": round(actual.val().Volume(), 9),
        "missing_source_void_mm3": round(missing_void, 9),
        "excess_void_mm3": round(excess_void, 9),
        "source_thread_relief_outside_smooth_pilot_mm3": round(
            source_thread_relief,
            9,
        ),
        "minimum_radial_wall_inside_lens_thread_root_mm": round(
            (MALE_LENS_ROOT_MM - A_INPUT_RECEIVER_GROOVE_DIAMETER_MM) / 2.0,
            6,
        ),
        "receiver_is_exact_source_brep": (
            missing_void <= 1e-5 and excess_void <= 1e-5
        ),
        "thread_relief_is_present": source_thread_relief > 1.0,
        "insertion_depth_is_internal_to_4f_arm": True,
    }


def build_dimensional_audit(
    spec: LensSpec,
    lens_info: dict[str, Any],
    arm_info: dict[str, dict[str, float]],
    cap_info: dict[str, dict[str, float]],
) -> dict[str, Any]:
    pocket = arm_info["A"]["pocket_mm"]
    aperture = arm_info["A"]["aperture_mm"]
    receiver_transition = (FEMALE_PIVOT_MM - pocket) / 2.0
    cap_transition_radial = (MALE_LENS_ROOT_MM - spec.diameter_mm) / 2.0
    cap_transition_angle = math.degrees(
        math.atan2(cap_transition_radial, receiver_transition)
    )
    inward_contact = float(lens_info["mechanical_inward_contact_z_mm"])
    outward_contact = float(lens_info["mechanical_outward_contact_z_mm"])
    lens_envelope = outward_contact - inward_contact
    if not math.isclose(
        lens_envelope,
        float(lens_info["holder_axial_envelope_mm"]),
        abs_tol=1e-6,
    ):
        raise RuntimeError(f"lens support envelope mismatch: {spec.key}")
    a_seat_to_end = arm_info["A"]["seat_mm"] - cap_info["A"]["outer_end_mm"]
    b_seat_to_end = cap_info["B"]["outer_end_mm"] - arm_info["B"]["seat_mm"]
    c_seat_to_end = cap_info["C"]["outer_end_mm"] - arm_info["C"]["seat_mm"]
    cavity_fit = {}
    for arm in ("A", "B", "C"):
        available = float(arm_info[arm]["available_lens_cavity_mm"])
        cavity_fit[arm] = {
            "inward_optical_vertex_mm": arm_info[arm]["optical_vertex_mm"],
            "holder_annular_support_mm": arm_info[arm]["seat_mm"],
            "cap_annular_support_mm": cap_info[arm]["contact_mm"],
            "mechanical_inward_support_offset_mm": inward_contact,
            "mechanical_outward_support_offset_mm": outward_contact,
            "lens_required_axial_envelope_mm": lens_envelope,
            "fully_inserted_available_cavity_mm": available,
            "fully_inserted_axial_clearance_mm": round(
                available - lens_envelope,
                6,
            ),
            "full_thread_engagement_mm": THREAD_LENGTH_MM,
        }

    return {
        "lens_fit": {
            "nominal_diameter_mm": spec.diameter_mm,
            "pocket_diameter_mm": pocket,
            "diametric_clearance_mm": round(pocket - spec.diameter_mm, 6),
            "radial_clearance_each_side_mm": round(
                (pocket - spec.diameter_mm) / 2.0,
                6,
            ),
            "clear_aperture_mm": aperture,
            "holder_support_land_radial_mm": round((pocket - aperture) / 2.0, 6),
            "cap_retainer_land_radial_mm": round(
                (spec.diameter_mm - aperture) / 2.0,
                6,
            ),
            "minimum_holder_wall_radial_mm": round(
                (CAP_OUTER_DIAMETER_MM - pocket) / 2.0,
                6,
            ),
            "retainer_tightening_travel_mm": AXIAL_LENS_CLEARANCE_MM,
            "mechanical_inward_support_offset_mm": inward_contact,
            "mechanical_outward_support_offset_mm": outward_contact,
            "mechanical_support_envelope_mm": round(lens_envelope, 6),
        },
        "fully_inserted_lens_cavities": cavity_fit,
        "receiver_chamfers": {
            "lens_pocket_to_female_pivot": {
                "from_diameter_mm": pocket,
                "to_diameter_mm": FEMALE_PIVOT_MM,
                "axial_length_mm": round(receiver_transition, 6),
                "angle_deg": 45.0,
            },
            "male_retainer_to_lens": {
                "from_diameter_mm": MALE_LENS_ROOT_MM,
                "to_diameter_mm": spec.diameter_mm,
                "axial_length_mm": round(receiver_transition, 6),
                "angle_deg": round(cap_transition_angle, 6),
            },
            "outer_mouth_to_thread": {
                "holder_angle_deg": 45.0,
                "cap_angle_deg": 45.0,
                "axial_length_mm": round(
                    (CAP_OUTER_DIAMETER_MM - FEMALE_PIVOT_MM) / 2.0,
                    6,
                ),
            },
        },
        "lens_retainer_thread_fit": {
            "pitch_mm": PITCH_MM,
            "radial_tooth_height_mm": TOOTH_RADIAL_HEIGHT_MM,
            "bounded_length_mm": THREAD_LENGTH_MM,
            "female_pivot_mm": FEMALE_PIVOT_MM,
            "female_groove_mm": FEMALE_GROOVE_MM,
            "male_root_mm": MALE_LENS_ROOT_MM,
            "male_crest_mm": round(
                MALE_LENS_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM,
                6,
            ),
            "root_radial_clearance_mm": round(
                (FEMALE_PIVOT_MM - MALE_LENS_ROOT_MM) / 2.0,
                6,
            ),
            "crest_radial_clearance_mm": round(
                (
                    FEMALE_GROOVE_MM
                    - (MALE_LENS_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM)
                )
                / 2.0,
                6,
            ),
            "construction_runout_mm": THREAD_RUNOUT_MM,
            "runout_clipped_to_parent_length": True,
        },
        "central_c_source_style_fit": {
            "female_pivot_mm": 29.6,
            "female_groove_mm": 30.4,
            "male_root_mm": LEGACY_MALE_ROOT_MM,
            "male_crest_mm": round(
                LEGACY_MALE_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM,
                6,
            ),
            "nominal_diametric_interference_mm": round(
                LEGACY_MALE_ROOT_MM - 29.6,
                6,
            ),
            "classification": (
                "preserved tight printed source interface, not a CAD clearance fit"
            ),
        },
        "camera_output_thread": {
            "root_mm": CAMERA_MALE_ROOT_MM,
            "crest_mm": round(
                CAMERA_MALE_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM,
                6,
            ),
            "pitch_mm": PITCH_MM,
            "bounded_length_mm": CAMERA_THREAD_LENGTH_MM,
            "classification": "source OpenHI printed C-mount-like profile",
            "standard_1in_32_major_mm": 25.4,
            "standard_1in_32_pitch_mm": 0.79375,
        },
        "a_input_receiver": {
            "classification": (
                "exact source OpenHI internal female receiver B-rep"
            ),
            "flange_seat_mm": cap_info["A"]["input_receiver_flange_seat_mm"],
            "receiver_min_mm": cap_info["A"]["input_receiver_min_mm"],
            "receiver_max_mm": cap_info["A"]["input_receiver_max_mm"],
            "receiver_depth_mm": cap_info["A"]["input_receiver_depth_mm"],
            "pilot_diameter_mm": cap_info["A"][
                "input_receiver_pilot_diameter_mm"
            ],
            "groove_diameter_mm": cap_info["A"][
                "input_receiver_groove_diameter_mm"
            ],
            "bore_transition_min_mm": cap_info["A"][
                "input_receiver_transition_min_mm"
            ],
            "bore_transition_max_mm": cap_info["A"][
                "input_receiver_transition_max_mm"
            ],
            "bore_transition_length_mm": cap_info["A"][
                "input_receiver_transition_length_mm"
            ],
            "bore_transition_angle_deg": (
                A_INPUT_RECEIVER_BORE_TRANSITION_ANGLE_DEG
            ),
            "insertion_depth_is_internal_to_optical_arm": True,
        },
        "optical_distance_chain": {
            "beam_splitter_to_inward_axis_vertex_mm": round(
                spec.focal_length_mm,
                6,
            ),
            "beam_splitter_to_outward_axis_vertex_mm": round(
                spec.focal_length_mm + spec.center_thickness_mm,
                6,
            ),
            "beam_splitter_to_annular_support_plane_mm": round(
                spec.focal_length_mm + inward_contact,
                6,
            ),
            "a_to_b_inward_vertex_spacing_2f_mm": round(
                arm_info["B"]["optical_vertex_mm"]
                - arm_info["A"]["optical_vertex_mm"],
                6,
            ),
            "a_to_c_inward_vertex_path_2f_mm": round(
                (BS_Z - arm_info["A"]["optical_vertex_mm"])
                + (arm_info["C"]["optical_vertex_mm"] - BS_X),
                6,
            ),
            "a_to_b_annular_support_spacing_mm": round(
                arm_info["B"]["seat_mm"] - arm_info["A"]["seat_mm"],
                6,
            ),
            "a_to_c_annular_support_path_mm": round(
                (BS_Z - arm_info["A"]["seat_mm"])
                + (arm_info["C"]["seat_mm"] - BS_X),
                6,
            ),
            "a_seat_to_outer_end_mm": round(a_seat_to_end, 6),
            "b_seat_to_outer_end_mm": round(b_seat_to_end, 6),
            "c_seat_to_outer_end_mm": round(c_seat_to_end, 6),
            "a_outer_end_to_beam_splitter_mm": round(
                BS_Z - cap_info["A"]["outer_end_mm"],
                6,
            ),
            "beam_splitter_to_b_outer_end_mm": round(
                cap_info["B"]["outer_end_mm"] - BS_Z,
                6,
            ),
            "beam_splitter_to_c_outer_end_mm": round(
                cap_info["C"]["outer_end_mm"] - BS_X,
                6,
            ),
            "a_to_b_complete_outer_end_path_mm": round(
                (BS_Z - cap_info["A"]["outer_end_mm"])
                + (cap_info["B"]["outer_end_mm"] - BS_Z),
                6,
            ),
            "a_to_c_complete_outer_end_path_mm": round(
                (BS_Z - cap_info["A"]["outer_end_mm"])
                + (cap_info["C"]["outer_end_mm"] - BS_X),
                6,
            ),
            "reference_plane_note": (
                "The inward optical-axis surface vertex is placed exactly one "
                "catalog EFL from the beam splitter. The annular holder seat is "
                "offset by the lens sag at its support radius, and the finite lens "
                "thickness is contained inside the fully inserted holder/cap "
                "cavity rather than added again to the 2f/4f arm distance. This "
                "surface vertex is not a certified thick-lens principal plane."
            ),
        },
    }


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
        print_shape, print_orientation = orient_for_print(name, shape)
        exporters.export(
            print_shape,
            str(stl),
            tolerance=0.035,
            angularTolerance=0.10,
        )
        sanitize_stl(stl, normalize_z=True)
        export_stl_as_3mf(stl, threemf, title=stem)
        mesh_validation = mesh_summary(stl)
        three_mf_validation = three_mf_summary(threemf)
        three_mf_validation["bounds_match_stl"] = bounds_match(
            mesh_validation["bounds_mm"],
            three_mf_validation["bounds_mm"],
        )
        outputs[name] = {
            "step": str(step.relative_to(ROOT)),
            "stl": str(stl.relative_to(ROOT)),
            "3mf": str(threemf.relative_to(ROOT)),
            "step_validation": step_summary(step),
            "mesh_validation": mesh_validation,
            "3mf_validation": three_mf_validation,
            "print_orientation": print_orientation,
            "sha256": {p.suffix.lstrip("."): sha256(p) for p in (step, stl, threemf)},
        }
    return outputs


def export_a_axis_inspection_sections(
    a_cap: cq.Workplane,
    a_holder: cq.Workplane,
    artifact_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Export non-printing half sections that expose the A receiver and lens seat."""

    inspection_dir = artifact_dir / "inspection"
    inspection_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, Any]] = {}
    for name, shape in {"A": a_cap, "A_C_BS": a_holder}.items():
        box = shape.val().BoundingBox()
        clip = (
            cq.Workplane("XY")
            .box(
                box.xlen + 4.0,
                BS_Y - box.ymin + 0.05,
                box.zlen + 4.0,
                centered=(True, False, False),
            )
            .translate(
                (
                    (box.xmin + box.xmax) / 2.0,
                    box.ymin - 0.05,
                    box.zmin - 2.0,
                )
            )
        )
        section = largest_solid(shape.intersect(clip).clean())
        step = inspection_dir / f"openhi_{name}_half_section.step"
        stl = inspection_dir / f"openhi_{name}_half_section.stl"
        exporters.export(section, str(step))
        exporters.export(
            section,
            str(stl),
            tolerance=0.025,
            angularTolerance=0.08,
        )
        sanitize_stl(stl)
        outputs[name] = {
            "step": str(step.relative_to(ROOT)),
            "stl": str(stl.relative_to(ROOT)),
            "step_validation": step_summary(step),
            "mesh_validation": mesh_summary(stl),
            "purpose": "visual inspection only; not a printable part",
        }
    return outputs


def write_readme(
    design_dir: Path,
    spec: LensSpec,
    lens_info: dict[str, Any],
    arm_info: dict[str, dict[str, float]],
    dimensional_audit: dict[str, Any],
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
- `artifacts/renders/openhi_4f_spatial_exploded.png`: spatial view with all mechanical parts, lenses, and beam splitter separated along their mating directions.
- `artifacts/renders/openhi_4f_print_parts_layout.png`: exact orientations used by the separate STL/3MF print files.
- `artifacts/renders/openhi_4f_a_input_receiver_section.png`: A-only half section proving the internal source receiver and lifted bore transition.
- `artifacts/renders/openhi_4f_a_lens_cavity_section.png`: A/A+C+BS half section with the installed lens B-rep at its checked optical datum.
- `runs/{PRINT_RELEASE_RUN_NAME}/`: checked one-object print files and the matching Nutstore handoff.

## Optical Layout

All three arms use the same `{spec.label}` lens. The beam-splitter center is the fixed datum `(255, 210, 600) mm`. The CAD places each inward optical-axis surface vertex exactly one catalog EFL from that datum: `{spec.focal_length_mm:.5f} mm`. Therefore the inward A-B and A-C surface-vertex paths are `2f = {2.0 * spec.focal_length_mm:.5f} mm` under the source OpenHI thin-lens convention.{bfl_note}

The optical vertex and the annular support seat are separate datums. At the support radius, this lens's inward surface is `{lens_info['mechanical_inward_contact_z_mm']:.6f} mm` from its axis vertex. Each holder seat is offset by that sag, while the matching A/B/C cap leaves the full `{lens_info['holder_axial_envelope_mm']:.6f} mm` support-to-support lens envelope plus `{AXIAL_LENS_CLEARANCE_MM:.2f} mm` tightening travel. Thus a fully inserted threaded pair captures the real finite lens without adding half or all of the lens thickness again to the `2f` or `4f` optical distance.

The complete physical A-to-B and A-to-C outer-end paths are both `{complete_end_path:.5f} mm = 4f + {END_TO_END_SEAT_ALLOWANCE_MM:.1f} mm`. The `4.6 mm` allowance is measured from the accepted ST018 assembly, not guessed: the A outer end contributes `f + {A_END_SEAT_EXTRA_MM:.1f} mm` and each output end contributes `f + {OUTPUT_END_SEAT_EXTRA_MM:.1f} mm`. Thread length overlaps its receiver and is not added again to this path.

For the plano-convex variants, all plane faces point inward toward the beam splitter, as requested. The manifest records the BFL-versus-EFL difference so a bench test can tune the final axial position rather than hiding a thick-lens assumption.

## Lens Fit

- nominal lens diameter: `{spec.diameter_mm:.3f} mm`;
- holder pocket: `{arm_info['A']['pocket_mm']:.3f} mm`;
- radial pocket clearance per side: `{dimensional_audit['lens_fit']['radial_clearance_each_side_mm']:.3f} mm`;
- clear aperture: `{arm_info['A']['aperture_mm']:.3f} mm`;
- holder/cap support lands: `{dimensional_audit['lens_fit']['holder_support_land_radial_mm']:.3f}/{dimensional_audit['lens_fit']['cap_retainer_land_radial_mm']:.3f} mm` radial;
- minimum holder wall beside the lens pocket: `{dimensional_audit['lens_fit']['minimum_holder_wall_radial_mm']:.3f} mm`;
- modeled mechanical edge thickness: `{lens_info['mechanical_edge_thickness_mm']:.3f} mm`;
- retaining axial envelope at the actual support radius: `{lens_info['holder_axial_envelope_mm']:.3f} mm`;
- retainer tightening travel: `{AXIAL_LENS_CLEARANCE_MM:.3f} mm`;
- female threads: `{FEMALE_PIVOT_MM:.1f}/{FEMALE_GROOVE_MM:.1f} mm`, pitch `{PITCH_MM:.1f} mm`, `{THREAD_LENGTH_MM:.2f} mm` bounded engagement;
- matching male lens threads: `{MALE_LENS_ROOT_MM:.1f}/{MALE_LENS_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM:.1f} mm` root/crest;
- root and crest radial thread clearance: `{dimensional_audit['lens_retainer_thread_fit']['root_radial_clearance_mm']:.3f}/{dimensional_audit['lens_retainer_thread_fit']['crest_radial_clearance_mm']:.3f} mm`;
- B optical axis: `X = {B_AXIS_X:.3f} mm`, intentionally `{B_AXIS_X - BS_X:.3f} mm` from the A/beam-splitter datum.

The central interface map is deliberately not uniform: the preserved A+C+BS side/C female remains `29.6/30.4 mm`; its lower/A female is `29.8/30.6 mm`; both regenerated B/C lens-side females are `29.8/30.6 mm`; and the Lens C holder beam-splitter-side male remains the unchanged source `29.8/30.6 mm` root/crest. The central C pair therefore has `0.2 mm` nominal diametric interference. It is a preserved tight printed source fit, not a zero-clearance CAD pair. The three newly regenerated lens-retainer pairs are the clearance fits.

The output thread also preserves the source OpenHI printed profile (`24.4 mm` root, `25.2 mm` crest, `0.8 mm` pitch). It is intentionally not relabeled as exact standard `1\"-32 UN` C-mount (`25.4 mm`, `0.79375 mm` pitch).

The A input end now preserves the exact internal female receiver cavity from the original `OpenHI_STEP/A.step`: `{A_INPUT_RECEIVER_DEPTH_MM:.3f} mm` insertion depth, `{A_INPUT_RECEIVER_PILOT_DIAMETER_MM:.1f} mm` pilot, and `{A_INPUT_RECEIVER_GROOVE_DIAMETER_MM:.1f} mm` groove envelope. Its mating flange seats at the A outer face. The entire receiver depth remains inside the A arm envelope, followed by a 45-degree transition to the lens clear aperture; it is not a second seat-height term in the focal chain.

The holder side supplies the flat locating shoulder. A/B/C retain from the opposite side. The 45-degree diameter transition is on the A/B/C-facing receiver side, preserving the original OpenHI design philosophy.

The A and C axes use the beam-splitter datum. The complete B chain, including holder bore, pocket, lens, retainer, and camera thread, preserves the accepted source axis at `X = {B_AXIS_X:.3f} mm`; it must not be recentered to `255 mm`.

The final validator probes a centered `{OPTICAL_CORE_PROBE_DIAMETER_MM:.1f} mm` cylinder through the complete A, B, and C mechanical paths. It also probes a `{C_RECEIVER_MEMBRANE_PROBE_DIAMETER_MM:.1f} mm` smooth core across the A+C+BS C receiver. All probes must have zero solid overlap. This explicitly prevents the earlier `0.10 mm` fusion membrane from returning at the C receiver.

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
    for subdir in ("parts", "inspection", "renders"):
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
    inward_contact = float(lens_info["mechanical_inward_contact_z_mm"])
    ac_bs, a_info = build_a_c_bs(spec, edge, inward_contact)
    b_holder, b_info = build_b_holder(spec, edge, inward_contact)
    c_holder, c_info = build_c_holder(spec, edge, inward_contact)
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
    inspection_outputs = export_a_axis_inspection_sections(
        caps["A"],
        ac_bs,
        artifact_dir,
    )

    lens_step = artifact_dir / f"{spec.key}_lens.step"
    lens_stl = artifact_dir / f"{spec.key}_lens.stl"
    lens_3mf = artifact_dir / f"{spec.key}_lens.3mf"
    exporters.export(lens, str(lens_step))
    lens_mesh_shape = fuse_source_solids(lens.val(), label=f"{spec.key} lens mesh")
    exporters.export(localize_for_print(lens_mesh_shape), str(lens_stl), tolerance=0.015, angularTolerance=0.05)
    sanitize_stl(lens_stl, normalize_z=True)
    export_stl_as_3mf(lens_stl, lens_3mf, title=f"{spec.key}_lens")
    lens_mesh_validation = mesh_summary(lens_stl)
    lens_three_mf_validation = three_mf_summary(lens_3mf)
    lens_three_mf_validation["bounds_match_stl"] = bounds_match(
        lens_mesh_validation["bounds_mm"],
        lens_three_mf_validation["bounds_mm"],
    )

    lens_a = place_lens(lens, a_info["optical_vertex_mm"], "A")
    lens_b = place_lens(lens, b_info["optical_vertex_mm"], "B")
    lens_c = place_lens(lens, c_info["optical_vertex_mm"], "C")
    lens_a_box = lens_a.val().BoundingBox()
    lens_b_box = lens_b.val().BoundingBox()
    lens_c_box = lens_c.val().BoundingBox()
    lens_axis_brep_audit = {
        "A": measure_lens_axis_interval(
            lens_a,
            spec,
            a_info["optical_vertex_mm"],
            "A",
        ),
        "B": measure_lens_axis_interval(
            lens_b,
            spec,
            b_info["optical_vertex_mm"],
            "B",
        ),
        "C": measure_lens_axis_interval(
            lens_c,
            spec,
            c_info["optical_vertex_mm"],
            "C",
        ),
    }
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
    source_c_holder_assembly = cq.importers.importStep(str(SOURCE_C_HOLDER)).val().moved(
        cq.Location(cq.Vector(-20.0, 0.0, 0.0))
    )
    source_b_holder_assembly = cq.importers.importStep(str(SOURCE_B_HOLDER)).val()
    source_a_c_bs_assembly = cq.importers.importStep(str(SOURCE_AC_BS)).val()
    central_mating_interference_mm3 = {
        "generated_a_c_bs_to_lens_b_holder": abs(
            ac_bs.val().intersect(b_holder.val()).Volume()
        ),
        "source_a_c_bs_to_lens_b_holder": abs(
            source_a_c_bs_assembly.intersect(source_b_holder_assembly).Volume()
        ),
        "generated_a_c_bs_to_lens_c_holder": abs(
            ac_bs.val().intersect(c_holder.val()).Volume()
        ),
        "source_a_c_bs_to_lens_c_holder": abs(
            source_a_c_bs_assembly.intersect(source_c_holder_assembly).Volume()
        ),
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
        "A_to_B_2f": abs(
            (b_info["optical_vertex_mm"] - a_info["optical_vertex_mm"])
            - 2.0 * spec.focal_length_mm
        ),
        "BS_to_A_f": abs(
            (BS_Z - a_info["optical_vertex_mm"]) - spec.focal_length_mm
        ),
        "BS_to_B_f": abs(
            (b_info["optical_vertex_mm"] - BS_Z) - spec.focal_length_mm
        ),
        "BS_to_C_f": abs(
            (c_info["optical_vertex_mm"] - BS_X) - spec.focal_length_mm
        ),
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
        "lens_measured_bbox_axis": abs(
            (lens_b_box.xmin + lens_b_box.xmax) / 2.0 - B_AXIS_X
        ),
    }
    complete_axis_chain_error_mm = {
        "A_holder_declared_x": abs(a_info["optical_axis_x_mm"] - BS_X),
        "A_holder_declared_y": abs(a_info["optical_axis_y_mm"] - BS_Y),
        "A_cap_declared_x": abs(cap_info["A"]["axis_x_mm"] - BS_X),
        "A_cap_declared_y": abs(cap_info["A"]["axis_y_mm"] - BS_Y),
        "A_lens_measured_x": abs(
            (lens_a_box.xmin + lens_a_box.xmax) / 2.0 - BS_X
        ),
        "A_lens_measured_y": abs(
            (lens_a_box.ymin + lens_a_box.ymax) / 2.0 - BS_Y
        ),
        "B_holder_declared_x": abs(b_info["optical_axis_x_mm"] - B_AXIS_X),
        "B_holder_declared_y": abs(b_info["optical_axis_y_mm"] - BS_Y),
        "B_cap_declared_x": abs(cap_info["B"]["axis_x_mm"] - B_AXIS_X),
        "B_cap_declared_y": abs(cap_info["B"]["axis_y_mm"] - BS_Y),
        "B_lens_measured_x": abs(
            (lens_b_box.xmin + lens_b_box.xmax) / 2.0 - B_AXIS_X
        ),
        "B_lens_measured_y": abs(
            (lens_b_box.ymin + lens_b_box.ymax) / 2.0 - BS_Y
        ),
        "C_holder_declared_y": abs(c_info["optical_axis_y_mm"] - BS_Y),
        "C_holder_declared_z": abs(c_info["optical_axis_z_mm"] - BS_Z),
        "C_cap_declared_y": abs(cap_info["C"]["axis_y_mm"] - BS_Y),
        "C_cap_declared_z": abs(cap_info["C"]["axis_z_mm"] - BS_Z),
        "C_lens_measured_y": abs(
            (lens_c_box.ymin + lens_c_box.ymax) / 2.0 - BS_Y
        ),
        "C_lens_measured_z": abs(
            (lens_c_box.zmin + lens_c_box.zmax) / 2.0 - BS_Z
        ),
    }
    optical_path_audit = build_optical_path_audit(parts, cap_info)
    thread_construction_audit = build_thread_construction_audit()
    dimensional_audit = build_dimensional_audit(spec, lens_info, arm_info, cap_info)
    a_input_receiver_audit = build_a_input_receiver_audit(caps["A"], cap_info["A"])
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
        "a_inward_optical_vertex_z_mm": a_info["optical_vertex_mm"],
        "b_inward_optical_vertex_z_mm": b_info["optical_vertex_mm"],
        "c_inward_optical_vertex_x_mm": c_info["optical_vertex_mm"],
        "a_holder_annular_support_plane_z_mm": a_info["seat_mm"],
        "b_holder_annular_support_plane_z_mm": b_info["seat_mm"],
        "c_holder_annular_support_plane_x_mm": c_info["seat_mm"],
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
            "Catalog EFL is applied to the inward optical-axis surface vertex. "
            "The annular mechanical support plane is derived separately from "
            "the actual lens sag at the support radius. Manufacturer BFL is "
            "retained as a physical tuning datum for thick plano-convex lenses."
        ),
        "lens_to_mechanical_interference_mm3": {
            key: round(value, 9) for key, value in lens_interference_mm3.items()
        },
        "mating_part_interference_mm3": {
            key: round(value, 9) for key, value in mating_interference_mm3.items()
        },
        "central_source_style_mating_interference_mm3": {
            key: round(value, 9)
            for key, value in central_mating_interference_mm3.items()
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
        "complete_axis_chain_error_mm": {
            key: round(value, 9)
            for key, value in complete_axis_chain_error_mm.items()
        },
        "mechanical_optical_path_audit": optical_path_audit,
        "plano_face_orientation": {
            "A": "plane face points +Z toward beam splitter",
            "B": "plane face points -Z toward beam splitter",
            "C": "plane face points -X toward beam splitter",
        }
        if spec.kind == "plano_convex"
        else None,
        "lens_axis_brep_audit": lens_axis_brep_audit,
        "source_st018_focal_length_mm": SOURCE_FOCAL_LENGTH_MM,
        "end_to_end_seat_allowance_mm": END_TO_END_SEAT_ALLOWANCE_MM,
        "expected_end_path_4f_plus_seat_mm": round(expected_end_path_mm, 9),
        "measured_end_path_mm": {key: round(value, 9) for key, value in end_path_mm.items()},
        "end_path_error_mm": {key: round(value, 9) for key, value in end_path_error_mm.items()},
    }
    checks = {
        "all_part_steps_valid": all(
            row["step_validation"]["occt_valid"] for row in part_outputs.values()
        ),
        "all_part_steps_are_single_solids": all(
            row["step_validation"]["solid_count"] == 1
            for row in part_outputs.values()
        ),
        "a_axis_inspection_sections_are_valid": all(
            row["step_validation"]["occt_valid"]
            and row["step_validation"]["solid_count"] == 1
            and row["mesh_validation"]["watertight"]
            for row in inspection_outputs.values()
        ),
        "all_part_meshes_watertight": all(
            row["mesh_validation"]["watertight"]
            for row in part_outputs.values()
        ),
        "all_part_meshes_cross_first_layer_from_z0": all(
            abs(row["mesh_validation"]["minimum_z_mm"]) <= 1e-5
            and row["mesh_validation"]["first_layer_triangle_count"] > 0
            for row in part_outputs.values()
        ),
        "all_part_3mfs_are_single_watertight_objects": all(
            row["3mf_validation"]["unit"] == "millimeter"
            and row["3mf_validation"]["mesh_object_count"] == 1
            and row["3mf_validation"]["build_item_count"] == 1
            and row["3mf_validation"]["build_items_reference_mesh_objects"]
            and row["3mf_validation"]["components"] == 1
            and row["3mf_validation"]["indices_valid"]
            and row["3mf_validation"]["watertight"]
            and row["3mf_validation"]["winding_consistent"]
            and row["3mf_validation"]["bounds_match_stl"]
            and abs(row["3mf_validation"]["minimum_z_mm"]) <= 1e-5
            and row["3mf_validation"]["first_layer_triangle_count"] > 0
            for row in part_outputs.values()
        ),
        "lens_step_valid": step_summary(lens_step)["occt_valid"],
        "lens_mesh_watertight": lens_mesh_validation["watertight"],
        "lens_3mf_is_single_watertight_object": (
            lens_three_mf_validation["unit"] == "millimeter"
            and lens_three_mf_validation["mesh_object_count"] == 1
            and lens_three_mf_validation["build_item_count"] == 1
            and lens_three_mf_validation["build_items_reference_mesh_objects"]
            and lens_three_mf_validation["components"] == 1
            and lens_three_mf_validation["indices_valid"]
            and lens_three_mf_validation["watertight"]
            and lens_three_mf_validation["winding_consistent"]
            and lens_three_mf_validation["bounds_match_stl"]
        ),
        "assembly_step_valid": step_summary(assembly_step)["occt_valid"],
        "three_identical_lens_copies": True,
        "placed_lens_brep_vertices_match_focal_datums": all(
            audit["inward_vertex_error_mm"] <= 1e-7
            and audit["outward_vertex_error_mm"] <= 1e-7
            for audit in lens_axis_brep_audit.values()
        ),
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
        "all_lens_holder_cap_axes_are_centered": (
            max(complete_axis_chain_error_mm.values()) <= 1e-8
        ),
        "all_three_mechanical_optical_cores_are_clear": all(
            path["total_overlap_mm3"] <= 1e-6
            for path in optical_path_audit["paths"].values()
        ),
        "central_c_receiver_has_no_membrane": (
            optical_path_audit["c_receiver_membrane_probe"][
                "generated_a_c_bs_overlap_mm3"
            ]
            <= 1e-6
            and optical_path_audit["c_receiver_membrane_probe"][
                "source_a_c_bs_overlap_mm3"
            ]
            <= 1e-6
        ),
        "thread_construction_is_bounded_to_parent_intervals": (
            thread_construction_audit[
                "all_samples_clipped_to_parent_interval"
            ]
        ),
        "lens_model_uses_analytic_optical_surfaces": bool(
            lens_info.get("analytic_spherical_faces")
        ),
        "lens_radial_clearance_is_positive": (
            dimensional_audit["lens_fit"]["radial_clearance_each_side_mm"] > 0.0
        ),
        "lens_support_lands_are_at_least_0p7mm": min(
            dimensional_audit["lens_fit"]["holder_support_land_radial_mm"],
            dimensional_audit["lens_fit"]["cap_retainer_land_radial_mm"],
        ) >= 0.7,
        "receiver_chamfers_are_manufacturable": (
            44.5
            <= dimensional_audit["receiver_chamfers"]["male_retainer_to_lens"][
                "angle_deg"
            ]
            <= 45.5
        ),
        "lens_retainer_threads_have_0p1mm_radial_clearance": math.isclose(
            dimensional_audit["lens_retainer_thread_fit"]["root_radial_clearance_mm"],
            0.1,
            abs_tol=1e-9,
        ) and math.isclose(
            dimensional_audit["lens_retainer_thread_fit"]["crest_radial_clearance_mm"],
            0.1,
            abs_tol=1e-9,
        ),
        "central_source_style_fit_matches_reference": (
            abs(
                central_mating_interference_mm3[
                    "generated_a_c_bs_to_lens_c_holder"
                ]
                - central_mating_interference_mm3[
                    "source_a_c_bs_to_lens_c_holder"
                ]
            )
            <= 0.5
            and central_mating_interference_mm3[
                "generated_a_c_bs_to_lens_b_holder"
            ]
            <= 0.01
        ),
        "a_input_receiver_exact_source_brep_is_preserved": bool(
            a_input_receiver_audit["receiver_is_exact_source_brep"]
        ),
        "a_input_receiver_thread_relief_is_present": bool(
            a_input_receiver_audit["thread_relief_is_present"]
        ),
        "a_input_receiver_has_structural_wall": (
            a_input_receiver_audit[
                "minimum_radial_wall_inside_lens_thread_root_mm"
            ]
            >= 1.5
        ),
        "all_fully_inserted_lens_cavities_have_0p2mm_axial_clearance": all(
            math.isclose(
                cavity["fully_inserted_axial_clearance_mm"],
                AXIAL_LENS_CLEARANCE_MM,
                abs_tol=1e-6,
            )
            for cavity in dimensional_audit[
                "fully_inserted_lens_cavities"
            ].values()
        ),
    }
    manifest = {
        "design": design_dir.name,
        "lens": asdict(spec),
        "lens_model": lens_info,
        "optical_layout": optical,
        "final_dimensional_audit": dimensional_audit,
        "a_input_receiver_audit": a_input_receiver_audit,
        "thread_construction_audit": thread_construction_audit,
        "arms": {"A": a_info, "B": b_info, "C": c_info},
        "caps": cap_info,
        "thread_interfaces": {
            "a_input_internal_female": {
                "pilot_mm": A_INPUT_RECEIVER_PILOT_DIAMETER_MM,
                "groove_mm": A_INPUT_RECEIVER_GROOVE_DIAMETER_MM,
                "depth_mm": A_INPUT_RECEIVER_DEPTH_MM,
                "status": "exact source B-rep preserved",
            },
            "a_c_bs_lower_a_female": {
                "pivot_mm": FEMALE_PIVOT_MM,
                "groove_mm": FEMALE_GROOVE_MM,
                "status": "regenerated",
            },
            "a_c_bs_side_c_female": {
                "pivot_mm": 29.6,
                "groove_mm": 30.4,
                "status": "preserved source interface",
            },
            "lens_b_holder_lens_side_female": {
                "pivot_mm": FEMALE_PIVOT_MM,
                "groove_mm": FEMALE_GROOVE_MM,
                "status": "regenerated",
            },
            "lens_c_holder_lens_side_female": {
                "pivot_mm": FEMALE_PIVOT_MM,
                "groove_mm": FEMALE_GROOVE_MM,
                "status": "regenerated",
            },
            "lens_c_holder_beam_splitter_side_male": {
                "root_mm": LEGACY_MALE_ROOT_MM,
                "crest_mm": round(
                    LEGACY_MALE_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM,
                    6,
                ),
                "status": "preserved source interface",
            },
            "a_b_c_lens_retainer_males": {
                "root_mm": MALE_LENS_ROOT_MM,
                "crest_mm": round(
                    MALE_LENS_ROOT_MM + 2.0 * TOOTH_RADIAL_HEIGHT_MM,
                    6,
                ),
                "status": "regenerated",
            },
        },
        "source_files": {
            path.name: {"path": str(path), "sha256": sha256(path)}
            for path in (
                SOURCE_A,
                SOURCE_A_INPUT_RECEIVER,
                SOURCE_B,
                SOURCE_C,
                SOURCE_AC_BS,
                SOURCE_B_HOLDER,
                SOURCE_C_HOLDER,
                SOURCE_SHAPR,
            )
            if path.exists()
        },
        "lens_source_evidence": source_evidence(
            GLA_SOURCE_ROOT if spec.key.startswith("gla11") else JH_SOURCE_ROOT
        ),
        "parts": part_outputs,
        "inspection_sections": inspection_outputs,
        "lens_outputs": {
            "step": str(lens_step.relative_to(ROOT)),
            "stl": str(lens_stl.relative_to(ROOT)),
            "3mf": str(lens_3mf.relative_to(ROOT)),
            "step_validation": step_summary(lens_step),
            "mesh_validation": lens_mesh_validation,
            "3mf_validation": lens_three_mf_validation,
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
    write_readme(
        design_dir,
        spec,
        lens_info,
        {"A": a_info, "B": b_info, "C": c_info},
        dimensional_audit,
    )

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

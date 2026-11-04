#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a light-duty hollow rotary-stage prototype around the owner's motor.

The GT2 rounded-groove construction adapts Chris Palmer's NopSCADlib
vitamins/pulley.scad (2018), GPL-3.0-or-later. See README and LICENSE.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

import cadquery as cq
import trimesh
from OCP.BRepTools import BRepTools
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402

MOTOR = ROOT / "cad/extracted/OpenHI_STEP/42 stepper FH PLP.step.step"
SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
P = {
    "clear_bore_mm": 30.0,
    "tray_underside_z_mm": 85.0,
    "lowest_rotating_cup_z_mm": 79.0,
    "stationary_carrier_underside_z_mm": 75.0,
    "output_top_z_mm": 98.5,
    "motor_front_z_mm": 80.0,
    "motor_body_mm": [42.0, 42.0, 40.0],
    "motor_hole_pitch_mm": 31.0,
    "motor_boss_diameter_mm": 22.0,
    "motor_boss_height_mm": 2.0,
    "motor_shaft_diameter_mm": 5.0,
    "motor_shaft_length_from_face_mm": 22.0,
    "motor_body_clearance_each_side_mm": 0.2,
    "motor_boss_clearance_diametral_mm": 0.4,
    "motor_tension_travel_each_way_mm": 3.0,
    "motor_screw_counterbore_floor_z_mm": 82.0,
    "motor_screw_head_top_z_mm": 86.0,
    "motor_screw_length_mm": 6.0,
    "motor_washer_total_thickness_mm": 1.0,
    "bearing": "6808-ZZ",
    "bearing_id_mm": 40.0,
    "bearing_od_mm": 52.0,
    "bearing_width_mm": 7.0,
    "fixed_inner_journal_mm": 39.9,
    "rotor_bearing_seat_mm": 52.1,
    "inner_race_shoulder_od_mm": 42.0,
    "outer_race_shoulder_id_mm": 49.8,
    "bearing_bottom_z_mm": 81.0,
    "bearing_top_z_mm": 88.0,
    "belt_pitch_mm": 2.0,
    "belt_width_mm": 6.0,
    "belt_length_mm": 320.0,
    "motor_teeth": 20,
    "rotor_teeth": 120,
    "belt_midplane_z_mm": 89.75,
    "rotor_tooth_channel_width_mm": 7.5,
    "GT2_pitch_to_crest_radial_mm": 0.254,
    "GT2_tooth_height_mm": 0.75,
    "GT2_groove_radius_mm": 0.555,
    "rotor_cap_od_mm": 82.0,
    "accessory_hole_square_mm": 30.0,
    "accessory_screw_max_insertion_mm": 6.0,
    "breadboard_grid_mm": 25.0,
    "breadboard_hole_clearance_mm": 6.4,
    "breadboard_screw_centers_mm": [[75, -25], [100, -25], [75, 25], [100, 25]],
    "stand_mounts_mm": [[64, -34], [104, -34], [64, 34], [104, 34]],
    "stand_foot_bounds_mm": [58, -42, 118, 42],
    "stand_top_z_mm": 75.0,
    "polarizer_nominal_diameter_mm": 25.4,
    "polarizer_seat_diameter_mm": 25.7,
    "polarizer_seat_depth_mm": 1.0,
    "polarizer_insert_clear_aperture_mm": 24.0,
    "polarizer_pilot_mm": 29.8,
    "generic_insertion_clearance_diametral_mm": 0.2,
    "ears_thickness_mm": 1.0,
    "ear_pad_diameter_mm": 16.0,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cyl(d, z0, h, x=0, y=0):
    return cq.Workplane("XY", origin=(x, y, z0)).circle(d / 2).extrude(h)


def ring(od, id, z0, h):
    return (
        cq.Workplane("XY", origin=(0, 0, z0)).circle(od / 2).circle(id / 2).extrude(h)
    )


def box(x0, x1, y0, y1, z0, z1):
    return (
        cq.Workplane("XY")
        .box(x1 - x0, y1 - y0, z1 - z0)
        .translate(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    )


def slot(d, travel, x, y, z0, h):
    return cq.Workplane("XY", origin=(x, y, z0)).slot2D(d + travel, d, 0).extrude(h)


def hex_prism(af, x, y, z, h, angle=0):
    # A flat, not a vertex, faces the radial optical opening.
    s = cq.Workplane("XY").polygon(6, af / math.cos(math.pi / 6)).extrude(h)
    return s.rotate((0, 0, 0), (0, 0, 1), 30 + angle).translate((x, y, z))


def polar_xy(radius, angle):
    a = math.radians(angle)
    return radius * math.cos(a), radius * math.sin(a)


def volume(shape):
    return sum(s.Volume(1e-8) for s in shape.solids().vals())


def valid(shape):
    for s in shape.vals():
        BRepTools.Clean_s(s.wrapped)
    return all(s.isValid() for s in shape.vals())


def exact_bounds(shape):
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.val().wrapped, bounds, False, False)
    return bounds.Get()


def center_distance():
    R, r = (
        P[key] * P["belt_pitch_mm"] / (2 * math.pi)
        for key in ("rotor_teeth", "motor_teeth")
    )

    def length(c):
        return (
            2 * math.sqrt(c * c - (R - r) ** 2)
            + math.pi * (R + r)
            + 2 * (R - r) * math.asin((R - r) / c)
        )

    lo, hi = 60.0, 110.0
    for _ in range(64):
        c = (lo + hi) / 2
        if length(c) < P["belt_length_mm"]:
            lo = c
        else:
            hi = c
    return c, length(c), R, r


def gt2_blank(teeth, id, z0, h):
    # Rounded GT2 grooves adapted from NopSCADlib; no globally scaled teeth.
    outer = (
        teeth * P["belt_pitch_mm"] / (2 * math.pi) - P["GT2_pitch_to_crest_radial_mm"]
    )
    r = P["GT2_groove_radius_mm"]
    q = outer - P["GT2_tooth_height_mm"] + r
    cutter = (
        cq.Workplane("XY", origin=(0, 0, z0 - 0.05))
        .moveTo(-r, q + 3)
        .lineTo(-r, q)
        .threePointArc((0, q - r), (r, q))
        .lineTo(r, q + 3)
        .close()
        .extrude(h + 0.1)
    )
    tools = cq.Compound.makeCompound(
        [
            cutter.val().rotate((0, 0, 0), (0, 0, 1), i * 360 / teeth)
            for i in range(teeth)
        ]
    )
    return ring(2 * outer, id, z0, h).cut(cq.Workplane(obj=tools))


def motor_reference():
    candidates = [
        (shape.moved(loc), label)
        for shape, label, loc, _ in cq.Assembly.load(str(MOTOR))
        if label.rsplit("/", 1)[-1] == "42 stepper motor"
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Exact named motor was not isolated from the mixed source assembly"
        )
    source, label = candidates[0]
    shape = cq.Workplane(obj=source.translate((-261, -114.5, -61.5)))
    bb = shape.val().BoundingBox()
    if (
        max(
            abs(a - b)
            for a, b in zip(
                (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax),
                (-21, 21, -21, 21, -40, 22),
            )
        )
        > 1e-4
    ):
        raise RuntimeError("Saved motor geometry does not match the inspected datums")
    return shape, label


def carrier(c):
    s = cyl(90, 75, 8).union(box(0, 116, -43, 43, 75, 83))
    s = (
        s.cut(cyl(80, 78, 6))
        .union(ring(42, 30, 75, 6))
        .union(ring(P["fixed_inner_journal_mm"], 30, 81, 7))
    )
    s = s.cut(cyl(30, 74, 16))
    # Clear the bought bearing's corner radius without increasing its fitted journal.
    s = s.cut(ring(40.4, 39.4, 80.7, 0.6))
    # Raised motor roof keeps the saved 22 mm shaft long enough for an inverted pulley.
    s = s.cut(box(c - 24.2, c + 24.2, -21.2, 21.2, 74, 80))
    s = s.union(box(c - 26, c + 26, -29, 29, 80, 84))
    s = s.cut(slot(22.4, 6, c, 0, 79.9, 4.2))
    for dx in (-15.5, 15.5):
        for y in (-15.5, 15.5):
            s = s.cut(slot(3.4, 6, c + dx, y, 79.8, 4.4))
            s = s.cut(slot(7.4, 6, c + dx, y, 82, 2.2))
    for x, y in P["stand_mounts_mm"]:
        s = s.cut(cyl(4.5, 74, 11, x, y))
    for a in (0, 120, 240):
        x, y = polar_xy(17.5, a)
        s = s.cut(cyl(2.3, 74, 16, x, y)).cut(hex_prism(4.2, x, y, 74.9, 2.9, a))
    return s


def rotor_cup():
    seat = P["rotor_bearing_seat_mm"]
    s = ring(58, 49.8, 79, 2).union(ring(58, seat, 81, 7))
    s = s.union(ring(80, seat, P["tray_underside_z_mm"], 1)).union(
        gt2_blank(120, seat, 86, 7.5)
    )
    s = s.cut(cyl(54.2, 88, 6))
    s = s.cut(ring(52.6, 51.4, 80.7, 0.6))
    for a in (0, 120, 240):
        x, y = polar_xy(32, a)
        s = s.cut(cyl(3.4, 78.9, 16, x, y)).cut(hex_prism(5.8, x, y, 84.4, 5.6, a))
    return s


def rotor_cap():
    s = ring(82, 30, 93.5, 5).union(ring(54, 49.8, 88, 5.5))
    for a in (0, 120, 240):
        x, y = polar_xy(32, a)
        s = s.cut(cyl(3.4, 93.4, 5.3, x, y))
        cone = cq.Solid.makeCone(1.7, 3.2, 1.8, cq.Vector(x, y, 96.7))
        s = s.cut(cq.Workplane(obj=cone))
    for x in (-15, 15):
        for y in (-15, 15):
            s = s.cut(cyl(3.3, 93.4, 5.3, x, y)).cut(hex_prism(5.8, x, y, 93.4, 2.5))
    return s


def inner_retainer():
    s = ring(42, 30, 88, 1.5)
    for a in (0, 120, 240):
        x, y = polar_xy(17.5, a)
        s = s.cut(cyl(2.3, 87.9, 1.7, x, y))
    return s


def stand():
    s = box(58, 118, -42, 42, 0, 8).edges("|Z").fillet(3)
    for sign in (-1, 1):
        y0, y1 = sorted((sign * 32, sign * 38))
        s = s.union(box(60, 114, y0, y1, 8, 75))
    s = s.union(box(106, 114, -32, 32, 8, 20))
    for x, y in P["stand_mounts_mm"]:
        s = s.union(cyl(12, 55, 20, x, y))
        taper = cq.Solid.makeCone(6 / 2, 12 / 2, 10, cq.Vector(x, y, 45))
        s = s.union(cq.Workplane(obj=taper)).cut(cyl(4.5, 65, 11, x, y))
        s = s.cut(hex_prism(7.3, x, y, 69, 3.7))
        s = s.cut(
            box(
                x - 4.2,
                x + 4.2,
                min(y, y - math.copysign(12, y)),
                max(y, y - math.copysign(12, y)),
                69,
                72.7,
            )
        )
    for x, y in P["breadboard_screw_centers_mm"]:
        s = s.cut(slot(6.4, 8, x, y, -0.2, 8.4))
    return s


def shim(c):
    s = box(58, 114, -40, 40, 75, 80).cut(box(57, c + 25.2, -22.2, 22.2, 74, 81))
    for x, y in P["stand_mounts_mm"]:
        s = s.cut(cyl(4.5, 74, 7, x, y))
    return s


def polarizer_parts():
    s = box(-21, 21, -21, 21, 98.5, 101.5).edges("|Z").fillet(1)
    s = (
        s.union(ring(29.8, 24, 96.5, 2))
        .cut(cyl(24, 96.4, 5.3))
        .cut(cyl(25.7, 100.5, 1.2))
    )
    top = ring(35.5, 24, 101.5, 2)
    for x in (-15, 15):
        for y in (-15, 15):
            s = s.cut(cyl(3.4, 98.4, 3.3, x, y))
    for a in (0, 120, 240):
        x, y = polar_xy(16, a)
        s = s.cut(cyl(2.3, 98.4, 3.3, x, y)).cut(hex_prism(4.2, x, y, 98.4, 1.7, a))
        top = top.cut(cyl(2.3, 101.4, 2.2, x, y))
    return s, top


def belt(c, R, r):
    def hull(delta):
        A, B = R + delta, r + delta
        angle = math.acos((R - r) / c)
        x, y = math.cos(angle), math.sin(angle)
        return (
            cq.Workplane("XY", origin=(0, 0, 86.75))
            .moveTo(A * x, A * y)
            .lineTo(c + B * x, B * y)
            .threePointArc((c + B, 0), (c + B * x, -B * y))
            .lineTo(A * x, -A * y)
            .threePointArc((-A, 0), (A * x, A * y))
            .close()
            .extrude(6)
        )

    return hull(0.376).cut(hull(-0.254))


def drive_pulley(c):
    # NopSCADlib GT2x20ob envelope, inverted: 1 + 7.5 + 1 + 5.5 mm.
    s = ring(16, 5, 85, 1).union(gt2_blank(20, 5, 86, 7.5))
    s = s.union(ring(16, 5, 93.5, 1)).union(ring(16, 5, 94.5, 5.5))
    return s.translate((c, 0, 0))


def hardware_references(c):
    parts = {}
    for dx in (-15.5, 15.5):
        for y in (-15.5, 15.5):
            x = c + dx
            stem = f"motor_screw_{dx}_{y}".replace("-", "minus").replace(".", "p")
            parts[stem] = (cyl(3, 77, 6, x, y).union(cyl(5.5, 83, 3, x, y)), "metal")
            parts[stem + "_washer"] = (
                cyl(7, 82, 1, x, y).cut(cyl(3.2, 81.9, 1.2, x, y)),
                "metal",
            )
    for a in (0, 120, 240):
        x, y = polar_xy(17.5, a)
        parts[f"fixed_M2_head_{a}"] = (cyl(3.8, 89.5, 2, x, y), "metal")
    return parts


def print_export(shape, run, name, invert=False, ears=False):
    if invert:
        shape = shape.rotate((0, 0, 0), (1, 0, 0), 180)
    xmin, ymin, zmin, xmax, ymax, _ = exact_bounds(shape)
    shape = shape.translate((-(xmin + xmax) / 2, -(ymin + ymax) / 2, -zmin))
    if ears:
        # Ear anchors use the nominal part's coordinates, so add before XY centering below.
        b = shape.val().BoundingBox()
        for dx in (-1, 1):
            for dy in (-1, 1):
                if name == "carrier":
                    x, y = (
                        (-b.xlen / 2 + 8 if dx < 0 else b.xlen / 2 - 4),
                        dy * (20 if dx < 0 else 38),
                    )
                else:
                    x, y = dx * (b.xlen / 2 - 4), dy * (b.ylen / 2 - 4)
                shape = shape.union(cyl(16, 0, 1, x + dx * 8, y + dy * 8))
                shape = shape.union(
                    box(
                        min(x, x + dx * 8) - 2.5,
                        max(x, x + dx * 8) + 2.5,
                        min(y, y + dy * 8) - 2.5,
                        max(y, y + dy * 8) + 2.5,
                        0,
                        1,
                    )
                )
    folder = run / "print" / name
    folder.mkdir(parents=True, exist_ok=True)
    stem = "PRINT_THIS_" + name
    cq.exporters.export(shape, str(folder / (stem + ".step")))
    cq.exporters.export(
        shape, str(folder / (stem + ".stl")), tolerance=0.025, angularTolerance=0.1
    )
    export_stl_as_3mf(folder / (stem + ".stl"), folder / (stem + ".3mf"), title=stem)
    mesh = trimesh.load_mesh(folder / (stem + ".stl"), force="mesh")
    back = cq.importers.importStep(str(folder / (stem + ".step")))
    with zipfile.ZipFile(folder / (stem + ".3mf")) as archive:
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    items = model.findall("m:build/m:item", ns)
    check = {
        "step_valid": valid(back),
        "solids": len(back.solids().vals()),
        "watertight": mesh.is_watertight,
        "mesh_components": len(mesh.split(only_watertight=False)),
        "min_z_mm": float(mesh.bounds[0, 2]),
        "first_layer_nonempty": mesh.section(
            plane_origin=(0, 0, 0.2), plane_normal=(0, 0, 1)
        )
        is not None,
        "3mf_build_items": len(items),
        "3mf_units": model.attrib["unit"],
        "invert_180": invert,
        "ears": ears,
        "stem": str((folder / stem).relative_to(run)),
        "bounds_mm": mesh.bounds.tolist(),
    }
    if not (
        check["step_valid"]
        and check["solids"] == 1
        and check["watertight"]
        and check["mesh_components"] == 1
        and abs(check["min_z_mm"]) < 1e-5
        and check["first_layer_nonempty"]
        and len(items) == 1
        and model.attrib["unit"] == "millimeter"
    ):
        raise RuntimeError(f"Invalid print part: {name}: {check}")
    return check


def fit_coupons():
    parts = {}
    for d in (52.0, 52.1, 52.2):
        parts[f"bearing_bore_{str(d).replace('.', 'p')}"] = ring(58, d, 0, 7)
    for d in (39.8, 39.9, 40.0):
        parts[f"bearing_journal_{str(d).replace('.', 'p')}"] = ring(44, 30, 0, 1).union(
            ring(d, 30, 1, 7)
        )
    parts["GT2_120T_belt_fit"] = gt2_blank(120, 68, 0, 7.5)
    return parts


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    old = list((DESIGN / "runs").glob("run-*"))
    number = max((int(p.name.split("-")[1]) for p in old), default=0) + 1
    run = (
        DESIGN
        / "runs"
        / f"run-{number}-common-carrier-30mm-bore-85mm-datum-prototype-{stamp}"
    )
    run.mkdir(parents=True)
    c, length, R, r = center_distance()
    motor, label = motor_reference()
    cq.exporters.export(motor, str(run / "OpenHI_NEMA17_exact_reference.step"))
    insert, retainer = polarizer_parts()
    printable = {
        "carrier": carrier(c),
        "rotor_cup": rotor_cup(),
        "rotor_cap": rotor_cap(),
        "inner_race_retainer": inner_retainer(),
        "footed_stand": stand(),
        "height_shim_5mm": shim(c),
        "polarizer_insert": insert,
        "polarizer_retainer": retainer,
    }
    parts = {
        **{
            name: (
                shape,
                "polymer_mid" if name in ("carrier", "footed_stand") else "polymer",
            )
            for name, shape in printable.items()
            if name != "height_shim_5mm"
        },
        "motor_OpenHI_exact": (motor.translate((c, 0, 80)), "metal"),
        "bearing_inner_reference": (ring(42, 40, 81, 7), "metal"),
        "bearing_outer_reference": (ring(52, 49.8, 81, 7), "metal"),
        "bearing_shield_reference": (ring(49.8, 42, 81.3, 6.4), "metal"),
        "belt_backing_reference": (belt(c, R, r), "belt"),
        "purchased_20T_pulley_reference": (drive_pulley(c), "metal"),
        "polarizer_1mm_reference": (cyl(25.4, 100.5, 1), "glass"),
    }
    parts.update(hardware_references(c))
    checks = {
        "center_distance_mm": c,
        "belt_pitch_length_mm": length,
        "small_pulley_wrap_deg": math.degrees(math.pi - 2 * math.asin((R - r) / c)),
        "ratio": 6,
        "full_step_command_deg": 1.8 / 6,
        "sixteen_microstep_command_deg": 1.8 / 6 / 16,
    }
    checks["motor_tension_extremes_vs_carrier_mm3"] = {}
    for shift in (-3, 0, 3):
        v = volume(
            parts["motor_OpenHI_exact"][0]
            .translate((shift, 0, 0))
            .intersect(printable["carrier"])
        )
        checks["motor_tension_extremes_vs_carrier_mm3"][str(shift)] = v
        if v > 1e-5:
            raise RuntimeError(f"Motor does not fit at tension shift {shift}: {v}")
    bore = cyl(30, -1, 101)
    checks["empty_stage_bore_obstruction_mm3"] = sum(
        volume(s.intersect(bore))
        for n, (s, _) in parts.items()
        if not n.startswith("polarizer_")
    )
    # Bearing contact is intentional; other moving-vs-fixed solids must remain disjoint.
    checks["moving_vs_fixed_intersections_mm3"] = {}
    for name in ("rotor_cup", "rotor_cap", "polarizer_insert", "polarizer_retainer"):
        for a in (0, 45, 90, 180):
            moving = parts[name][0].rotate((0, 0, 0), (0, 0, 1), a)
            for fixed in (
                "carrier",
                "footed_stand",
                "inner_race_retainer",
                "motor_OpenHI_exact",
            ):
                value = volume(moving.intersect(parts[fixed][0]))
                checks["moving_vs_fixed_intersections_mm3"][f"{name}/{fixed}/{a}"] = (
                    value
                )
                if value > 1e-5:
                    raise RuntimeError(f"Interference: {name} / {fixed} / {a}: {value}")
    if checks["empty_stage_bore_obstruction_mm3"] > 1e-5:
        raise RuntimeError("Optical bore is not clear")
    envelope = ring(80, 49.8, 79, 14.5).union(ring(82, 30, 93.5, 5))
    envelope = envelope.union(ring(59.4, 24, 98.5, 5)).union(ring(29.8, 24, 96.5, 2))
    checks["full_rotation_envelope_intersections_mm3"] = {}
    for fixed in (
        "carrier",
        "footed_stand",
        "inner_race_retainer",
        "motor_OpenHI_exact",
    ):
        v = volume(envelope.intersect(parts[fixed][0]))
        checks["full_rotation_envelope_intersections_mm3"][fixed] = v
        if v > 1e-5:
            raise RuntimeError(f"Full-rotation envelope interference: {fixed}: {v}")
    checks["belt_to_motor_screw_intersections_mm3"] = {}
    for name, (shape, _) in parts.items():
        if name.startswith("motor_screw_"):
            v = volume(shape.intersect(parts["belt_backing_reference"][0]))
            checks["belt_to_motor_screw_intersections_mm3"][name] = v
            if v > 1e-5:
                raise RuntimeError(f"Motor fastener touches belt: {name}: {v}")
    checks["motor_screw_head_to_belt_vertical_gap_mm"] = (
        86.75 - P["motor_screw_head_top_z_mm"]
    )
    outputs = {}
    assembly = cq.Assembly(name="DIY_30mm_hollow_rotary_stage_OpenHI_NEMA17")
    meshes = run / "render_meshes"
    meshes.mkdir()
    for name, (shape, category) in parts.items():
        if not valid(shape):
            raise RuntimeError(f"Invalid source geometry: {name}")
        cq.exporters.export(shape, str(run / (name + ".step")))
        cq.exporters.export(
            shape, str(meshes / (name + ".stl")), tolerance=0.04, angularTolerance=0.12
        )
        assembly.add(shape, name=name)
        outputs[name] = {
            "category": category,
            "mesh": str((meshes / (name + ".stl")).relative_to(run)),
        }
    assembly_path = run / "diy_hollow_rotary_stage_85mm_assembly.step"
    assembly.save(str(assembly_path))
    back = cq.importers.importStep(str(assembly_path))
    if not valid(back):
        raise RuntimeError("Assembly STEP failed re-import")
    checks["assembly_step_valid"] = True
    prints = {}
    for name, shape in printable.items():
        print("Print export", name, flush=True)
        prints[name] = print_export(
            shape,
            run,
            name,
            invert=name in ("rotor_cup", "rotor_cap", "polarizer_insert"),
            ears=name in ("carrier", "footed_stand"),
        )
    coupons = {}
    for name, shape in fit_coupons().items():
        print("Fit coupon", name, flush=True)
        coupons[name] = print_export(shape, run, "coupon_" + name)
    checks["accessory_screw_tip_clearance_to_fixed_screw_head_mm"] = 98.5 - 6 - 91.5
    checks["motor_mount_screw_engagement_mm"] = (
        P["motor_screw_length_mm"] - 2 - P["motor_washer_total_thickness_mm"]
    )
    checks["carrier_to_rotor_cup_gap_mm"] = 79 - 78
    checks["bearing_retainer_to_rotor_cap_gap_mm"] = (49.8 - 42) / 2
    checks["M4_stand_screw_tip_z_mm_with_1mm_washer"] = 83 + 1 - 16
    checks["M4_stand_screw_bottom_clearance_mm"] = (
        checks["M4_stand_screw_tip_z_mm_with_1mm_washer"] - 65
    )
    checks["M3_cap_nut_thread_protrusion_mm"] = (90 - 2.4) - (98.5 - 12)
    checks["bare_bore_diameter_mm"] = 30
    checks["with_insert_clear_aperture_mm"] = 24
    flange_probe = printable["rotor_cup"].intersect(ring(78, 60, 0, 86))
    checks["measured_main_flange_underside_z_mm"] = exact_bounds(flange_probe)[2]
    if (
        abs(checks["measured_main_flange_underside_z_mm"] - P["tray_underside_z_mm"])
        > 1e-6
    ):
        raise RuntimeError("Physical flange does not match its declared 85 mm datum")
    data = {
        "design": DESIGN.name,
        "run_name": run.name,
        "parameters": P,
        "checks": checks,
        "source_motor": {
            "step": str(MOTOR.relative_to(ROOT)),
            "sha256": sha(MOTOR),
            "selected_label": label,
            "shapr": str(SHAPR.relative_to(ROOT)),
            "shapr_sha256": sha(SHAPR),
            "neutral_front_datum_transform_mm": [-261, -114.5, -61.5],
        },
        "parts": outputs,
        "print_validation": prints,
        "fit_coupons": coupons,
        "assembly_step": assembly_path.name,
        "prototype_limitations": [
            "Not physically tested. Print bearing/gear fits and hand-spin before applying motor power.",
            "85 mm is the main tray underside datum; the cup reaches Z79 and the stationary carrier reaches Z75. It is not an 85 mm unobstructed cylinder around the entire stage.",
            "The saved motor CAD models its 3 mm holes through the body; this does not establish real thread engagement depth. Keep motor screws near 3 mm engagement and verify physically.",
            "Bearing races, pulley and belt are reference envelopes, not supplier-complete internal bearing or belt-tooth CAD. Buy a compatible 20T 5 mm-bore 6 mm-belt pulley and confirm dimensions.",
            "Fixed cage rods must terminate below Z75 (recommend Z74 or lower), not merely below the Z85 tray: the bearing/carrier occupies the 30 mm cage-rod circle. They cannot pass through rotating mounting holes.",
            "The legacy 30 mm dock lower optical chain reaches Z79 and clashes with this carrier. A 25 mm dock reduces it to Z74, leaving only 1 mm: check the actual stack or fit the optional 5 mm height shim and use longer M4 screws.",
            "Carrier printing needs localized support below the raised motor roof. Rotor-cup flanges and stand nut pockets may need small supports depending on the printer. No universal support-free claim is made.",
            "With the optional polarizer insert fitted, the optical aperture is 24 mm, not 30 mm. The 1 mm optic thickness is a reference; thinner film needs a soft peripheral shim.",
            "No tested angular accuracy, load rating or CNC bearing-fit class is claimed. Do not tension the belt like a musical string.",
        ],
    }
    (run / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    art = DESIGN / "artifacts"
    art.mkdir(exist_ok=True)
    (art / "latest.json").write_text(
        json.dumps(
            {
                "run_dir": str(run.relative_to(ROOT)),
                "manifest": str((run / "manifest.json").relative_to(ROOT)),
                "prototype": True,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"run": str(run), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()

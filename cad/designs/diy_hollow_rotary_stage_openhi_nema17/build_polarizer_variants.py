#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Two floating-cap polarizer holders; preserve the installed stage and its fits."""

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import build_stage as base
import cadquery as cq

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
BASELINE = DESIGN / "runs/run-7-upright-chamfered-rotor-prototype-20261106T110659Z"
FIT = {
    "optic_diameter_mm": 25.4,
    "optic_thickness_mm": 4.5,
    "pocket_diameter_mm": 25.7,
    "pocket_depth_each_mm": 2.0,
    "retaining_lip_mm": 1.6,
    "soft_edge_pad_each_mm": 0.1,
    "clear_aperture_mm": 24.0,
    "base_width_mm": 42.0,
    "mount_face_z_mm": 98.5,
    "pilot_diameter_mm": 29.8,
    "pilot_length_mm": 2.0,
    "cap_screw_circle_radius_mm": 16.7,
    "cap_outer_ring_diameter_mm": 35.5,
    "cap_screw_lobe_radius_mm": 3.1,
    "cap_screw_clearance_mm": 3.3,
    "direct_M3_pilot_mm": 2.5,
    "nut_pocket_af_mm": 5.8,
    "nut_pocket_depth_mm": 2.6,
    "nut_nominal_af_mm": 5.5,
    "nut_nominal_height_mm": 2.4,
    "cap_screw_length_mm": 8.0,
    "cap_screw_washer_mm": 0.5,
}


def datums():
    h = FIT["pocket_depth_each_mm"] + FIT["retaining_lip_mm"]
    bottom = FIT["mount_face_z_mm"]
    seat = bottom + FIT["retaining_lip_mm"]
    glass_bottom = seat + FIT["soft_edge_pad_each_mm"]
    glass_top = glass_bottom + FIT["optic_thickness_mm"]
    cap_bottom = glass_top + FIT["soft_edge_pad_each_mm"] - FIT["pocket_depth_each_mm"]
    return {
        "base_bottom": bottom,
        "base_top": bottom + h,
        "glass_bottom": glass_bottom,
        "glass_top": glass_top,
        "cap_bottom": cap_bottom,
        "cap_top": cap_bottom + h,
        "part_body_height": h,
        "seam_gap": cap_bottom - (bottom + h),
        "bare_glass_seam_gap": FIT["optic_thickness_mm"]
        - 2 * FIT["pocket_depth_each_mm"],
    }


def screw_points():
    return [base.polar_xy(FIT["cap_screw_circle_radius_mm"], a) for a in (0, 120, 240)]


def optical_parts(variant):
    d = datums()
    z, top = d["base_bottom"], d["base_top"]
    width = FIT["base_width_mm"]
    height = d["part_body_height"]
    body = (
        base.box(-width / 2, width / 2, -width / 2, width / 2, z, top)
        .edges("|Z")
        .fillet(1)
    )
    body = body.union(
        base.ring(FIT["pilot_diameter_mm"], FIT["clear_aperture_mm"], z - 2, 2)
    )
    body = body.cut(base.cyl(FIT["clear_aperture_mm"], z - 2.1, height + 2.3))
    body = body.cut(base.cyl(FIT["pocket_diameter_mm"], top - 2, 2.2))
    # Only the pocket mouth is relieved; the annular glass-contact seat stays flat.
    mouth = cq.Solid.makeCone(
        FIT["pocket_diameter_mm"] / 2,
        FIT["pocket_diameter_mm"] / 2 + 0.15,
        0.15,
        cq.Vector(0, 0, top - 0.15),
    )
    body = body.cut(cq.Workplane(obj=mouth))
    cap = base.ring(
        FIT["cap_outer_ring_diameter_mm"],
        FIT["clear_aperture_mm"],
        d["cap_bottom"],
        height,
    )
    for x, y in screw_points():
        cap = cap.union(
            base.cyl(2 * FIT["cap_screw_lobe_radius_mm"], d["cap_bottom"], height, x, y)
        )
    cap = cap.cut(base.cyl(FIT["pocket_diameter_mm"], d["cap_bottom"] - 0.1, 2.1))
    for x in (-15, 15):
        for y in (-15, 15):
            body = body.cut(base.cyl(3.4, z - 0.1, height + 0.2, x, y))
    for index, (x, y) in enumerate(screw_points()):
        cap = cap.cut(
            base.cyl(
                FIT["cap_screw_clearance_mm"], d["cap_bottom"] - 0.1, height + 0.2, x, y
            )
        )
        if variant == "direct_pilot":
            body = body.cut(
                base.cyl(FIT["direct_M3_pilot_mm"], z - 0.1, height + 0.2, x, y)
            )
        elif variant == "captive_nut":
            body = body.cut(base.cyl(3.3, z - 0.1, height + 0.2, x, y))
            # Load the nuts from below before bolting the insert onto the tray.
            body = body.cut(
                base.hex_prism(
                    FIT["nut_pocket_af_mm"],
                    x,
                    y,
                    z - 0.1,
                    FIT["nut_pocket_depth_mm"] + 0.1,
                    index * 120,
                )
            )
        else:
            raise ValueError(variant)
    return body, cap


def require_clear(records, name, a, b):
    v = base.volume(a.intersect(b))
    records[name] = v
    if v > 1e-5:
        raise RuntimeError(f"Interference {name}: {v}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.run_dir and (args.run_dir / "manifest.json").exists():
        raise ValueError("Completed runs cannot be overwritten")
    number = max(int(p.name.split("-")[1]) for p in (DESIGN / "runs").glob("run-*")) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = (
        args.run_dir
        or DESIGN
        / "runs"
        / f"run-{number}-gsp25-4p5mm-two-fasteners-print-ready-{stamp}"
    )
    run.mkdir(parents=True, exist_ok=True)
    old = json.loads((BASELINE / "manifest.json").read_text())
    fixed = {
        n: cq.importers.importStep(str(BASELINE / (n + ".step")))
        for n in old["parts"]
        if not n.startswith("polarizer_")
    }
    d = datums()
    glass = base.cyl(
        FIT["optic_diameter_mm"], d["glass_bottom"], FIT["optic_thickness_mm"]
    )
    pads = [
        base.ring(25.4, 24, d["glass_bottom"] - 0.1, 0.1),
        base.ring(25.4, 24, d["glass_top"], 0.1),
    ]
    manifest = {
        "run_name": run.name,
        "base_run": BASELINE.name,
        "parameters": FIT,
        "datums_mm": d,
        "physically_tested": False,
        "promoted_to_default": False,
        "variants": {},
        "limits": [
            "The measured optic is 4.5mm; the public catalog's approximate thickness is not used.",
            "Floating cap: never force the two plastic faces together across the glass.",
            "Soft 0.1mm peripheral pads are reference envelopes, not factory print items.",
            "M3 pilot is intended for tapping or controlled plastic thread forming, not a modeled helix.",
        ],
    }
    for variant in ("direct_pilot", "captive_nut"):
        folder = run / variant
        folder.mkdir(exist_ok=True)
        (folder / "render_meshes").mkdir(exist_ok=True)
        body, cap = optical_parts(variant)
        checks = {}
        for name, s in (("insert", body), ("retainer", cap)):
            if not base.valid(s) or len(s.solids().vals()) != 1:
                raise RuntimeError(f"Invalid {variant}/{name}")
            require_clear(checks, name + "/glass", s, glass)
            require_clear(checks, name + "/optical_aperture", s, base.cyl(24, 95, 15))
            require_clear(checks, name + "/rotor_cap", s, fixed["rotor_cap"])
        require_clear(checks, "halves", body, cap)
        parts = {
            "polarizer_insert": (body, "polymer"),
            "polarizer_retainer": (cap, "polymer_mid"),
            "polarizer_gsp25_4p5mm": (glass, "glass"),
            "soft_lower_edge_pad": (pads[0], "belt"),
            "soft_upper_edge_pad": (pads[1], "belt"),
        }
        for i, (x, y) in enumerate(screw_points()):
            washer_top = d["cap_top"] + FIT["cap_screw_washer_mm"]
            length = FIT["cap_screw_length_mm"]
            screw = base.cyl(3, washer_top - length, length, x, y).union(
                base.cyl(5.5, washer_top, 3, x, y)
            )
            require_clear(checks, f"screw_{i}/glass", screw, glass)
            require_clear(checks, f"screw_{i}/rotor_cap", screw, fixed["rotor_cap"])
            parts[f"cap_M3x8_{i}"] = (screw, "metal")
            parts[f"cap_M3_washer_{i}"] = (
                base.ring(7, 3.2, d["cap_top"], 0.5).translate((x, y, 0)),
                "metal",
            )
            if variant == "captive_nut":
                nut = base.hex_prism(
                    5.5,
                    x,
                    y,
                    d["base_bottom"] + FIT["nut_pocket_depth_mm"] - 2.4,
                    2.4,
                    i * 120,
                ).cut(base.cyl(3, x=x, y=y, z0=d["base_bottom"] - 1, h=4))
                require_clear(checks, f"nut_{i}/rotor_cap", nut, fixed["rotor_cap"])
                require_clear(checks, f"nut_{i}/insert", nut, body)
                parts[f"cap_M3_nut_{i}"] = (nut, "metal")
        for i, (x, y) in enumerate((x, y) for x in (-15, 15) for y in (-15, 15)):
            head = base.cyl(5.5, d["base_top"], 3, x, y)
            require_clear(checks, f"mount_head_{i}/retainer", head, cap)
            parts[f"existing_M3_mount_head_{i}"] = (head, "metal")
        rows = {}
        for name, (shape, category) in parts.items():
            cq.exporters.export(shape, str(folder / (name + ".step")))
            mesh = folder / "render_meshes" / (name + ".stl")
            cq.exporters.export(shape, str(mesh), tolerance=0.025, angularTolerance=0.1)
            rows[name] = {"category": category, "mesh": str(mesh.relative_to(folder))}
        assembly = cq.Assembly(name="GSP25_" + variant)
        for name, (shape, _) in parts.items():
            assembly.add(shape, name=name)
        step = folder / ("GSP25_4p5mm_" + variant + "_assembly.step")
        assembly.save(str(step))
        if not base.valid(cq.importers.importStep(str(step))):
            raise RuntimeError("STEP round trip")
        stage = cq.Assembly(name="OpenHI_stage_GSP25_" + variant)
        for name, shape in fixed.items():
            stage.add(shape, name=name)
        for name, (shape, _) in parts.items():
            stage.add(shape, name=name)
        stage.save(str(folder / ("OpenHI_stage_GSP25_" + variant + "_assembly.step")))
        prints = {
            "insert": base.print_export(body, folder, "insert", invert=True, ears=True),
            "retainer": base.print_export(cap, folder, "retainer", invert=True),
        }
        for name, shape in (("insert", body), ("retainer", cap)):
            row = base.print_export(shape, folder, "factory_" + name, invert=True)
            row["factory_no_ears"] = True
            prints["factory_" + name] = row
        manifest["variants"][variant] = {
            "assembly_step": str(step.relative_to(run)),
            "parts": rows,
            "checks_mm3": checks,
            "print_validation": prints,
            "cap_screw_engagement_mm": FIT["cap_screw_length_mm"]
            - FIT["cap_screw_washer_mm"]
            - d["part_body_height"]
            - d["seam_gap"],
            "cap_screw_tip_above_mount_face_mm": d["cap_top"]
            + FIT["cap_screw_washer_mm"]
            - FIT["cap_screw_length_mm"]
            - d["base_bottom"],
        }
        (folder / "manifest.json").write_text(
            json.dumps({"parts": rows, "variant": variant, "datums_mm": d}, indent=2)
            + "\n"
        )
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (run / "source").mkdir(exist_ok=True)
    shutil.copy2(__file__, run / "source" / Path(__file__).name)
    shutil.copy2(DESIGN / "build_stage.py", run / "source/build_stage.py")
    (DESIGN / "artifacts/polarizer_variant.json").write_text(
        json.dumps(
            {"run_dir": str(run.relative_to(ROOT)), "promoted_to_default": False},
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"run_dir": str(run), "datums": d}, indent=2))


if __name__ == "__main__":
    main()

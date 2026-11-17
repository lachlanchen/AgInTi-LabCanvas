#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact factory quantities and full, checksum-verified optical-holder handoff."""

import argparse
import json
import shutil
from pathlib import Path

import package_stage as shared

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
NUTSTORE = Path.home() / "Nutstore Files/Projects/LabCanvas" / DESIGN.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-order", action="store_true")
    args = parser.parse_args()
    run = (
        ROOT
        / json.loads((DESIGN / "artifacts/polarizer_variant.json").read_text())[
            "run_dir"
        ]
    )
    out = run / "manufacturing/wenext"
    out.mkdir(parents=True, exist_ok=True)
    a = run / "direct_pilot/print/factory_retainer/PRINT_THIS_factory_retainer.stl"
    b = run / "captive_nut/print/factory_retainer/PRINT_THIS_factory_retainer.stl"
    if shared.digest(a) != shared.digest(b):
        raise RuntimeError("Shared cap meshes differ")
    rows = []
    for name, source, quantity in (
        (
            "GSP25_4p5_base_M3_pilot_D2p5",
            "direct_pilot/print/factory_insert/PRINT_THIS_factory_insert",
            1,
        ),
        (
            "GSP25_4p5_base_M3_captive_nuts",
            "captive_nut/print/factory_insert/PRINT_THIS_factory_insert",
            1,
        ),
        (
            "GSP25_4p5_split_cap",
            "direct_pilot/print/factory_retainer/PRINT_THIS_factory_retainer",
            2,
        ),
    ):
        row = {"part": name, "quantity": quantity}
        for ext in ("stl", "step", "3mf"):
            destination = out / (name + "." + ext)
            shutil.copy2(run / (source + "." + ext), destination)
            row[ext] = str(destination.relative_to(run))
            row[ext + "_sha256"] = shared.digest(destination)
        rows.append(row)
    contract = {
        "run_name": run.name,
        "unique_models": 3,
        "total_parts": 4,
        "parts": rows,
        "preferred_material": "Same functional white nylon as accepted WeNext run7: future7000, subject to current quote",
        "exclude": [
            "optical glass",
            "metal fasteners",
            "soft pads",
            "stage",
            "coupons",
            "FDM ears",
        ],
        "submission_authorized": True,
        "payment_authorized": False,
    }
    (out / "manufacturing_manifest.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )
    if args.prepare_order:
        print(
            json.dumps(
                {"run_dir": str(run), "manufacturing": str(out), "parts": rows},
                indent=2,
            )
        )
        return
    checks = json.loads((run / "render_checks.json").read_text())
    for row in checks["renders"]:
        b = row["camera_bounds"]
        if min(b["xmin"], b["ymin"]) < 0.079 or max(b["xmax"], b["ymax"]) > 0.921:
            raise RuntimeError("Insufficient render margins")
        shared.flatten(run / row["path"])
    for name in (
        "POLARIZER_GSP25_4P5.md",
        "build_polarizer_variants.py",
        "render_polarizer_variants.py",
        "package_polarizer_variants.py",
        "build_stage.py",
        "LICENSE",
    ):
        shutil.copy2(DESIGN / name, run / "source" / name)
    shutil.copy2(DESIGN / "POLARIZER_GSP25_4P5.md", run / "README.md")
    hashes = {
        str(p.relative_to(run)): shared.digest(p)
        for p in run.rglob("*")
        if p.is_file() and p.name != "checksums.json"
    }
    (run / "checksums.json").write_text(json.dumps(hashes, indent=2) + "\n")
    target = NUTSTORE / "optical-insert-upgrades" / run.name
    shutil.copytree(run, target, dirs_exist_ok=True)
    for name, expected in hashes.items():
        if shared.digest(target / name) != expected:
            raise RuntimeError("Nutstore mismatch: " + name)
    record = {
        "run_dir": str(run.relative_to(ROOT)),
        "nutstore_run": str(target),
        "verified_files": len(hashes),
        "all_checksums_match": True,
        "promoted_to_default": False,
    }
    (DESIGN / "artifacts/polarizer_sync.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

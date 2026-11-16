#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sync only the optional motor-plate variant; preserve the proven default."""

import json
import shutil
from pathlib import Path

import package_stage as shared

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
NUTSTORE = Path.home() / "Nutstore Files/Projects/LabCanvas" / DESIGN.name


def main():
    pointer = json.loads((DESIGN / "artifacts/parallel_variant.json").read_text())
    run = ROOT / pointer["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    renders = json.loads((run / "render_checks.json").read_text())
    for row in renders["renders"]:
        bounds = row["camera_bounds"]
        if (
            min(bounds["xmin"], bounds["ymin"]) < 0.079
            or max(bounds["xmax"], bounds["ymax"]) > 0.921
        ):
            raise RuntimeError("Render is cropped or has insufficient camera margins")
        shared.flatten(run / row["path"])
    shared.contacts(run, data)
    for name in (
        "build_stage.py",
        "build_parallel_variant.py",
        "package_parallel_variant.py",
        "render_stage.py",
        "fastener_contract.json",
        "FIELD_VALIDATION.md",
        "fastener_selection_20261116.json",
        "FASTENERS.zh-CN.md",
        "LICENSE",
    ):
        shutil.copy2(DESIGN / name, run / "source" / name)
    files = {
        str(p.relative_to(run)): shared.digest(p)
        for p in run.rglob("*")
        if p.is_file() and p.name != "checksums.json"
    }
    (run / "checksums.json").write_text(json.dumps(files, indent=2) + "\n")
    target = NUTSTORE / "optional-variants" / run.name
    shutil.copytree(run, target, dirs_exist_ok=True)
    for name, expected in files.items():
        if shared.digest(target / name) != expected:
            raise RuntimeError(f"Nutstore checksum mismatch: {name}")
    for name in (
        "FIELD_VALIDATION.md",
        "fastener_contract.json",
        "fastener_selection_20261116.json",
        "FASTENERS.zh-CN.md",
    ):
        shutil.copy2(DESIGN / name, NUTSTORE / name)
    record = {
        "run_dir": pointer["run_dir"],
        "nutstore_run": str(target),
        "assembly_step": str(target / data["assembly_step"]),
        "verified_files": len(files),
        "all_checksums_match": True,
        "physically_tested": False,
        "promoted_to_default": False,
    }
    (DESIGN / "artifacts/parallel_sync.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

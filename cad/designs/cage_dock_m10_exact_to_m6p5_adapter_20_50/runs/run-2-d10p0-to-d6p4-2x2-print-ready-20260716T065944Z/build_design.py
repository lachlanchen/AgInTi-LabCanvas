#!/usr/bin/env python3
"""Build exact 10.0 mm to 6.4 mm smooth dock adapters."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "cad" / "tools" / "cylindrical_print_ready.py").is_file():
            return parent
    raise RuntimeError("Could not locate the AgenticApp repository root")


ROOT = find_repo_root()
DESIGN_DIR = ROOT / "cad" / "designs" / "cage_dock_m10_exact_to_m6p5_adapter_20_50"
sys.path.insert(0, str(ROOT / "cad" / "tools"))

from cylindrical_print_ready import build_adapter_design


def main() -> None:
    manifest = build_adapter_design(
        root=ROOT,
        design_dir=DESIGN_DIR,
        run_name="run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z",
        stem="cage_dock_m10_exact_to_m6p4_adapter_20_50",
        lower_diameter_mm=10.0,
        lower_length_mm=20.0,
        upper_diameter_mm=6.4,
        upper_length_mm=50.0,
        rows=2,
        cols=2,
        pitch_mm=25.0,
        chamfer_mm=0.25,
        color=(0.86, 0.36, 0.12),
        source_path=Path(__file__),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

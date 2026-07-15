#!/usr/bin/env python3
"""Build exact 10.0 mm to 6.5 mm smooth dock adapters."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cad" / "tools"))

from cylindrical_print_ready import build_adapter_design


def main() -> None:
    manifest = build_adapter_design(
        root=ROOT,
        design_dir=DESIGN_DIR,
        run_name="run-1-d10p0-to-d6p5-2x2-print-ready-20260715T085116Z",
        stem="cage_dock_m10_exact_to_m6p5_adapter_20_50",
        lower_diameter_mm=10.0,
        lower_length_mm=20.0,
        upper_diameter_mm=6.5,
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

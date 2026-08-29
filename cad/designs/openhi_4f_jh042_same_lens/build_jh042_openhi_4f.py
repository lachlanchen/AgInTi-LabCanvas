#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cad/tools"))
from openhi_same_lens_4f import run_design_cli


if __name__ == "__main__":
    run_design_cli("jh042", Path(__file__).resolve().parent)

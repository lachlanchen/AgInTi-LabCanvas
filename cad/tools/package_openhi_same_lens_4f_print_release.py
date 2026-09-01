#!/usr/bin/env python3
"""Package one validated same-lens OpenHI 4f system for printing and handoff."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "cad/tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import openhi_same_lens_4f as openhi  # noqa: E402


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def package_design(design_dir: Path) -> dict[str, object]:
    design_dir = design_dir.resolve()
    artifact_dir = design_dir / "artifacts"
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("checks") or not all(manifest["checks"].values()):
        raise RuntimeError(f"refusing to package a failed design: {design_dir}")

    spec_key = manifest["lens"]["key"]
    run_dir = design_dir / "runs" / openhi.PRINT_RELEASE_RUN_NAME
    render_dir = run_dir / "renders"
    run_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    packaged_parts: dict[str, dict[str, object]] = {}
    for name, record in manifest["parts"].items():
        source_step = ROOT / record["step"]
        source_stl = ROOT / record["stl"]
        source_3mf = ROOT / record["3mf"]
        stem = f"PRINT_THIS_{spec_key}_{name}"
        target_step = run_dir / f"{stem}.step"
        target_stl = run_dir / f"{stem}.stl"
        target_3mf = run_dir / f"{stem}.3mf"

        shape = cq.importers.importStep(str(source_step))
        print_shape, orientation = openhi.orient_for_print(name, shape)
        exporters.export(print_shape, str(target_step))
        copy(source_stl, target_stl)
        copy(source_3mf, target_3mf)
        step_validation = openhi.step_summary(target_step)
        mesh_validation = openhi.mesh_summary(target_stl)
        three_mf_validation = openhi.three_mf_summary(target_3mf)
        three_mf_validation["bounds_match_stl"] = openhi.bounds_match(
            mesh_validation["bounds_mm"],
            three_mf_validation["bounds_mm"],
        )
        if not (
            step_validation["occt_valid"]
            and step_validation["solid_count"] == 1
            and mesh_validation["watertight"]
            and mesh_validation["components"] == 1
            and abs(mesh_validation["minimum_z_mm"]) <= 1e-5
            and mesh_validation["first_layer_triangle_count"] > 0
            and three_mf_validation["unit"] == "millimeter"
            and three_mf_validation["mesh_object_count"] == 1
            and three_mf_validation["build_item_count"] == 1
            and three_mf_validation["build_items_reference_mesh_objects"]
            and three_mf_validation["components"] == 1
            and three_mf_validation["indices_valid"]
            and three_mf_validation["watertight"]
            and three_mf_validation["winding_consistent"]
            and three_mf_validation["bounds_match_stl"]
            and abs(three_mf_validation["minimum_z_mm"]) <= 1e-5
            and three_mf_validation["first_layer_triangle_count"] > 0
        ):
            raise RuntimeError(f"print artifact validation failed: {stem}")
        packaged_parts[name] = {
            "step": target_step.name,
            "stl": target_stl.name,
            "3mf": target_3mf.name,
            "print_orientation": orientation,
            "step_validation": step_validation,
            "mesh_validation": mesh_validation,
            "3mf_validation": three_mf_validation,
            "sha256": {
                "step": openhi.sha256(target_step),
                "stl": openhi.sha256(target_stl),
                "3mf": openhi.sha256(target_3mf),
            },
        }

    reference_files = {
        f"ASSEMBLY_REFERENCE_{spec_key}_openhi_4f.step": (
            design_dir / f"USE_THIS_{spec_key}_openhi_4f_assembly.step"
        ),
        f"REFERENCE_{spec_key}_lens.step": artifact_dir / f"{spec_key}_lens.step",
        f"REFERENCE_{spec_key}_lens.stl": artifact_dir / f"{spec_key}_lens.stl",
        f"REFERENCE_{spec_key}_lens.3mf": artifact_dir / f"{spec_key}_lens.3mf",
        "source_manifest.json": manifest_path,
        "source_README.md": design_dir / "README.md",
        f"build_{spec_key}_openhi_4f.py": (
            design_dir / f"build_{spec_key}_openhi_4f.py"
        ),
        "shared_builder_snapshot.py": ROOT / "cad/tools/openhi_same_lens_4f.py",
    }
    for name, source in reference_files.items():
        copy(source, run_dir / name)

    render_names = (
        "openhi_4f_assembly.png",
        "openhi_4f_optical_axis.png",
        "openhi_4f_spatial_exploded.png",
        "openhi_4f_print_parts_layout.png",
        "openhi_4f_a_input_receiver_section.png",
        "openhi_4f_a_lens_cavity_section.png",
    )
    for name in render_names:
        source = artifact_dir / "renders" / name
        if not source.exists():
            raise FileNotFoundError(f"missing release render: {source}")
        copy(source, render_dir / name)

    release_manifest = {
        "design": design_dir.name,
        "run": openhi.PRINT_RELEASE_RUN_NAME,
        "lens": manifest["lens"],
        "source_manifest_sha256": openhi.sha256(manifest_path),
        "shared_builder_sha256": openhi.sha256(
            ROOT / "cad/tools/openhi_same_lens_4f.py"
        ),
        "all_source_checks_passed": all(manifest["checks"].values()),
        "parts": packaged_parts,
        "renders": list(render_names),
        "assembly_is_reference_only": True,
        "print_contract": (
            "Print one part from one PRINT_THIS file. Each STL/3MF is a single "
            "watertight object in millimetres; do not split the assembly STEP."
        ),
    }
    release_manifest_path = run_dir / "manifest.json"
    release_manifest_path.write_text(
        json.dumps(release_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "README.md").write_text(
        f"""# {spec_key} OpenHI 4f Print Release

Use one matching `PRINT_THIS_*.3mf` or `PRINT_THIS_*.stl` per mechanical part.
Each file contains exactly one watertight object in millimetres. The C-axis
retainer and holder are rotated so their thread axes are vertical, and the
Lens B holder is inverted onto its outer planar end. The assembly STEP retains
the original OpenHI coordinates and is reference-only, not a direct print file.

The lens files are geometric references, not printable optical substitutes.
`source_manifest.json` contains the full lens-fit, thread, focal-distance,
axis-alignment, optical-core, interference, STEP, STL, and 3MF checks.

Before committing all material, print one central C thread-fit coupon or test
the mating pair because that preserved source interface is intentionally tight.
""",
        encoding="utf-8",
    )

    openhi.sync_outputs(design_dir, openhi.LENS_SPECS[spec_key])
    nutstore_run = (
        openhi.NUTSTORE_ROOT / design_dir.name / openhi.PRINT_RELEASE_RUN_NAME
    )
    nutstore_run.mkdir(parents=True, exist_ok=True)
    for source in sorted(run_dir.rglob("*")):
        if source.is_file():
            copy(source, nutstore_run / source.relative_to(run_dir))

    return {
        "design": design_dir.name,
        "run_dir": str(run_dir),
        "nutstore_run_dir": str(nutstore_run),
        "part_count": len(packaged_parts),
        "all_checks_passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-dir", action="append", required=True, type=Path)
    args = parser.parse_args()
    results = [package_design(path) for path in args.design_dir]
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

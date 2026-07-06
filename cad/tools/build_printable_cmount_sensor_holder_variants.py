#!/usr/bin/env python3
"""Build clean printable variants of the C-mount sensor holders.

The historical folders are named ``*_printable_saddle``. They now intentionally
contain clean, no-saddle geometry because the flat fill made the holders bulky
and visually awkward.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROOT = ROOT / "cad/designs"


@dataclass(frozen=True)
class VariantSpec:
    key: str
    source_stem: str
    variant_stem: str
    title: str
    sensor_label: str
    datum_key: str

    @property
    def source_dir(self) -> Path:
        return DESIGN_ROOT / self.source_stem

    @property
    def variant_dir(self) -> Path:
        return DESIGN_ROOT / self.variant_stem


VARIANTS: dict[str, VariantSpec] = {
    "gy302": VariantSpec(
        key="gy302",
        source_stem="gy302_bh1750_cmount_light_sensor_holder",
        variant_stem="gy302_bh1750_cmount_light_sensor_holder_printable_saddle",
        title="GY-302 BH1750 C-Mount Light Sensor Holder Clean Printable",
        sensor_label="BH1750 photodiode/package",
        datum_key="sensor",
    ),
    "as7343": VariantSpec(
        key="as7343",
        source_stem="as7343_cmount_spectral_module_holder",
        variant_stem="as7343_cmount_spectral_module_holder_printable_saddle",
        title="AS7343 C-Mount Spectral Module Holder Clean Printable",
        sensor_label="AS7343 package/window",
        datum_key="sensor",
    ),
    "tsl25911": VariantSpec(
        key="tsl25911",
        source_stem="tsl25911_cmount_intensity_sensor_holder",
        variant_stem="tsl25911_cmount_intensity_sensor_holder_printable_saddle",
        title="TSL25911 C-Mount Intensity Sensor Holder Clean Printable",
        sensor_label="TSL25911 window",
        datum_key="window",
    ),
    "as7341": VariantSpec(
        key="as7341",
        source_stem="as7341_cmount_sensor_holder",
        variant_stem="as7341_cmount_sensor_holder_printable_saddle",
        title="AS7341 C-Mount Sensor Holder Clean Printable",
        sensor_label="AS7341 aperture",
        datum_key="aperture",
    ),
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def load_source_module(spec: VariantSpec) -> ModuleType:
    script = spec.source_dir / f"build_{spec.source_stem}.py"
    module_name = f"_labcanvas_{spec.source_stem}"
    module_spec = importlib.util.spec_from_file_location(module_name, script)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot import {script}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def total_length(module: ModuleType) -> float:
    return float(module.total_length())


def remove_legacy_saddle_files(artifact_dir: Path, variant_stem: str) -> None:
    for suffix in ("step", "stl"):
        legacy = artifact_dir / f"{variant_stem}_support_saddle.{suffix}"
        if legacy.exists():
            legacy.unlink()


def build_clean_holder(module: ModuleType) -> cq.Workplane:
    return module.build_holder().clean()


def add_if_available(assembly: cq.Assembly, module: ModuleType, func_name: str, name: str, color: cq.Color) -> cq.Workplane | None:
    func = getattr(module, func_name, None)
    if not func:
        return None
    obj = func()
    assembly.add(obj, name=name, color=color)
    return obj


def build_assembly(module: ModuleType, holder: cq.Workplane, spec: VariantSpec) -> tuple[cq.Assembly, dict[str, cq.Workplane]]:
    assembly = cq.Assembly(name=f"{spec.variant_stem}_assembly")
    assembly.add(holder, name="clean_printable_holder_no_saddle_fill", color=cq.Color(0.10, 0.10, 0.09, 1.0))

    proxies: dict[str, cq.Workplane] = {}
    board = add_if_available(assembly, module, "build_board_proxy", "board_proxy", cq.Color(0.0, 0.22, 0.50, 0.72))
    sensor = add_if_available(assembly, module, "build_sensor_proxy", "sensor_on_optical_axis", cq.Color(0.95, 0.74, 0.10, 1.0))
    accessory = (
        add_if_available(assembly, module, "build_header_proxy", "connector_or_header_clearance_proxy", cq.Color(0.95, 0.92, 0.82, 0.65))
        or add_if_available(assembly, module, "build_connector_proxy", "connector_or_header_clearance_proxy", cq.Color(0.95, 0.92, 0.82, 0.65))
    )
    cutter = add_if_available(assembly, module, "female_thread_cutter", "female_thread_boolean_cutter", cq.Color(0.9, 0.2, 0.1, 0.35))
    axis = add_if_available(assembly, module, "build_axis_proxy", "optical_axis_proxy", cq.Color(1.0, 0.72, 0.08, 0.60))

    for key, obj in (
        ("board_proxy", board),
        ("sensor_proxy", sensor),
        ("accessory_proxy", accessory),
        ("thread_cutter", cutter),
        ("axis_proxy", axis),
    ):
        if obj is not None:
            proxies[key] = obj

    return assembly, proxies


def center_check(module: ModuleType, spec: VariantSpec) -> dict[str, Any]:
    params = module.PARAMS
    ref = module.board_reference_geometry()
    if spec.datum_key == "sensor":
        board_center = ref.get("board_center_relative_to_sensor_mm", {})
        y_offset = float(params.get(f"{spec.key}_sensor_offset_y_mm", 0.0))
        z_offset = float(params.get(f"{spec.key}_sensor_offset_z_mm", 0.0))
        if spec.key == "gy302":
            y_offset = float(params.get("bh1750_sensor_offset_y_mm", 0.0))
            z_offset = float(params.get("bh1750_sensor_offset_z_mm", 0.0))
        if spec.key == "as7343":
            y_offset = float(params.get("as7343_sensor_offset_y_mm", 0.0))
            z_offset = float(params.get("as7343_sensor_offset_z_mm", 0.0))
    elif spec.datum_key == "window":
        board_center = ref.get("board_center_relative_to_window_mm", {})
        y_offset = 0.0
        z_offset = 0.0
    else:
        board_center = ref.get("board_center_relative_to_aperture_mm", {})
        y_offset = 0.0
        z_offset = 0.0

    return {
        "sensor_label": spec.sensor_label,
        "optical_axis_yz_mm": {"y": 0.0, "z": 0.0},
        "sensor_datum_yz_mm": {"y": round(y_offset, 4), "z": round(z_offset, 4)},
        "sensor_datum_is_on_optical_axis": abs(y_offset) < 1e-6 and abs(z_offset) < 1e-6,
        "board_center_relative_to_sensor_or_window_mm": board_center,
        "note": "The active sensor datum is at Y=0, Z=0. Board center may be offset when the sensor is not at board center.",
    }


def write_readme(spec: VariantSpec, module: ModuleType, manifest: dict[str, Any]) -> None:
    outputs = manifest["outputs"]
    center = manifest["center_check"]
    print_policy = manifest["print_policy"]
    output_rows = "\n".join(f"| {key} | `{value}` |" for key, value in outputs.items())
    source_readme = spec.source_dir / "README.md"
    original_note = repo_path(source_readme) if source_readme.exists() else repo_path(spec.source_dir)
    readme = f"""# {spec.title}

This folder keeps the historical `{spec.variant_stem}` name, but the generated
geometry is now the clean holder shape with no flat-bottom saddle/fill body.
The source holder remains the authoritative parametric design.

## What Changed

- Removed the integrated flat-bottom saddle and overflow fill because it made
  the design visually bulky.
- Preserved the original board pocket, sensor datum, thread convention, and
  source reference assumptions.
- Re-exported the holder, board proxy, sensor proxy, connector/header proxy,
  thread cutter, optical axis, assembly, render, and print-orientation render.

## Sensor Center Check

`{center['sensor_label']}` is placed on the optical axis:

```json
{json.dumps(center, indent=2, ensure_ascii=False)}
```

## Print Policy

```json
{json.dumps(print_policy, indent=2, ensure_ascii=False)}
```

Use the holder STL for printing. Use the assembly STEP/STL to inspect the board
proxy, sensor datum, thread cutter, and optical axis together.

## Source Design

- Source design: `{repo_path(spec.source_dir)}`
- Source README: `{original_note}`
- Local OpenHI thread reference: `cad/references/openhi-print-fit-and-thread-reference.md`

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/tools/build_printable_cmount_sensor_holder_variants.py {spec.key}
blender --background --python cad/tools/render_printable_cmount_sensor_holder_variants.py -- {spec.key}
```
"""
    spec.variant_dir.mkdir(parents=True, exist_ok=True)
    (spec.variant_dir / "README.md").write_text(readme, encoding="utf-8")


def export_variant(spec: VariantSpec) -> dict[str, Any]:
    module = load_source_module(spec)
    artifact_dir = spec.variant_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    remove_legacy_saddle_files(artifact_dir, spec.variant_stem)

    holder = build_clean_holder(module)
    assembly, proxies = build_assembly(module, holder, spec)

    outputs: dict[str, str] = {}

    def export_obj(name: str, obj: cq.Workplane) -> None:
        step = artifact_dir / f"{spec.variant_stem}_{name}.step"
        stl = artifact_dir / f"{spec.variant_stem}_{name}.stl"
        exporters.export(obj, str(step))
        exporters.export(obj, str(stl))
        outputs[f"{name}_step"] = repo_path(step)
        outputs[f"{name}_stl"] = repo_path(stl)

    export_obj("holder", holder)
    for name, obj in proxies.items():
        export_obj(name, obj)

    assembly_step = artifact_dir / f"{spec.variant_stem}_assembly.step"
    assembly_stl = artifact_dir / f"{spec.variant_stem}_assembly.stl"
    assembly.save(str(assembly_step))
    assembly.save(str(assembly_stl))
    outputs["assembly_step"] = repo_path(assembly_step)
    outputs["assembly_stl"] = repo_path(assembly_stl)
    outputs["render_png"] = repo_path(artifact_dir / f"{spec.variant_stem}_render.png")
    outputs["print_orientation_render_png"] = repo_path(artifact_dir / f"{spec.variant_stem}_print_orientation_render.png")

    params = module.PARAMS
    bbox = holder.val().BoundingBox()
    print_policy = {
        "type": "clean holder without extra saddle or overflow fill",
        "legacy_folder_name": spec.variant_stem,
        "saddle_fill_removed": True,
        "holder_bounding_box_mm": {
            "x": [round(bbox.xmin, 4), round(bbox.xmax, 4)],
            "y": [round(bbox.ymin, 4), round(bbox.ymax, 4)],
            "z": [round(bbox.zmin, 4), round(bbox.zmax, 4)],
        },
        "print_note": "Use normal slicer-generated supports if needed. The CAD no longer adds a custom fill block under the C-mount tube.",
    }

    manifest = {
        "name": spec.variant_stem,
        "source_design": repo_path(spec.source_dir),
        "variant": "clean_printable_no_saddle_fill",
        "params": params,
        "reference_geometry": module.board_reference_geometry(),
        "center_check": center_check(module, spec),
        "print_policy": print_policy,
        "outputs": outputs,
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["outputs"]["manifest"] = repo_path(manifest_path)
    write_readme(spec, module, manifest)
    return manifest


def selected_variants(args: list[str]) -> list[VariantSpec]:
    if not args or args == ["all"]:
        return list(VARIANTS.values())
    specs = []
    for arg in args:
        try:
            specs.append(VARIANTS[arg])
        except KeyError as exc:
            valid = ", ".join(sorted(VARIANTS))
            raise SystemExit(f"Unknown variant {arg!r}. Valid: {valid}, all") from exc
    return specs


def main(argv: list[str]) -> int:
    manifests = []
    for spec in selected_variants(argv):
        manifest = export_variant(spec)
        manifests.append(manifest)
        print(f"built {spec.variant_stem}: {manifest['outputs']['holder_stl']}")
    print(json.dumps({"built": [m["name"] for m in manifests]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Config-driven JLCPCB order wrapper for generated KiCad boards.

This script is the board-level entry point above the lower-level CDP tools. It
keeps public board settings in the repository, merges private recipient/session
settings from ~/.config/jlcpcb-order/private.json, packages Gerbers, validates
KiCad reports, and then calls the maintained quick-order scripts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PRIVATE_CONFIG = Path("~/.config/jlcpcb-order/private.json").expanduser()
DEFAULT_GENERATED_CONFIG_DIR = Path("~/.config/jlcpcb-order/generated").expanduser()
DEFAULT_RUN_LOG_DIR = Path("~/.config/jlcpcb-order/runs").expanduser()
CHINA_OSP_MIN_SIDE_MM = 70.0


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any], private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if private:
        os.chmod(path, 0o600)


def resolve_from_config(config_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def project_name(config: dict[str, Any], config_path: Path) -> str:
    return str(config.get("project_name") or config_path.parent.parent.name)


def board_size_mm(config: dict[str, Any]) -> tuple[float, float]:
    board = config.get("board", {})
    size = board.get("expected_size_mm") or {}
    try:
        return float(size.get("x")), float(size.get("y"))
    except (TypeError, ValueError):
        return 0.0, 0.0


def board_size_label(config: dict[str, Any]) -> str:
    x_mm, y_mm = board_size_mm(config)
    if x_mm and y_mm:
        return f"{x_mm / 10:.1f} cm x {y_mm / 10:.1f} cm"
    return str(config.get("order", {}).get("board_size") or "")


def choose_surface_finish(config: dict[str, Any], site: str, override: str | None = None) -> str:
    if override:
        return override
    order = config.get("order", {})
    if site == "global":
        finish = order.get("surface_finish_global") or order.get("surface_finish")
        return "Lead-free HASL" if str(finish or "auto").lower().startswith("auto") else str(finish)

    finish = order.get("surface_finish_china") or order.get("surface_finish")
    if not finish or str(finish).lower().startswith("auto"):
        x_mm, y_mm = board_size_mm(config)
        if x_mm and y_mm and min(x_mm, y_mm) < CHINA_OSP_MIN_SIDE_MM:
            return "无铅喷锡"
        return "OSP"
    return str(finish)


def gerber_files(config: dict[str, Any], config_path: Path) -> list[Path]:
    gerber_dir = resolve_from_config(config_path, config.get("gerber_dir") or "../gerber")
    if not gerber_dir or not gerber_dir.exists():
        raise SystemExit(f"missing Gerber directory: {gerber_dir}")
    files = []
    for path in sorted(gerber_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".svg", ".png", ".pdf", ".txt"}:
            continue
        files.append(path)
    required = [".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gm1", ".drl"]
    suffixes = {path.suffix.lower() for path in files}
    missing = [suffix for suffix in required if suffix not in suffixes]
    if missing:
        raise SystemExit(f"Gerber package is missing required suffixes: {', '.join(missing)}")
    return files


def zip_path_for_config(config: dict[str, Any], config_path: Path) -> Path:
    value = config.get("gerber_zip") or f"{project_name(config, config_path)}-jlcpcb-gerber.zip"
    path = Path(os.path.expanduser(str(value)))
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def package_gerbers(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    output = zip_path_for_config(config, config_path)
    files = gerber_files(config, config_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    entries = []
    with zipfile.ZipFile(output) as zf:
        for info in sorted(zf.infolist(), key=lambda item: item.filename):
            entries.append(
                {
                    "name": info.filename,
                    "size_bytes": info.file_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name(config, config_path),
        "upload_file": output.name,
        "sha256": digest,
        "size_bytes": output.stat().st_size,
        "files": entries,
        "excluded_review_files": [
            os.path.relpath(path, output.parent)
            for path in sorted(resolve_from_config(config_path, config.get("gerber_dir") or "../gerber").glob("*"))
            if path.suffix.lower() in {".svg", ".png", ".pdf", ".txt"}
        ],
        "validation_reports": config.get("validation_reports", {}),
        "renders": config.get("renders", {}),
    }
    manifest_path = output.parent / "preflight-manifest.json"
    write_json(manifest_path, manifest)
    print(f"packaged={output}")
    print(f"manifest={manifest_path}")
    return manifest


def validation_report_path(config: dict[str, Any], config_path: Path, key: str, fallback: str) -> Path:
    reports = config.get("validation_reports", {})
    return resolve_from_config(config_path, reports.get(key) or fallback)  # type: ignore[arg-type]


def validate_reports(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    erc_path = validation_report_path(config, config_path, "erc", "../artifacts/erc.json")
    drc_path = validation_report_path(config, config_path, "drc", "../artifacts/drc.json")
    erc = load_json(erc_path)
    drc = load_json(drc_path)
    erc_violations = erc.get("violations", [])
    drc_violations = drc.get("violations", [])
    unconnected = drc.get("unconnected_items", [])
    validation = config.get("validation", {})
    allowed_warning_types = set(validation.get("allowed_drc_warning_types", []))
    unallowed = []
    for item in drc_violations:
        severity = item.get("severity")
        kind = item.get("type")
        if severity != "warning" or kind not in allowed_warning_types:
            unallowed.append({"type": kind, "severity": severity, "description": item.get("description", "")})

    summary = {
        "erc_violations": len(erc_violations),
        "drc_violations": len(drc_violations),
        "drc_unconnected_items": len(unconnected),
        "unallowed_drc_violations": unallowed,
    }
    if erc_violations:
        raise SystemExit(f"ERC has {len(erc_violations)} violation(s); refusing order")
    if unconnected:
        raise SystemExit(f"DRC has {len(unconnected)} unconnected item(s); refusing order")
    if unallowed:
        raise SystemExit(f"DRC has unallowed violation(s): {json.dumps(unallowed, ensure_ascii=False)}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merged_private_config(
    config: dict[str, Any],
    config_path: Path,
    private_config_path: Path,
    site: str,
    surface_finish: str,
    order_channel: str,
    shipping_mode: str,
    confirm_mode: str,
) -> Path:
    private = load_json(private_config_path, default={})
    order = config.get("order", {})
    public_overlay = {
        "project_name": project_name(config, config_path),
        "gerber_zip": str(zip_path_for_config(config, config_path)),
        "order": {
            "project_name": project_name(config, config_path),
            "quantity": int(order.get("quantity", 5)),
            "material": order.get("material", "FR-4"),
            "layers": int(order.get("layers", config.get("board", {}).get("layers", 2))),
            "board_size": board_size_label(config),
            "thickness_mm": str(order.get("thickness_mm", "1.6")),
            "copper_weight": str(order.get("copper_weight", "1 oz")),
            "solder_mask": str(order.get("solder_mask", "green")),
            "silkscreen": str(order.get("silkscreen", "white")),
            "surface_finish": surface_finish,
            "surface_finish_site": site,
            "compensation": order.get("compensation", "按标准合同常规处理"),
            "confirm_mode": confirm_mode,
            "shipping_mode": shipping_mode,
            "order_channel": order_channel,
            "smt": order.get("smt", "not_needed"),
            "stencil": order.get("stencil", "not_needed"),
            "pcb_assembly": "disabled",
        },
    }
    merged = deep_merge(private, public_overlay)
    DEFAULT_GENERATED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out = DEFAULT_GENERATED_CONFIG_DIR / f"{project_name(config, config_path)}-{site}.json"
    write_json(out, merged, private=True)
    return out


def run_and_log(command: list[str], env: dict[str, str], log_path: Path, dry_run: bool = False) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("command=" + " ".join(command))
    print(f"log={log_path}")
    if dry_run:
        return 0
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n\n# {datetime.now().isoformat(timespec='seconds')}\n")
        log.write("command=" + " ".join(command) + "\n")
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log.write(line)
        return proc.wait()


def place(args: argparse.Namespace) -> None:
    config_path = args.config.resolve()
    config = load_json(config_path)
    package_gerbers(config, config_path)
    validate_reports(config, config_path)
    surface_finish = choose_surface_finish(config, args.site, args.surface_finish)
    order = config.get("order", {})
    order_channel = args.order_channel or order.get("order_channel") or "web"
    shipping_mode = args.shipping_mode or order.get("shipping_mode") or "separate"
    confirm_mode = args.confirm_mode or order.get("confirm_mode") or "manual"
    merged_config = merged_private_config(
        config,
        config_path,
        args.private_config,
        args.site,
        surface_finish,
        order_channel,
        shipping_mode,
        confirm_mode,
    )

    zip_path = zip_path_for_config(config, config_path)
    if args.site == "china":
        script = SCRIPT_DIR / "quick_order_china.sh"
    else:
        script = SCRIPT_DIR / "quick_order_global.sh"
    env = os.environ.copy()
    env.update(
        {
            "JLCPCB_ORDER_CONFIG": str(merged_config),
            "JLCPCB_SURFACE_FINISH": surface_finish,
            "JLCPCB_SHIPPING_MODE": shipping_mode,
            "JLCPCB_ORDER_CHANNEL": order_channel,
            "JLCPCB_CONFIRM_MODE": confirm_mode,
            "JLCPCB_ALLOW_SUBMIT": "1" if args.allow_submit else "0",
            "JLCPCB_SCREENSHOT": str(Path("~/.config/jlcpcb-order/screenshots").expanduser() / f"{project_name(config, config_path)}-{args.site}.png"),
        }
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = DEFAULT_RUN_LOG_DIR / f"{project_name(config, config_path)}-{args.site}-{stamp}.log"
    rc = run_and_log([str(script), str(zip_path)], env, log_path, dry_run=args.dry_run)
    if rc != 0:
        raise SystemExit(rc)
    print(f"surface_finish={surface_finish}")
    print(f"merged_private_config={merged_config}")


def status(args: argparse.Namespace) -> None:
    script = SCRIPT_DIR / "jlc_order_cdp.py"
    env = os.environ.copy()
    if args.private_config.exists():
        env["JLCPCB_ORDER_CONFIG"] = str(args.private_config)
    rc = run_and_log([sys.executable, str(script), "--config", str(args.private_config), "status"], env, DEFAULT_RUN_LOG_DIR / "status.log", dry_run=args.dry_run)
    if rc != 0:
        raise SystemExit(rc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Public board order config JSON.")
    parser.add_argument("--private-config", type=Path, default=DEFAULT_PRIVATE_CONFIG)
    parser.add_argument("--site", choices=["china", "global"], default="china")
    parser.add_argument("--surface-finish", help="Override selected surface finish label.")
    parser.add_argument("--order-channel", choices=["web", "assistant"])
    parser.add_argument("--shipping-mode", choices=["separate", "combined"])
    parser.add_argument("--confirm-mode", choices=["manual", "auto"])
    parser.add_argument("--allow-submit", action="store_true", help="Allow final submit to review/payment boundary.")
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("package").set_defaults(func=lambda args: package_gerbers(load_json(args.config), args.config.resolve()))
    sub.add_parser("validate").set_defaults(func=lambda args: validate_reports(load_json(args.config), args.config.resolve()))
    sub.add_parser("place").set_defaults(func=place)
    sub.add_parser("status").set_defaults(func=status)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

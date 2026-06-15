#!/usr/bin/env python3
"""Generate a Lumileds LXCL_MN08_4000 KiCad board without the series resistor."""

from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REF_DIR = ROOT / "pcb/nhi-pcb/nhi-pcb/leds/lumileds"
OUT_DIR = ROOT / "pcb/lumileds-no-resistor"
ARTIFACT_DIR = OUT_DIR / "artifacts"
GERBER_DIR = OUT_DIR / "gerber"
FOOTPRINT_DIR = OUT_DIR / "footprints.pretty"
SYMBOL_LIB = OUT_DIR / "symbols.kicad_sym"
BOARD_NAME = "lumileds-no-resistor"
OLD_NAME = "lumileds"


def remove_block(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"marker not found: {marker}")

    line_start = text.rfind("\n", 0, start) + 1
    depth = 0
    in_string = False
    escape = False
    end = None

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = index + 1
                while end < len(text) and text[end] in " \t\r\n":
                    end += 1
                break

    if end is None:
        raise ValueError(f"unterminated block for marker: {marker}")
    return text[:line_start] + text[end:]


def extract_block(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"marker not found: {marker}")

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError(f"unterminated block for marker: {marker}")


def remove_wire(text: str, start_xy: str, end_xy: str) -> str:
    marker = f"(wire (pts (xy {start_xy}) (xy {end_xy}))"
    return remove_block(text, marker)


def update_project() -> None:
    src = REF_DIR / f"{OLD_NAME}.kicad_pro"
    dst = OUT_DIR / f"{BOARD_NAME}.kicad_pro"
    data = json.loads(src.read_text())
    data["meta"]["filename"] = f"{BOARD_NAME}.kicad_pro"
    for sheet in data.get("sheets", []):
        if len(sheet) == 2:
            sheet[1] = ""
    dst.write_text(json.dumps(data, indent=2) + "\n")


def update_schematic() -> None:
    src = REF_DIR / f"{OLD_NAME}.kicad_sch"
    dst = OUT_DIR / f"{BOARD_NAME}.kicad_sch"
    text = src.read_text()
    text = text.replace(f"{OLD_NAME}.kicad_sch", f"{BOARD_NAME}.kicad_sch")
    text = text.replace('(project "lumileds"', f'(project "{BOARD_NAME}"')
    text = remove_block(text, '(symbol "Device:R_US"')
    text = remove_block(text, '(symbol (lib_id "Device:R_US")')

    for a, b in [
        ("118.11 78.74", "118.11 62.23"),
        ("130.81 62.23", "130.81 64.77"),
        ("132.08 78.74", "146.05 78.74"),
        ("118.11 62.23", "130.81 62.23"),
        ("130.81 64.77", "132.08 64.77"),
        ("132.08 72.39", "132.08 78.74"),
    ]:
        text = remove_wire(text, a, b)

    direct_wire = """  (wire (pts (xy 118.11 78.74) (xy 146.05 78.74))
    (stroke (width 0) (type default))
    (uuid 3b5f3789-608b-5049-9c92-2937640c9c9f)
  )
"""
    ground_wire = """  (wire (pts (xy 118.11 81.28) (xy 146.05 81.28))
    (stroke (width 0) (type default))
    (uuid b7cdf803-b9dc-4508-85c6-38cc3a18ff68)
  )
"""
    if "(wire (pts (xy 118.11 78.74) (xy 146.05 78.74))" not in text:
        if ground_wire in text:
            text = text.replace(ground_wire, direct_wire + ground_wire)
        else:
            ground_marker = "(wire (pts (xy 118.11 81.28) (xy 146.05 81.28))"
            text = text.replace(ground_marker, direct_wire + ground_marker, 1)
    dst.write_text(text)


def update_board() -> None:
    src = REF_DIR / f"{OLD_NAME}.kicad_pcb"
    dst = OUT_DIR / f"{BOARD_NAME}.kicad_pcb"
    text = src.read_text()
    text = text.replace(f"{OLD_NAME}.kicad_sch", f"{BOARD_NAME}.kicad_sch")
    text = text.replace(
        '(outputdirectory "../../gerber/pcb_printing_lumileds/")',
        '(outputdirectory "gerber/")',
    )
    text = text.replace(
        "${KICAD6_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Horizontal.wrl",
        "/usr/share/kicad/3dmodels/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Horizontal.step",
    )
    text = text.replace('  (net 3 "Net-(U1-VCC)")\n', "")
    text = remove_block(text, '(footprint "Resistor_SMD:R_0201_0603Metric"')
    text = text.replace(
        '(net 3 "Net-(U1-VCC)") (pinfunction "VCC")',
        '(net 2 "Net-(J1-Pin_2)") (pinfunction "VCC")',
    )

    for marker in [
        '(segment (start 155.86 98.46) (end 160 98.46)',
        '(segment (start 155.26 99.06) (end 155.86 98.46)',
        '(segment (start 153.81 98.25) (end 150 98.25)',
        '(segment (start 154.62 99.06) (end 153.81 98.25)',
    ]:
        text = remove_block(text, marker)

    direct_segments = """  (segment (start 160 98.46) (end 153.81 98.25) (width 0.25) (layer "F.Cu") (net 2) (tstamp 9e331dd6-769b-522d-9f99-e3f73283e208))
  (segment (start 153.81 98.25) (end 150 98.25) (width 0.25) (layer "F.Cu") (net 2) (tstamp 38f855b0-6a8b-51f0-b5a7-9e46d20304e4))
"""
    insert_after = '  (segment (start 150.25 101) (end 150 101.25) (width 0.25) (layer "F.Cu") (net 1) (tstamp 68fc38c1-6641-4985-8361-6adb08d65acf))\n'
    text = text.replace(insert_after, insert_after + direct_segments)
    dst.write_text(text)


def write_library_tables_and_custom_libs() -> None:
    FOOTPRINT_DIR.mkdir(parents=True, exist_ok=True)

    board_text = (REF_DIR / f"{OLD_NAME}.kicad_pcb").read_text()
    footprint = extract_block(board_text, '(footprint "Custom_Footprint_Library:LXCL_MN08_4000"')
    footprint = footprint.replace(
        '(footprint "Custom_Footprint_Library:LXCL_MN08_4000" (layer "F.Cu")',
        '(footprint "LXCL_MN08_4000"\n  (version 20240108)\n  (generator "labcanvas-lumileds-no-resistor-generator")\n  (layer "F.Cu")',
        1,
    )
    footprint = re.sub(r'\n\s+\(tstamp [^)]+\)', "", footprint)
    footprint = re.sub(r'\n\s+\(at 150 100 90\)', "", footprint, count=1)
    footprint = re.sub(r'\s+\(net \d+ "[^"]+"\)', "", footprint)
    for marker in ['(property "Sheetfile"', '(property "Sheetname"', '(path "']:
        if marker in footprint:
            footprint = remove_block(footprint, marker)
    (FOOTPRINT_DIR / "LXCL_MN08_4000.kicad_mod").write_text(footprint + "\n")

    sch_text = (REF_DIR / f"{OLD_NAME}.kicad_sch").read_text()
    symbol = extract_block(sch_text, '(symbol "Custom_Symbol_Library:LUMILEDS_4040_Spot_LED"')
    symbol = symbol.replace(
        '(symbol "Custom_Symbol_Library:LUMILEDS_4040_Spot_LED"',
        '(symbol "LUMILEDS_4040_Spot_LED"',
        1,
    )
    SYMBOL_LIB.write_text(
        f"""(kicad_symbol_lib
  (version 20230121)
  (generator "labcanvas-lumileds-no-resistor-generator")
{symbol}
)
"""
    )

    (OUT_DIR / "fp-lib-table").write_text(
        """(fp_lib_table
  (version 7)
  (lib (name "MountingHole") (type "KiCad") (uri "/usr/share/kicad/footprints/MountingHole.pretty") (options "") (descr "KiCad mounting holes"))
  (lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "/usr/share/kicad/footprints/Connector_PinHeader_2.54mm.pretty") (options "") (descr "KiCad 2.54 mm pin headers"))
  (lib (name "Custom_Footprint_Library") (type "KiCad") (uri "${KIPRJMOD}/footprints.pretty") (options "") (descr "Project-local Lumileds footprint"))
)
"""
    )
    (OUT_DIR / "sym-lib-table").write_text(
        """(sym_lib_table
  (version 7)
  (lib (name "Connector") (type "KiCad") (uri "/usr/share/kicad/symbols/Connector.kicad_sym") (options "") (descr "KiCad connector symbols"))
  (lib (name "Mechanical") (type "KiCad") (uri "/usr/share/kicad/symbols/Mechanical.kicad_sym") (options "") (descr "KiCad mechanical symbols"))
  (lib (name "Custom_Symbol_Library") (type "KiCad") (uri "${KIPRJMOD}/symbols.kicad_sym") (options "") (descr "Project-local Lumileds symbol"))
)
"""
    )


def write_bom() -> None:
    with (OUT_DIR / f"{BOARD_NAME}.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Id", "Designator", "Footprint", "Quantity", "Designation", "Supplier and ref"])
        writer.writerow([1, "H1,H2,H3,H4", "MountingHole_2.2mm_M2", 4, "MountingHole", ""])
        writer.writerow([2, "U1", "LXCL_MN08_4000", 1, "LXCL_MN08_4000", ""])
        writer.writerow([3, "J1", "PinHeader_1x02_P2.54mm_Horizontal", 1, "Conn_01x02_Pin", ""])


def write_docs() -> None:
    (OUT_DIR / ".gitignore").write_text("*.kicad_prl\nfp-info-cache\n")
    (OUT_DIR / "README.md").write_text(
        """# Lumileds No-Resistor PCB

Sibling board to `pcb/hybec-hbl-273-g4`, derived from the historical Lumileds reference board at
`pcb/nhi-pcb/nhi-pcb/leds/lumileds`.

This version keeps the same 24 mm circular outline, four M2 mounting holes, `LXCL_MN08_4000`
Lumileds footprint, and horizontal 1x2 power header. The original `R1` 1.8 ohm 0201 series
resistor is removed; `J1 Pin_2` routes directly to `U1 VCC`.

![Full board render](artifacts/lumileds-no-resistor-render-full.png)

## Files

- `lumileds-no-resistor.kicad_pcb` - KiCad board.
- `lumileds-no-resistor.kicad_sch` - matching schematic with no resistor symbol.
- `lumileds-no-resistor.csv` - BOM without `R1`.
- `generate_lumileds_no_resistor_board.py` - deterministic generator from the reference design.
- `fp-lib-table`, `sym-lib-table`, `footprints.pretty/`, `symbols.kicad_sym` - local library bindings.
- `artifacts/` - ERC/DRC reports, STEP export, and rendered previews.
- `gerber/` - Gerber and drill files for fabrication review.

## Validation Status

- KiCad CLI 10.0.3.
- ERC: 0 violations.
- DRC: 0 unconnected items; 5 warnings remain from copied reference geometry (`lib_footprint_mismatch` x2 and connector silkscreen clipped by the circular board edge x3).
- STEP export uses the installed KiCad 10 pin-header model at `/usr/share/kicad/3dmodels/...Horizontal.step`.

## Validate

```bash
kicad-cli sch erc --format json --severity-all -o artifacts/erc.json lumileds-no-resistor.kicad_sch
kicad-cli pcb drc --format json --severity-all -o artifacts/drc.json lumileds-no-resistor.kicad_pcb
kicad-cli pcb export step --force --include-pads --include-tracks --include-silkscreen --include-soldermask -o artifacts/lumileds-no-resistor.step lumileds-no-resistor.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab --precision 6 -o gerber lumileds-no-resistor.kicad_pcb
kicad-cli pcb export drill --generate-map --map-format svg --generate-report --report-path artifacts/drill-report.txt -o gerber lumileds-no-resistor.kicad_pcb
xvfb-run -a kicad-cli pcb render --output artifacts/lumileds-no-resistor-render-full.png --width 1400 --height 1000 --background opaque --quality high --floor --perspective --rotate 315,0,35 --zoom 0.95 lumileds-no-resistor.kicad_pcb
```
"""
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    GERBER_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REF_DIR / "fp-info-cache", OUT_DIR / "fp-info-cache")
    update_project()
    update_schematic()
    update_board()
    write_library_tables_and_custom_libs()
    write_bom()
    write_docs()


if __name__ == "__main__":
    main()

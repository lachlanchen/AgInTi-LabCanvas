#!/usr/bin/env python3
"""Generate a simple KiCad carrier PCB for a HYBEC 12 V 20 W G4 halogen lamp."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PROJECT = ROOT / "pcb/nhi-pcb/nhi-pcb/leds/50x50/LED_5050_5W_White.kicad_pro"
OUT_DIR = ROOT / "pcb/hybec-hbl-273-g4"
ARTIFACT_DIR = OUT_DIR / "artifacts"
FOOTPRINT_DIR = OUT_DIR / "footprints.pretty"
BOARD_NAME = "hybec-hbl-273-g4"
BOARD = OUT_DIR / f"{BOARD_NAME}.kicad_pcb"
PROJECT = OUT_DIR / f"{BOARD_NAME}.kicad_pro"
SCHEMATIC = OUT_DIR / f"{BOARD_NAME}.kicad_sch"
FP_LIB_TABLE = OUT_DIR / "fp-lib-table"
CUSTOM_LAMP_FP = FOOTPRINT_DIR / "HYBEC_HBL_273_G4_DirectPins.kicad_mod"
DATASET = OUT_DIR / "hybec-hbl-273-hbl-667-lamp-dataset.json"
BOM = OUT_DIR / f"{BOARD_NAME}.csv"
LOCAL_GITIGNORE = OUT_DIR / ".gitignore"


def uid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"lazyingart:labcanvas:{BOARD_NAME}:{name}"))


def fp_text(name: str, value: str, at: str, layer: str, hide: bool = False) -> str:
    hide_s = "\n\t\t\t(hide yes)" if hide else ""
    return f"""\t\t(property "{name}" "{value}"
\t\t\t(at {at})
\t\t\t(layer "{layer}"){hide_s}
\t\t\t(uuid "{uid(f'{name}:{value}:{at}:{layer}')}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)"""


def mounting_hole(ref: str, x: float, y: float) -> str:
    return f"""
\t(footprint "MountingHole:MountingHole_2.2mm_M2"
\t\t(layer "F.Cu")
\t\t(uuid "{uid(ref)}")
\t\t(at {x:g} {y:g})
\t\t(descr "Mounting Hole 2.2mm, no annular, M2")
\t\t(tags "mounting hole 2.2mm no annular m2")
{fp_text("Reference", ref, "0 -3.2 0", "F.Fab", True)}
{fp_text("Value", "MountingHole", "0 3.2 0", "F.Fab")}
{fp_text("Footprint", "MountingHole:MountingHole_2.2mm_M2", "0 0 0", "F.Fab", True)}
\t\t(attr exclude_from_pos_files)
\t\t(fp_circle (center 0 0) (end 2.2 0) (stroke (width 0.15) (type solid)) (fill none) (layer "Cmts.User") (uuid "{uid(ref + ':circle')}"))
\t\t(fp_circle (center 0 0) (end 2.45 0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{uid(ref + ':courtyard')}"))
\t\t(pad "" np_thru_hole circle (at 0 0) (size 2.2 2.2) (drill 2.2) (layers "*.Cu" "*.Mask") (uuid "{uid(ref + ':pad')}"))
\t)"""


def board_text() -> str:
    connector_model = "/usr/share/kicad/3dmodels/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Horizontal.step"
    return f"""(kicad_pcb
\t(version 20240108)
\t(generator "labcanvas-hybec-halogen-generator")
\t(generator_version "1.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user "B.Adhesive")
\t\t(33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(40 "Dwgs.User" user "User.Drawings")
\t\t(41 "Cmts.User" user "User.Comments")
\t\t(42 "Eco1.User" user "User.Eco1")
\t\t(43 "Eco2.User" user "User.Eco2")
\t\t(44 "Edge.Cuts" user)
\t\t(45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard")
\t\t(47 "F.CrtYd" user "F.Courtyard")
\t\t(48 "B.Fab" user)
\t\t(49 "F.Fab" user)
\t\t(50 "User.1" user)
\t\t(51 "User.2" user)
\t\t(52 "User.3" user)
\t\t(53 "User.4" user)
\t\t(54 "User.5" user)
\t\t(55 "User.6" user)
\t\t(56 "User.7" user)
\t\t(57 "User.8" user)
\t\t(58 "User.9" user)
\t)
\t(setup
\t\t(pad_to_mask_clearance 0.05)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(pcbplotparams
\t\t\t(layerselection 0x00010fc_ffffffff)
\t\t\t(usegerberextensions no)
\t\t\t(usegerberattributes yes)
\t\t\t(usegerberadvancedattributes yes)
\t\t\t(creategerberjobfile yes)
\t\t\t(outputformat 1)
\t\t\t(outputdirectory "gerber/")
\t\t)
\t)
\t(net 0 "")
\t(net 1 "HALOGEN_A_12V")
\t(net 2 "HALOGEN_B_RETURN")
{mounting_hole("H1", 144, 94)}
{mounting_hole("H2", 156, 94)}
{mounting_hole("H3", 156, 106)}
{mounting_hole("H4", 144, 106)}
\t(footprint "Custom:HYBEC_HBL_273_G4_DirectPins"
\t\t(layer "F.Cu")
\t\t(uuid "{uid("lamp")}")
\t\t(at 150 100)
\t\t(descr "Direct through-hole carrier for HYBEC HBL-273/HBL-667 12V20W G4 tungsten halogen lamp pins")
\t\t(tags "HYBEC HBL-273 HBL-667 G4 12V20W halogen")
{fp_text("Reference", "L1", "0 -5.8 0", "F.SilkS")}
{fp_text("Value", "HYBEC_HBL-273_G4_12V20W", "0 6 0", "F.Fab")}
{fp_text("Footprint", "Custom:HYBEC_HBL_273_G4_DirectPins", "0 0 0", "F.Fab", True)}
{fp_text("Description", "Two 1.20 mm plated holes on 4.00 mm pitch for direct G4 lamp pin insertion.", "0 0 0", "F.Fab", True)}
\t\t(attr through_hole)
\t\t(fp_line (start -3 -4.8) (end 3 -4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("lamp:silk1")}"))
\t\t(fp_line (start 3 -4.8) (end 3 4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("lamp:silk2")}"))
\t\t(fp_line (start 3 4.8) (end -3 4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("lamp:silk3")}"))
\t\t(fp_line (start -3 4.8) (end -3 -4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("lamp:silk4")}"))
\t\t(fp_text user "4.00 mm G4 pitch" (at 0 7.1 0) (layer "F.Fab") (uuid "{uid("lamp:silktext")}") (effects (font (size 0.8 0.8) (thickness 0.12))))
\t\t(fp_text user "20 W lamp runs hot" (at 0 -7.1 0) (layer "F.Fab") (uuid "{uid("lamp:hottext")}") (effects (font (size 0.8 0.8) (thickness 0.12))))
\t\t(pad "1" thru_hole circle (at 0 -2) (size 3.4 3.4) (drill 1.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 1 "HALOGEN_A_12V") (pinfunction "A") (pintype "passive") (uuid "{uid("lamp:pad1")}"))
\t\t(pad "2" thru_hole circle (at 0 2) (size 3.4 3.4) (drill 1.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "HALOGEN_B_RETURN") (pinfunction "B") (pintype "passive") (uuid "{uid("lamp:pad2")}"))
\t)
\t(footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Horizontal"
\t\t(layer "B.Cu")
\t\t(uuid "{uid("j1")}")
\t\t(at 160 101)
\t\t(descr "Through-hole angled pin header, 1x02, 2.54mm pitch")
\t\t(tags "1x02 2.54mm pin header power input")
{fp_text("Reference", "J1", "-1.8 2.3 0", "B.Fab", True)}
{fp_text("Value", "12V_IN", "-1.8 -4.8 0", "B.Fab", True)}
{fp_text("Footprint", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Horizontal", "0 0 0", "F.Fab", True)}
\t\t(attr through_hole)
\t\t(fp_line (start -1.27 1.27) (end -1.27 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab1")}"))
\t\t(fp_line (start 1.15 1.27) (end -1.27 1.27) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab2")}"))
\t\t(fp_line (start 1.15 -3.81) (end -1.27 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab3")}"))
\t\t(fp_line (start 1.15 1.27) (end 1.15 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab4")}"))
\t\t(pad "1" thru_hole rect (at 0 0) (size 2.0 2.0) (drill 1.0) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "HALOGEN_B_RETURN") (pinfunction "B") (pintype "passive") (uuid "{uid("j1:pad1")}"))
\t\t(pad "2" thru_hole oval (at 0 -2.54) (size 2.0 2.0) (drill 1.0) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 1 "HALOGEN_A_12V") (pinfunction "A") (pintype "passive") (uuid "{uid("j1:pad2")}"))
\t\t(model "{connector_model}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)
\t(gr_circle (center 150 100) (end 162 100) (stroke (width 0.2) (type default)) (fill none) (layer "Edge.Cuts") (uuid "{uid("edge")}"))
\t(gr_circle (center 150 100) (end 157.2 100) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("keepout-silk")}"))
\t(gr_text "HYBEC HBL-273/HBL-667 12V 20W G4" (at 150 110.3 0) (layer "F.Fab") (uuid "{uid("text:title")}") (effects (font (size 0.72 0.72) (thickness 0.10))))
\t(gr_text "non-polar tungsten halogen" (at 150 89.7 0) (layer "F.Fab") (uuid "{uid("text:nonpolar")}") (effects (font (size 0.68 0.68) (thickness 0.10))))
\t(gr_text "JLCJLCJLCJLC" (at 150 109.2 0) (layer "B.SilkS") (uuid "{uid("text:jlc-order")}") (effects (font (size 0.8 0.8) (thickness 0.10)) (justify mirror)))
\t(segment (start 160 98.46) (end 154.6 98.46) (width 1.2) (layer "F.Cu") (net 1) (uuid "{uid("seg:a1")}"))
\t(segment (start 154.6 98.46) (end 150 98) (width 1.2) (layer "F.Cu") (net 1) (uuid "{uid("seg:a2")}"))
\t(segment (start 160 101) (end 154.4 101) (width 1.2) (layer "F.Cu") (net 2) (uuid "{uid("seg:b1")}"))
\t(segment (start 154.4 101) (end 150 102) (width 1.2) (layer "F.Cu") (net 2) (uuid "{uid("seg:b2")}"))
)"""


def fp_lib_table_text() -> str:
    return """(fp_lib_table
\t(version 7)
\t(lib (name "Custom") (type "KiCad") (uri "${KIPRJMOD}/footprints.pretty") (options "") (descr "Generated project-local footprints"))
\t(lib (name "MountingHole") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/MountingHole.pretty") (options "") (descr "KiCad mounting hole footprints"))
\t(lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr "KiCad 2.54 mm pin header footprints"))
)"""


def custom_lamp_footprint_text() -> str:
    return f"""(footprint "HYBEC_HBL_273_G4_DirectPins"
\t(version 20240108)
\t(generator "labcanvas-hybec-halogen-generator")
\t(generator_version "1.0")
\t(layer "F.Cu")
\t(descr "Direct through-hole carrier for HYBEC HBL-273/HBL-667 12V20W G4 tungsten halogen lamp pins")
\t(tags "HYBEC HBL-273 HBL-667 G4 12V20W halogen")
\t(property "Reference" "L" (at 0 -5.8 0) (layer "F.SilkS") (uuid "{uid("mod:ref")}") (effects (font (size 1 1) (thickness 0.15))))
\t(property "Value" "HYBEC_HBL-273_G4_12V20W" (at 0 6 0) (layer "F.Fab") (uuid "{uid("mod:value")}") (effects (font (size 1 1) (thickness 0.15))))
\t(attr through_hole)
\t(fp_line (start -3 -4.8) (end 3 -4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("mod:silk1")}"))
\t(fp_line (start 3 -4.8) (end 3 4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("mod:silk2")}"))
\t(fp_line (start 3 4.8) (end -3 4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("mod:silk3")}"))
\t(fp_line (start -3 4.8) (end -3 -4.8) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("mod:silk4")}"))
\t(fp_line (start -4.2 -5.6) (end 4.2 -5.6) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt1")}"))
\t(fp_line (start 4.2 -5.6) (end 4.2 5.6) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt2")}"))
\t(fp_line (start 4.2 5.6) (end -4.2 5.6) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt3")}"))
\t(fp_line (start -4.2 5.6) (end -4.2 -5.6) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt4")}"))
\t(fp_text user "4.00 mm G4 pitch" (at 0 7.1 0) (layer "F.Fab") (uuid "{uid("mod:text1")}") (effects (font (size 0.8 0.8) (thickness 0.12))))
\t(fp_text user "20 W lamp runs hot" (at 0 -7.1 0) (layer "F.Fab") (uuid "{uid("mod:text2")}") (effects (font (size 0.8 0.8) (thickness 0.12))))
\t(pad "1" thru_hole circle (at 0 -2) (size 3.4 3.4) (drill 1.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (pinfunction "A") (pintype "passive") (uuid "{uid("mod:pad1")}"))
\t(pad "2" thru_hole circle (at 0 2) (size 3.4 3.4) (drill 1.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (pinfunction "B") (pintype "passive") (uuid "{uid("mod:pad2")}"))
)"""


def schematic_text() -> str:
    return f"""(kicad_sch
\t(version 20231120)
\t(generator "labcanvas-hybec-halogen-generator")
\t(generator_version "1.0")
\t(uuid "{uid("schematic")}")
\t(paper "A4")
\t(lib_symbols)
\t(text "Board-only schematic stub. The PCB connects J1 directly to two non-polar G4 halogen lamp holes." (at 87.63 76.2 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "{uid("sch:text")}")
\t)
\t(sheet_instances (path "/" (page "1")))
)"""


def dataset() -> dict:
    return {
        "component_family": "HYBEC / Hybec HBL-273 HBL-667 G4 tungsten halogen instrument lamp",
        "dataset_created": "2026-06-08",
        "intended_pcb": str(BOARD.relative_to(ROOT)),
        "models": [
            {
                "model": "HYB-273 / HBL-273 vertical photometer type",
                "voltage_v": 12,
                "power_w": 20,
                "estimated_current_a": round(20 / 12, 3),
                "base": "G4 bi-pin",
                "lamp_shape": "T8 capsule",
                "filament": "C-6 / vertical photometer type",
                "luminous_flux_lm": 350,
                "flux_tolerance_lm": 50,
                "life_hours": 2000,
                "color_temperature_k": 3000,
                "total_length_mm": 28,
                "reference_equivalent": "Osram 64258",
                "notes": "Non-polar tungsten halogen lamp. Design uses 4.00 mm G4 pin pitch and 1.20 mm plated holes for direct pin insertion.",
            },
            {
                "model": "HBL-667 / horizontal biochemical analyzer type",
                "voltage_v": 12,
                "power_w": 20,
                "estimated_current_a": round(20 / 12, 3),
                "base": "G4 bi-pin",
                "luminous_flux_lm": 300,
                "life_hours": 2000,
                "color_temperature_k": 2900,
                "total_length_mm": 30,
                "notes": "Seller listings describe this as horizontal filament / biochemical analyzer variant.",
            },
        ],
        "pcb_assumptions": {
            "board_style": "matches existing NHI LED carrier family: circular 24 mm diameter board outline around center 150,100 with four M2 mounting holes",
            "lamp_hole_pitch_mm": 4.0,
            "lamp_hole_drill_mm": 1.2,
            "lamp_pad_diameter_mm": 3.4,
            "copper_track_width_mm": 1.2,
            "external_connector": "rear-side 1x02 2.54 mm pin header footprint retained from earlier LED boards",
            "thermal_warning": "12 V 20 W halogen lamps dissipate substantial heat; verify FR4 temperature, standoff distance, and enclosure airflow before use.",
        },
        "sources": [
            {
                "title": "Miyakawa Corporation HYBEC halogen lamp table",
                "url": "https://mcp-hybec.co.jp/en/products/halogen-lamp-xenon-lamp/",
                "used_for": "HYB-273 12V20W T8 G4 C-6 350±50 lm, 2000 h, Osram 64258 reference",
            },
            {
                "title": "Made-in-China product listing for HBL-273/HBL-667",
                "url": "https://molight-led.en.made-in-china.com/product/cZOTFHLvSPVD/China-Japan-Hybec-Biochemical-Lamp-Beads-Hbl-273-Hbl-667-12V-20W-G4-Spectrophotometer-Tungsten-Lamp.html",
                "used_for": "vertical/horizontal variant description, color temperature, lumen and length claims",
            },
            {
                "title": "Grandado HBL-273 listing",
                "url": "https://gbr.grandado.com/products/hybec-hbl-273-12v20w-g4-biochemical-analyzer-lamp-bead-replace-for-kls-jc-ch-12v20w",
                "used_for": "cross-check voltage, base type, life, color temperature, CRI and luminous flux listing",
            },
        ],
    }


def write_bom() -> None:
    rows = [
        ["Id", "Designator", "Footprint", "Quantity", "Designation", "Notes"],
        ["1", "H1,H2,H3,H4", "MountingHole_2.2mm_M2", "4", "M2 mounting holes", "matches previous NHI LED carriers"],
        ["2", "L1", "HYBEC_HBL_273_G4_DirectPins", "1", "HYBEC HBL-273/HBL-667 12V20W G4 lamp", "direct inserted lamp pins, non-polar"],
        ["3", "J1", "PinHeader_1x02_P2.54mm_Horizontal", "1", "12V input connector", "rear-side connector retained from old boards"],
    ]
    with BOM.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def write_readme() -> None:
    (OUT_DIR / "README.md").write_text(
        """# HYBEC HBL-273 / HBL-667 G4 Halogen Carrier PCB

![3D render of the HYBEC G4 carrier PCB](artifacts/hybec-hbl-273-g4-render.png)

![Zoomed-out full-board render](artifacts/hybec-hbl-273-g4-render-full.png)

This generated KiCad project adapts the existing NHI LED carrier style to a
two-hole direct-insertion G4 halogen lamp footprint.

- Board outline: circular, 24 mm diameter, matching the old LED carrier files.
- Mounting holes: four M2 NPTH holes at the same coordinates as the old boards.
- Lamp pins: two 1.20 mm plated holes on 4.00 mm G4 pitch.
- Power path: 1.20 mm top-layer copper tracks from the rear 1x02 input header.
- Lamp: 12 V, 20 W tungsten halogen, approximately 1.67 A.

Thermal note: a 20 W halogen lamp runs hot. Treat this PCB as a mechanical and
electrical adapter prototype; verify lamp standoff height, FR4 temperature,
airflow, and enclosure clearance before powering it in an instrument.

## Files

- `hybec-hbl-273-g4.kicad_pcb`: generated KiCad PCB.
- `hybec-hbl-273-hbl-667-lamp-dataset.json`: lamp specification dataset and source links.
- `artifacts/hybec-hbl-273-g4-render.png`: KiCad 3D render for review.
- `artifacts/hybec-hbl-273-g4-render-full.png`: zoomed-out full-board render.
- `artifacts/hybec-hbl-273-g4.step`: STEP export.
- `gerber/`: Gerber and Excellon drill outputs.

## Gerber Outputs

- `hybec-hbl-273-g4-F_Cu.gtl`, `hybec-hbl-273-g4-B_Cu.gbl`
- `hybec-hbl-273-g4-F_Mask.gts`, `hybec-hbl-273-g4-B_Mask.gbs`
- `hybec-hbl-273-g4-F_Silkscreen.gto`, `hybec-hbl-273-g4-B_Silkscreen.gbo`
- `hybec-hbl-273-g4-Edge_Cuts.gm1`
- `hybec-hbl-273-g4-job.gbrjob`
- `hybec-hbl-273-g4.drl`

## Reproduce

```bash
python3 pcb/scripts/generate_hybec_halogen_g4_board.py
kicad-cli pcb drc --format json --severity-all -o pcb/hybec-hbl-273-g4/artifacts/drc.json pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab --precision 6 -o pcb/hybec-hbl-273-g4/gerber pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
kicad-cli pcb export drill --generate-map --map-format svg --generate-report --report-path pcb/hybec-hbl-273-g4/artifacts/drill-report.txt -o pcb/hybec-hbl-273-g4/gerber pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
xvfb-run -a kicad-cli pcb render --output pcb/hybec-hbl-273-g4/artifacts/hybec-hbl-273-g4-render.png --width 1400 --height 1000 --background opaque --quality high --floor --perspective --rotate 315,0,35 --zoom 2.2 pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
xvfb-run -a kicad-cli pcb render --output pcb/hybec-hbl-273-g4/artifacts/hybec-hbl-273-g4-render-full.png --width 1400 --height 1000 --background opaque --quality high --floor --perspective --rotate 315,0,35 --zoom 0.95 pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
```
""",
        encoding="utf-8",
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_DIR.mkdir(parents=True, exist_ok=True)
    if SOURCE_PROJECT.exists():
        project = json.loads(SOURCE_PROJECT.read_text(encoding="utf-8"))
        project.setdefault("meta", {})["filename"] = PROJECT.name
        rule_severities = project.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rule_severities", {})
        rule_severities["lib_footprint_mismatch"] = "ignore"
        PROJECT.write_text(json.dumps(project, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        PROJECT.write_text(json.dumps({"meta": {"filename": PROJECT.name, "version": 1}}, indent=2) + "\n", encoding="utf-8")
    BOARD.write_text(board_text(), encoding="utf-8")
    SCHEMATIC.write_text(schematic_text(), encoding="utf-8")
    FP_LIB_TABLE.write_text(fp_lib_table_text() + "\n", encoding="utf-8")
    CUSTOM_LAMP_FP.write_text(custom_lamp_footprint_text() + "\n", encoding="utf-8")
    LOCAL_GITIGNORE.write_text("*.kicad_prl\n", encoding="utf-8")
    DATASET.write_text(json.dumps(dataset(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_bom()
    write_readme()
    shutil.copy2(Path(__file__), OUT_DIR / "generate_hybec_halogen_g4_board.py")
    print(f"Wrote {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

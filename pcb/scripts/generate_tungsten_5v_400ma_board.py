#!/usr/bin/env python3
"""Generate a KiCad carrier PCB for a 3 mm 5 V 400 mA tungsten lamp."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "pcb/tungsten-5v-400ma-3mm"
ARTIFACT_DIR = OUT_DIR / "artifacts"
GERBER_DIR = OUT_DIR / "gerber"
FOOTPRINT_DIR = OUT_DIR / "footprints.pretty"
MODEL_DIR = OUT_DIR / "3dmodels"
ORDER_DIR = OUT_DIR / "jlcpcb_order"
BOARD_NAME = "tungsten-5v-400ma-3mm"
BOARD = OUT_DIR / f"{BOARD_NAME}.kicad_pcb"
PROJECT = OUT_DIR / f"{BOARD_NAME}.kicad_pro"
SCHEMATIC = OUT_DIR / f"{BOARD_NAME}.kicad_sch"
FP_LIB_TABLE = OUT_DIR / "fp-lib-table"
CUSTOM_LAMP_FP = FOOTPRINT_DIR / "Japan_Tungsten_3mm_5V_400mA_1mmPitch.kicad_mod"
LAMP_MODEL = MODEL_DIR / "Japan_Tungsten_3mm_5V_400mA.step"
DATASET = OUT_DIR / "japan-tungsten-5v-400ma-3mm-lamp-dataset.json"
BOM = OUT_DIR / f"{BOARD_NAME}.csv"
LOCAL_GITIGNORE = OUT_DIR / ".gitignore"


PARAMS = {
    "board_diameter_mm": 24.0,
    "board_center_x": 150.0,
    "board_center_y": 100.0,
    "mount_hole_diameter_mm": 2.2,
    "mount_hole_pattern_mm": 12.0,
    "lamp_body_diameter_mm": 3.0,
    "lamp_voltage_v": 5.0,
    "lamp_current_ma": 400.0,
    "lamp_power_w": 2.0,
    "lamp_lead_diameter_mm": 0.25,
    "lamp_lead_pitch_mm": 1.0,
    "lamp_lead_drill_mm": 0.45,
    "lamp_pad_diameter_mm": 0.75,
    "lamp_hole_edge_gap_mm": 1.0 - 0.45,
    "lamp_pad_edge_gap_mm": 1.0 - 0.75,
    "trace_width_main_mm": 0.8,
    "trace_width_neck_mm": 0.3,
    "connector_pitch_mm": 2.54,
    "connector_drill_mm": 1.0,
    "connector_pad_mm": 2.0,
}


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
    p = PARAMS
    cx = p["board_center_x"]
    cy = p["board_center_y"]
    r = p["board_diameter_mm"] / 2.0
    mount = p["mount_hole_pattern_mm"] / 2.0
    connector_model = "/usr/share/kicad/3dmodels/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x02_P2.54mm_Horizontal.step"
    return f"""(kicad_pcb
\t(version 20240108)
\t(generator "labcanvas-tungsten-5v-generator")
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
\t(net 1 "LAMP_A_5V")
\t(net 2 "LAMP_B_RETURN")
{mounting_hole("H1", cx - mount, cy - mount)}
{mounting_hole("H2", cx + mount, cy - mount)}
{mounting_hole("H3", cx + mount, cy + mount)}
{mounting_hole("H4", cx - mount, cy + mount)}
\t(footprint "Custom:Japan_Tungsten_3mm_5V_400mA_1mmPitch"
\t\t(layer "F.Cu")
\t\t(uuid "{uid("lamp")}")
\t\t(at {cx:g} {cy:g})
\t\t(descr "3 mm non-polar 5 V 400 mA tungsten lamp, 0.25 mm feet, 1.0 mm pitch")
\t\t(tags "tungsten incandescent lamp 5V 400mA 3mm 1mm pitch")
{fp_text("Reference", "L1", "0 -3.3 0", "F.SilkS")}
{fp_text("Value", "3mm_5V_400mA_Tungsten", "0 3.5 0", "F.Fab")}
{fp_text("Footprint", "Custom:Japan_Tungsten_3mm_5V_400mA_1mmPitch", "0 0 0", "F.Fab", True)}
{fp_text("Description", "Two 0.45 mm plated holes on 1.00 mm pitch for 0.25 mm lamp feet.", "0 0 0", "F.Fab", True)}
\t\t(attr through_hole)
\t\t(fp_circle (center 0 0) (end 1.7 0) (stroke (width 0.10) (type solid)) (fill none) (layer "F.SilkS") (uuid "{uid("lamp:silk-body")}"))
\t\t(fp_circle (center 0 0) (end 1.5 0) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("lamp:fab-body")}"))
\t\t(fp_line (start -2.0 -2.2) (end 2.0 -2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("lamp:crt1")}"))
\t\t(fp_line (start 2.0 -2.2) (end 2.0 2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("lamp:crt2")}"))
\t\t(fp_line (start 2.0 2.2) (end -2.0 2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("lamp:crt3")}"))
\t\t(fp_line (start -2.0 2.2) (end -2.0 -2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("lamp:crt4")}"))
\t\t(fp_text user "1.00 mm pitch / D0.45 drill" (at 0 2.75 0) (layer "F.Fab") (uuid "{uid("lamp:text-pitch")}") (effects (font (size 0.45 0.45) (thickness 0.07))))
\t\t(fp_text user "5V 400mA 2W non-polar" (at 0 -2.75 0) (layer "F.Fab") (uuid "{uid("lamp:text-power")}") (effects (font (size 0.45 0.45) (thickness 0.07))))
\t\t(pad "1" thru_hole circle (at 0 -0.5) (size {p['lamp_pad_diameter_mm']} {p['lamp_pad_diameter_mm']}) (drill {p['lamp_lead_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 1 "LAMP_A_5V") (pinfunction "A") (pintype "passive") (uuid "{uid("lamp:pad1")}"))
\t\t(pad "2" thru_hole circle (at 0 0.5) (size {p['lamp_pad_diameter_mm']} {p['lamp_pad_diameter_mm']}) (drill {p['lamp_lead_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "LAMP_B_RETURN") (pinfunction "B") (pintype "passive") (uuid "{uid("lamp:pad2")}"))
\t\t(model "${{KIPRJMOD}}/3dmodels/Japan_Tungsten_3mm_5V_400mA.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)
\t(footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Horizontal"
\t\t(layer "B.Cu")
\t\t(uuid "{uid("j1")}")
\t\t(at 160 101)
\t\t(descr "Through-hole angled pin header, 1x02, 2.54mm pitch")
\t\t(tags "1x02 2.54mm pin header power input")
{fp_text("Reference", "J1", "-1.8 2.3 0", "B.Fab", True)}
{fp_text("Value", "5V_IN", "-1.8 -4.8 0", "B.Fab", True)}
{fp_text("Footprint", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Horizontal", "0 0 0", "F.Fab", True)}
\t\t(attr through_hole)
\t\t(fp_line (start -1.27 1.27) (end -1.27 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab1")}"))
\t\t(fp_line (start 1.15 1.27) (end -1.27 1.27) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab2")}"))
\t\t(fp_line (start 1.15 -3.81) (end -1.27 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab3")}"))
\t\t(fp_line (start 1.15 1.27) (end 1.15 -3.81) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab4")}"))
\t\t(pad "1" thru_hole rect (at 0 0) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "LAMP_B_RETURN") (pinfunction "B") (pintype "passive") (uuid "{uid("j1:pad1")}"))
\t\t(pad "2" thru_hole oval (at 0 -2.54) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 1 "LAMP_A_5V") (pinfunction "A") (pintype "passive") (uuid "{uid("j1:pad2")}"))
\t\t(model "{connector_model}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)
\t(gr_circle (center {cx:g} {cy:g}) (end {cx + r:g} {cy:g}) (stroke (width 0.2) (type default)) (fill none) (layer "Edge.Cuts") (uuid "{uid("edge")}"))
\t(gr_circle (center {cx:g} {cy:g}) (end {cx + 1.5:g} {cy:g}) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("lamp-body-fab")}"))
\t(gr_circle (center {cx:g} {cy:g}) (end {cx + 3.2:g} {cy:g}) (stroke (width 0.10) (type dash)) (fill none) (layer "F.Fab") (uuid "{uid("lamp-thermal-fab")}"))
\t(gr_text "3mm 5V 400mA W lamp" (at {cx:g} {cy + 10.2:g} 0) (layer "F.Fab") (uuid "{uid("text:title")}") (effects (font (size 0.62 0.62) (thickness 0.10))))
\t(gr_text "lead D0.25 / pitch 1.00 / hole D0.45" (at {cx:g} {cy - 10.2:g} 0) (layer "F.Fab") (uuid "{uid("text:dim")}") (effects (font (size 0.52 0.52) (thickness 0.08))))
\t(gr_text "JLCJLCJLCJLC" (at {cx:g} {cy + 9.2:g} 0) (layer "B.SilkS") (uuid "{uid("text:jlc-order")}") (effects (font (size 0.8 0.8) (thickness 0.10)) (justify mirror)))
\t(segment (start 160 98.46) (end 154 98.46) (width {p['trace_width_main_mm']}) (layer "F.Cu") (net 1) (uuid "{uid("seg:a1")}"))
\t(segment (start 154 98.46) (end 151.4 99.5) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:a2")}"))
\t(segment (start 151.4 99.5) (end 150 99.5) (width {p['trace_width_neck_mm']}) (layer "F.Cu") (net 1) (uuid "{uid("seg:a3")}"))
\t(segment (start 160 101) (end 154 101) (width {p['trace_width_main_mm']}) (layer "F.Cu") (net 2) (uuid "{uid("seg:b1")}"))
\t(segment (start 154 101) (end 151.4 100.5) (width 0.5) (layer "F.Cu") (net 2) (uuid "{uid("seg:b2")}"))
\t(segment (start 151.4 100.5) (end 150 100.5) (width {p['trace_width_neck_mm']}) (layer "F.Cu") (net 2) (uuid "{uid("seg:b3")}"))
)"""


def fp_lib_table_text() -> str:
    return """(fp_lib_table
\t(version 7)
\t(lib (name "Custom") (type "KiCad") (uri "${KIPRJMOD}/footprints.pretty") (options "") (descr "Generated project-local footprints"))
\t(lib (name "MountingHole") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/MountingHole.pretty") (options "") (descr "KiCad mounting hole footprints"))
\t(lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr "KiCad 2.54 mm pin header footprints"))
)"""


def custom_lamp_footprint_text() -> str:
    p = PARAMS
    return f"""(footprint "Japan_Tungsten_3mm_5V_400mA_1mmPitch"
\t(version 20240108)
\t(generator "labcanvas-tungsten-5v-generator")
\t(generator_version "1.0")
\t(layer "F.Cu")
\t(descr "3 mm non-polar 5 V 400 mA tungsten lamp, 0.25 mm feet, 1.0 mm pitch")
\t(tags "tungsten incandescent lamp 5V 400mA 3mm 1mm pitch")
\t(property "Reference" "L" (at 0 -3.3 0) (layer "F.SilkS") (uuid "{uid("mod:ref")}") (effects (font (size 1 1) (thickness 0.15))))
\t(property "Value" "3mm_5V_400mA_Tungsten" (at 0 3.5 0) (layer "F.Fab") (uuid "{uid("mod:value")}") (effects (font (size 1 1) (thickness 0.15))))
\t(attr through_hole)
\t(fp_circle (center 0 0) (end 1.7 0) (stroke (width 0.10) (type solid)) (fill none) (layer "F.SilkS") (uuid "{uid("mod:silk-body")}"))
\t(fp_circle (center 0 0) (end 1.5 0) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("mod:fab-body")}"))
\t(fp_line (start -2.0 -2.2) (end 2.0 -2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt1")}"))
\t(fp_line (start 2.0 -2.2) (end 2.0 2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt2")}"))
\t(fp_line (start 2.0 2.2) (end -2.0 2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt3")}"))
\t(fp_line (start -2.0 2.2) (end -2.0 -2.2) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "{uid("mod:crt4")}"))
\t(fp_text user "1.00 mm pitch / D0.45 drill" (at 0 2.75 0) (layer "F.Fab") (uuid "{uid("mod:text-pitch")}") (effects (font (size 0.45 0.45) (thickness 0.07))))
\t(fp_text user "5V 400mA 2W non-polar" (at 0 -2.75 0) (layer "F.Fab") (uuid "{uid("mod:text-power")}") (effects (font (size 0.45 0.45) (thickness 0.07))))
\t(pad "1" thru_hole circle (at 0 -0.5) (size {p['lamp_pad_diameter_mm']} {p['lamp_pad_diameter_mm']}) (drill {p['lamp_lead_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (pinfunction "A") (pintype "passive") (uuid "{uid("mod:pad1")}"))
\t(pad "2" thru_hole circle (at 0 0.5) (size {p['lamp_pad_diameter_mm']} {p['lamp_pad_diameter_mm']}) (drill {p['lamp_lead_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (pinfunction "B") (pintype "passive") (uuid "{uid("mod:pad2")}"))
\t(model "${{KIPRJMOD}}/3dmodels/Japan_Tungsten_3mm_5V_400mA.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
)"""


def schematic_text() -> str:
    return f"""(kicad_sch
\t(version 20231120)
\t(generator "labcanvas-tungsten-5v-generator")
\t(generator_version "1.0")
\t(uuid "{uid("schematic")}")
\t(paper "A4")
\t(lib_symbols)
\t(text "Board-only schematic stub. The PCB connects J1 directly to a non-polar 5 V 400 mA tungsten lamp." (at 87.63 76.2 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "{uid("sch:text")}")
\t)
\t(sheet_instances (path "/" (page "1")))
)"""


def dataset() -> dict:
    return {
        "component_family": "Japan original 3 mm non-polar tungsten filament lamp",
        "dataset_created": "2026-06-26",
        "intended_pcb": str(BOARD.relative_to(ROOT)),
        "source_status": "user-provided listing and dimensions; verify against physical sample before volume use",
        "listing_text": "5v 400 ma (10个)日本原装 2W 5V 400mA 无极性3mm钨丝灯泡 暖黄色光小灯珠",
        "electrical": {
            "voltage_v": 5.0,
            "current_ma": 400.0,
            "power_w": 2.0,
            "polarity": "non-polar tungsten filament",
            "expected_light": "warm yellow",
        },
        "mechanical": {
            "bulb_diameter_mm": 3.0,
            "lead_diameter_mm": 0.25,
            "lead_pitch_mm": 1.0,
            "selected_pcb_drill_mm": 0.45,
            "selected_pad_diameter_mm": 0.75,
            "hole_edge_gap_mm": 0.55,
            "pad_edge_gap_mm": 0.25,
        },
        "pcb_assumptions": {
            "board_style": "24 mm round carrier matching the existing LED/tungsten carrier family",
            "mounting": "four M2 NPTH holes on 12 x 12 mm pattern",
            "external_connector": "rear-side 1x02 2.54 mm horizontal pin header footprint",
            "surface_finish": "auto for JLC China; small 24 mm board usually uses lead-free HASL instead of OSP",
            "copper": "1 oz is sufficient for 400 mA on short traces; neck-down at lamp pads is 0.3 mm",
            "thermal_warning": "2 W tungsten lamp still runs hot; verify FR4 temperature, lamp standoff, and airflow.",
        },
        "manufacturing_sources": [
            {
                "title": "JLCPCB PCB manufacturing capabilities",
                "url": "https://jlcpcb.com/capabilities/pcb-capabilities",
                "used_for": "Current JLC manufacturing capability cross-check.",
            },
            {
                "title": "JLCPCB via design guidance",
                "url": "https://jlcpcb.com/blog/pcb-via-design-best-practices",
                "used_for": "0.3 mm and larger holes are easier; minimum mechanical drill increments and slot notes.",
            },
            {
                "title": "JLCPCB hole-size pitfall note",
                "url": "https://jlcpcb.com/blog/how-to-avoid-pitfalls-in-pcb-design",
                "used_for": "Small-hole warning; standard 0.3 mm hole guidance and slot cautions.",
            },
        ],
    }


def write_bom() -> None:
    rows = [
        ["Id", "Designator", "Footprint", "Quantity", "Designation", "Notes"],
        ["1", "H1,H2,H3,H4", "MountingHole_2.2mm_M2", "4", "M2 mounting holes", "same 24 mm carrier family"],
        ["2", "L1", "Japan_Tungsten_3mm_5V_400mA_1mmPitch", "1", "3 mm 5 V 400 mA tungsten lamp", "0.25 mm feet, 1.0 mm pitch, non-polar"],
        ["3", "J1", "PinHeader_1x02_P2.54mm_Horizontal", "1", "5 V input connector", "manual solder/use connector"],
    ]
    with BOM.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def write_readme() -> None:
    (OUT_DIR / "README.md").write_text(
        """# 3 mm 5 V 400 mA Tungsten Lamp Carrier PCB

![3D render of the 3 mm tungsten lamp carrier](artifacts/tungsten-5v-400ma-3mm-render.png)

![Zoomed-out full-board render](artifacts/tungsten-5v-400ma-3mm-render-full.png)

This generated KiCad project adapts the existing 24 mm round LED/lamp carrier
style to a very small non-polar tungsten filament lamp:

- Lamp listing: `2 W, 5 V, 400 mA, non-polar, 3 mm bulb, warm yellow`.
- Lead diameter: `0.25 mm`.
- Lead pitch: `1.00 mm`.
- PCB lamp holes: `0.45 mm` plated through holes on `1.00 mm` pitch.
- Lamp pads: `0.75 mm` diameter, leaving about `0.25 mm` copper-to-copper gap.
- Power path: short direct traces from the 1x02 input header, no resistor.
- Board outline: 24 mm circular carrier with four M2 mounting holes.

The drill is intentionally larger than the 0.25 mm foot so it is easier for JLC
to fabricate and easier to solder by hand. Verify fit with the actual lamp
before ordering a large quantity.

## Files

- `tungsten-5v-400ma-3mm.kicad_pcb`: generated KiCad PCB.
- `japan-tungsten-5v-400ma-3mm-lamp-dataset.json`: source assumptions and dimensions.
- `3dmodels/Japan_Tungsten_3mm_5V_400mA.step`: simple inspection proxy for the lamp.
- `artifacts/tungsten-5v-400ma-3mm-render.png`: close KiCad render.
- `artifacts/tungsten-5v-400ma-3mm-render-full.png`: full-board render.
- `artifacts/tungsten-5v-400ma-3mm.step`: KiCad STEP export.
- `gerber/`: Gerber and Excellon drill outputs.
- `jlcpcb_order/`: JLC China order package and settings.

## Thermal And Electrical Notes

- A 2 W tungsten bulb can still heat the PCB and nearby printed holder.
- Use direct 5 V supply. Do not add a series resistor unless the lamp sample
  behaves differently from the listing.
- Because the lamp is non-polar, the two lamp pads are named A/B only for routing.
- Keep the lamp body lifted above FR4 if the real sample radiates too much heat.

## Reproduce

```bash
python3 pcb/scripts/generate_tungsten_5v_400ma_board.py
kicad-cli sch erc --format json --severity-all -o pcb/tungsten-5v-400ma-3mm/artifacts/erc.json pcb/tungsten-5v-400ma-3mm/tungsten-5v-400ma-3mm.kicad_sch
kicad-cli pcb drc --format json --severity-all -o pcb/tungsten-5v-400ma-3mm/artifacts/drc.json pcb/tungsten-5v-400ma-3mm/tungsten-5v-400ma-3mm.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab --precision 6 -o pcb/tungsten-5v-400ma-3mm/gerber pcb/tungsten-5v-400ma-3mm/tungsten-5v-400ma-3mm.kicad_pcb
kicad-cli pcb export drill --generate-map --map-format svg --generate-report --report-path pcb/tungsten-5v-400ma-3mm/artifacts/drill-report.txt -o pcb/tungsten-5v-400ma-3mm/gerber pcb/tungsten-5v-400ma-3mm/tungsten-5v-400ma-3mm.kicad_pcb
```
""",
        encoding="utf-8",
    )


def write_order_files() -> None:
    ORDER_DIR.mkdir(parents=True, exist_ok=True)
    settings = {
        "schema": "agentic_tools/jlcpcb_order_agent/board-order-settings.v1",
        "manufacturer": "JLCPCB / JiaLiChuang",
        "project_name": BOARD_NAME,
        "order_type": "bare PCB fabrication only",
        "board_dir": "..",
        "gerber_dir": "../gerber",
        "gerber_zip": f"{BOARD_NAME}-jlcpcb-gerber.zip",
        "board": {
            "name": BOARD_NAME,
            "layers": 2,
            "shape": "round",
            "expected_size_mm": {"x": PARAMS["board_diameter_mm"], "y": PARAMS["board_diameter_mm"]},
            "delivery_format": "Single PCB",
        },
        "order": {
            "quantity": 5,
            "material": "FR-4",
            "layers": 2,
            "thickness_mm": 1.6,
            "copper_weight": "1 oz",
            "surface_finish": "auto-china-size-aware",
            "surface_finish_china": "auto",
            "surface_finish_global": "Lead-free HASL",
            "solder_mask": "green",
            "silkscreen": "white",
            "confirm_mode": "manual",
            "shipping_mode": "separate",
            "order_channel": "web",
            "compensation": "按标准合同常规处理",
            "smt": "not_needed",
            "stencil": "not_needed",
        },
        "disabled_options": {
            "pcb_assembly": True,
            "smt_stencil": True,
            "castellated_holes": True,
            "edge_plating": True,
        },
        "validation": {
            "allow_drc_warnings": True,
            "allowed_drc_warning_types": ["lib_footprint_mismatch", "silk_edge_clearance"],
        },
        "validation_reports": {
            "erc": "../artifacts/erc.json",
            "drc": "../artifacts/drc.json",
            "drill_report": "../artifacts/drill-report.txt",
        },
        "renders": {
            "close": f"../artifacts/{BOARD_NAME}-render.png",
            "full": f"../artifacts/{BOARD_NAME}-render-full.png",
        },
        "notes": [
            "China site should choose lead-free HASL automatically for this 24 mm board because OSP is rejected when any side is under 70 mm.",
            "No SMT, no stencil, no PCB assembly; the 3 mm tungsten lamp is installed manually.",
            "Verify actual 0.25 mm foot fit in 0.45 mm plated holes before ordering many copies.",
        ],
    }
    (ORDER_DIR / "order-settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ORDER_DIR / "README.md").write_text(
        f"""# JLCPCB Order Pack: {BOARD_NAME}

This folder is generated for bare-PCB fabrication only. The lamp and connector
are manually installed after receiving the boards.

## Package And Validate

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \\
  --config pcb/{BOARD_NAME}/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \\
  --config pcb/{BOARD_NAME}/jlcpcb_order/order-settings.json validate
```

## China Web Order

The board is 24 mm x 24 mm. For JLC China, the order wrapper should select
lead-free HASL instead of OSP because OSP was rejected for small boards in prior
orders.

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \\
  --config pcb/{BOARD_NAME}/jlcpcb_order/order-settings.json \\
  --site china \\
  --allow-submit \\
  place
```

The automation stops at the JLC review/payment boundary. Payment is manual.
""",
        encoding="utf-8",
    )


def write_project() -> None:
    PROJECT.write_text(
        json.dumps(
            {
                "meta": {"filename": PROJECT.name, "version": 1},
                "board": {
                    "design_settings": {
                        "rule_severities": {
                            "lib_footprint_mismatch": "ignore",
                            "silk_edge_clearance": "warning",
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_lamp_step_model() -> None:
    try:
        import cadquery as cq  # type: ignore
    except Exception:
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    pitch = PARAMS["lamp_lead_pitch_mm"]
    lead_r = PARAMS["lamp_lead_diameter_mm"] / 2.0
    lead_len = 4.5
    model = None
    for y in (-pitch / 2.0, pitch / 2.0):
        lead = cq.Workplane("XY").workplane(offset=0).center(0, y).circle(lead_r).extrude(lead_len)
        model = lead if model is None else model.union(lead)
    stem = cq.Workplane("XY").workplane(offset=3.2).circle(0.45).extrude(1.0)
    bulb = cq.Workplane("XY").sphere(1.5).translate((0, 0, 4.9))
    filament = cq.Workplane("XY").workplane(offset=4.9).box(0.9, 0.08, 0.08)
    model = model.union(stem).union(bulb).union(filament)
    cq.exporters.export(model, str(LAMP_MODEL))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    GERBER_DIR.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    write_project()
    BOARD.write_text(board_text(), encoding="utf-8")
    SCHEMATIC.write_text(schematic_text(), encoding="utf-8")
    FP_LIB_TABLE.write_text(fp_lib_table_text() + "\n", encoding="utf-8")
    CUSTOM_LAMP_FP.write_text(custom_lamp_footprint_text() + "\n", encoding="utf-8")
    LOCAL_GITIGNORE.write_text("*.kicad_prl\nfp-info-cache\n", encoding="utf-8")
    DATASET.write_text(json.dumps(dataset(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_bom()
    write_readme()
    write_order_files()
    write_lamp_step_model()
    shutil.copy2(Path(__file__), OUT_DIR / "generate_tungsten_5v_400ma_board.py")
    print(f"Wrote {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

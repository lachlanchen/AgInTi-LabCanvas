#!/usr/bin/env python3
"""Generate a KiCad carrier PCB for a WS2812B 5050 addressable RGB LED."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "pcb/ws2812b-5050-rgb-led"
ARTIFACT_DIR = OUT_DIR / "artifacts"
GERBER_DIR = OUT_DIR / "gerber"
FOOTPRINT_DIR = OUT_DIR / "footprints.pretty"
REFERENCE_DIR = OUT_DIR / "references"
ORDER_DIR = OUT_DIR / "jlcpcb_order"
BOARD_NAME = "ws2812b-5050-rgb-led"
BOARD = OUT_DIR / f"{BOARD_NAME}.kicad_pcb"
PROJECT = OUT_DIR / f"{BOARD_NAME}.kicad_pro"
SCHEMATIC = OUT_DIR / f"{BOARD_NAME}.kicad_sch"
FP_LIB_TABLE = OUT_DIR / "fp-lib-table"
LED_FP = FOOTPRINT_DIR / "WS2812B_5050_PLCC4.kicad_mod"
R_FP = FOOTPRINT_DIR / "R_0603.kicad_mod"
C_FP = FOOTPRINT_DIR / "C_0603.kicad_mod"
DATASET = OUT_DIR / "ws2812b-5050-rgb-led-dataset.json"
BOM = OUT_DIR / f"{BOARD_NAME}.csv"
LOCAL_GITIGNORE = OUT_DIR / ".gitignore"


PARAMS = {
    "board_diameter_mm": 24.0,
    "board_center_x": 150.0,
    "board_center_y": 100.0,
    "mount_hole_diameter_mm": 2.2,
    "mount_hole_pattern_mm": 12.0,
    "led_package": "5050 PLCC-4",
    "led_footprint": "LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm",
    "led_body_mm": [5.0, 5.0],
    "supply_nominal_v": 5.0,
    "supply_allowed_v": [3.5, 5.3],
    "recommended_logic_high": "0.7*VDD minimum",
    "data_rate_kbps": 800,
    "full_white_estimated_ma": 60,
    "din_series_resistor_ohm": 330,
    "decoupling_capacitor": "0.1 uF 0603 X7R close to VDD/VSS",
    "connector_pitch_mm": 2.54,
    "connector_drill_mm": 1.0,
    "connector_pad_mm": 2.0,
    "trace_width_power_mm": 0.5,
    "trace_width_data_mm": 0.25,
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


def led_footprint_block() -> str:
    cx = PARAMS["board_center_x"]
    cy = PARAMS["board_center_y"]
    model = "${KICAD10_3DMODEL_DIR}/LED_SMD.3dshapes/LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm.step"
    return f"""
\t(footprint "Custom:WS2812B_5050_PLCC4"
\t\t(layer "F.Cu")
\t\t(uuid "{uid("d1")}")
\t\t(at {cx:g} {cy:g})
\t\t(descr "WS2812B 5050 PLCC-4 addressable RGB LED; KiCad pad geometry")
\t\t(tags "WS2812B 5050 RGB LED NeoPixel addressable")
{fp_text("Reference", "D1", "0 -3.5 0", "F.SilkS")}
{fp_text("Value", "WS2812B_5050", "0 4 0", "F.Fab")}
{fp_text("Footprint", "Custom:WS2812B_5050_PLCC4", "0 0 0", "F.Fab", True)}
{fp_text("Description", "WS2812B 5050 RGB LED with integrated controller", "0 0 0", "F.Fab", True)}
\t\t(attr smd)
\t\t(fp_line (start -3.5 -2.75) (end -3.5 2.75) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("d1:silk1")}"))
\t\t(fp_line (start -3.5 -2.75) (end 3.5 -2.75) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("d1:silk2")}"))
\t\t(fp_line (start -3.5 2.75) (end 3.05 2.75) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("d1:silk3")}"))
\t\t(fp_line (start 3.05 2.75) (end 3.5 2.3) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("d1:silk4")}"))
\t\t(fp_line (start 3.5 2.3) (end 3.5 -2.75) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid("d1:silk5")}"))
\t\t(fp_line (start -2.5 -2.5) (end -2.5 2.5) (stroke (width 0.10) (type solid)) (layer "F.Fab") (uuid "{uid("d1:fab1")}"))
\t\t(fp_line (start -2.5 2.5) (end 2.0 2.5) (stroke (width 0.10) (type solid)) (layer "F.Fab") (uuid "{uid("d1:fab2")}"))
\t\t(fp_line (start 2.0 2.5) (end 2.5 2.0) (stroke (width 0.10) (type solid)) (layer "F.Fab") (uuid "{uid("d1:fab3")}"))
\t\t(fp_line (start 2.5 2.0) (end 2.5 -2.5) (stroke (width 0.10) (type solid)) (layer "F.Fab") (uuid "{uid("d1:fab4")}"))
\t\t(fp_line (start 2.5 -2.5) (end -2.5 -2.5) (stroke (width 0.10) (type solid)) (layer "F.Fab") (uuid "{uid("d1:fab5")}"))
\t\t(fp_rect (start -3.6 -2.85) (end 3.6 2.85) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{uid("d1:crtyd")}"))
\t\t(fp_text user "1" (at -4 -1.6 0) (layer "F.SilkS") (uuid "{uid("d1:pin1")}") (effects (font (size 0.8 0.8) (thickness 0.15))))
\t\t(pad "1" smd roundrect (at -2.45 -1.65) (size 1.5 0.9) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.1) (net 1 "+5V") (pinfunction "VDD") (pintype "power_in") (uuid "{uid("d1:pad1")}"))
\t\t(pad "2" smd roundrect (at -2.45 1.65) (size 1.5 0.9) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.1) (net 4 "DOUT") (pinfunction "DOUT") (pintype "output") (uuid "{uid("d1:pad2")}"))
\t\t(pad "3" smd roundrect (at 2.45 1.65) (size 1.5 0.9) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.1) (net 2 "GND") (pinfunction "VSS") (pintype "power_in") (uuid "{uid("d1:pad3")}"))
\t\t(pad "4" smd roundrect (at 2.45 -1.65) (size 1.5 0.9) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.1) (net 5 "DIN_LED") (pinfunction "DIN") (pintype "input") (uuid "{uid("d1:pad4")}"))
\t\t(model "{model}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)"""


def resistor_block() -> str:
    return f"""
\t(footprint "Custom:R_0603"
\t\t(layer "F.Cu")
\t\t(uuid "{uid("r1")}")
\t\t(at 156.3 98.35)
\t\t(descr "0603 resistor, simple local footprint")
{fp_text("Reference", "R1", "0 -1.1 0", "F.SilkS")}
{fp_text("Value", "330R", "0 1.1 0", "F.Fab")}
{fp_text("Footprint", "Custom:R_0603", "0 0 0", "F.Fab", True)}
\t\t(attr smd)
\t\t(fp_line (start -0.15 -0.48) (end 0.15 -0.48) (stroke (width 0.10) (type solid)) (layer "F.SilkS") (uuid "{uid("r1:silk1")}"))
\t\t(fp_line (start -0.15 0.48) (end 0.15 0.48) (stroke (width 0.10) (type solid)) (layer "F.SilkS") (uuid "{uid("r1:silk2")}"))
\t\t(fp_rect (start -1.55 -0.75) (end 1.55 0.75) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{uid("r1:crtyd")}"))
\t\t(fp_rect (start -0.8 -0.4) (end 0.8 0.4) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("r1:fab")}"))
\t\t(pad "1" smd roundrect (at -0.8 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.15) (net 5 "DIN_LED") (pinfunction "1") (pintype "passive") (uuid "{uid("r1:pad1")}"))
\t\t(pad "2" smd roundrect (at 0.8 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.15) (net 3 "DIN") (pinfunction "2") (pintype "passive") (uuid "{uid("r1:pad2")}"))
\t)"""


def capacitor_block() -> str:
    return f"""
\t(footprint "Custom:C_0603"
\t\t(layer "F.Cu")
\t\t(uuid "{uid("c1")}")
\t\t(at 151 104)
\t\t(descr "0603 capacitor, simple local footprint")
{fp_text("Reference", "C1", "0 -1.1 0", "F.Fab", True)}
{fp_text("Value", "0.1uF", "0 1.1 0", "F.Fab")}
{fp_text("Footprint", "Custom:C_0603", "0 0 0", "F.Fab", True)}
\t\t(attr smd)
\t\t(fp_line (start -0.15 -0.48) (end 0.15 -0.48) (stroke (width 0.10) (type solid)) (layer "F.SilkS") (uuid "{uid("c1:silk1")}"))
\t\t(fp_line (start -0.15 0.48) (end 0.15 0.48) (stroke (width 0.10) (type solid)) (layer "F.SilkS") (uuid "{uid("c1:silk2")}"))
\t\t(fp_rect (start -1.55 -0.75) (end 1.55 0.75) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{uid("c1:crtyd")}"))
\t\t(fp_rect (start -0.8 -0.4) (end 0.8 0.4) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{uid("c1:fab")}"))
\t\t(pad "1" smd roundrect (at -0.8 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.15) (net 2 "GND") (pinfunction "1") (pintype "passive") (uuid "{uid("c1:pad1")}"))
\t\t(pad "2" smd roundrect (at 0.8 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.15) (net 1 "+5V") (pinfunction "2") (pintype "passive") (uuid "{uid("c1:pad2")}"))
\t)"""


def connector_block() -> str:
    p = PARAMS
    model = "/usr/share/kicad/3dmodels/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x04_P2.54mm_Horizontal.step"
    return f"""
\t(footprint "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal"
\t\t(layer "B.Cu")
\t\t(uuid "{uid("j1")}")
\t\t(at 158.7 103.81)
\t\t(descr "Through-hole angled pin header, 1x04, 2.54mm pitch")
\t\t(tags "1x04 2.54mm pin header WS2812B")
{fp_text("Reference", "J1", "-1.8 2.3 0", "B.Fab", True)}
{fp_text("Value", "5V_GND_DIN_DOUT", "-1.8 -9.8 0", "B.Fab", True)}
{fp_text("Footprint", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal", "0 0 0", "F.Fab", True)}
\t\t(attr through_hole)
\t\t(fp_line (start -1.27 1.27) (end -1.27 -8.89) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab1")}"))
\t\t(fp_line (start 1.15 1.27) (end -1.27 1.27) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab2")}"))
\t\t(fp_line (start 1.15 -8.89) (end -1.27 -8.89) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab3")}"))
\t\t(fp_line (start 1.15 1.27) (end 1.15 -8.89) (stroke (width 0.10) (type solid)) (layer "B.Fab") (uuid "{uid("j1:fab4")}"))
\t\t(pad "1" thru_hole rect (at 0 0) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 1 "+5V") (pinfunction "5V") (pintype "power_in") (uuid "{uid("j1:pad1")}"))
\t\t(pad "2" thru_hole oval (at 0 -2.54) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "GND") (pinfunction "GND") (pintype "power_in") (uuid "{uid("j1:pad2")}"))
\t\t(pad "3" thru_hole oval (at 0 -5.08) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 3 "DIN") (pinfunction "DIN") (pintype "input") (uuid "{uid("j1:pad3")}"))
\t\t(pad "4" thru_hole oval (at 0 -7.62) (size {p['connector_pad_mm']} {p['connector_pad_mm']}) (drill {p['connector_drill_mm']}) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 4 "DOUT") (pinfunction "DOUT") (pintype "output") (uuid "{uid("j1:pad4")}"))
\t\t(model "{model}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)"""


def board_text() -> str:
    p = PARAMS
    cx = p["board_center_x"]
    cy = p["board_center_y"]
    r = p["board_diameter_mm"] / 2.0
    mount = p["mount_hole_pattern_mm"] / 2.0
    return f"""(kicad_pcb
\t(version 20240108)
\t(generator "labcanvas-ws2812b-generator")
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
\t\t(33 "F.Adhes" user)
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
\t(net 1 "+5V")
\t(net 2 "GND")
\t(net 3 "DIN")
\t(net 4 "DOUT")
\t(net 5 "DIN_LED")
{mounting_hole("H1", cx - mount, cy - mount)}
{mounting_hole("H2", cx + mount, cy - mount)}
{mounting_hole("H3", cx + mount, cy + mount)}
{mounting_hole("H4", cx - mount, cy + mount)}
{led_footprint_block()}
{resistor_block()}
{capacitor_block()}
{connector_block()}
\t(gr_circle (center {cx:g} {cy:g}) (end {cx + r:g} {cy:g}) (stroke (width 0.2) (type default)) (fill none) (layer "Edge.Cuts") (uuid "{uid("edge")}"))
\t(gr_text "WS2812B 5050 RGB" (at {cx:g} {cy + 10.2:g} 0) (layer "F.Fab") (uuid "{uid("text:title")}") (effects (font (size 0.62 0.62) (thickness 0.10))))
\t(gr_text "J1: 5V GND DIN DOUT" (at {cx:g} {cy - 10.2:g} 0) (layer "F.Fab") (uuid "{uid("text:pinout")}") (effects (font (size 0.52 0.52) (thickness 0.08))))
\t(gr_text "5V" (at 156.6 103.8 0) (layer "F.SilkS") (uuid "{uid("text:5v")}") (effects (font (size 0.8 0.8) (thickness 0.10))))
\t(gr_text "G" (at 156.7 101.25 0) (layer "F.SilkS") (uuid "{uid("text:gnd")}") (effects (font (size 0.8 0.8) (thickness 0.10))))
\t(gr_text "DI" (at 156.5 98.72 0) (layer "F.Fab") (uuid "{uid("text:din")}") (effects (font (size 0.8 0.8) (thickness 0.10))))
\t(gr_text "DO" (at 156.4 96.18 0) (layer "F.SilkS") (uuid "{uid("text:dout")}") (effects (font (size 0.8 0.8) (thickness 0.10))))
\t(gr_text "JLCJLCJLCJLC" (at {cx:g} {cy + 9.2:g} 0) (layer "B.SilkS") (uuid "{uid("text:jlc-order")}") (effects (font (size 0.8 0.8) (thickness 0.10)) (justify mirror)))
\t(segment (start 158.7 103.81) (end 151.8 104) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:5v1")}"))
\t(segment (start 151.8 104) (end 151.8 105) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:5v2")}"))
\t(segment (start 151.8 105) (end 145.8 105) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:5v3")}"))
\t(segment (start 145.8 105) (end 145.8 98.35) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:5v4")}"))
\t(segment (start 145.8 98.35) (end 147.55 98.35) (width 0.5) (layer "F.Cu") (net 1) (uuid "{uid("seg:5v5")}"))
\t(segment (start 158.7 101.27) (end 153.5 101.65) (width 0.5) (layer "F.Cu") (net 2) (uuid "{uid("seg:gnd1")}"))
\t(segment (start 153.5 101.65) (end 152.45 101.65) (width 0.5) (layer "F.Cu") (net 2) (uuid "{uid("seg:gnd2")}"))
\t(segment (start 150.2 104) (end 150.2 101.65) (width 0.3) (layer "F.Cu") (net 2) (uuid "{uid("seg:c1g")}"))
\t(segment (start 150.2 101.65) (end 152.45 101.65) (width 0.3) (layer "F.Cu") (net 2) (uuid "{uid("seg:c1g2")}"))
\t(segment (start 158.7 98.73) (end 157.1 98.35) (width 0.25) (layer "F.Cu") (net 3) (uuid "{uid("seg:din1")}"))
\t(segment (start 155.5 98.35) (end 152.45 98.35) (width 0.25) (layer "F.Cu") (net 5) (uuid "{uid("seg:dinled1")}"))
\t(segment (start 158.7 96.19) (end 156 96.2) (width 0.25) (layer "B.Cu") (net 4) (uuid "{uid("seg:dout1")}"))
\t(segment (start 156 96.2) (end 154.2 99.0) (width 0.25) (layer "B.Cu") (net 4) (uuid "{uid("seg:dout2")}"))
\t(segment (start 154.2 99.0) (end 154.2 102.8) (width 0.25) (layer "B.Cu") (net 4) (uuid "{uid("seg:dout3")}"))
\t(segment (start 154.2 102.8) (end 148.2 103.2) (width 0.25) (layer "B.Cu") (net 4) (uuid "{uid("seg:dout4")}"))
\t(via (at 148.2 103.2) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 4) (uuid "{uid("via:dout")}"))
\t(segment (start 148.2 103.2) (end 147.55 101.65) (width 0.25) (layer "F.Cu") (net 4) (uuid "{uid("seg:dout5")}"))
)"""


def fp_lib_table_text() -> str:
    return """(fp_lib_table
\t(version 7)
\t(lib (name "Custom") (type "KiCad") (uri "${KIPRJMOD}/footprints.pretty") (options "") (descr "Generated project-local footprints"))
\t(lib (name "MountingHole") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/MountingHole.pretty") (options "") (descr "KiCad mounting hole footprints"))
\t(lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr "KiCad 2.54 mm pin header footprints"))
)"""


def footprint_file_text(kind: str) -> str:
    if kind == "led":
        block = led_footprint_block().replace('\t(footprint "Custom:WS2812B_5050_PLCC4"', '(footprint "WS2812B_5050_PLCC4"', 1)
        block = block.replace(f'\n\t\t(uuid "{uid("d1")}")', "")
        return block.strip() + "\n"
    if kind == "r":
        block = resistor_block().replace('\t(footprint "Custom:R_0603"', '(footprint "R_0603"', 1)
        block = block.replace(f'\n\t\t(uuid "{uid("r1")}")', "")
        return block.strip() + "\n"
    if kind == "c":
        block = capacitor_block().replace('\t(footprint "Custom:C_0603"', '(footprint "C_0603"', 1)
        block = block.replace(f'\n\t\t(uuid "{uid("c1")}")', "")
        return block.strip() + "\n"
    raise ValueError(kind)


def schematic_text() -> str:
    return f"""(kicad_sch
\t(version 20231120)
\t(generator "labcanvas-ws2812b-generator")
\t(generator_version "1.0")
\t(uuid "{uid("schematic")}")
\t(paper "A4")
\t(lib_symbols)
\t(text "Board-only schematic stub. The PCB has one WS2812B 5050 LED, 330R DIN resistor, 0.1uF local decoupling, and 1x04 5V/GND/DIN/DOUT header." (at 65 76.2 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "{uid("sch:text")}")
\t)
\t(sheet_instances (path "/" (page "1")))
)"""


def dataset() -> dict:
    return {
        "component_family": "WS2812B 5050 addressable RGB LED with integrated IC",
        "dataset_created": "2026-07-06",
        "intended_pcb": str(BOARD.relative_to(ROOT)),
        "source_status": "datasheet-backed carrier; confirm exact vendor reel footprint before volume assembly",
        "user_listing_text": "WS2812B灯珠 5050RGB幻彩雾状LED发光二极管内置IC可编程贴片5V",
        "datasheet_sources": [
            {
                "title": "WS2812B Datasheet, WORLDSEMI CO., LIMITED, Jan 2016 V1.0",
                "url": "https://cdn.sparkfun.com/assets/e/6/1/f/4/WS2812B-LED-datasheet.pdf",
                "used_for": "5050 package, pin functions, supply range, protocol, and timing",
            },
            {
                "title": "WS2812B Datasheet mirror used by KiCad footprint metadata",
                "url": "https://cdn-shop.adafruit.com/datasheets/WS2812B.pdf",
                "used_for": "KiCad LED symbol/footprint cross-check and pin mapping",
            },
            {
                "title": "KiCad LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm footprint",
                "url": "file:///usr/share/kicad/footprints/LED_SMD.pretty/LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm.kicad_mod",
                "used_for": "Pad geometry and 3D model reference",
            },
        ],
        "pinout": {
            "1": "VDD / +5V",
            "2": "DOUT / cascaded data output",
            "3": "VSS / GND",
            "4": "DIN / data input",
        },
        "electrical": {
            "nominal_supply_v": 5.0,
            "absolute_supply_range_v": [3.5, 5.3],
            "normal_operating_condition_v": "4.5 to 5.5 V in datasheet electrical-characteristics table",
            "data_protocol": "single-wire NRZ, 24-bit GRB color stream",
            "data_rate_kbps": 800,
            "logic_high_requirement": "DIN high >= 0.7*VDD",
            "estimated_max_led_current_ma": 60,
        },
        "pcb_assumptions": {
            "board_style": "24 mm round carrier matching the existing LED/lamp carrier family",
            "mounting": "four M2 NPTH holes on 12 x 12 mm pattern",
            "connector": "rear-side 1x04 2.54 mm horizontal header with 5V, GND, DIN, DOUT",
            "din_series_resistor": "330 ohm 0603 near LED DIN pad",
            "decoupling": "0.1 uF 0603 capacitor near VDD/VSS",
            "trace_widths": {
                "power_mm": 0.5,
                "data_mm": 0.25,
            },
            "soldering": "manual soldering or JLC SMT if the exact WS2812B reel and orientation are matched later",
        },
    }


def write_bom() -> None:
    rows = [
        ["Id", "Designator", "Footprint", "Quantity", "Designation", "Notes"],
        ["1", "H1,H2,H3,H4", "MountingHole_2.2mm_M2", "4", "M2 mounting holes", "same 24 mm carrier family"],
        ["2", "D1", "WS2812B_5050_PLCC4", "1", "WS2812B 5050 addressable RGB LED", "pad 1 VDD, 2 DOUT, 3 VSS, 4 DIN"],
        ["3", "R1", "R_0603", "1", "330 ohm DIN series resistor", "place close to LED data input"],
        ["4", "C1", "C_0603", "1", "0.1 uF decoupling capacitor", "place close to VDD/VSS"],
        ["5", "J1", "PinHeader_1x04_P2.54mm_Horizontal", "1", "5V/GND/DIN/DOUT connector", "manual install"],
    ]
    with BOM.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def write_readme() -> None:
    (OUT_DIR / "README.md").write_text(
        """# WS2812B 5050 RGB LED Carrier PCB

![3D render of the WS2812B LED carrier](artifacts/ws2812b-5050-rgb-led-render.png)

![Zoomed-out full-board render](artifacts/ws2812b-5050-rgb-led-render-full.png)

This generated KiCad project adapts the existing 24 mm round LED carrier style
to a single WS2812B 5050 addressable RGB LED.

- Board outline: 24 mm circular carrier.
- Mounting: four M2 NPTH holes on a 12 x 12 mm pattern.
- LED: WS2812B 5050 PLCC-4, centered on the board.
- Header: 1x04 2.54 mm rear-side connector. Bottom-to-top in the render is
  `5V`, `GND`, `DIN`, `DOUT`.
- Input protection habit: `330R` 0603 series resistor on `DIN`.
- Local supply stability: `0.1 uF` 0603 capacitor close to LED `VDD`/`VSS`.

## Datasheet Notes

The WS2812B datasheet identifies the package as a 5050 integrated RGB LED and
controller. The pinout used here is:

1. `VDD`
2. `DOUT`
3. `VSS`
4. `DIN`

Run it from a nominal 5 V supply. If the controller is 3.3 V logic while the LED
is powered at 5 V, use a level shifter or verify that the DIN high level still
meets the datasheet threshold.

## Files

- `ws2812b-5050-rgb-led.kicad_pcb`: generated KiCad PCB.
- `ws2812b-5050-rgb-led-dataset.json`: source assumptions and dimensions.
- `references/`: downloaded datasheet copies when available.
- `artifacts/ws2812b-5050-rgb-led-render.png`: close KiCad render.
- `artifacts/ws2812b-5050-rgb-led-render-full.png`: full-board render.
- `artifacts/ws2812b-5050-rgb-led.step`: KiCad STEP export.
- `gerber/`: Gerber and Excellon drill outputs.
- `jlcpcb_order/`: optional JLC bare-board order package.

## Reproduce

```bash
python3 pcb/scripts/generate_ws2812b_5050_rgb_board.py
kicad-cli sch erc --format json --severity-all -o pcb/ws2812b-5050-rgb-led/artifacts/erc.json pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_sch
kicad-cli pcb drc --format json --severity-all -o pcb/ws2812b-5050-rgb-led/artifacts/drc.json pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab --precision 6 -o pcb/ws2812b-5050-rgb-led/gerber pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb
kicad-cli pcb export drill --generate-map --map-format svg --generate-report --report-path pcb/ws2812b-5050-rgb-led/artifacts/drill-report.txt -o pcb/ws2812b-5050-rgb-led/gerber pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb
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
            "compensation": "standard",
            "smt": "not_needed",
            "stencil": "not_needed",
        },
        "disabled_options": {
            "pcb_assembly": True,
            "smt_stencil": True,
            "castellated_holes": True,
            "edge_plating": True,
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
            "Bare PCB only; LED, R1, C1, and header are manually assembled unless a future SMT order has exact LCSC/JLC part mapping.",
            "China site may reject OSP for very small boards; let the order tool choose a size-compatible finish.",
            "Pin order at J1 is 5V, GND, DIN, DOUT from the visible bottom pad toward the top; top-to-bottom is DOUT, DIN, GND, 5V.",
        ],
    }
    (ORDER_DIR / "order-settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ORDER_DIR / "README.md").write_text(
        f"""# JLCPCB Order Pack: {BOARD_NAME}

This folder is generated for bare-PCB fabrication only. The WS2812B LED,
resistor, capacitor, and header are intended for manual assembly unless a later
SMT order maps exact parts and orientation.

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \\
  --config pcb/{BOARD_NAME}/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \\
  --config pcb/{BOARD_NAME}/jlcpcb_order/order-settings.json validate
```
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    GERBER_DIR.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    write_project()
    BOARD.write_text(board_text(), encoding="utf-8")
    SCHEMATIC.write_text(schematic_text(), encoding="utf-8")
    FP_LIB_TABLE.write_text(fp_lib_table_text() + "\n", encoding="utf-8")
    LED_FP.write_text(footprint_file_text("led"), encoding="utf-8")
    R_FP.write_text(footprint_file_text("r"), encoding="utf-8")
    C_FP.write_text(footprint_file_text("c"), encoding="utf-8")
    LOCAL_GITIGNORE.write_text("*.kicad_prl\nfp-info-cache\n", encoding="utf-8")
    DATASET.write_text(json.dumps(dataset(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_bom()
    write_readme()
    write_order_files()
    shutil.copy2(Path(__file__), OUT_DIR / "generate_ws2812b_5050_rgb_board.py")
    print(f"Wrote {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

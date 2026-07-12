# WS2812B / SK6812 C-Mount LED Holder Run 1

Shared holder for the two 24 mm round addressable LED carrier PCBs:

- `pcb/ws2812b-5050-rgb-led`
- `pcb/sk6812rgbw-5050-rgbw-led`

The two KiCad boards have the same mechanical layout, so one holder works for
both. Both boards include a backside `Custom:C_0603` decoupling capacitor
footprint and no onboard series resistor footprint.

## Design

- C-mount side: `5 mm` long female socket with a `5 mm` bounded printable
  C-mount-style internal thread.
- Nominal thread: `25.0 mm` pilot/root, `25.4 mm` cutter crest, `0.8 mm`
  pitch. The thread cutter is swept an extra half pitch beyond both ends and
  then clipped/subtracted inside the socket so it reaches the faces without
  leaving overflow.
- Holder side: `5 mm` thick square plate, similar to the clean Lumileds PCB
  holder but without cage-rod holes.
- Bodies are decoupled: the C-mount socket is one body, the PCB holder plate is
  a second adjacent body. They touch at x=`5.0`.
- PCB sink: `24.4 mm` diameter, `1.7 mm` deep for the `24 mm` board.
- PCB fixation pilots: four `1.8 mm` holes at the board's `12 x 12 mm`
  mounting-hole pattern.
- Header clearances: two side clearances. Each side uses two overlapping
  `3.0 mm` holes on the real `2.54 mm` pin pitch plus a bridge and a larger
  rectangular head clearance, so the material between pins is removed.
- LED aperture: `10 mm`, centered on the optical axis.

## Board Geometry

Mounting holes:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
| mount | `-6.0` | `-6.0` | `2.2` | `1.8` |
| mount | `6.0` | `-6.0` | `2.2` | `1.8` |
| mount | `-6.0` | `6.0` | `2.2` | `1.8` |
| mount | `6.0` | `6.0` | `2.2` | `1.8` |

Header pads:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
| J1 pad 1 | `-8.7` | `-1.27` | `1.0` | `3.0` |
| J1 pad 2 | `-8.7` | `1.27` | `1.0` | `3.0` |
| J2 pad 1 | `8.7` | `-1.27` | `1.0` | `3.0` |
| J2 pad 2 | `8.7` | `1.27` | `1.0` | `3.0` |

Backside footprint:

```json
{
  "y": 0.0,
  "z": -3.7,
  "footprint": "Custom:C_0603",
  "body_size_mm": [
    1.6,
    0.8
  ],
  "courtyard_mm": [
    3.1,
    1.5
  ]
}
```

## Outputs

| Output | Path |
| --- | --- |
| print_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.step` |
| print_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.stl` |
| print_3mf | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.3mf` |
| use_this_assembly_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/USE_THIS_ws2812b_sk6812_cmount_led_holder_run1_assembly.step` |
| decoupled_holder_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_decoupled_holder.step` |
| decoupled_holder_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_decoupled_holder.stl` |
| cmount_socket_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_cmount_socket.step` |
| holder_plate_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_holder_plate.step` |
| board_proxy_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_board_proxy.step` |
| board_proxy_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_board_proxy.stl` |
| female_thread_cutter_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_female_thread_cutter.step` |
| female_thread_cutter_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_female_thread_cutter.stl` |
| assembly_with_proxies_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_assembly_with_proxies.step` |
| assembly_with_proxies_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_assembly_with_proxies.stl` |
| rear_alignment_svg | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_rear_alignment.pdf` |
| render_png | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1_render.png` |
| manifest | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/manifest.json` |

Nutstore sync folder:

`/home/lachlan/Nutstore Files/Projects/LabCanvas/ws2812b_sk6812_cmount_led_holder/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z`

## Validation

```json
{
  "print_step": {
    "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.step",
    "valid": true,
    "solid_count": 2,
    "bbox_mm": [
      10.0,
      42.0,
      42.0
    ]
  },
  "print_stl": {
    "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.stl",
    "is_watertight": true,
    "component_count": 2,
    "bbox_mm": [
      10.0,
      42.0,
      42.0
    ],
    "triangles": 9774
  },
  "print_3mf": {
    "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run1.3mf",
    "valid": true,
    "zip_entries": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ]
  },
  "assembly_step_with_proxies": {
    "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/artifacts/ws2812b_sk6812_cmount_led_holder_run1_assembly_with_proxies.step",
    "valid": true,
    "solid_count": 9,
    "bbox_mm": [
      18.75,
      42.0,
      42.0
    ]
  },
  "source_layout_match": true
}
```

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `ws2812b_sk6812_cmount_led_holder_run1` |
| `units` | `mm` |
| `source_boards` | `['pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb', 'pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb']` |
| `shared_layout_note` | `WS2812B and SK6812 boards have the same 24 mm round carrier outline, same 12 x 12 mm mounting holes, same side 1x02 headers, and same backside C_0603 decoupling capacitor footprint.` |
| `board_outer_diameter_mm` | `24.0` |
| `board_sink_diameter_mm` | `24.4` |
| `board_thickness_mm` | `1.6` |
| `board_sink_depth_mm` | `1.7` |
| `holder_plate_width_y_mm` | `42.0` |
| `holder_plate_height_z_mm` | `42.0` |
| `holder_plate_thickness_x_mm` | `5.0` |
| `holder_edge_fillet_mm` | `0.8` |
| `pcb_fixation_pilot_diameter_mm` | `1.8` |
| `pcb_fixation_note` | `Four 1.8 mm pilot holes for small self-tapping screws in printed plastic.` |
| `pin_header_relief_diameter_mm` | `3.0` |
| `pin_header_relief_note` | `Each 1x02 side header gets two overlapping 3.0 mm clearance holes plus a bridge so the material between pins is fully removed.` |
| `pin_header_head_relief_extra_y_mm` | `1.6` |
| `pin_header_head_relief_extra_z_mm` | `1.0` |
| `led_aperture_diameter_mm` | `10.0` |
| `cmount_socket_length_mm` | `5.0` |
| `cmount_thread_length_mm` | `5.0` |
| `cmount_outer_diameter_mm` | `34.0` |
| `cmount_female_pilot_root_diameter_mm` | `25.0` |
| `cmount_female_thread_cutter_crest_diameter_mm` | `25.4` |
| `cmount_standard_note` | `C-mount nominal major diameter is 25.4 mm and pitch is 1/32 inch = 0.79375 mm. This printable proxy uses a 25.0 mm pilot/root and a 25.4 mm cutter maximum with local 0.8 mm pitch.` |
| `thread_pitch_mm` | `0.8` |
| `thread_tooth_height_mm` | `0.2` |
| `thread_tooth_base_mm` | `0.8` |
| `thread_runout_extra_cycles_each_end` | `0.5` |
| `thread_runout_extra_length_each_end_mm` | `0.4` |
| `thread_boolean_note` | `Female cutter is swept half-pitch beyond both ends, then subtracted from the 5 mm socket so the thread reaches both faces without leaving overflow. Socket and holder plate remain independent adjacent bodies.` |
| `optical_bore_diameter_mm` | `10.0` |
| `independent_body_contact_plane_x_mm` | `5.0` |
| `print_orientation` | `C-mount axis is X. Print/check in the supplied orientation; if support is undesirable, split socket/plate or rotate in slicer after inspecting the render.` |

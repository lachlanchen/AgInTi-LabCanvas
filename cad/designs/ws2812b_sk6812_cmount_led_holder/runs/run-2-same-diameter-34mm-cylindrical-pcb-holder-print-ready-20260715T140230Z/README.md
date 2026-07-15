# WS2812B / SK6812 C-Mount LED Holder Run 2

Print-ready surgical variant of preserved run 1. The `42 x 42 x 5 mm` square
PCB holder blank is replaced by a `34.0 mm OD x 5.0 mm` coaxial cylinder. The
adjacent `34.0 mm OD x 5.0 mm` C-mount socket and every source-board-derived
cut remain on the same optical axis.

## Body Contract

- C-mount socket: independent body at `x=0..5 mm`.
- Cylindrical PCB holder: independent body at `x=5..10 mm`.
- Contact: the two bodies touch at `x=5.0 mm`; there is no overlap, bridge, or
  middle body.
- Overall printable envelope: approximately `10 x 34 x 34 mm`, two solids.
- Female C-mount: `25.0 mm` pilot/root, `25.4 mm` cutter crest, `0.8 mm`
  pitch, and `0.4 mm` half-pitch construction runout beyond both ends before
  clipping by the 5 mm socket.

## Retained Board Features

- Centered `24.4 mm` PCB sink, nominal `1.7 mm` depth.
- Centered `10 mm` LED/optical aperture.
- Four `1.8 mm` fixation pilots at the source-board `(±6, ±6) mm` locations.
- Both source-position side headers: overlapping `3.0 mm` pin clearances,
  bridge cuts, and connector-head clearances.
- All retained cuts fit within the 17 mm plate radius. No outer wire/header
  breakout is introduced.

Both KiCad boards are parsed during every build and must pass mechanical-layout
equivalence before any output is exported:

- `pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb`
- `pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb`

## Source Geometry

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

## Build

```bash
cad/.conda/cad-python/bin/python cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/build_run2_same_diameter_34mm_cylindrical_pcb_holder.py
```

The builder exports analytic B-reps and meshes, runs Blender for both the exact
direct-print holder and the proxy assembly, validates STEP/STL/3MF data, checks
the source layouts and radial cut envelopes, and then copies the clean handoff
set to:

`/home/lachlan/Nutstore Files/Projects/LabCanvas/ws2812b_sk6812_cmount_led_holder/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z`

## Stable Run-1 Integrity

The run-1 source/artifact integrity digest is cache-independent. The builder
excludes `__pycache__`, Python bytecode (`*.pyc`, `*.pyo`), common Python tool
caches, editor swap/temporary files, and OS metadata before hashing the sorted
root-relative file checksums. The expected stable digest is:

`48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e`

The manifest records the same exclusion rules plus the included/excluded file
counts and stable digests measured before and after every regeneration.

## Outputs

| Output | Path |
| --- | --- |
| print_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.step` |
| print_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.stl` |
| print_3mf | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.3mf` |
| use_this_assembly_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/USE_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly.step` |
| cmount_socket_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cmount_socket.step` |
| cmount_socket_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cmount_socket.stl` |
| cylindrical_holder_plate_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cylindrical_holder_plate.step` |
| cylindrical_holder_plate_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cylindrical_holder_plate.stl` |
| decoupled_holder_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_decoupled_holder.step` |
| decoupled_holder_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_decoupled_holder.stl` |
| board_proxy_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_board_proxy.step` |
| board_proxy_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_board_proxy.stl` |
| female_thread_cutter_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_female_thread_cutter.step` |
| female_thread_cutter_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_female_thread_cutter.stl` |
| assembly_with_proxies_step | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies.step` |
| assembly_with_proxies_stl | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies.stl` |
| rear_alignment_svg | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_rear_alignment.pdf` |
| print_render_png | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_render.png` |
| assembly_render_png | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies_render.png` |
| manifest | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/manifest.json` |
| readme | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/README.md` |

## Validation

```json
{
  "step_brep": {
    "print_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.step",
      "valid": true,
      "solid_count": 2,
      "bbox_mm": [
        10.0,
        34.0,
        34.0
      ],
      "face_count": 31,
      "bspline_face_count": 2
    },
    "use_this_assembly_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/USE_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly.step",
      "valid": true,
      "solid_count": 2,
      "bbox_mm": [
        10.0,
        34.0,
        34.0
      ],
      "face_count": 31,
      "bspline_face_count": 2
    },
    "cmount_socket_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cmount_socket.step",
      "valid": true,
      "solid_count": 1,
      "bbox_mm": [
        5.0,
        34.0,
        34.0
      ],
      "face_count": 13,
      "bspline_face_count": 2
    },
    "cylindrical_holder_plate_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cylindrical_holder_plate.step",
      "valid": true,
      "solid_count": 1,
      "bbox_mm": [
        5.0,
        34.0,
        34.0
      ],
      "face_count": 18,
      "bspline_face_count": 0
    },
    "decoupled_holder_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_decoupled_holder.step",
      "valid": true,
      "solid_count": 2,
      "bbox_mm": [
        10.0,
        34.0,
        34.0
      ],
      "face_count": 31,
      "bspline_face_count": 2
    },
    "board_proxy_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_board_proxy.step",
      "valid": true,
      "solid_count": 1,
      "bbox_mm": [
        1.6,
        24.0,
        24.0
      ],
      "face_count": 11,
      "bspline_face_count": 0
    },
    "female_thread_cutter_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_female_thread_cutter.step",
      "valid": true,
      "solid_count": 1,
      "bbox_mm": [
        5.0,
        25.4001,
        25.4001
      ],
      "face_count": 6,
      "bspline_face_count": 3
    },
    "assembly_with_proxies_step": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies.step",
      "valid": true,
      "solid_count": 8,
      "bbox_mm": [
        18.75,
        34.0,
        34.0
      ],
      "face_count": 69,
      "bspline_face_count": 2
    }
  },
  "stl_mesh": {
    "print_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.stl",
      "combined_mesh_is_watertight": false,
      "component_count": 2,
      "component_watertightness": [
        true,
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        10.0,
        34.0,
        33.9894
      ],
      "triangles": 9688
    },
    "cmount_socket_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cmount_socket.stl",
      "combined_mesh_is_watertight": true,
      "component_count": 1,
      "component_watertightness": [
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        5.0,
        34.0,
        33.9894
      ],
      "triangles": 6104
    },
    "cylindrical_holder_plate_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_cylindrical_holder_plate.stl",
      "combined_mesh_is_watertight": true,
      "component_count": 1,
      "component_watertightness": [
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        5.0,
        34.0,
        33.9894
      ],
      "triangles": 3584
    },
    "decoupled_holder_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_decoupled_holder.stl",
      "combined_mesh_is_watertight": false,
      "component_count": 2,
      "component_watertightness": [
        true,
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        10.0,
        34.0,
        33.9894
      ],
      "triangles": 9688
    },
    "board_proxy_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_board_proxy.stl",
      "combined_mesh_is_watertight": true,
      "component_count": 1,
      "component_watertightness": [
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        1.6,
        24.0,
        23.9925
      ],
      "triangles": 4564
    },
    "female_thread_cutter_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_female_thread_cutter.stl",
      "combined_mesh_is_watertight": true,
      "component_count": 1,
      "component_watertightness": [
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        5.0,
        25.4,
        25.4
      ],
      "triangles": 7324
    },
    "assembly_with_proxies_stl": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies.stl",
      "combined_mesh_is_watertight": false,
      "component_count": 8,
      "component_watertightness": [
        true,
        true,
        true,
        true,
        true,
        true,
        true,
        true
      ],
      "all_components_watertight": true,
      "bbox_mm": [
        18.75,
        34.0,
        33.9894
      ],
      "triangles": 14800
    }
  },
  "print_3mf": {
    "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical.3mf",
    "valid_zip": true,
    "has_model": true,
    "model_unit": "millimeter",
    "object_count": 1,
    "build_item_count": 1,
    "zip_entries": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ]
  },
  "source_layout_match": true,
  "source_board_sha256": {
    "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb": "ed8fe751c5267796b9abd5a496fa2abb3194679dcb00419d89674da922965692",
    "pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb": "27514ab1c6367e44af9881c8343e7ac8a3c4ea44cfe4c8825648b7982ea655fa"
  },
  "retained_cut_fit": {
    "holder_outer_radius_mm": 17.0,
    "all_retained_cuts_fit_within_34mm_circle": true,
    "outer_breakouts": [],
    "intentional_open_wire_or_header_exits": [],
    "minimum_radial_material_margin_mm": 4.8,
    "feature_envelopes": [
      {
        "feature": "24.4 mm centered PCB sink",
        "radial_extent_mm": 12.2,
        "radial_margin_to_outer_profile_mm": 4.8,
        "source": "named run-1 parameter"
      },
      {
        "feature": "10 mm centered LED/optical aperture",
        "radial_extent_mm": 5.0,
        "radial_margin_to_outer_profile_mm": 12.0,
        "source": "named run-1 parameter"
      },
      {
        "feature": "fixation pilot 1",
        "radial_extent_mm": 9.3853,
        "radial_margin_to_outer_profile_mm": 7.6147,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb mounting hole"
      },
      {
        "feature": "fixation pilot 2",
        "radial_extent_mm": 9.3853,
        "radial_margin_to_outer_profile_mm": 7.6147,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb mounting hole"
      },
      {
        "feature": "fixation pilot 3",
        "radial_extent_mm": 9.3853,
        "radial_margin_to_outer_profile_mm": 7.6147,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb mounting hole"
      },
      {
        "feature": "fixation pilot 4",
        "radial_extent_mm": 9.3853,
        "radial_margin_to_outer_profile_mm": 7.6147,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb mounting hole"
      },
      {
        "feature": "J1 pad 1 3 mm clearance",
        "radial_extent_mm": 10.2922,
        "radial_margin_to_outer_profile_mm": 6.7078,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header pad"
      },
      {
        "feature": "J1 pad 2 3 mm clearance",
        "radial_extent_mm": 10.2922,
        "radial_margin_to_outer_profile_mm": 6.7078,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header pad"
      },
      {
        "feature": "J2 pad 1 3 mm clearance",
        "radial_extent_mm": 10.2922,
        "radial_margin_to_outer_profile_mm": 6.7078,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header pad"
      },
      {
        "feature": "J2 pad 2 3 mm clearance",
        "radial_extent_mm": 10.2922,
        "radial_margin_to_outer_profile_mm": 6.7078,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header pad"
      },
      {
        "feature": "J1 bridge clearance",
        "radial_extent_mm": 10.2838,
        "radial_margin_to_outer_profile_mm": 6.7162,
        "source": "run-1 bridge construction"
      },
      {
        "feature": "J2 bridge clearance",
        "radial_extent_mm": 10.2838,
        "radial_margin_to_outer_profile_mm": 6.7162,
        "source": "run-1 bridge construction"
      },
      {
        "feature": "J1 connector-head clearance",
        "radial_extent_mm": 11.1908,
        "radial_margin_to_outer_profile_mm": 5.8092,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header body plus retained run-1 clearance"
      },
      {
        "feature": "J2 connector-head clearance",
        "radial_extent_mm": 11.1908,
        "radial_margin_to_outer_profile_mm": 5.8092,
        "source": "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb header body plus retained run-1 clearance"
      }
    ]
  },
  "independent_body_relationship": {
    "socket_x_interval_mm": [
      -0.0,
      5.0
    ],
    "holder_x_interval_mm": [
      5.0,
      10.0
    ],
    "contact_plane_x_mm": 5.0,
    "contact_plane_matches_both_bodies": true,
    "boolean_overlap_volume_mm3": 0,
    "zero_overlap": true,
    "bridge_or_middle_body_count": 0,
    "coaxial_yz_center_mm": [
      0.0,
      0.0
    ],
    "same_outside_diameter_mm": [
      34.0,
      34.0
    ]
  },
  "proxy_contract_preserved": {
    "positions": true,
    "colors_rgba": true,
    "source": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z/build_run1_shared_24mm_pcb_cmount_5mm.py",
    "bounded_thread_cutter_exported_separately_to_keep_proxy_assembly_clean": true
  },
  "renders": {
    "direct_print": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_render.png",
      "valid_png_signature": true,
      "width_px": 1800,
      "height_px": 1500,
      "bytes": 3465468,
      "nontrivial_file": true
    },
    "assembly_with_proxies": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies_render.png",
      "valid_png_signature": true,
      "width_px": 1800,
      "height_px": 1500,
      "bytes": 3493503,
      "nontrivial_file": true
    },
    "rear_alignment": {
      "path": "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_rear_alignment.png",
      "valid_png_signature": true,
      "width_px": 1800,
      "height_px": 826,
      "bytes": 559237,
      "nontrivial_file": true
    }
  },
  "run1_integrity": {
    "digest_scope": "stable run-1 source/artifact files excluding obvious generated caches",
    "digest_algorithm": "SHA-256 of concatenated sorted '<file_sha256>  <root-relative-path>\\n' records",
    "exclusion_rules": {
      "directory_names": [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache"
      ],
      "file_names": [
        ".DS_Store",
        "Thumbs.db"
      ],
      "file_suffixes": [
        ".pyc",
        ".pyo",
        ".swp",
        ".swo",
        ".tmp"
      ],
      "file_name_endings": [
        "~"
      ]
    },
    "expected_tree_sha256": "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e",
    "before_generation": "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e",
    "after_generation": "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e",
    "before_snapshot": {
      "sha256": "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e",
      "included_file_count": 22,
      "excluded_transient_file_count": 0,
      "excluded_transient_paths": []
    },
    "after_snapshot": {
      "sha256": "48ea05e76138f7b437cf3e979f9e0f32a97b5d299e9f38c6a571991790d1936e",
      "included_file_count": 22,
      "excluded_transient_file_count": 0,
      "excluded_transient_paths": []
    },
    "preserved_exactly": true
  },
  "visual_inspection": {
    "status": "passed: full frame, coaxial cylindrical geometry, clear body seam, readable proxies and circular rear drawing",
    "checked_files": [
      "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/PRINT_THIS_ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_render.png",
      "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_assembly_with_proxies_render.png",
      "cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-2-same-diameter-34mm-cylindrical-pcb-holder-print-ready-20260715T140230Z/artifacts/ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical_rear_alignment.png"
    ]
  }
}
```

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `ws2812b_sk6812_cmount_led_holder_run2_same_diameter_34mm_cylindrical` |
| `units` | `mm` |
| `source_boards` | `['pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb', 'pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb']` |
| `shared_layout_note` | `WS2812B and SK6812 boards have the same 24 mm round carrier outline, same 12 x 12 mm mounting holes, same side 1x02 headers, and same backside C_0603 decoupling capacitor footprint.` |
| `board_outer_diameter_mm` | `24.0` |
| `board_sink_diameter_mm` | `24.4` |
| `board_thickness_mm` | `1.6` |
| `board_sink_depth_mm` | `1.7` |
| `holder_plate_thickness_x_mm` | `5.0` |
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
| `variant_mode` | `surgical outer-profile replacement from preserved run 1` |
| `run1_reference` | `cad/designs/ws2812b_sk6812_cmount_led_holder/runs/run-1-shared-24mm-pcb-cmount-5mm-20260712T031500Z` |
| `holder_outer_profile` | `coaxial circular cylinder` |
| `holder_outer_diameter_mm` | `34.0` |
| `body_interval_note` | `C-mount socket occupies x=0..5 mm and cylindrical PCB holder occupies x=5..10 mm. They are independent, adjacent bodies with zero overlap.` |
| `outer_profile_change_note` | `Only the run-1 square 42 x 42 mm holder blank is replaced by a coaxial 34.0 mm OD cylindrical blank; all board-derived Y/Z cuts and proxies are retained.` |
| `outer_breakout_policy` | `No retained cut may meet the 17 mm outer radius; no wire/header exit is opened in run 2.` |

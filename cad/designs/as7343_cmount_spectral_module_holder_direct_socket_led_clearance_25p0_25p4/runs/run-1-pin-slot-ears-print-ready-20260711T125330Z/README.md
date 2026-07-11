# AS7343 Pin-Slot Holder Print-Ready Run

This run keeps the current AS7343 holder geometry and the current `3.0 mm`
connected pin-header reservation slot. The only geometry added is four
removable anti-warp ears on the rear print face.

## Print This

Use the root `PRINT_THIS_*` files in this run folder:

- `PRINT_THIS_as7343_pin_slot_ears_print_ready.3mf`
- `PRINT_THIS_as7343_pin_slot_ears_print_ready.stl`
- `PRINT_THIS_as7343_pin_slot_ears_print_ready.step`

The print files are already rotated to a rear-face-down orientation: the PCB
tray side is on the build plate and the C-mount rises upward.

## Ears

- Thickness: `1.0 mm`
- Side contact on each adjacent edge: `5.0 mm`
- Four filled corner/diagonal sacrificial tabs
- Remove after printing with a knife or flush cutter.

## Outputs

```json
{
  "design_orientation_step": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/as7343_pin_slot_ears_print_ready_design_orientation_with_ears.step",
  "design_orientation_stl": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/as7343_pin_slot_ears_print_ready_design_orientation_with_ears.stl",
  "print_layout_step": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/as7343_pin_slot_ears_print_ready_print_layout.step",
  "print_layout_stl": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/as7343_pin_slot_ears_print_ready_print_layout.stl",
  "print_layout_3mf": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/as7343_pin_slot_ears_print_ready_print_layout.3mf",
  "print_this_step": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/PRINT_THIS_as7343_pin_slot_ears_print_ready.step",
  "print_this_stl": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/PRINT_THIS_as7343_pin_slot_ears_print_ready.stl",
  "print_this_3mf": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/PRINT_THIS_as7343_pin_slot_ears_print_ready.3mf",
  "render_png": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/PRINT_THIS_as7343_pin_slot_ears_print_ready_render.png",
  "manifest": "cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/runs/run-1-pin-slot-ears-print-ready-20260711T125330Z/artifacts/manifest.json",
  "nutstore_folder": "/home/lachlan/Nutstore Files/Projects/LabCanvas/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/run-1-pin-slot-ears-print-ready-20260711T125330Z"
}
```

## Validation

```json
{
  "source_pin_header_relief_mm": 3.0,
  "source_pin_header_pitch_mm": 2.54,
  "print_step": {
    "valid": true,
    "solids": 1,
    "bounds_mm": [
      74.0,
      82.0,
      19.0
    ]
  },
  "print_stl": {
    "watertight": true,
    "component_count": 1,
    "bounds_mm": {
      "min": [
        -37.0,
        -41.0,
        -0.0
      ],
      "max": [
        37.0,
        41.0,
        19.0
      ],
      "size": [
        74.0,
        82.0,
        19.0
      ]
    },
    "vertices": 7824,
    "faces": 15652
  },
  "print_3mf_entries": [
    "3D/3dmodel.model",
    "[Content_Types].xml",
    "_rels/.rels"
  ]
}
```

# Local CAD Archive

On 2026-07-28, 29 superseded CAD design trees were removed from the tracked
working set and preserved locally under:

```text
cad/designs/archived/
```

That directory is intentionally ignored because it is a 506 MB byte-preserving
operator archive, not the active design source. Before removal, all 592 tracked
files were compared with their archived counterparts using the corresponding
`HEAD` blob; every file matched and none were missing.

Archived design directories:

- `as7341_cmount_sensor_holder`
- `as7343_cmount_spectral_module_holder`
- `as7343_cmount_spectral_module_holder_decoupled`
- `as7343_cmount_spectral_module_holder_direct_socket`
- `as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p4`
- `as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes`
- `as7343_cmount_spectral_module_holder_printable_saddle`
- `cage_sample_holder_openhi_slide_petri35`
- `cage_sample_holder_two_piece_lock_slide_petri35_h60_each30`
- `cmount_reflector_adapter`
- `cmount_threaded_reflector_assembly`
- `gy302_bh1750_cmount_light_sensor_holder`
- `lumileds_gt090101_cage`
- `lumileds_hengyang_30mm_cage_holder`
- `lumileds_hengyang_30mm_cage_holder_2p_right_angle`
- `lumileds_pcb_aligned_simple_cage_holder`
- `openhi_lens_b_holder_shapr_exact_regen`
- `openhi_lens_c_holder_receiver_25p4`
- `openhi_lens_c_holder_receiver_30p0_30p4_print_fit`
- `openhi_lens_c_holder_shapr_exact_regen`
- `qyh1123_light_valve_aligned_cage_holder`
- `tsl25911_cmount_intensity_sensor_holder`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p4`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10`
- `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4`
- `tsl25911_cmount_intensity_sensor_holder_printable_saddle`

Active designs remain directly under `cad/designs/`. New revisions should use
the run-folder and print-ready conventions in `AGENTS.md`, not this local
archive.

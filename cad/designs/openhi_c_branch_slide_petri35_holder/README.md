# OpenHI C-Branch Slide And Petri 35 Holder

This is a clean, decoupled variant of the accepted two-piece slide/Petri holder.
Every sample-facing feature is rebuilt by importing the accepted parametric
functions from `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/build_cage_sample_holder_two_piece_lock_slide_petri35.py`. Only the lower four cage
rod sockets are removed and replaced by a separate smooth OpenHI C-branch
adapter.

## Measured C Interface

Source: `cad/extracted/OpenHI_STEP/C.step`.

- Plain nose/body: `24.4 mm` measured diameter.
- Thread crest envelope in the reference: about `25.2 mm`.
- Taper: `7.8 mm` axial length, from approximately `40 mm` to the nose.
- User-confirmed new socket: `25.0 mm` smooth ID, no generated thread.
- Adapter OD: `40.0 mm`, matching the OpenHI 4F tube OD.
- Taper mouth: `39.0 mm`; this leaves a printable `0.5 mm` radial lip and seats
  just before the original 40 mm shoulder.

The `25.0 mm` ID is intentionally tighter than the measured `25.2 mm` thread
crest. Print `PRINT_THIS_openhi_c_branch_slide_petri35_holder_25mm_fit_coupon.*` before the full holder. Sand
or ream the coupon only after checking the physical C branch.

## Unchanged Sample Geometry

- Tray: `110 x 70 x 8 mm`.
- Slide seat: `75 x 22 mm`, `1.2 mm` deep, for the accepted `72.96 x 20 mm` strip.
- Petri seat: `35.4 mm`, `1.8 mm` deep, for a nominal `33 mm` dish.
- Optical opening: `18 mm`.
- Chamber gap: `18 mm`.
- Lock feet, finger access, anti-warp ears, and top frame are unchanged.

## Decoupled Parts

1. `bottom_tray`: accepted sample tray without lower cage holes; adds a
   `38.2 x 2.2 mm` underside registration pocket.
2. `c_branch_adapter`: independent `40 mm` OD socket with a `38.0 x 2.0 mm`
   registration spigot. Use adhesive after confirming fit.
3. `top_frame_180deg_print`: accepted top frame in its validated print orientation.
4. `25mm_fit_coupon`: fast physical fit check for the user-confirmed socket ID.

The assembly STEP keeps these as separate solids for clean Shapr3D editing.

## Print Files

- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_bottom_tray.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_c_branch_adapter_supported_orientation.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_top_frame_180deg.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_25mm_fit_coupon.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_all_parts_layout.*`

Print the adapter with the small registration/optical face on the build plate
and its wide tapered mouth upward. This avoids an unsupported 39 mm first-layer
opening.

## Validation

- Adapter STEP: 1 solid, bbox
  `[40.0, 40.0, 14.8] mm`, B-spline faces
  `0`.
- Adapter STL watertight: `True`.
- Tray STEP: 1 solids; STL
  watertight `True`.
- Top frame matches accepted bbox and volume: `True`.
- 3MF files valid: `True`.
- Feature checks: `{'tray_optical_axis_open': True, 'tray_slide_seat_open_at_top': True, 'tray_petri_seat_open_at_top': True, 'old_lower_rod_socket_location_is_solid': True, 'registration_pocket_open': True, 'registration_pocket_has_roof': True, 'adapter_optical_axis_open': True, 'adapter_25mm_bore_open': True, 'adapter_bore_wall_present': True, 'adapter_mouth_open': True, 'adapter_mouth_lip_present': True, 'top_center_open': True}`.

The OpenHI C body in the fit-check file is visualization-only and must not be
printed.

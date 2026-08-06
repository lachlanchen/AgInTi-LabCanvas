# OpenHI C-Branch Slide And Petri 35 Holder

This run contains exactly two printable parts. The first is the bottom sample
tray/holder with the accepted slide and Petri-dish seats. The second is one
continuous socket that covers the OpenHI C-branch C-mount nose and chamfer and
then screws directly into the holder.

## Two Parts

1. `sample_holder_female30_thread`: accepted bottom tray geometry, without cage
   rod sockets, lock feet, or top frame. Its underside has a 5 mm female OpenHI
   30 mm thread.
2. `c_branch_socket_male30_thread`: a 42 mm OD cup with a 40.2-to-25.5 mm
   internal C-branch receiver and a 5 mm male OpenHI 30 mm thread at the holder
   end.

There is no coupon, top frame, adhesive spigot, or third connector part.

## C-Branch Receiver

Measured source: `cad/extracted/OpenHI_STEP/C.step`.

- Reference C nose/body: 24.4 mm.
- Reference thread crest envelope: about 25.2 mm.
- Smooth receiver ID: 25.5 mm.
- Reference chamfer/taper length: 7.8 mm.
- Receiver taper: 40.2 mm at the branch shoulder to 25.5 mm at the nose.
- Socket cup OD: 42.0 mm, leaving a 0.9 mm radial wall at the wide mouth.

The 42 mm cup is required to cover the approximately 40 mm C-branch chamfer.
The 29.8 mm dimension belongs only to the upper male thread root, not to the
lower C-branch cup.

## Direct Threaded Interface

- Pitch: 0.8 mm.
- Radial tooth height: 0.2 mm.
- Male root/crest: 29.8 / 30.2 mm.
- Female land/groove: 30.0 / 30.4 mm.
- Diametral clearance: 0.2 mm at both the land and crest pairs.
- Thread length: 5.0 mm.
- Both thread sweeps extend half a pitch during construction and are clipped
  back to their exact 5 mm parent length, so no tooth overflows either end.

## Print Files

- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_sample_holder_female30_thread.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_c_branch_socket_male30_thread.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_two_part_layout.*`

Print the tray normally with its anti-warp ears on the build plate. The socket
print export is already rotated so the male-thread end rests on the build plate
and the wide C-branch cavity points upward.

## Validation

- Holder STEP: 1 valid solid; bbox
  `[161.0, 121.0, 8.0] mm`.
- Socket STEP: 1 valid solid; bbox
  `[42.0, 42.0, 17.8] mm`.
- Assembly solid count: 2.
- Print-layout STL components: 2.
- Holder/socket STL watertight: True /
  True.
- 3MF packages valid: True.
- Thread clearances: {'land_diametral': 0.2, 'crest_diametral': 0.2}.
- Feature checks: {'holder_optical_axis_open': True, 'holder_slide_seat_open_at_top': True, 'holder_petri_seat_open_at_top': True, 'old_lower_cage_socket_location_is_solid': True, 'old_lock_foot_is_absent': True, 'female_land_is_open': True, 'female_outer_wall_is_present': True, 'socket_optical_axis_open': True, 'socket_smooth_c_receiver_is_open': True, 'socket_smooth_receiver_wall_is_present': True, 'socket_taper_mouth_is_open': True, 'socket_taper_mouth_wall_is_present': True, 'male_thread_root_is_present': True, 'socket_outside_is_empty': True}.

The OpenHI C body in the fit-check file is visualization-only and must not be
printed.

// C-mount male to reflector-cube adapter.
// Units: millimetres.

$fn = 96;

// C-mount reference: 1"-32 UN, 25.4 mm nominal major diameter.
nominal_cmount_major_d = 25.4;
thread_major_d = 24.4;        // Printed-fit value inferred from local STEP files.
thread_pitch = 25.4 / 32;     // 0.79375 mm.
thread_length = 5.5;
thread_depth = 0.42;

body_d = 26;
body_length = 18;
bore_d = 20;

inner_cube = 20;
wall = 3;
outer_cube = inner_cube + 2 * wall;
cube_length = outer_cube;

clearance = 0.05;
render_thread = true;

axis_z = body_d / 2;
cube_x0 = thread_length + body_length;
total_length = thread_length + body_length + cube_length;

module x_cylinder(d, h, x0) {
    translate([x0, 0, axis_z])
        rotate([0, 90, 0])
            cylinder(d = d, h = h);
}

module approximate_external_thread() {
    turns = thread_length / thread_pitch;
    tooth_w = thread_pitch * 0.55;

    translate([0, 0, axis_z])
        rotate([0, 90, 0])
            linear_extrude(
                height = thread_length,
                twist = 360 * turns,
                slices = max(32, ceil(turns * 36)),
                convexity = 10
            )
                translate([thread_major_d / 2 - thread_depth, 0])
                    polygon(points = [
                        [0, -tooth_w / 2],
                        [thread_depth, 0],
                        [0, tooth_w / 2]
                    ]);
}

module adapter_solid() {
    union() {
        x_cylinder(thread_major_d - 2 * thread_depth, thread_length, 0);

        if (render_thread) {
            approximate_external_thread();
        } else {
            x_cylinder(thread_major_d, thread_length, 0);
        }

        x_cylinder(body_d, body_length, thread_length);

        translate([cube_x0, -outer_cube / 2, 0])
            cube([cube_length, outer_cube, outer_cube]);
    }
}

module adapter_voids() {
    // Main optical bore. Diameter matches the square cavity height/width.
    x_cylinder(bore_d + clearance, total_length + 2, -1);

    // Reflector pocket. It opens at the far face so a reflector can slide in.
    translate([cube_x0 + wall, -inner_cube / 2, wall])
        cube([inner_cube + wall + 1, inner_cube, inner_cube]);
}

difference() {
    adapter_solid();
    adapter_voids();
}

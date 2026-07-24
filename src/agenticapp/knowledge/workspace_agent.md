# LabCanvas Workspace Knowledge

This is the compact, packaged operating knowledge for the LabCanvas agent. It
travels with the Python package. Repository reference documents remain the
measurement evidence and should be read before a geometry-sensitive change.

## General Method

- Read the existing design, code, manifest, render, and user measurements before
  choosing an implementation.
- Decide whether the request is an exact reconstruction, a constrained variant,
  or a new design. Never silently replace one with another.
- Keep source geometry, generated artifacts, validation evidence, and direct-use
  outputs separate.
- Prefer named parameters and reproducible builders over manual one-off edits.
- Use the simplest proven domain tool: CadQuery/build123d/OCP or OpenSCAD for
  mechanical source, KiCad for PCB, Blender for presentation render, TeX for
  publication assembly, and the existing GUI/MCP bridge for proprietary apps.
- Treat rendered inspection and round-trip import as required validation, not
  decoration.

## CAD and Shapr3D-Compatible Design

### Source hierarchy

Use evidence in this order:

1. User measurements and print feedback.
2. Original STEP/Parasolid and the paired `.shapr` archive.
3. Datasheet drawings and vendor CAD.
4. Existing repository builders and manifests.
5. Assumptions, clearly recorded as assumptions.

A `.shapr` file is a ZIP package containing a SQLite workspace. Its history can
reveal operation names, imported bodies, sketches, alignments, transforms,
booleans, offsets, chamfers, revolves, sweeps, and splits. The proprietary
feature parameters are not always recoverable. Use history to infer design
intent and STEP/Parasolid B-reps to recover exact geometry.

The repository's historical Shapr3D pattern is:

```text
import or sketch -> extrude/revolve -> align/transform -> OffsetFace fit tuning
-> split/boolean -> chamfer -> physical print feedback
```

Convert repeated face offsets into named parameters such as:

```text
pcb_clearance_xy = 0.2
socket_relief_extra_y = 2.0
female_thread_pilot = 25.0
female_thread_cutter_max = 25.4
```

### Geometry organization

- Define a single assembly origin and explicit optical, board, and cage datums.
- Align the active sensor/LED/aperture center to the optical axis. Do not merely
  center the PCB outline when the active element is offset.
- Keep imported reference bodies separate from editable holder bodies.
- Keep logical solids decoupled: mount, plate, pocket, thread cutter, component
  proxy, socket envelope, wire relief, and print aids.
- Use tiny boolean overlap only where a final union needs it. Preserve separate
  editable assembly STEP files when the parts should remain selectable.
- Avoid unexplained middle blocks, internal slivers, duplicate shells, and
  geometry that depends on a long chain of fragile booleans.

### Shapr3D import quality

"OCCT valid" is necessary but not sufficient. A STEP can still trigger a slow
Shapr3D repair pass, lose threads, or show transparent regions. Shapr-friendly
outputs should favor analytic boxes, cylinders, cones, planes, and simple
chamfers. Inspect B-spline face count and remove accidental helical/B-spline
topology from the editable handoff when it causes repair.

For a fragile imported threaded B-rep:

1. Preserve the original stable body outside the repair region.
2. Replace only the receiver region with a clean analytic sleeve/socket.
3. Export a smooth editable STEP.
4. Keep a separate threaded or ring-groove preview when needed.
5. Re-import the actual exported STEP and verify solids, bbox, BRep validity,
   surface types, and visual appearance.

### Threads

Do not confuse nominal major diameter with the pilot/root diameter.

Standard C-mount:

```text
nominal: 1 inch - 32 UN
nominal major diameter: 25.4 mm
pitch: 0.79375 mm (local printed references often round to 0.8 mm)
printed male root starting point: about 24.6 mm
standard-like printed female pilot: about 25.0 mm
female thread cutter maximum: about 25.4 mm
```

The old OpenHI local camera pair uses measured print-fit roots around 24.4 male
and 24.8 female, with larger crest envelopes. Preserve that family only when
compatibility with the old printed parts is required.

The larger OpenHI lens/beam-splitter family is near 30 mm and is not C-mount.
Measured historical designs use a local triangular profile near 0.8 mm pitch.
Recent tightened receiver variants use a 30.0 mm pilot and approximately 30.4
mm groove/cutter maximum. Preserve the lens seat and adjust the transition
chamfer when changing the pilot.

Thread runout rule:

- Extend an internal thread cutter about half a pitch beyond each nominal end;
  subtraction clips it at the body boundary.
- Extend an external thread about half a pitch, then trim it back to the exact
  end face.
- Do not change pitch or tooth profile when adding construction runout.
- Prefer a real 1"-32 UN or M30x0.75 tap when physical tooling is the design
  intent; do not claim the old local 0.8 mm profile is identical to M30x0.75.

### Sensors, PCBs, sockets, and wires

- Measure board width/length/thickness, hole coordinates, active-element
  coordinates, component envelopes, connector body, mating plug, and wire exit.
- Position the active element at the optical center using its measured offset
  from a known board edge.
- Put pin-header holes on the PCB footprint when that is the real geometry.
- A connector relief must start from the PCB seating plane, not the outside
  bottom face of the holder.
- Continue socket relief to a free edge when a plug and cable need to enter.
- Add clearance for the mating connector and bend radius, not only the socket
  body shown in a vendor proxy.
- Keep component proxies in assembly renders but exclude them from direct-print
  solids.

### Optical cages and print fit

For the repository's 30 mm cage family:

```text
rod centers: x/y = +/-15 mm from optical center
nominal rod: 6.0 mm
first printed socket trial: 6.2-6.4 mm, then use actual printer feedback
```

Do not move cage holes to the outer corners of a wide plate. The cage datum is
independent from the plate envelope.

Use explicit fit classes:

- exact/press: nominal or measured near-zero clearance;
- sliding: small printer-specific clearance;
- removable pocket: moderate clearance;
- visual/reference: no manufacturing claim.

Never apply a global tolerance to every feature. Holes, shafts, pockets,
threads, snap fits, and optical seats need separate values.

For broad flat prints, add removable anti-warp ears to the print layout. After
physical dock feedback, the default is stronger full-corner ears: roughly
0.8-1.0 mm sacrificial thickness, contact on both adjacent sides, a diagonal
corner pull, and a larger tail pad. Keep ears out of the clean assembled model
when possible.

### CAD output contract

For a serious design or revision:

```text
cad/designs/<project>/
  builder source and parameters
  README.md
  artifacts/                 latest checked output
  runs/run-N-short-name-YYYYMMDDTHHMMSSZ/
```

For print-ready work, include:

- `PRINT_THIS_*.step`
- `PRINT_THIS_*.stl`
- `PRINT_THIS_*.3mf`
- separate part STEP files where useful
- assembly STEP
- exact print-layout render
- assembly render
- manifest and short README

"Nutstore sync" means:

```text
/home/lachlan/Nutstore Files/Projects/LabCanvas
```

Copy the direct-use assembly STEP there for normal handoff. For print-ready
runs, create a clean design/run subfolder and copy only the slicer-ready files,
part files, manifest, README, and renders.

Validate:

- STEP re-import and BRep validity;
- expected solid count and bounding box;
- STL watertightness;
- 3MF ZIP/model structure and millimeter scale;
- no unexpected B-spline faces for a Shapr-target analytic fixture;
- visual render from at least one useful assembly view and the print layout.

## KiCad and PCB

- Start from a datasheet-backed footprint and board dimensions.
- Keep component pin count, net count, footprint pads, header holes, and render
  proxies consistent. A four-pad LED must not display a fictitious fifth trace.
- Use deterministic board generators where the repository already has them.
- Run schematic ERC and PCB DRC before manufacturing output.
- Export Gerbers, drill files/maps/reports, board STEP, and a full-board render.
- Inspect board edges, holes, silkscreen, sockets, pin alignment, and connector
  access in both KiCad and the render.
- Manufacturing submission is a separate confirmed action. Package and preflight
  can run automatically; payment and irreversible submission require explicit
  authorization.

## Blender and 3D Presentation

- Preserve engineering source separately from presentation scenes.
- Import the final checked STEP/STL or build from the scene manifest.
- Use a neutral bright studio world, readable materials, real scale, shadows,
  and camera framing that shows the full object.
- Render the complete assembly and, when useful, an exploded/detail view.
- Verify the PNG is nonblank and the geometry is not clipped before registering
  it in the artifact canvas.

## TeX, Papers, and Figures

- Generated overview bitmaps are concepts, not final editable source.
- Decompose a figure into named panels, icons, labels, CAD renders, plots, and
  clipping/assembly layers.
- Use SVG/PDF/PNG according to the source; preserve vector text and lines where
  possible.
- Use TeX for stable panel placement, labels, captions, and final PDF assembly.
- Compile and inspect the PDF. Return both source and final PDF when requested.

## WeChat

- Treat WeChat as a message and artifact transport to the same agent routines.
- Keep each group/DM session, message history, media, queue, and agent thread
  isolated.
- Use existing direct database/mirror and GUI sender routines. Do not implement
  a second ad hoc controller inside a task.
- Deliver actual requested artifacts, not only filesystem paths.
- Do not process the system's own messages recursively.
- Do not flood delayed messages after a network restart; stale work may fail or
  be compacted rather than bombarding a chat.
- Public publication, orders, payments, and account/security changes require a
  current explicit instruction and evidence of the final external state.

## LabVIEW and Instrument Control

- Probe the installed NI/LabVIEW state before assuming a runtime is available.
- Reuse the isolated Xvfb/x11vnc/noVNC desktop and the existing MCP/bridge
  scripts. Do not mix its display with WeChat or browser automation displays.
- A VI/control task should preserve source VI/project files, configuration,
  screenshots, captured data, and a reproducible launch/probe command.
- Camera tests must stop the capture process when finished unless continuous
  monitoring was explicitly requested.

## Protein Structure and AlphaFold

- Reuse `external/ProteinStructure/scripts/alphafold_server/` for AlphaFold
  submission, polling, download, metric extraction, rendering, and screenshots.
  LabCanvas is a thin transport and orchestration layer, not a second pipeline.
- Use `labcanvas protein start` to reuse the logged-in Chrome profile, then
  `submit`, `poll --download`, `metrics`, `render`, and `capture` as needed.
- Keep reusable code and inputs in the submodule. Keep generated downloads,
  copied full result payloads, plots, screenshots, compiled PDFs, and logs in
  the ignored sibling `../ProteinStructure` workspace.
- Return useful structure files, confidence/interface metrics, plots,
  screenshots, and reports as artifacts. A local path alone is not delivery.
- Separate evidence layers: an AlphaFold model is a prediction; confidence
  scores describe model reliability; docking is a hypothesis; literature,
  databases, biochemical assays, and clinical evidence have different weight.
- Check applicable AlphaFold Server terms before submitting a job or using an
  output for docking/screening. Never describe a predicted pose as a validated
  inhibitor or clinical result.

## Social Content Management

- Use `labcanvas social` and its SQLite ledger instead of one-off posting
  scripts. Register the repository first so every public claim has evidence.
- Use one persistent Codex conversation per project. Default serious campaign
  drafting to `gpt-5.6-sol` with medium reasoning.
- Adapt copy to each platform and community. Do not mass-cross-post identical
  text, automate engagement, fabricate traction, or send unsolicited outreach.
- Reddit requires review of the exact community rules before approval.
- Hacker News is manual-only: its guidelines reject generated or AI-edited
  submission text. Prepare a verified fact worksheet, then let the human write
  and import the final title and body.
- Postiz is the broad optional OAuth transport. The official X MCP is an
  optional X-specific adapter with a narrow tool allowlist.
- External writes require both `--live` and an unexpired approval token bound
  to the exact content hash. Any edit to title, body, target, media, or settings
  invalidates approval.
- Report Postiz acceptance or scheduling accurately. Do not claim destination
  publication until provider status or analytics confirms it.

## Agent Behavior

- A short question can use low reasoning. Planning, review, file/tool
  execution, exact reconstruction, and multi-tool validation use medium.
  Legacy high, xhigh, max, and Ultra labels are capped at medium.
- Resume one agent session per LabCanvas conversation so follow-up messages have
  context. Never reuse a session across unrelated users/workspaces.
- A request may change direction. Re-read the latest message before irreversible
  work and continue from real external state rather than blindly replaying an
  old plan.
- Return a concise reply plus direct artifacts. The task record stores detailed
  evidence and command state for later inspection.

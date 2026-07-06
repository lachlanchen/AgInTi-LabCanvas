# C-Mount Threaded Reflector Assembly Scale Reference

Date: 2026-06-09

## Purpose

New two-part design for connecting the old 4f system female C-mount side to a top-open reflector holder. This does not replace the earlier one-piece adapter.

## Old Design Details Used

The old OpenHI/Nature STEP files are millimetre STEP exports. Exact thread labels found:

- `OpenHI_STEP/A.step`: `Thread top`
- `OpenHI_STEP/B.step`: `Thread camera 24.4`, `Thread lens 29.6*`
- `OpenHI_STEP/C.step`: `Thread camera 24.4`, `Thread lens 29.6`
- `OpenHI_STEP/Collimator tube.step`: `Outer thread`, `Thread left 24.8`
- `OpenHI_STEP/Collimator cap.step`: `Cap thread 24.8`
- `Nature_STEP/BS lateral.step.step`: repeated `Thread camera 24.4`, `Thread lens 29.6`, `Thread top`, `Thread BS`

Imported A/B/C branch bounding boxes:

| Branch | Bounding box |
| --- | --- |
| `A.step` | `40 x 40 x 50 mm` |
| `B.step` | `40 x 40 x 54.4 mm` |
| `C.step` | `54 x 40 x 40 mm` |

## Artifact Versions

| Version | Folder | Notes |
| --- | --- | --- |
| v1 | `cad/designs/cmount_threaded_reflector_assembly/artifacts/v1_20mm_threads/` | Previous `20 mm + 10 mm + 20 mm` tube, `20 x 20 x 20 mm` pocket. |
| v2 | `cad/designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/` | Current print-fit design using the old STEP `24.4/24.8` male/female rule and `0.4 mm` reflector pocket clearance. The folder is split into named run subfolders. |

Current v2 runs:

| Run | Folder | Main file |
| --- | --- | --- |
| Printable assembly | `2026-06-09_v2_printable_assembly/` | `threaded_reflector_assembly_threaded.step` |
| Editable decomposition | `2026-06-10_v2_editable_decomposition/` | `threaded_reflector_full_decomposition.step` |

## Thread And Fit Rule

The old STEP thread profile uses a swept triangular tooth: `0.4 mm` radial height, `0.8 mm` base, and `0.8 mm` pitch/gap. The camera-side printed male label is `24.4`; matching female/cutter labels are `24.8`. Use this as a diametral print allowance table rather than scaling the full part.

Purchased taps now recorded in the reusable thread reference:

- C-mount standard tap: `1"-32UN`, also searched as `C口镜头丝锥` or `1-32UN tap`.
- Larger available tap: `M30x0.75`, useful for new tooling-based large-thread interfaces. It is close to, but not identical with, the old OpenHI larger `29.6` root / about `30.6-30.9 mm` crest / inferred `0.8 mm` pitch family.

See `openhi-print-fit-and-thread-reference.md` for the measured table.

## Current V2 Tube

| Feature | Value |
| --- | ---: |
| Total length | `50 mm` |
| Left male thread length | `15 mm` |
| Right male thread length | `15 mm` |
| Center unthreaded body | `20 mm` |
| Male root OD | `24.4 mm` |
| Male crest OD | `25.2 mm` |
| Body OD | `28.4 mm` |
| Bore | `20 mm` |
| Center body wall | `4.2 mm` |
| Thread pitch | `0.8 mm` |
| Thread tooth | `0.4 mm` high, `0.8 mm` base |
| Thread hand | right-hand when viewed from each engaging end |
| Center body bottom plane | `Z = 0`, same as holder bottom |

## Current V2 Reflector Holder

| Feature | Value |
| --- | ---: |
| Nominal reflector | `20 x 20 x 20 mm` |
| Reflector pocket | `20.4 x 20.4 x 20.4 mm` |
| Wall thickness | `4 mm` |
| Top | open |
| Left side | open through threaded socket |
| Female socket length | `24 mm` |
| Maximum internal female thread length | `20 mm` |
| Female bore/root OD | `24.8 mm` |
| Female groove cutter crest OD | `25.6 mm` |
| Socket outer OD | `34 mm`, clipped flat at bottom |
| Optical axis height | `14.2 mm` |
| Tube STL bounds | `50.0 x 28.4 x 28.4 mm` |
| Holder STL bounds | `48.4 x 34.0 x 31.2 mm` |
| Assembly STL bounds | `83.4 x 34.0 x 31.2 mm` |

## Generated Support Files

Primary printable files:

- `cad/designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/male_male_cmount_tube.stl`
- `cad/designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/top_open_reflector_holder.stl`

Support files:

- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/male_male_cmount_tube_envelope.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/top_open_reflector_holder_envelope.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/threaded_reflector_assembly_envelope.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/male_male_cmount_tube_threaded.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/top_open_reflector_holder_threaded.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/threaded_reflector_assembly_threaded.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/threaded_reflector_exploded_thread_detail.png`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/assembly_side_section.svg`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/assembly_top_view.svg`
- `artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/threaded_reflector_assembly_top_sketch.dxf`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/male_male_cmount_tube_decomposed.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/male_male_cmount_tube_decomposed_exploded.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/top_open_reflector_holder_boolean_recipe.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/top_open_reflector_holder_decomposed.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/top_open_reflector_holder_decomposed_exploded.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/threaded_reflector_full_decomposition.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/tube_left_male_thread.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/tube_right_male_thread.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/holder_female_thread_cutter.step`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/thread_profile_sketch.svg`
- `artifacts/v2_15mm_threads_print_fit/2026-06-10_v2_editable_decomposition/decomposition_recipe_sketch.svg`

Use STL for printing because it is generated directly from the printable OpenSCAD thread geometry. Use `threaded_reflector_assembly_threaded.step` when a single STEP file with both threaded parts is needed. The envelope STEP files are intentionally smooth and lightweight.

For editable CAD, use the decomposition STEP files:

- Tube: `tube_base_no_threads + tube_left_male_thread + tube_right_male_thread`.
- Holder: `holder_smooth_bore_base - holder_female_thread_cutter = threaded holder`.
- If starting from a fully solid holder base, subtract `holder_full_thread_cutter`, which includes the smooth bore plus the female thread cutter.

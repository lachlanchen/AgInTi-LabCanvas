# OpenHI Print-Fit And Thread Reference

Date: 2026-06-09

## Scope

This note records the print-fit dimensions inferred from the local OpenHI/Nature STEP reference files. The raw STEP archives remain ignored under `cad/sources/` and `cad/extracted/`; this file keeps the reusable measurements.

Use these values for parts that thread into, slip into, or otherwise mate with the old 4f system. Do not scale a whole model to tune fit. Change the named male, female, pocket, or clearance parameters.

## Shapr3D And STEP Regeneration Notes

`/home/lachlan/Downloads/Nature.shapr` and `cad/extracted/OpenHI_STEP/` should be treated as the same OpenHI/Nature design geometry. The STEP folder is the flatter working export: the bodies were moved to a root-level/simple layout so the agent can inspect and export them more easily.

Current Shapr3D experience on Ubuntu:

- The `.shapr` file can be inspected as a package/database, but the useful holder solids are imported Parasolid/B-rep bodies, not a clean editable Shapr feature tree.
- Exact regeneration should therefore start from the exported STEP B-rep and verify bbox, solid count, face count, surface type counts, and thread/chamfer evidence.
- Make physical-fit changes as sibling surgical variants from the exact baseline. Do not overwrite the exact regeneration folder.
- Preserve named bodies separately where possible. For Lens C, `Thread BS` is the left threaded solid and `T branch head (1)` is the main holder body.
- STEP export/re-import can shift reported tolerance boxes by a few microns. Record construction facts and tolerance-based checks instead of brittle exact bbox string equality.

The earlier `openhi_lens_c_holder_receiver_25p4` folder was a C-mount-sized experiment and is not the corrected Lens C OpenHI task. The corrected Lens C task is a 30 mm OpenHI print-fit change, not a 25.4 mm C-mount conversion.

## Thread Tooth Profile

The old STEP files include repeated swept-triangle evidence:

| Evidence | Value | Meaning |
| --- | ---: | --- |
| Side vector length | `0.565685 mm` | 45 degree side of a `0.4 x 0.4 mm` right triangle |
| Tooth radial height | `0.4 mm` | root radius to crest radius |
| Tooth base | `0.8 mm` | axial base of the isosceles tooth |
| Pitch / gap | `0.8 mm` | helix advance per tooth, close to C-mount `0.79375 mm` |

Practical rule: model the old printed thread as a `0.8 mm` pitch helix with a triangular tooth that is `0.4 mm` high and `0.8 mm` wide. Industrial C-mount is 1"-32, but the local STEP geometry appears rounded to `0.8 mm`.

## Thread Runout Modeling Rule

When a swept helix starts and stops exactly on the nominal end faces, the first
and last partial teeth can disappear or leave a short smooth section. For clean
printed threads:

- Female/internal thread by subtraction: make the thread cutter extend by about
  half a pitch beyond each nominal end before subtraction. For the local
  `0.8 mm` pitch, use `0.4 mm` extra at each end. The final socket body clips
  the cutter naturally, so no visible overflow remains.
- Male/external thread: generate the male thread with the same extra half pitch,
  then trim/cut the final solid back to the real mount end face. This preserves
  a fully developed thread at the end without leaving thread geometry outside
  the intended cylinder length.
- Keep the tooth height, tooth base, and pitch unchanged when adding this
  runout. The runout is a construction technique, not a thread-spec change.

## C-Mount Versus OpenHI 30 mm Thread

Do not mix the two systems:

- Standard C-mount is `1"-32 UN`: nominal major diameter `25.4 mm`, pitch `0.79375 mm`.
- In a printed CAD model, a male C-mount thread may use a smaller root cylinder such as `24.6 mm`, with thread crests reaching `25.4 mm`.
- For a female C-mount socket, make a smaller pilot bore, then subtract a male-thread-shaped cutter whose max diameter is `25.4 mm` or slightly larger for print clearance. A plain `25.8 mm` hole is usually too large and may not engage.
- The OpenHI lens/BS/top family is a larger printed thread family near 30 mm. Do not convert Lens B/C holders to 25.4 mm unless the actual task is to make a new C-mount adapter.

For future female printed C-mount experiments, a reasonable starting point is:

| Parameter | Starting value |
| --- | ---: |
| nominal C-mount major diameter | `25.4 mm` |
| pitch | `0.79375 mm` or local rounded `0.8 mm` |
| male root | about `24.6 mm` |
| female pilot | about `24.8-25.0 mm` |
| female cutter max | `25.4-25.8 mm`, depending required printer clearance |

If using a real `1"-32UN` tap, design the pilot for tapping and cut the thread physically rather than relying on printed thread accuracy.

## Lens C Holder 30.0/30.4 Receiver Fix

For `cad/extracted/OpenHI_STEP/Lens C holder.step`, the corrected task is to tighten the positive-X OpenHI female receiver, not to add C-mount.

Original measured receiver evidence:

| Feature | Original value |
| --- | ---: |
| left preserved `Thread BS` male/root-like thread faces | about `29.8 mm` |
| positive-X female receiver cylindrical/root faces | about `30.2 mm` |
| center bore | `24.0 mm` |
| lens seat cylinder before receiver chamfer | `25.5 mm`, x `324.5-325.0 mm` |
| original transition chamfer | `25.5 -> 30.2 mm`, x `325.0-327.35 mm`, about 45 degrees |

Corrected print-fit idea:

| Feature | New value |
| --- | ---: |
| female smooth pilot/start diameter | `30.0 mm` |
| female groove/thread cutter max diameter | `30.4 mm` |
| pitch | `0.8 mm` |
| radial tooth height | `0.2 mm` |
| preserved lens seat | `25.5 mm`, x `324.5-325.0 mm` |
| rebuilt transition chamfer | `25.5 -> 30.0 mm`, length `2.25 mm`, x `325.0-327.25 mm` |
| thread section | starts at x `327.25 mm`; preserves the old thread end near x `335.9 mm` |

Important chamfer rule: when reducing the female start diameter from `30.2` to `30.0`, adjust the lens-side 45 degree transition chamfer. Keeping the old x-length would make the chamfer angle/landing inconsistent. The clean OpenHI version preserves the 25.5 mm lens seat and shortens the 45 degree chamfer from `2.35 mm` to `2.25 mm`.

## Purchased Thread Tools

Use this table when choosing whether to tap/chase a printed part or model a new
mate around available tooling.

| Tool bought | How to say/search it | Use | Relation to STEP evidence |
| --- | --- | --- | --- |
| C-mount standard tap | `C口镜头丝锥 1"-32UN`, `1-32UN tap`, `1 inch 32 TPI` | Real C-mount female/internal thread; best for optical C-mount compatibility | Standard C-mount is `25.4 mm` major diameter and `0.79375 mm` pitch. This is the correct standard tool for the smaller camera/C-mount side. |
| Metric fine tap | `M30x0.75 丝锥`, `M30 x 0.75 right-hand tap` | Practical available tool for the larger OpenHI lens/top/BS family if designing new matching parts around this tap | The old STEP larger family is labelled around `Thread lens 29.6` with about `30.6 x 30.9 mm` crest envelope and inferred `0.8 mm` pitch. `M30x0.75` is close but not the same; use it deliberately as a new tooling-based interface or test-fit before relying on old-part compatibility. |

Taobao wording:

```text
C口标准丝锥：C口镜头螺纹丝锥，规格 1"-32UN，右旋，60度牙型。
30mm细牙丝锥：M30x0.75 丝锥，右旋，60度牙型。
```

## Mating Fit Table

| Fit role | Reference STEP evidence | Measured envelope | Print-fit rule |
| --- | --- | ---: | --- |
| C-mount/camera male thread | `OpenHI_STEP/B.step`, `OpenHI_STEP/C.step`: `Thread camera 24.4` | about `25.2 x 25.4 x 5.1 mm` thread envelope | Use `24.4 mm` male root OD and `25.2 mm` crest OD. |
| Matching female socket/cutter | `OpenHI_STEP/Collimator tube.step`: `Thread left 24.8`; `Collimator cap.step`: `Cap thread 24.8` | about `25.6 x 25.4 x 5.8 mm` thread envelope | Use `24.8 mm` female bore/root and `25.6 mm` groove cutter crest. |
| Larger lens/BS/top thread | `Thread lens 29.6`, `Thread lens 29.6*`, `Thread top`, `Thread BS`, `Outer thread` | about `30.6 x 30.9 mm` crest envelope | Use `29.6 mm` root OD for the inserted threaded side; enlarge the receiving side by the needed print clearance. |
| Square branch module | `Lens B camera`, `Lens C camera`, `Scope fittings`, `T branch head` | exact `40 x 40 mm` cross sections | Keep the inserted body exact; add clearance to the receiving pocket. |
| Reflector cube pocket | New holder for nominal `20 x 20 x 20 mm` reflector | v2 pocket is `20.4 x 20.4 x 20.4 mm` | Add `0.4 mm` total clearance for a printed receiver. |

## Measured OpenHI Bodies

| File | Solid label | Measured bounding box |
| --- | --- | ---: |
| `A.step` | `Thread top` | `30.600 x 30.860 x 8.749 mm` |
| `A.step` | `Scope fittings (2)* (1)**` | `40.000 x 40.000 x 37.526 mm` |
| `A.step` | `Scope fittings (2)* (1)*` | `40.000 x 40.000 x 12.874 mm` |
| `B.step` | `Thread lens 29.6*` | `30.400 x 30.659 x 9.050 mm` |
| `B.step` | `Thread camera 24.4` | `25.200 x 25.415 x 5.100 mm` |
| `B.step` | `Lens B camera (1)**` | `40.000 x 40.000 x 35.013 mm` |
| `B.step` | `Lens B camera (2)*` | `40.000 x 40.000 x 18.987 mm` |
| `C.step` | `Thread camera 24.4` | `5.098 x 25.414 x 25.200 mm` |
| `C.step` | `Thread lens 29.6` | `9.150 x 30.658 x 30.400 mm` |
| `C.step` | `Lens C camera (1)*` | `35.013 x 40.000 x 40.000 mm` |
| `C.step` | `Lens C camera (2)*` | `18.987 x 40.000 x 40.000 mm` |
| `Collimator tube.step` | `Outer thread` | `30.860 x 20.800 x 30.600 mm` |
| `Collimator tube.step` | `Thread left 24.8` | `25.616 x 5.800 x 25.400 mm` |
| `Collimator tube.step` | `Collimating tube (1)` | `29.801 x 30.401 x 29.801 mm` |
| `Collimator cap.step` | `Cap thread 24.8` | `25.616 x 5.800 x 25.400 mm` |
| `Collimator cap.step` | `Collimator cap` | `33.800 x 20.000 x 33.800 mm` |
| `Lens C holder.step` | `Thread BS` | `6.300 x 30.860 x 30.600 mm` |
| `Lens C holder.step` | `T branch head (1)` | `50.000 x 40.000 x 40.000 mm` |

## Current Use In The Reflector Assembly

`cad/designs/cmount_threaded_reflector_assembly/` v2 applies this table as:

- male root OD `24.4 mm`, male crest OD `25.2 mm`;
- female bore/root OD `24.8 mm`, female groove cutter crest OD `25.6 mm`;
- thread pitch `0.8 mm`, tooth height `0.4 mm`, tooth base `0.8 mm`;
- two `15 mm` male thread sections;
- female socket length `24 mm`, internally threaded for at most `20 mm`;
- reflector pocket `20.4 x 20.4 x 20.4 mm`.

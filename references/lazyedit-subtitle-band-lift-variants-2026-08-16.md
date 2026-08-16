# LazyEdit Subtitle Band Lift Variants

Date: 2026-08-16

This note records two accepted four-language subtitle layouts and the reusable
LabCanvas policy for selecting between them. It is a layout comparison only;
neither published video should be processed or published again.

## Shared Settings

Both inspected final masters were `1080x1920` portrait blur-fill renders with a
top-right logo and the same four-row subtitle order:

```text
top
English
Japanese
Traditional Chinese
French
bottom
```

LazyEdit CLI language order is bottom-to-top, so the corresponding flag is:

```bash
--languages fr,zh-Hant,ja,en
```

Both used `heightRatio=0.4`, `rows=4`, `cols=1`, and `liftSlots=0`. The relevant
difference was only `liftRatio`.

## Style A: Lifted Band

The Paris LALACHAN publication used:

```bash
--subtitle-lift-ratio 0.1
```

At `1920px` height, this moves the complete subtitle band upward by `192px`.
The lower French row has more space beneath it, while English is visibly higher
in the portrait frame.

Evidence:

- LazyEdit video `520`
- publication session `67`
- publish job `353`
- final burn record `719`
- `liftRatio=0.1`

## Style B: Bottom-Anchored Band

The robotic-arm publication used:

```bash
--subtitle-lift-ratio 0
```

The complete subtitle band stays at the bottom of the frame. This puts English
closer to its familiar position in an unlifted three-language layout after the
French row is added.

Evidence:

- LazyEdit video `521`
- publish job `355`
- final burn record `720`
- `liftRatio=0.0`

## Renderer Meaning

LazyEdit calculates the band origin as:

```python
band_height = int(frame_height * height_ratio)
lift_pixels = int(frame_height * lift_ratio)
top_y = max(0, frame_height - band_height - lift_pixels)
```

For these two renders:

```text
band height:                 1920 * 0.4 = 768px
Paris lift:                  1920 * 0.1 = 192px
Paris band top:              1920 - 768 - 192 = 960px
Robotic-arm band top:        1920 - 768       = 1152px
whole-band position change:                       192px
```

Therefore, yes: the later style was produced by reducing total lift from `0.1`
to `0.0` when French was added. The new language itself does not automatically
change `liftRatio`.

This is approximate top-row continuity, not an exact baseline lock. Changing
from three rows to four also reduces each row's height. With a fixed 40% band
and the current gutter, the first-row center moves by roughly 33px even when
the band origin is unchanged. Exact baseline preservation would need a
reference layout and a calculated adjustment; the accepted `0.0` style is the
simple visual match.

## LabCanvas Policy

The WeChat worker exposes both styles as semantic one-shot options:

| Style | LazyEdit value | Use when |
| --- | ---: | --- |
| `lifted` | `0.1` | The full band should move upward or needs lower-edge clearance. |
| `bottom_anchored` | `0.0` | An added bottom language should keep upper rows visually near an unlifted layout. |

Rules:

1. Explicit layout wording is authoritative.
2. `subtitle_band_style` is task evidence; `subtitle_lift_ratio` is the actual
   LazyEdit CLI value.
3. If the request specifies no vertical style, omit both values and inherit the
   current LazyEdit Studio setting through `--use-current-settings`.
4. These are one-shot options. Do not pass `--persist-settings` unless the user
   explicitly asks to change Studio defaults.
5. Inspect a representative final frame before a new public publish because
   source composition and line wrapping can change the visual result.

The two inspected publications were both accepted. No preference or global
default is inferred from this comparison.

## LazyEdit Reference

The corresponding renderer-side note is:

```text
/home/lachlan/DiskMech/Projects/lazyedit/references/subtitle-band-lift-variants-2026-08-16.md
```

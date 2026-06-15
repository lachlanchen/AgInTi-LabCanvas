# Lumileds No-Resistor Generation And Order Log

## PCB Generation

Source reference: `pcb/nhi-pcb/nhi-pcb/leds/lumileds`.

Generator: `generate_lumileds_no_resistor_board.py`.

Method:

1. Copied the historical Lumileds KiCad project, schematic, and board.
2. Removed schematic symbol `R1` (`Device:R_US`) and board footprint
   `Resistor_SMD:R_0201_0603Metric`.
3. Removed the old split positive-net routing through the 1.8 ohm resistor.
4. Reassigned `U1 VCC` to `Net-(J1-Pin_2)` and added a direct positive trace from
   the header to the Lumileds pad.
5. Preserved the 24 mm circular outline, four M2 mounting holes, Lumileds
   footprint, and horizontal 1x2 power header.
6. Added project-local `fp-lib-table`, `sym-lib-table`, `footprints.pretty/`, and
   `symbols.kicad_sym` so the board opens without the original custom libraries.

## KiCad Outputs

Commands used:

```bash
kicad-cli sch erc --format json --severity-all -o artifacts/erc.json lumileds-no-resistor.kicad_sch
kicad-cli pcb drc --format json --severity-all -o artifacts/drc.json lumileds-no-resistor.kicad_pcb
kicad-cli pcb export step --force --include-pads --include-tracks --include-silkscreen --include-soldermask -o artifacts/lumileds-no-resistor.step lumileds-no-resistor.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab --precision 6 -o gerber lumileds-no-resistor.kicad_pcb
kicad-cli pcb export drill --generate-map --map-format svg --generate-report --report-path artifacts/drill-report.txt -o gerber lumileds-no-resistor.kicad_pcb
xvfb-run -a kicad-cli pcb render --output artifacts/lumileds-no-resistor-render-full.png --width 1400 --height 1000 --background opaque --quality high --floor --perspective --rotate 315,0,35 --zoom 0.95 lumileds-no-resistor.kicad_pcb
```

Validation:

- KiCad CLI: 10.0.3.
- ERC: 0 violations.
- DRC: 0 unconnected items.
- DRC warnings: copied footprint/library mismatch x2 and inherited connector
  silkscreen-edge warnings x3.

Full-view render:

```text
artifacts/lumileds-no-resistor-render-full.png
```

## JLC Automation

Public board config:

```text
jlcpcb_order/order-settings.json
```

Reusable script:

```text
agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py
```

The script packages Gerbers, validates ERC/DRC, chooses a size-aware surface
finish, merges private JLC shipping/login config from `~/.config/jlcpcb-order/`,
and delegates to the CDP browser automation.

JLC China fixes learned during this run:

- Fill board dimensions explicitly as `2.4 cm x 2.4 cm`; JLC did not auto-fill
  them from the Gerber.
- Force `FR-4` and `2` layers by row label because the page can retain old state.
- Use lead-free HASL (`无铅喷锡`) because OSP is not suitable for this 24 mm board
  on the China site.
- Reuse an already-selected default address instead of opening the address iframe.
- Set `出货方式 -> 单片`, no SMT, no stencil, and no edge polishing.
- Select the free board mark, then handle the `加客编` modal by choosing
  `每个单片内增加` and confirming.

Final submission:

- Time: 2026-06-15 14:52 HKT.
- State: submitted to JLC review.
- Success text: `订单提交成功，请等待审核`.
- Payment: not paid by automation.
- Private records: stored under `~/.config/jlcpcb-order/`.

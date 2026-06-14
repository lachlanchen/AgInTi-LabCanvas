# JLCPCB / JiaLiChuang Order Pack

Use this folder to manufacture the HYBEC HBL-273 / HBL-667 G4 halogen carrier as a bare PCB.

## Upload File

Upload this ZIP to JLCPCB/JiaLiChuang:

```text
hybec-hbl-273-g4-jlcpcb-gerber.zip
```

Do not upload the whole repository folder. JLCPCB expects a ZIP containing the Gerber and drill files.

## Agent-Assisted Ordering

The reusable browser automation tool is in:

```text
../../../agentic_tools/jlcpcb_order_agent/
```

It attaches to the shared Chrome profile on CDP port `49237`, uploads the Gerber ZIP, fills the JLC China order form, takes screenshots, and runs `检查订单`. Private recipient, phone, address, and login state stay outside git in `~/.config/jlcpcb-order/private.json`.

Example:

```bash
python3 ../../../agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py fill-settings
python3 ../../../agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py check-order
```

The live order currently has the address region/detail filled, but still needs recipient name and mobile phone before JLC can save the address and accept final submission.

## Recommended Order Settings

- Product type: Industrial / Consumer electronics.
- PCB type: FR-4 rigid PCB.
- Layers: 2.
- Dimensions: auto-detected from Gerber, expected about 24 mm x 24 mm circular board.
- Delivery format: Single PCB.
- Quantity: 5 for first prototype.
- Thickness: 1.6 mm.
- Copper weight: 1 oz for normal prototype, 2 oz if you want extra current/heat margin.
- Solder mask: Green for fastest/cheapest, or any color you prefer.
- Surface finish: Lead-free HASL for prototype cost, ENIG if you want better pad finish.
- Via covering: Tented or default is fine.
- Castellated holes: No.
- Edge plating: No.
- PCB assembly: No.
- SMT stencil: No.
- Order number: Specify a location. The back silkscreen contains `JLCJLCJLCJLC`.

## Human Checks Before Payment

1. Upload `hybec-hbl-273-g4-jlcpcb-gerber.zip`.
2. Confirm JLCPCB detects a 2-layer board and a ~24 mm circular outline.
3. Open Gerber Viewer and check:
   - two large G4 lamp holes near the center,
   - four M2 mounting holes,
   - circular board edge,
   - no missing drill file warning.
4. Confirm PCB assembly is disabled.
5. Confirm quantity, color, surface finish, and shipping address.
6. Pay only after the preview matches the render in `../artifacts/`.

The automation should stop at JLC's final order-check/payment boundary unless the user explicitly authorizes final submission.

## Thermal Warning

This is a 12 V, 20 W tungsten halogen lamp carrier. The PCB fabrication files pass KiCad DRC/ERC, but the physical design still needs thermal validation: lamp standoff height, airflow, nearby plastic, solder joint temperature, and FR-4 temperature must be checked before long powered operation.

## Sources Used For Order Workflow

- JLCPCB order guide: https://jlcpcb.com/help/article/how-do-i-place-an-order
- JLCPCB quote page: https://jlcpcb.com/quote
- JLCPCB Gerber viewer: https://jlcpcb.com/RGE
- JLCPCB API platform: https://api.jlcpcb.com/
- KiCad/JLCPCB MCP options: https://github.com/mixelpixx/KiCAD-MCP-Server and https://www.npmjs.com/package/@jlcpcb/mcp

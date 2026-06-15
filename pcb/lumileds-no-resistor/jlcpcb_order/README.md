# JLCPCB / JiaLiChuang Order Pack

This folder contains the manufacturing package and automation config for the
`lumileds-no-resistor` bare PCB.

## Upload Package

- Gerber ZIP: `lumileds-no-resistor-jlcpcb-gerber.zip`
- Manifest: `preflight-manifest.json`
- Full render: `../artifacts/lumileds-no-resistor-render-full.png`

The ZIP contains only Gerber and drill files. The drill map SVG is intentionally
excluded from the upload package and kept as a review artifact.

## Recommended Settings

- Site: JLC China web flow.
- PCB type: FR-4 rigid PCB, 2 layers.
- Size: `2.4 cm x 2.4 cm` circular board.
- Quantity: 5.
- Thickness: 1.6 mm.
- Copper: 1 oz.
- Solder mask / silkscreen: green / white.
- Finish: lead-free HASL (`无铅喷锡`). OSP is avoided because this board is under
  the China-site 70 mm minimum side rule for OSP.
- SMT / stencil / assembly: disabled.
- Compensation: standard contract handling (`按标准合同常规处理`).
- Shipping: separate shipment, default courier from private config.
- Board mark: free JLC customer code (`加嘉立创客编（免费）`).

## Automation Commands

Run from the repository root:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json validate

python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json \
  --site china place
```

Use `--allow-submit` only after the order-check drawer is clean:

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json \
  --site china --allow-submit place
```

Private recipient, address, cookies, screenshots, and order database rows stay in
`~/.config/jlcpcb-order/` and are not committed.

## Run Status

On 2026-06-15, the China web flow submitted this board to JLC review. The success
page reported `订单提交成功，请等待审核`. Payment was not made by the automation.

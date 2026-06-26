# JLCPCB Order Pack: tungsten-5v-400ma-3mm

This folder is generated for bare-PCB fabrication only. The lamp and connector
are manually installed after receiving the boards.

## Package And Validate

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/tungsten-5v-400ma-3mm/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/tungsten-5v-400ma-3mm/jlcpcb_order/order-settings.json validate
```

## China Web Order

The board is 24 mm x 24 mm. For JLC China, the order wrapper should select
lead-free HASL instead of OSP because OSP was rejected for small boards in prior
orders.

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/tungsten-5v-400ma-3mm/jlcpcb_order/order-settings.json \
  --site china \
  --allow-submit \
  place
```

The automation stops at the JLC review/payment boundary. Payment is manual.

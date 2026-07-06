# JLCPCB Order Pack: ws2812b-5050-rgb-led

This folder is generated for bare-PCB fabrication only. The WS2812B LED,
resistor, capacitor, and header are intended for manual assembly unless a later
SMT order maps exact parts and orientation.

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/ws2812b-5050-rgb-led/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/ws2812b-5050-rgb-led/jlcpcb_order/order-settings.json validate
```

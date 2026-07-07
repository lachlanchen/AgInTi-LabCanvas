# JLCPCB Order Pack: sk6812rgbw-5050-rgbw-led

This folder is generated for bare-PCB fabrication only. The SK6812RGBW LED,
capacitor, and two 1x02 headers are intended for manual assembly unless a later
SMT order maps exact parts and orientation. No onboard DIN resistor is fitted.

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/sk6812rgbw-5050-rgbw-led/jlcpcb_order/order-settings.json package

python3 agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/sk6812rgbw-5050-rgbw-led/jlcpcb_order/order-settings.json validate
```

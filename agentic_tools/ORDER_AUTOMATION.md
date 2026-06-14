# Manufacturing Order Automation

This repository keeps guarded, browser-assisted order tools for manufacturing workflows. The tools attach to logged-in Chrome sessions through CDP, store private state outside git, and stop at review/payment boundaries unless explicitly authorized.

## Unified Agent-Assisted Entry Point

Use the shared wrapper when you want a resilient run that creates an agent handoff packet if the website blocks automation:

```bash
python3 agentic_tools/order_assistant.py --provider wenext --site china status
python3 agentic_tools/order_assistant.py --provider wenext --site china --allow-submit place
python3 agentic_tools/order_assistant.py --provider jlc --site china --allow-submit place path/to/gerber.zip
```

Failure or blocker packets are written privately under:

```text
~/.config/manufacturing-order-assistant/packets/
```

Each packet includes the provider/site, command, redacted stdout/stderr tails, parsed state where available, diagnosis, and a concise agent prompt for the next Codex/AgInTi run. The wrapper delegates to the provider-specific scripts below; maintain provider DOM fixes there first, then keep this wrapper as the common safety layer.

## JLCPCB / JiaLiChuang PCB

Tool path:

```text
agentic_tools/jlcpcb_order_agent/
```

Primary commands:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh path/to/gerber.zip
agentic_tools/jlcpcb_order_agent/scripts/quick_order_global.sh path/to/gerber.zip
agentic_tools/jlcpcb_order_agent/scripts/quick_order_assistant.sh path/to/gerber.zip
```

Private config and logs:

```text
~/.config/jlcpcb-order/private.json
~/.config/jlcpcb-order/orders.sqlite3
```

The JLC tool handles Gerber upload, conservative PCB defaults, OSP/surface-finish checks, standard compensation, address/courier selection, and submit-to-review/payment boundaries.

## Wenext / 未来工场 3D Printing

Tool path:

```text
agentic_tools/wenext_3d_order_agent/
```

Primary commands:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_global.sh upload --navigate
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh upload --navigate
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh china-flow --allow-submit
```

Private config and logs:

```text
~/.config/wenext-3d-order/private.json
~/.config/wenext-3d-order/orders.sqlite3
```

The Wenext tool handles STL/STP/STEP upload, quote polling, cart/checkout delayed-load checks, personal `数电普票` invoice setup, address reuse, and stops at `checkout/payment` or `cashier?orderId=...`.

## Safety Rules

- Do not commit private configs, cookies, browser profiles, addresses, phones, OTP codes, or screenshots with personal data.
- Do not click recharge, wallet, PayPal, payment-link, QR-payment, or `发起支付` controls unless the user explicitly asks for payment.
- Record a snapshot and database state after each submitted-to-payment order.
- Treat disabled buttons, empty product tables, modal overlays, and invoice warnings as blockers until resolved.

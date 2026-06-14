# JLCPCB Order Agent

Reusable browser-assisted tooling for preparing and submitting JLCPCB/JiaLiChuang PCB orders from KiCad-generated Gerber ZIPs.

This agent is intentionally conservative. It automates upload, option prefill, address/contact entry, screenshots, and order checks, but it stops before final paid submission unless `--allow-submit` is passed for the `submit` command.

## Live Configuration

Private values stay outside git:

```bash
mkdir -p ~/.config/jlcpcb-order
cp agentic_tools/jlcpcb_order_agent/config.example.json ~/.config/jlcpcb-order/private.json
chmod 600 ~/.config/jlcpcb-order/private.json
```

The live browser profile used for the HYBEC test order:

```text
port: 49237
profile: ~/.cache/jlcpcb-order-shared
```

Do not commit `~/.config/jlcpcb-order/private.json`; it may contain address, recipient, phone, and login preferences.

Set `order.confirm_mode` to `manual` for `手动确认订单` or `auto` for `系统自动扣款并确认`. The tool keeps `manual` as the public example default.

## Tools Used

- `kicad-cli 10.0.3`: DRC/ERC, Gerber/drill export, render/STEP validation.
- Python `playwright`: attaches to the existing Chrome DevTools Protocol port.
- Google Chrome shared profile: keeps the JLC login persistent without launching a no-sandbox browser.
- JLC China order page: `https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder`.
- JLC global quote page: `https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006`.
- JLC desktop assistant: optional fallback, preferably installed locally at `~/.local/bin/jlc-assistant`.
- `xdotool` and ImageMagick `import`: manual UI fallback and screenshots when CDP selectors are unstable.

## Commands

Preferred unified wrapper with blocker packets:

```bash
python3 agentic_tools/order_assistant.py --provider jlc --site china status
python3 agentic_tools/order_assistant.py --provider jlc --site china --allow-submit place path/to/gerber.zip
```

If the website is difficult, the wrapper writes a private agent handoff packet under `~/.config/manufacturing-order-assistant/packets/`.

Launch or reuse the persistent browser:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
```

Inspect browser status:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py status
```

Global options such as `--config` and `--screenshot` go before the subcommand:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  --screenshot /tmp/jlc-status.png status
```

Upload a Gerber ZIP and open the order form:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py upload \
  --zip pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip
```

Apply standard bare-PCB settings:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py fill-settings
```

Fast path for the next order:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py prepare
```

`prepare` reuses an existing JLC order tab when present; otherwise it uploads the configured Gerber ZIP, opens the parsed order form, fills settings/address, and runs `检查订单`.

Quick China-site wrapper, defaulting to free `OSP` finish and separate shipment:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh \
  pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip
```

It records a private SQLite snapshot and stops before final submit. To submit only after manual review:

```bash
JLCPCB_ALLOW_SUBMIT=1 agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh
```

Important: JLC's China form rejected `OSP` for the current `2.4 cm x 2.4 cm` HYBEC board because any side is under `7 cm`. The script now blocks submit when JLC shows this warning. Use a larger board for OSP or explicitly choose another valid finish after review.

The China flow defaults to `顺丰电商标快` through `shipping.courier` in the private config and reselects it before `检查订单`.

Open the global quote flow and snapshot its DOM:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_global.sh \
  pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip
```

Submit the currently selected global cart item only after review:

```bash
JLCPCB_ALLOW_SUBMIT=1 agentic_tools/jlcpcb_order_agent/scripts/quick_order_global.sh
```

The global path selects the cart item, fills the China checkout address from private config, chooses `Review Before Payment`, submits for review, and stops before payment.

Prepare the cheaper assistant handoff:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_assistant.sh
```

Install the official Linux desktop assistant locally from the downloaded JLC ZIP:

```bash
agentic_tools/jlcpcb_order_agent/scripts/install_assistant_local.sh \
  ~/Downloads/JLCPcAssit-linux-x64-5.0.69.zip
```

This installs the unpacked app under `~/.local/opt/jlc-assistant-5.0.69/` and writes a wrapper to `~/.local/bin/jlc-assistant`. The assistant stores its own login/session under `~/.config/jlc-assistant`; keep that profile private and out of git.

Start or check the local assistant with the health-checked launcher:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_assistant_local.sh --restart
agentic_tools/jlcpcb_order_agent/scripts/launch_assistant_local.sh --status
```

On this remote Ubuntu desktop, the Electron sandbox helper was installed but the desktop namespace still blocked normal startup. The launcher therefore starts the app in a separate `setsid` session, defaults to remote-safe no-sandbox mode plus `--disable-gpu`, writes logs to `~/.cache/jlcpcb-order/assistant/assistant.log`, and verifies the process stays alive after startup. Avoid adding generic Chromium flags unless needed; the assistant's own command-line parser can crash on some flags. Set `JLCPCB_ASSISTANT_USE_SANDBOX=1` only when testing a normal local desktop session.

Fill address/contact from private config:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py fill-address --save-address
```

Run JLC order validation:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py check-order
```

After final submission, write a private completion log:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py post-submit-log
```

The log is written under `~/.config/jlcpcb-order/submissions/` with mode `600`.

Record the current live order state into the private SQLite database:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py record-order \
  --status draft_pending_invoice \
  --note "HYBEC G4 order after SMS ownership verification; invoice still unselected."
```

The database is `~/.config/jlcpcb-order/orders.sqlite3` with mode `600`. It stores board options, Gerber path, order page URL, shipping/contact fields, JLC validation count, price breakdown, and visible order-check lines. Do not store one-time SMS codes, browser cookies, or payment secrets.

For the detailed next-time checklist, exact DOM labels, script methods, and problem/fix table, see `docs/FAST_ORDERING_PLAYBOOK.md`.

For the shared manufacturing-order automation index covering both JLCPCB PCB orders and Wenext 3D-print orders, see `../ORDER_AUTOMATION.md`.

## Price and Shipping Notes

- `特价` is JLC's promotional base PCB fabrication price.
- `喷镀费` is the pad surface-finish/plating fee. For this order it came from `无铅喷锡`; switching to `OSP 免费` usually removes this fee, but OSP is less robust for storage and repeated handling.
- `OSP` can be invalid on very small China-site boards. The HYBEC `2.4 cm x 2.4 cm` board triggered JLC's warning that OSP is unsupported when any side is under `7 cm`.
- `品质赔付费` is caused by paid quality-compensation options such as `元器件移植全额赔付`. Bare PCB orders should use `按标准合同常规处理` unless component-transfer compensation is intentionally needed.
- `并单发货` means combining multiple orders into one shipment. If the chosen SF service says it does not support combined shipment, choose `不同交期订单不一起发货`.
- `顺丰电商标快` is the default prepaid courier for China web orders.
- The assistant price can be cheaper, but it changes the flow to `下载下单助手`; use it later only when intentionally continuing in the desktop assistant.
- The assistant login is separate from Chrome login. Run `~/.local/bin/jlc-assistant` once and confirm the customer center opens before relying on assistant handoff.

## HYBEC Live Order State

The first China web order was submitted on the JLC webpage and is pending JLC review/payment confirmation. Submitted settings:

- FR-4, 2 layers, `2.4 cm x 2.4 cm`.
- Quantity `5`.
- 1.6 mm thickness, 1 oz copper, green solder mask, white silkscreen.
- `无铅喷锡` lead-free HASL.
- Normal compensation: `按标准合同常规处理`.
- No SMT, no stencil.
- Free JLC customer-code mark selected.
- No edge polishing.
- Electronic receipt/delivery note.
- Shipping address/contact saved from private config.
- Account ownership verified as personal through SMS.
- Shipping mode changed to `不同交期订单不一起发货` to avoid SF combined-shipment incompatibility.
- Default courier selected: `顺丰电商标快`.
- Price breakdown observed before submission: base special price `￥30.00`, plating fee `￥30.09`, shipping `包邮`, web total `￥60.09`.

Private snapshots and the completion log are stored under `~/.config/jlcpcb-order/`.

The latest China web submission reached `嘉立创-下单成功` and is waiting for JLC review/payment. No payment or recharge action was performed by the automation.

A separate global-site test order was also submitted successfully through `https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006` using `Review Before Payment`. It used the global cart/checkout flow and stopped before payment. The global quote page did not expose OSP for this configuration; it used the valid global finish option visible in that flow.

The assistant-channel China test was not submitted because the requested `OSP` finish produced JLC's small-board incompatibility warning for this `2.4 cm x 2.4 cm` board. The script now treats that as a blocker.

After JLC review, finish payment manually from the order list or JLC notification:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py record-order --status paid_or_reviewed
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py post-submit-log
```

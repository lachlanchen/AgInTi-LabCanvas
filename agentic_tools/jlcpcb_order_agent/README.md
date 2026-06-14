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
- JLC desktop assistant: optional fallback installed at `/opt/jlc-assistant/jlc-assistant`.
- `xdotool` and ImageMagick `import`: manual UI fallback and screenshots when CDP selectors are unstable.

## Commands

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

## HYBEC Live Order State

The live order reached JLC's order-check drawer with:

- FR-4, 2 layers, `2.4 cm x 2.4 cm`.
- Quantity `5`.
- 1.6 mm thickness, 1 oz copper, green solder mask, white silkscreen.
- `无铅喷锡` lead-free HASL.
- Normal compensation: `按标准合同常规处理`.
- No SMT, no stencil.
- Shipping address partially filled as Guangdong/Shenzhen/Nanshan/Xili plus the provided detail line.

Remaining required live fields: recipient name and mobile phone number.

Once those are added to the private config, the live finish sequence is:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py fill-address --save-address
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py check-order
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py submit --allow-submit
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py post-submit-log
```

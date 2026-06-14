# Auto Order System Runbook

This runbook documents the exact system used for the HYBEC HBL-273/HBL-667 G4 bare-PCB JLC order.

## Scope

The system prepares a manufacturable KiCad board package, uploads the Gerber ZIP to JLC/JiaLiChuang, fills prototype settings, and stops at JLC's final order-check/payment boundary.

It is not a blind payment bot. Final submission requires explicit `--allow-submit`, a complete address/contact, and no visible payment/wallet blocker.

## PCB Inputs

- KiCad board: `pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb`.
- Gerber ZIP: `pcb/hybec-hbl-273-g4/jlcpcb_order/hybec-hbl-273-g4-jlcpcb-gerber.zip`.
- Preflight manifest: `pcb/hybec-hbl-273-g4/jlcpcb_order/preflight-manifest.json`.
- Order settings: `pcb/hybec-hbl-273-g4/jlcpcb_order/order-settings.json`.
- DRC/ERC: `pcb/hybec-hbl-273-g4/artifacts/drc.json`, `erc.json`.
- Renders: `pcb/hybec-hbl-273-g4/artifacts/hybec-hbl-273-g4-render*.png`.

## Browser Architecture

The stable route uses a normal Chrome profile with CDP enabled:

```bash
JLCPCB_CDP_PORT=49237 \
JLCPCB_CHROME_PROFILE=~/.cache/jlcpcb-order-shared \
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
```

The Python driver attaches with `playwright.chromium.connect_over_cdp("http://127.0.0.1:49237")`.

This avoids the earlier one-off Playwright persistent-context path that triggered Chrome's unsupported/no-sandbox banner.

## Live Order Steps

1. Uploaded the HYBEC Gerber ZIP on the China site.
2. Opened the parsed order form from the uploaded-file history.
3. Dismissed JLC onboarding overlays and the material selector.
4. Filled settings:
   - FR-4, 2 layers.
   - `2.4 cm x 2.4 cm`.
   - quantity `5`.
   - 1.6 mm, 1 oz, green mask, white silkscreen.
   - lead-free HASL: `无铅喷锡`.
   - normal compensation: `按标准合同常规处理`.
   - no SMT and no stencil.
5. Ran `检查订单`.
6. Filled address region/detail:
   - `广东省 / 深圳市 / 南山区 / 西丽街道`.
   - detail line from the private address.
7. Filled recipient/contact from private config for shipping, order contact, and technical contact.
8. Explicitly set:
   - no SMT;
   - no stencil;
   - free JLC customer-code board mark;
   - no edge polishing;
   - no laser stencil through `是否开钢网 -> 不需要`;
   - electronic receipt/delivery note;
   - manual order confirmation.
9. Completed JLC account ownership setup as a personal account through SMS verification.
10. Selected the personal ordinary electronic invoice profile created by JLC after ownership verification.
11. Changed shipping mode from `不同交期订单一起发货` to `不同交期订单不一起发货` after SF showed combined-shipment incompatibility.
12. Selected `顺丰电商标快` as the default prepaid courier.
13. Submitted the order on the web page and stopped at the JLC review/payment boundary.

Current live state: `嘉立创-下单成功`, submitted and pending JLC review/payment. JLC states that review usually takes 10-60 minutes, then payment/confirmation is required.

## Price and Shipping Terms

- `特价`: promotional base PCB manufacturing price.
- `喷镀费`: surface-finish/plating fee for the selected pad finish. In the HYBEC order this was charged for `无铅喷锡`. Selecting `OSP 免费` can remove the fee, but OSP is less durable for storage/handling.
- `OSP`: blocked by the China order form for the current `2.4 cm x 2.4 cm` board because JLC states that OSP cannot be used when any side is under `7 cm`.
- `品质赔付费`: paid quality-compensation fee. For bare PCB orders, keep `按标准合同常规处理`; do not use `元器件移植全额赔付` unless PCBA/component-transfer compensation is intentionally required.
- `快递费 包邮`: shipping is free for the selected prepaid courier.
- `顺丰电商标快`: default prepaid courier for China web orders.
- `并单发货`: combined shipment, meaning multiple orders wait and ship together. If SF says it does not support this, use `不同交期订单不一起发货`.
- `下单助手(优惠10.00元)`: cheaper assistant workflow. It changes the page action to downloading/opening the desktop assistant, so keep `网页版下单` unless intentionally using the assistant app.

Observed web price before submission:

```text
特价: ￥30.00
喷镀费: ￥30.09
快递费: 包邮
网页版下单总价: ￥60.09
下单助手价: ￥50.09
```

## Private Order Database

Order snapshots are stored in SQLite for repeatable handoff and audit:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py record-order \
  --status draft_pending_invoice \
  --note "HYBEC G4 order after SMS ownership verification; invoice still unselected."
```

Default database:

```text
~/.config/jlcpcb-order/orders.sqlite3
```

The database file is chmod `600` and is not committed. It stores Gerber path, board settings, shipping/contact fields, page URL, validation count, price breakdown, visible order-check lines, and a JSON snapshot. Do not store one-time SMS codes, browser cookies, payment credentials, or screenshots with private data.

Useful inspection commands:

```bash
sqlite3 ~/.config/jlcpcb-order/orders.sqlite3 ".schema order_snapshots"
sqlite3 ~/.config/jlcpcb-order/orders.sqlite3 \
  "SELECT id, created_at, status, web_total, plating_fee, selected_order_channel FROM order_snapshots ORDER BY id DESC LIMIT 5;"
```

## Fast Next-Time Flow

For the same kind of bare-PCB prototype order, update `~/.config/jlcpcb-order/private.json`, then run:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py prepare
```

`prepare` is the one-command path for routine orders. It:

1. reuses the existing `pcbPlaceOrder` tab when one is open;
2. otherwise uploads the configured Gerber ZIP and opens the parsed order form;
3. fills board settings, address/contact fields, and the configured default courier;
4. runs `检查订单`;
5. stops before final submission.

For new low-cost prototypes, use the wrapper defaults:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh path/to/gerber.zip
```

The wrapper sets `OSP`, separate shipment, web order channel, manual confirmation, `顺丰电商标快`, and records a private `china_checked` SQLite snapshot. To intentionally use the assistant discount path instead:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_assistant.sh path/to/gerber.zip
```

This selects the `下单助手` price card and opens `/opt/jlc-assistant/jlc-assistant` when present. It is a handoff; continue manually in the assistant and verify the CAM preview.

For the global site, use the provided global quote URL:

```bash
agentic_tools/jlcpcb_order_agent/scripts/quick_order_global.sh path/to/gerber.zip
```

This opens `https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006`, uploads the Gerber if a file input is present, writes `~/.config/jlcpcb-order/dom/global-quote-latest.json`, and stops before order submission.

To submit an already-correct global cart item for review:

```bash
JLCPCB_ALLOW_SUBMIT=1 agentic_tools/jlcpcb_order_agent/scripts/quick_order_global.sh
```

The global submit path used successfully in the live run:

1. select `.data-choice-list .el-checkbox__inner` on the cart page;
2. confirm the selected subtotal is nonzero;
3. click `Secure Checkout`;
4. fill the China address fields from private config, with postal code from `shipping.postal_code` or `518055`;
5. save the address and use `SF Express (Within Guangdong)`;
6. click `Continue`;
7. choose `Review Before Payment`;
8. click `Submit Order`.

Observed success URL:

```text
https://trade.jlcpcb.com/checkout/orderSuccess?systemType=order_pcb&spm=Jlcpcb.Confirmorder.1001
```

Observed success text:

```text
Your order has been submitted.
```

The assistant-channel China path was tested to order-check but was not submitted, because OSP was requested and JLC rejected OSP for this small board size. The correct next action is either enlarge the board beyond the OSP limit or explicitly select a valid finish such as HASL, then rerun `检查订单`.

If address contact values are complete and the order-check drawer is clean:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py fill-address --save-address
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py submit --allow-submit
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py record-order --status submitted
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py post-submit-log
```

The completion log is private by default and saved under `~/.config/jlcpcb-order/submissions/`.

Treat `pcbPlaceSuccess` as the submitted-success page for China orders. The order agent records that page into the private SQLite database after submission.

## Safety Rules

- Keep `~/.config/jlcpcb-order/private.json` mode `600`.
- Do not commit recipient, phone, address, cookies, screenshots containing personal details, or tokens.
- Do not click payment, recharge, wallet, or final submit controls without explicit user confirmation.
- For first prototypes, keep quantity low and inspect Gerber preview manually.
- Treat JLC option labels as unstable UI text; verify screenshots after automation.

## Fallback Tools

- JLC assistant: `/opt/jlc-assistant/jlc-assistant`.
- `xdotool`: click stubborn visible controls when selectors are blocked by overlays.
- ImageMagick `import`: capture visible desktop screenshots for manual verification.

## DOM Reference

The maintained DOM map is in `docs/DOM_MAP.md`. Refresh it from the live browser with:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py dump-dom \
  --url-contains www.jlc.com \
  --output ~/.config/jlcpcb-order/dom/current-page.json
```

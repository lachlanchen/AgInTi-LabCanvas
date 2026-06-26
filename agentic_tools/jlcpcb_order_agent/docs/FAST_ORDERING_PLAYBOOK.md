# Fast JLC Ordering Playbook

This document records the problems, DOM elements, scripts, and fixes from the successful China web order so the next Gerber order can be completed faster.

For the 2026-06-26 tungsten 5V 400mA order narrative and exact recovery
sequence, see `TUNGSTEN_5V_400MA_ORDER_HANDOFF.md`.

## Fast Path

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh path/to/gerber.zip
```

For generated board folders with a public order config, prefer the config-driven
wrapper:

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json \
  --site china place
```

Submit only after reviewing the clean order-check drawer:

```bash
JLCPCB_ALLOW_SUBMIT=1 agentic_tools/jlcpcb_order_agent/scripts/quick_order_china.sh path/to/gerber.zip
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/lumileds-no-resistor/jlcpcb_order/order-settings.json \
  --site china --allow-submit place
```

Default private config: `~/.config/jlcpcb-order/private.json`. Keep it mode `600` and never commit it.

## Script Map

- `launch_shared_chrome.sh`: opens the persistent logged-in Chrome profile on CDP port `49237`.
- `quick_order_china.sh`: wraps upload, setting fill, address/courier fill, order check, private DB record, optional submit.
- `submit_board_order.py`: board-config wrapper that packages Gerbers, validates ERC/DRC, chooses size-aware finish, merges public board config with private recipient config, and delegates to the quick China/global flow.
- `quick_order_global.sh`: opens global quote/cart flow, snapshots DOM, optionally submits selected cart item for review.
- `install_assistant_local.sh`: installs the official Linux assistant ZIP into `~/.local/opt/` and creates `~/.local/bin/jlc-assistant`.
- `launch_assistant_local.sh`: starts/stops/status-checks the local assistant as a detached process with remote-session stability flags and health checks.
- `quick_order_assistant.sh`: selects the China `下单助手` channel and opens `~/.local/bin/jlc-assistant` through `launch_assistant_local.sh`, falling back to `/opt/jlc-assistant/jlc-assistant` only if local is absent.
- `jlc_order_cdp.py status`: lists open JLC tabs.
- `jlc_order_cdp.py dump-dom --url-contains www.jlc.com --output ~/.config/jlcpcb-order/dom/current-page.json`: saves selectors/buttons/inputs.
- `jlc_order_cdp.py record-order`: writes a private SQLite snapshot to `~/.config/jlcpcb-order/orders.sqlite3`.
- `jlc_order_cdp.py post-submit-log`: writes a private completion log after success.

## Code Methods To Reuse

- `connect_page()`: attaches to existing Chrome over CDP, scores duplicate JLC tabs, prefers a visible clean order-check drawer for form work, and can prefer `pcbPlaceSuccess` for post-submit logging.
- `click_button()` / `click_first_button_text()`: click visible buttons by exact text.
- `click_option_near_label()`: safest way to choose a field option; it finds an exact label and clicks the matching option on the same row.
- `select_standard_compensation()`: selects `按标准合同常规处理` and handles the comparison modal.
- `select_courier()`: selects configured courier text, default `顺丰电商标快`.
- `selected_order_check_text()`: reads only the visible order-check drawer instead of the whole page.
- `visible_price_text()`: reads the right price panel for fee blockers.
- `assert_clean_for_submit()`: requires an open order-check drawer and blocks submit on missing fields, payment/recharge blockers, OSP incompatibility, or paid quality fee.
- `fill_settings()`: fills board defaults and uses row-label selection for SMT/stencil.
- `fill_address()`: fills private address/contact and then selects courier.
- `global_submit_current_cart()`: global checkout path through `Review Before Payment`.
- `handle_customer_code_modal()`: handles the `加客编` modal by selecting `每个单片内增加` and confirming after the free customer-code mark is selected.
- `handle_smt_required_modal()`: handles the JLC `请选择本单是否需要SMT贴片` modal by confirming `确定，不需要SMT`, then reruns order check.

## Problems And Fixes

| Problem | Symptom | Fix |
| --- | --- | --- |
| OSP not allowed on small board | Modal says `当前订单尺寸过小（任意边＜7cm），选择OSP工艺生产不能支持` | Choose `选择无铅喷锡`, `选择有铅喷锡`, or `选择沉金`; do not force OSP. |
| False paid-compensation blocker | Full page still contains unselected `元器件移植全额赔付` text | Check selected drawer text and price panel only. Block only if price has `品质赔付费` or drawer lacks `按标准合同常规处理`. |
| Stencil missing after “no SMT” | Drawer says `是否需要钢网 去填写` | Actual form label is `是否开钢网`; click `是否开钢网 -> 不需要`. |
| Generic `不需要` clicked wrong row | Automation clicked SMT or another option | Use `click_option_near_label(label, option)` instead of occurrence-based clicks. |
| Courier still unfilled | Drawer says `快递方式 去填写` | Select exact text `顺丰电商标快`. This is the default China courier. |
| Combined shipping rejected by SF | Page indicates SF does not support `并单发货` | Use `不同交期订单不一起发货`. |
| Browser no-sandbox/unsupported banner | One-off Playwright browser created warnings | Use the persistent Chrome profile and CDP attach via `launch_shared_chrome.sh`. |
| Success not detected | Submit stays ambiguous if only `pcbPlaceOrder` is recognized | Treat `pcbPlaceSuccess` and text `订单提交成功，请等待审核` as China success. |
| Board dimensions not parsed | Drawer shows `板子尺寸 去填写` | Fill `input[placeholder='长']` and `input[placeholder='宽']` from board config in centimeters. |
| Page retains old material/layer state | Drawer shows wrong material or layer count | Set `板材类别`, `板子层数`, and `出货方式` by row label every run. |
| JLC customer-code mark remains missing | Drawer shows `板上加标志 去填写` | Select `标志增加方式 -> 每个单片内增加`, choose `加嘉立创客编（免费）`, then confirm the `加客编` modal. |
| Existing default address opens as modal | Address iframe blocks earlier fields on rerun | Reuse the selected address from the main order page when address/contact text is already present. |
| Legacy upload already exists | User wants the old row submitted and no new upload | Use the row-specific `立即下单` for the matching Gerber stem or an existing `pcbFileId`; do not run upload again unless the row is absent or invalid. |
| SMT confirmation modal blocks order check | `检查订单` opens `请选择本单是否需要SMT贴片` instead of the drawer | Click `确定，不需要SMT`, then click `检查订单` again. |
| Confirmation/shipping still show `去填写` | Drawer reports `确认订单方式 去填写` or `发货方式 去填写` even after generic clicks | Select by row label: `确认订单方式 -> 手动确认订单`, `发货方式 -> 不同交期订单不一起发货`. |
| Duplicate JLC tabs cause false guards | Submit helper reads a stale form or the whole page body and sees wrong material names | Prefer the tab with a visible clean order-check drawer; after success, prefer `pcbPlaceSuccess` for record/log commands. |

## China DOM Elements

Entry URL:

```text
https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business
```

Stable page markers:

- Upload page: URL contains `newOnlinePlaceOrder`.
- Order form: URL contains `pcbPlaceOrder`.
- Success page: URL contains `pcbPlaceSuccess`.
- Upload input: first `input[type=file]`.
- Uploaded file action: `立即下单`.
- Existing uploaded row: match the Gerber ZIP stem and click that row's `立即下单`; this is safer than uploading a duplicate file.
- Order check drawer: `.selectedParamsCompCheck` or visible `.el-drawer`.
- Price panel: `#rightcontent` or `.rightcontentBox`.

Important labels/buttons:

- Quantity: `input[placeholder='数量'], input.listInput`, then visible quantity `5`.
- Production proof: `确认生产稿 -> 不需要`.
- Board size: fill `长` and `宽` in centimeters from the board config when JLC does not parse dimensions.
- Delivery format: `出货方式 -> 单片` for single-board Gerbers.
- Finish: `焊盘喷镀 -> OSP 免费 / 有铅喷锡 / 无铅喷锡 / 沉金`.
- OSP modal buttons: `选择沉金`, `选择有铅喷锡`, `选择无铅喷锡`, `取消`.
- Compensation: `品质赔付服务 -> 按标准合同常规处理【仅赔偿PCB，但不负责PCBA移植及元器件赔偿】`.
- Edge polish: `是否需要磨边 -> 不需要`.
- Board mark: `标志增加方式 -> 每个单片内增加`, `板上加标志 -> 加嘉立创客编（免费）`, then modal `每个单片内增加 -> 确认`.
- SMT: `是否SMT贴片 -> 不需要`.
- Stencil: `是否开钢网 -> 不需要`.
- Confirmation: `手动确认订单` unless the user explicitly wants auto confirmation.
- Receipt: `电子收据/送货单`.
- Shipping mode: `不同交期订单不一起发货`.
- Courier: `顺丰电商标快`.
- Check: `检查订单`.
- Submit from clean drawer: `确认并提交`.
- SMT modal after check: `请选择本单是否需要SMT贴片` -> `确定，不需要SMT`, then rerun `检查订单`.

## Submit Gate

Before clicking `确认并提交`, the visible drawer must not contain:

- `检测到您的订单还有`
- `去填写`
- `系统未检测到`
- `余额不足`
- `充值`
- OSP small-board warning

The selected drawer should contain:

- `品质赔付服务 按标准合同常规处理`
- `是否需要钢网 不需要` or `是否开钢网 不需要`
- `快递方式 顺丰电商标快`

The price panel must not contain `品质赔付费`. After success, record the page and stop before payment.

Do not submit from the plain form body. The submit guard should read the visible
order-check drawer only. If the drawer is closed or another JLC tab is active,
reopen `检查订单` on the correct row and verify the drawer again.

## Desktop Assistant Path

Preferred local install:

```bash
agentic_tools/jlcpcb_order_agent/scripts/install_assistant_local.sh \
  ~/Downloads/JLCPcAssit-linux-x64-5.0.69.zip
```

The app path is `~/.local/opt/jlc-assistant-5.0.69/jlc-assistant/jlc-assistant`, with wrapper `~/.local/bin/jlc-assistant`. It keeps assistant cookies and account state in `~/.config/jlc-assistant`; do not commit or copy that directory into a repo.

Run the assistant once and confirm it reaches `嘉立创客户中心`. The Chrome login profile does not automatically authenticate the desktop assistant. In this remote desktop, the setuid sandbox helper can be present yet still fail because namespaces are blocked. Use the stable launcher instead of a foreground terminal:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_assistant_local.sh --restart
agentic_tools/jlcpcb_order_agent/scripts/launch_assistant_local.sh --status
```

The launcher starts the assistant in a separate `setsid` session so it survives after the Codex shell command exits. It defaults to `JLC_ASSISTANT_NO_SANDBOX=1` with only `--disable-gpu`, logs to `~/.cache/jlcpcb-order/assistant/assistant.log`, and verifies the app stays alive. Keep extra Chromium flags empty unless debugging; this assistant can crash in its own command-line parser on some otherwise normal Chromium flags. If raw CDP inspection is needed, set `JLCPCB_ASSISTANT_DEBUG_PORT=51369`; do not use Playwright's browser-level `connect_over_cdp` against this Electron build because it can fail on browser-context management.

Use the assistant channel only after a clean China order-check drawer. It may show a lower price, but it is a separate desktop continuation and should be reviewed again before any final submit/payment.

## Global DOM Elements

- Quote URL: `https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006`.
- Gerber input: hidden `input[type=file][name=file]`.
- Cart URL: `https://cart.jlcpcb.com/shopcart/cart/`.
- Cart checkbox: `.data-choice-list .el-checkbox__inner`.
- Checkout button: `Secure Checkout`.
- Address placeholders: `First Name`, `Last Name`, `Country / Region`, `State`, `City`, `Street Address`, `Postal Code`, `Cell/Mobile number`.
- Submit mode: `Review Before Payment`.
- Final button: `Submit Order`.
- Success text: `Your order has been submitted.`

## Data Hygiene

- Commit scripts/docs only.
- Keep config, SQLite DB, DOM snapshots, completion logs, assistant profile data, cookies, OTP codes, and screenshots with private fields outside git.
- Use public summaries with redacted or generic address/contact language.

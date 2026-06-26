# Tungsten 5V 400mA JLC Order Handoff

Date: 2026-06-26

This note documents the successful China JLCPCB/JiaLiChuang submission for the
`tungsten-5v-400ma-3mm` bare PCB order. It is written as a reusable handoff for
the next agent run. Private contact, address, order IDs, screenshots with
personal data, cookies, and payment state remain only under `~/.config`.

## Outcome

The order was submitted on the China web site from an existing uploaded Gerber
row. No duplicate final upload was made during the final submission. The browser
reached the JLC success page:

```text
订单提交成功，请等待审核
```

The order is pending JLC review/payment. The automation did not pay, recharge,
or click wallet controls.

Private audit records:

```text
~/.config/jlcpcb-order/orders.sqlite3
~/.config/jlcpcb-order/submissions/jlcpcb-order-20260626-154025.md
```

## Board Package

Public board files:

```text
pcb/tungsten-5v-400ma-3mm/
pcb/tungsten-5v-400ma-3mm/tungsten-5v-400ma-3mm.kicad_pcb
pcb/tungsten-5v-400ma-3mm/jlcpcb_order/order-settings.json
pcb/tungsten-5v-400ma-3mm/jlcpcb_order/preflight-manifest.json
pcb/tungsten-5v-400ma-3mm/jlcpcb_order/tungsten-5v-400ma-3mm-jlcpcb-gerber.zip
```

Lamp constraints captured in the board dataset:

- 5 V, 400 mA, 2 W tungsten lamp.
- 3 mm lamp body.
- lead diameter: 0.25 mm.
- lead pitch: 1.00 mm.
- board footprint uses 0.45 mm plated drills and 0.75 mm pads.

Validation state before ordering:

- ERC: 0 violations.
- DRC: 0 violations and 0 unconnected items.
- JLC ZIP contains only manufacturing layers and drill files; Fab layers,
  `.gbrjob`, and drill map previews are excluded by `submit_board_order.py`.

## Verified JLC Settings

The final clean `检查订单` drawer showed:

```text
板材类别 FR-4
板子尺寸 2.4 CM x 2.4 CM
板子数量 5
板子层数 2
确认生产稿 不需要
出货方式 单片资料单片出货
成品板厚 1.6 MM
外层铜厚 1盎司
阻焊颜色 绿色
字符颜色 白色
焊盘喷镀 无铅喷锡
是否需要SMT 不需要
是否需要钢网 不需要
确认订单方式 手动确认订单
收据/送货单 电子收据/送货单
发货方式 不同交期订单不一起发货
快递方式 顺丰电商标快
```

The clean drawer had no `检测到您的订单还有`, no `去填写`, and no paid
`品质赔付费` blocker.

## Scripts Used

Main entry points:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/tungsten-5v-400ma-3mm/jlcpcb_order/order-settings.json \
  --site china place
python3 -u agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  --config ~/.config/jlcpcb-order/generated/tungsten-5v-400ma-3mm-china.json \
  check-order
python3 -u agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  --config ~/.config/jlcpcb-order/generated/tungsten-5v-400ma-3mm-china.json \
  submit --allow-submit
```

Private state paths:

```text
~/.config/jlcpcb-order/private.json
~/.config/jlcpcb-order/generated/tungsten-5v-400ma-3mm-china.json
~/.config/jlcpcb-order/screenshots/
~/.config/jlcpcb-order/orders.sqlite3
~/.config/jlcpcb-order/submissions/
```

Useful private screenshots from this run:

```text
tungsten-order-check-final-verified.png
tungsten-direct-submit-result.png
tungsten-submit-after-patch-already-success-4.png
```

Do not commit those screenshots; they can include personal or account state.

## Code Methods That Mattered

- `submit_board_order.py package`: creates a clean JLC ZIP and manifest.
- `submit_board_order.py validate`: blocks ordering on ERC/DRC failures.
- `choose_surface_finish()`: chooses `无铅喷锡` for small China-site boards
  when OSP is not valid.
- `connect_page()`: attaches to the persistent Chrome CDP session and now
  scores duplicate JLC tabs.
- `click_option_near_label()`: selects row-local options such as
  `确认订单方式 -> 手动确认订单`.
- `handle_smt_required_modal()`: clears the JLC modal
  `请选择本单是否需要SMT贴片` by selecting `确定，不需要SMT`.
- `selected_order_check_text()`: reads only the visible order-check drawer.
- `assert_clean_for_submit()`: requires an open, clean order-check drawer
  before final submit.
- `record_order()` and `post_submit_log()`: write the private audit trail.

## Problems Found And Fixes

| Problem | What happened | Fix |
| --- | --- | --- |
| Repeated uploads risk | A valid legacy uploaded row already existed. More uploads made the page confusing. | Reuse the row-specific `立即下单` or existing `pcbFileId`; upload only when no matching row exists. |
| Chrome died after launch | The launcher returned while Chrome was still tied to the shell. | `launch_shared_chrome.sh` now starts Chrome with `setsid`/`nohup` and checks the CDP endpoint before returning. |
| Wrong/stale JLC tab | Duplicate order tabs made the helper inspect a stale form. | `connect_page()` now scores tabs and can prefer a clean drawer or success page. |
| Quantity was blank | JLC parsed dimensions but not board quantity. | Select quantity `5` from the custom JLC grid, then verify the input and drawer. |
| Surface finish mismatch | The form initially selected leaded HASL. | Explicitly select `焊盘喷镀 -> 无铅喷锡`. |
| SMT modal blocked check | `检查订单` opened `请选择本单是否需要SMT贴片`. | Click `确定，不需要SMT`, then run `检查订单` again. |
| Two missing fields | Drawer showed `确认订单方式 去填写` and `发货方式 去填写`. | Use label-local clicks for `手动确认订单` and `不同交期订单不一起发货`. |
| False material blocker | Whole form text includes unselected `铜基板`, `铝基板`, and `FPC`. | Submit guard now reads only the visible clean drawer, not the whole page body. |
| Success logging used stale tab | Post-submit logs could record an old form URL. | Record/log commands can prefer `pcbPlaceSuccess`. |

## Next-Time Smooth Flow

For a board folder with `jlcpcb_order/order-settings.json`:

```bash
agentic_tools/jlcpcb_order_agent/scripts/launch_shared_chrome.sh

python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/BOARD/jlcpcb_order/order-settings.json \
  --site china package

python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/BOARD/jlcpcb_order/order-settings.json \
  --site china validate

python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/BOARD/jlcpcb_order/order-settings.json \
  --site china place
```

Review the clean drawer. If the user explicitly authorizes submit:

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/submit_board_order.py \
  --config pcb/BOARD/jlcpcb_order/order-settings.json \
  --site china --allow-submit place
```

If a matching uploaded row already exists and the user asks to use the legacy
file, do not run package/upload again. Use the existing form row, fill settings,
run `检查订单`, and submit only from a verified clean drawer.

After submission:

```bash
python3 -u agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  --config ~/.config/jlcpcb-order/generated/BOARD-china.json \
  record-order --status submitted_pending_review \
  --note "Submitted from verified clean drawer; payment pending review."

python3 -u agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  --config ~/.config/jlcpcb-order/generated/BOARD-china.json \
  post-submit-log
```

## Safety Checklist

Before final submit, require:

- Matching board file/legacy row.
- Correct board size, layer count, and quantity.
- `FR-4`, `无铅喷锡` or other intentionally selected valid finish.
- No SMT, no stencil, no paid compensation for bare PCB.
- Correct courier and shipping mode.
- Drawer has no missing-field warning.
- User has explicitly authorized final submit.

Stop before payment/recharge. Payment and review confirmation remain manual
unless the user explicitly asks otherwise.

# RGB 5050 LED PCB JLC Order Handoff

Date: 2026-07-09

This note documents the successful China JiaLiChuang/JLC web submissions for
the two 24 mm LED prototype boards:

- `pcb/ws2812b-5050-rgb-led`
- `pcb/sk6812rgbw-5050-rgbw-led`

Both orders reached the JLC success/review page. The automation did not pay,
recharge, or confirm payment.

## Submitted Settings

Both boards used the same manufacturing settings:

- quantity: `5`
- material: `FR-4`
- layers: `2`
- size: `2.4 cm x 2.4 cm`
- thickness: `1.6 mm`
- copper: `1 oz`
- solder mask: green
- silkscreen: white
- finish: `有铅喷锡`
- compensation: `按标准合同常规处理`
- SMT: not needed
- stencil: not needed
- confirmation: manual
- receipt: electronic
- shipping mode: `不同交期订单不一起发货`
- courier: `顺丰电商标快`
- channel: `网页版下单`

The visible web total was `¥30` per board at submission time.

## Private Evidence

Private logs, screenshots, generated configs, and order snapshots are stored
under:

```text
~/.config/jlcpcb-order/
```

Relevant private completion logs:

```text
~/.config/jlcpcb-order/submissions/jlcpcb-order-20260709-154417.md
~/.config/jlcpcb-order/submissions/jlcpcb-order-20260709-154847.md
```

The private SQLite database is:

```text
~/.config/jlcpcb-order/orders.sqlite3
```

## Fixes Learned In This Run

- Match JLC order tabs by the current Gerber ZIP stem to avoid cross-board reuse.
- After clicking an uploaded row, switch to the newly opened `pcbPlaceOrder` tab.
- Wait for SPA controls before filling; URL presence alone is not enough.
- Select quantity from the dropdown grid. Directly setting the input value does
  not update JLC's internal state.
- For China small-board `auto-china-size-aware`, use `有铅喷锡` unless lead-free
  is explicitly required; `无铅喷锡` added `喷镀费`.
- Select normal compensation through the comparison modal's left option.
- Submit can require either drawer `确认并提交` or side-panel `提交订单`.


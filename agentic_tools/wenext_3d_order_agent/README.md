# Wenext 3D Order Agent

Reusable browser-assisted tooling for preparing Wenext / 未来工场 3D-print orders from STL, STP, or STEP files.

The agent attaches to an already logged-in Chrome profile through Chrome DevTools Protocol (CDP). It can upload files, snapshot DOM state, record order state to a private SQLite database, fill known address forms, and continue checkout only when `--allow-submit` is passed. It never clicks payment buttons.

## Private Configuration

Keep account, address, phone, and login details outside git:

```bash
mkdir -p ~/.config/wenext-3d-order
cp agentic_tools/wenext_3d_order_agent/config.example.json \
  ~/.config/wenext-3d-order/private.json
chmod 600 ~/.config/wenext-3d-order/private.json
```

The live browser profile used for this test run:

```text
port: 53729
profile: ~/.cache/wenext-3d-order/chrome-profile
```

## Commands

Preferred unified wrapper with blocker packets:

```bash
python3 agentic_tools/order_assistant.py --provider wenext --site china status
python3 agentic_tools/order_assistant.py --provider wenext --site china --allow-submit place
```

If the website is difficult, the wrapper writes a private agent handoff packet under `~/.config/manufacturing-order-assistant/packets/`.

List active Wenext browser targets:

```bash
python3 agentic_tools/wenext_3d_order_agent/scripts/wenext_order_cdp.py \
  --site china list-targets
```

Snapshot the current global or China page:

```bash
python3 agentic_tools/wenext_3d_order_agent/scripts/wenext_order_cdp.py \
  --site global snapshot
python3 agentic_tools/wenext_3d_order_agent/scripts/wenext_order_cdp.py \
  --site china snapshot
```

Upload configured files and wait for a quote:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_global.sh upload --navigate
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh upload --navigate
```

Prepare the China flow and stop before checkout submission:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh china-flow
```

Submit only after manual review:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh \
  china-flow --allow-submit
```

For the global site, use the same safety gate:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_global.sh \
  global-flow --allow-submit
```

Snapshots and the private database are stored under `~/.config/wenext-3d-order/` with mode `600`.

## Tools Used

- Google Chrome with a persistent CDP profile.
- Python `websocket-client` for raw CDP calls.
- Wenext global site: `https://www.wenext.com/manufacture/quote?technology=3d-printing`.
- Wenext China site: `https://www.wenext.cn/manufacture/`.
- Private SQLite log: `~/.config/wenext-3d-order/orders.sqlite3`.

## Live Run Summary

Global Wenext order `10898885` was submitted to the payment page for two reflector assembly STL files. The order is waiting for payment; no payment button was clicked.

China Wenext order `95969306` was submitted to the cashier page. The order used the same two reflector assembly STL files, `数电普票(个人)`, normal delivery from the Shenzhen warehouse, and total payable `¥26.60`. The automation stopped at `发起支付`; no payment button was clicked.

Important China-site behavior now handled by the script:

- The cart and checkout pages can initially render `暂无产品`; wait until the product rows and `已选产品 2 款` appear.
- Direct quick checkout can show an empty product list; use `加入购物车`, then the header cart route.
- `数电普票` requires a saved invoice title. The private config supports `invoice.type`, `invoice.title`, and `invoice.email`.

See `docs/DOM_MAP.md` and `docs/FAST_ORDERING_PLAYBOOK.md` for selectors, page states, and recovery steps.

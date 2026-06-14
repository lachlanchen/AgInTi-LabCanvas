# JLCPCB DOM Map

This map records the selectors and visible labels used by the order agent. JLC changes labels and overlays often, so treat this as a starting point and refresh with `dump-dom` before high-value orders.

## China Web Flow

Entry URL:

```text
https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business
```

Stable selectors:

- Gerber upload: first `input[type=file]`.
- Uploaded-file action: `button:has-text('立即下单')`.
- Existing order tab detection: page URL contains `pcbPlaceOrder`.
- Quantity input: `input[placeholder='数量'], input.listInput`.
- Final action button: `#submitBtn`, after a clean check drawer.

Verified visible labels:

- Production proof: `不需要`.
- Thickness: `1.6`.
- Copper: `1盎司`.
- Solder mask: `绿色`.
- Silkscreen: `白色`.
- Surface finish: `OSP`, `无铅喷锡`, `有铅喷锡`, `沉金`.
- Compensation: `按标准合同常规处理【仅赔偿PCB，但不负责PCBA移植及元器件赔偿】`.
- SMT and stencil: `不需要`.
- Confirmation: `手动确认订单` or `系统自动扣款并确认`.
- Receipt: `电子收据/送货单`.
- Shipping mode: `不同交期订单不一起发货` or `不同交期订单一起发货(省运费)`.
- Order check: `检查订单`.
- Order-check drawer submit: `确认并提交`.

Address and invoice:

- Address iframe URL contains `receiveAddressListForOrder`.
- Address region selector: first `input[placeholder='请选择']` inside that iframe.
- Detail address input: `input[placeholder='请填写详细地址（例如xx街xx号）']`.
- Invoice entry link: visible text `选择开票资料`.
- Ordinary personal e-invoice card: `增值税普通发票 不可抵税`, then `确认选择`.

Price channel:

- Web card contains `网页版下单`.
- Assistant card contains `下单助手`.
- Selected card has a class containing `checked`.

## Global Quote Flow

Entry URL:

```text
https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006
```

The global wrapper opens the page in the same logged-in Chrome profile, tries the first `input[type=file]` for Gerber upload, writes a DOM snapshot, and stops. Use the China flow for fully verified automated submission until the global cart and checkout selectors are confirmed after login.

Observed on the logged-in global quote page:

- Page title: `Online PCB Instant Quote - JLCPCB`.
- Gerber upload: hidden `input[type=file][name=file]`.
- Material buttons: `FR-4`, `Flex`, `Aluminum`, `Copper Core`, `Rogers`, `PTFE Teflon`.
- Layer buttons: `1`, `2`, `4`, `6`, `8`, `10`, `12`, `14`, `16`.
- Thickness buttons include `0.4mm`, `0.6mm`, `0.8mm`, `1.0mm`, `1.2mm`, `1.6mm`, `2.0mm`.
- Solder mask buttons include `Green`, `Purple`, `Red`, `Yellow`, `Blue`, `White`, `Black`.
- Surface finish buttons observed: `HASL(with lead)`, `LeadFree HASL`, `ENIG`.
- Copper buttons include `1 oz`, `2 oz`, `2.5 oz`, `3.5 oz`, `4.5 oz`.
- Cart action: `SAVE TO CART`; the current automation does not click it.
- Cart page: `https://cart.jlcpcb.com/shopcart/cart/`.
- Cart item checkbox: `.data-choice-list .el-checkbox__inner`.
- Checkout button: `Secure Checkout`.
- Checkout address inputs: `First Name`, `Last Name`, `Country / Region`, `State`, `City`, `Street Address`, `Postal Code`, `Cell/Mobile number`.
- Checkout submit mode: `Review Before Payment`.
- Final submit button: `Submit Order`.

Snapshot command:

```bash
python3 agentic_tools/jlcpcb_order_agent/scripts/jlc_order_cdp.py \
  dump-dom --url-contains cart.jlcpcb.com \
  --output ~/.config/jlcpcb-order/dom/global-quote-latest.json
```

## Desktop Assistant Flow

The web page assistant card is selected through a button containing `下单助手`. After selection, JLC may change the action to `下载下单助手` or require desktop-app continuation.

Installed binary:

```text
/opt/jlc-assistant/jlc-assistant
```

The current script opens the assistant and records an `assistant_handoff` snapshot. It does not automate payment or final desktop submission.

## Terms Observed

- `特价`: promotional PCB base price.
- `喷镀费`: surface-finish/plating fee. `无铅喷锡` charged this; `OSP 免费` avoids it for typical prototype orders.
- `品质赔付费`: paid quality-compensation fee; select `按标准合同常规处理` to avoid it for bare PCB.
- `OSP` limit: the China site rejected OSP for the `2.4 cm x 2.4 cm` board because any side under `7 cm` is unsupported.
- `并单发货`: combined shipment. If SF rejects it, choose `不同交期订单不一起发货`.

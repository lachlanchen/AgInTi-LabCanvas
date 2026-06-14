# Wenext Fast Ordering Playbook

## Safe Order Path

1. Start Chrome with the persistent Wenext profile and CDP port `53729`.
2. Log in manually on the target site, preferably before uploading.
3. Run `list-targets` and confirm the target URL is `wenext.com` or `wenext.cn`.
4. Upload STL/STP/STEP files with `upload --navigate`, or use the existing quote page.
5. Wait until product rows show dimensions, material, accuracy, lead time, and price.
6. Review price and shipping manually.
7. Run the flow command with `--allow-submit` only when the page is ready.
8. Stop at the payment page. Pay manually.

## Global Site Flow

The global site is currently the most reliable path for the reflector print order.

Observed sequence:

```text
upload files -> address confirm -> Apply shipping -> Check Out -> Submit Order -> payment page
```

The completed test order reached:

```text
https://www.wenext.com/manufacture/checkout/payment?order_id=10898885
```

Observed totals:

- Parts: `$6.90`.
- SF Express: `$1.91`.
- Total payable: `$8.81`.
- Ships by: June 16, 2026.

Do not automate `Payment Link` or `PayPal`; payment remains manual.

## China Site Flow

Verified sequence:

```text
upload files -> wait for quote rows -> select rows -> 加入购物车 -> header cart -> wait cart rows -> 去结账 -> wait checkout rows -> 数电普票 -> 提交订单 -> cashier
```

Use the China wrapper:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh upload --navigate
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh china-flow
```

Only after the product rows and totals are visible:

```bash
agentic_tools/wenext_3d_order_agent/scripts/quick_order_china.sh \
  china-flow --allow-submit
```

The successful China run reached:

```text
https://www.wenext.cn/manufacture/cashier?orderId=95969306
```

Observed totals:

- Model total: `¥14.60`.
- Shipping: `¥12.00`.
- Total payable: `¥26.60`.
- Invoice: `数电普票(个人)`.
- Stop point: cashier page with `发起支付`; payment remains manual.

## Observed China Quote Data

Before the quote state was lost, the China site parsed both files:

- `male_male_cmount_tube.stl`: `50 x 28 x 28 mm`, volume `10976.36 mm3`.
- `top_open_reflector_holder.stl`: `48 x 34 x 31 mm`, volume `18195.90 mm3`.
- Material: `未来R4600树脂`.
- Accuracy: `±200微米或±0.2%`.
- Prices:
  - Tube: `24小时 ¥7.00`, `48小时 ¥5.50`, `72小时 ¥4.70`.
  - Holder: `24小时 ¥11.60`, `48小时 ¥9.10`, `72小时 ¥7.80`.
- Selected 48-hour cart total observed: `¥14.60`.
- Estimated dispatch observed: before `2026-06-16 23:30`.

## Failure Recovery

- If the page shows `解析文件报价中` for more than three minutes, record a snapshot and retry one file at a time.
- If a clean tab shows login/binding prompts, finish login in that same profile before upload.
- If `/manufacture/checkout?type=quick` shows `暂无产品`, go back to quote/cart and use `加入购物车`, then the header cart route.
- If `/manufacture/cart` initially shows `暂无产品`, wait up to a minute. The product rows can appear after the initial render.
- If `/manufacture/checkout` initially shows `暂无产品`, wait until product rows, shipping, invoice, and `提交订单` are enabled.
- If `提交订单` warns that invoice email is missing, choose `数电普票`, add a personal title, fill `收票人邮箱`, save, wait for `数电普票(个人)` on checkout, then submit again.
- If Element UI region selectors do not open from typed text, click the visible option labels directly: `广东省`, `深圳市`, `南山区`.
- If a modal or tip blocks a click, snapshot first, then close the highest visible `.el-dialog` or click the modal close button.

## Persistent Logs

The script writes:

- JSON snapshots: `~/.config/wenext-3d-order/submissions/<site>/snapshot-*.json`.
- SQLite state log: `~/.config/wenext-3d-order/orders.sqlite3`.

These files are private and include redacted page text. Do not commit browser profiles, cookies, screenshots with full address, or payment pages containing personal details.

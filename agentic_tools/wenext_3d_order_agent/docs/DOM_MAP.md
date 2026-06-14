# Wenext DOM Map

This map records selectors, labels, and page states observed during the June 14, 2026 ordering session. Refresh with `snapshot` before high-value orders because Wenext uses dynamic Element UI components.

## Global Site

Entry and checkout URLs:

```text
https://www.wenext.com/manufacture/quote?technology=3d-printing
https://www.wenext.com/manufacture/checkout
https://www.wenext.com/manufacture/checkout/payment?order_id=<id>
```

Observed selectors and labels:

- Upload: first `input[type=file]`.
- Address modal fields: `FirstName`, `LastName`, `Company`, `Tel./Mobile`, `Country`, `Address`, `Address2(Optional)`, `Address3(Optional)`, `Zip/Postal Code`, `City`, `State/Province`.
- Address confirm button: `Confirm`.
- Shipment panel address action: `Select Address`.
- Shipping price refresh: `Apply`.
- Checkout button: `Check Out`.
- Final order button: `Submit Order`.
- Payment page buttons: `Payment Link`, `PayPal`.

The global flow successfully reached payment page `order_id=10898885`. Payment was not clicked.

## China Site

Entry URL:

```text
https://www.wenext.cn/manufacture/
```

Observed selectors and labels:

- Upload: hidden `input[type=file]` with accept `.stl,.stp,.step,.STL,.STP,.STEP`.
- Header cart button: text like `0件产品 - ￥0.00`.
- Batch buttons: `删除选中产品`, `批量编辑`, `一键最长交期`, `一键最短交期`.
- Product row starts with `名称： <filename>`.
- Parser busy state: `<filename> 100% 解析文件报价中`.
- Material observed: `未来R4600树脂`.
- Accuracy observed: `±200微米或±0.2%`.
- Lead-time choices observed: `24小时`, `48小时`, `72小时`.
- Add-to-cart button: `加入购物车`.
- Direct checkout button: `去结账`.
- Cart page URL: `/manufacture/cart`.
- Cart-loaded markers: product filenames, `已选产品 2 款`, `总计 (含税) ¥ 14.60`.
- Checkout page URL: `/manufacture/checkout`.
- Checkout-loaded markers: `确认订单信息`, product filenames, `已选产品 2 款`, `总计 (含税) ¥26.60`.
- Cashier URL: `/manufacture/cashier?orderId=<id>`.
- Cashier markers: `收银台支付`, `订单号：`, `应付金额`, `发起支付`.

Address modal:

- Modal title: `新增收货地址`.
- Save button: `保存`.
- Input index map under visible `.el-dialog input`:
  - `0`: 公司名称
  - `1`: 收货人
  - `2`: country, prefilled `中 国`
  - `3`: province selector
  - `4`: city selector
  - `5`: district selector
  - `6`: detailed street address
  - `7`: phone prefix, prefilled `中国大陆 +86`
  - `8`: mobile phone
  - `9`: fixed phone
- Region option labels used: `广东省`, `深圳市`, `南山区`.
- Successful save toast: `保存成功`.

Invoice modal:

- Open button: `修改发票信息`.
- Invoice type labels: `数电普票`, `数电专票`, `不开发票`.
- New title button: `新增抬头`.
- Personal-title label: `个人`.
- Personal 普票 inputs: placeholders `发票抬头`, `收票人邮箱`.
- Save button: `保存`.
- Successful selected state on checkout: `数电普票(个人)`.

## Blocking States

- Login/binding overlay: body contains `您好，请登录`, `密码登录`, `验证码登录`, `账号绑定`, or `微信未绑定`. Finish login in the same Chrome profile before automation.
- Parser stuck: body contains `解析文件报价中`, checkout buttons disabled, and selected products remain `0 款，0 件产品`.
- Empty quick checkout: direct `去结账` can navigate to `/manufacture/checkout?type=quick` with `暂无产品` if the quote/cart state is not valid. Prefer `加入购物车` after product rows are ready.
- Delayed cart/checkout load: `/manufacture/cart` and `/manufacture/checkout` can show `暂无产品` for several seconds before rows appear. Do not submit or conclude failure until the wait expires.
- Submit no-op: if `提交订单` appears to do nothing, check whether the page already advanced to `/manufacture/cashier?orderId=<id>` in another polling interval.

## Snapshot Command

```bash
python3 agentic_tools/wenext_3d_order_agent/scripts/wenext_order_cdp.py \
  --site china snapshot
```

Snapshots include URL, title, visible body text, button states, input metadata, and visible modal text. Phone and email patterns are redacted before writing to disk.

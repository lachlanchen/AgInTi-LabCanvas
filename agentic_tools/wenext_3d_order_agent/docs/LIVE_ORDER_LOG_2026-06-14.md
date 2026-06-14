# Live Wenext Order Log - 2026-06-14

## Files

The test order used the printable reflector assembly STL files:

- `cad/designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/male_male_cmount_tube.stl`
- `cad/designs/cmount_threaded_reflector_assembly/artifacts/v2_15mm_threads_print_fit/2026-06-09_v2_printable_assembly/top_open_reflector_holder.stl`

## Global Site

Status: submitted to payment page, payment not clicked.

- Order ID: `10898885`.
- Page: `https://www.wenext.com/manufacture/checkout/payment?order_id=10898885`.
- Parts price: `$6.90`.
- Shipping: SF Express `$1.91`.
- Total payable: `$8.81`.
- Estimated ship date: June 16, 2026.

## China Site

Status: submitted to cashier page, payment not clicked.

Completed:

- Logged-in China page was accessible in the shared CDP browser.
- Shipping address modal was filled and saved successfully.
- The initial China quote parsed both STL files with 72-hour total `¥14.60`.
- The product rows were added to the China cart and loaded correctly after a delayed render.
- The checkout page loaded both product rows, shipping, and invoice information.
- A personal `数电普票` title was created with the private invoice email.
- Order ID: `95969306`.
- Page: `https://www.wenext.cn/manufacture/cashier?orderId=95969306`.
- Model total: `¥14.60`.
- Shipping: `¥12.00`.
- Total payable: `¥26.60`.
- Payment button shown: `发起支付`; not clicked.

Issues encountered and handled:

- Direct `去结账` entered `/manufacture/checkout?type=quick` with an empty product list.
- Returning to quote lost the parsed products.
- Re-uploading both files stayed at `100% 解析文件报价中`; `加入购物车` and `去结账` stayed disabled.
- A clean retry tab displayed login/binding overlays and ignored `DOM.setFileInputFiles`.
- Cart and checkout pages initially rendered `暂无产品`, then populated rows after waiting.
- Submit was blocked once because invoice email was missing; fixed by creating/selecting `数电普票(个人)`.

Next retry:

1. Re-authenticate the China site in the same CDP profile if any login/binding prompt appears.
2. Upload one STL at a time and wait for a complete product row.
3. Select the rows, click `加入购物车`, then open the header cart.
4. Wait for cart and checkout product tables to populate before clicking the next button.
5. Use `数电普票` or `不开发票` from private config, then submit only to cashier/payment boundary.

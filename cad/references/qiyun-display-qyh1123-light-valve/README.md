# Qiyun Display QYH1123 Light Valve References

This folder collects the local source material used for the QYH1123 cage holder
design in `cad/designs/qyh1123_light_valve_aligned_cage_holder`.

## Source Links

- Official product page: <http://www.qiyun-display.cn/Products_1/59.html>
- Baidu Netdisk: <https://pan.baidu.com/s/1X6MXwynprdCrXlzr4ncWeQ?pwd=w7by>
- Baidu extraction code: `w7by`
- Original local PDF: `/home/lachlan/Downloads/QYH1123DP8V3B.pdf`
- Original WeChat image: `/home/lachlan/Downloads/_cgi-bin_mmwebwx-bin_webwxgetmsgimg__&MsgID=86591867701543143&skey=@crypt_2b68eaed_26f270b4d904cc07c98d3c29100380d0&mmweb_appid=wx_webfilehelper.jpeg`

## Saved Files

- `source/QYH1123DP8V3B.pdf`: PDF copied from Downloads.
- `source/qiyun-official-qyh1123dp8v3b.pdf`: PDF downloaded from the official product page.
- `source/qiyun-product-page-59.html`: official page snapshot.
- `source/qiyun-product-image-*.jpg`: official product-page images.
- `source/wechat-qyh1123-links.jpeg`: WeChat image containing the URLs.
- `extracted/qiyun-product-page-59.txt`: text extracted from the official page.
- `extracted/QYH1123DP8V3B_page-1.png`: rasterized drawing sheet.
- `extracted/QYH1123DP8V3B.txt`: text extracted from the PDF.

## Dimensions Used

From the official page and drawing:

- Product model: `QYH1123` / `QYH1123DP8V3B`.
- Outer body: `18.0 x 20.0 x 2.0 mm`.
- Visible area: `15.0 x 15.0 mm`.
- Active-area offset: the drawing gives a `0.60 mm` left margin, so the active
  center is `0.90 mm` left of the physical glass center.
- Pins: two metal pins, `2.54 mm` pitch, about `8.0 mm` tail length.
- Pin table: pin 1 = `COM`, pin 2 = `SEG`.
- Drawing tolerance: `+/-0.2 mm`.
- Drive: static, `3.0 V`.
- Operating temperature: `-20 C` to `70 C`.

## Design Interpretation

The cage holder centers the 30 mm cage on the 15 x 15 mm visible area, not on
the physical 18 x 20 mm glass outline. The LCD body sits in a shallow sink; a
smaller through-window is derived from the visible area with a 1 mm support
terrace on each side.

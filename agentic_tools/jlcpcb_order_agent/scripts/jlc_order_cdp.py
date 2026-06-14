#!/usr/bin/env python3
"""Browser-assisted JLCPCB/JiaLiChuang order automation.

The script attaches to an already logged-in Chrome profile via CDP. It does not
create a fresh Playwright browser, so it avoids Chromium no-sandbox warnings and
reuses the user's persistent JLC session.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path("~/.config/jlcpcb-order/private.json").expanduser()
CHINA_UPLOAD_URL = "https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business"
GLOBAL_QUOTE_URL = "https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006"
DEFAULT_LOG_DIR = Path("~/.config/jlcpcb-order/submissions").expanduser()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = ROOT / path
    return path


def port_from_config(config: dict[str, Any]) -> int:
    return int(config.get("browser_debug_port") or os.environ.get("JLCPCB_CDP_PORT") or 49237)


def connect_page(config: dict[str, Any], prefer_order: bool = True) -> Page:
    port = port_from_config(config)
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]
    pages = list(context.pages)
    if prefer_order:
        for page in pages:
            if "pcbPlaceOrder" in page.url:
                page.bring_to_front()
                return page
    for page in pages:
        if "jlc.com/newOrder" in page.url:
            page.bring_to_front()
            return page
    page = context.new_page()
    page.goto(CHINA_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    return page


def visible_exact_button(page: Page, text: str) -> list[dict[str, Any]]:
    return page.evaluate(
        """(text) => [...document.querySelectorAll('button')].map((el, i) => {
            const r = el.getBoundingClientRect();
            const label = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            return {i, text: label, cls: String(el.className), x: r.x, y: r.y, w: r.width, h: r.height};
        }).filter(x => x.text === text && x.w > 0 && x.h > 0)""",
        text,
    )


def click_button(page: Page, text: str, occurrence: int = 0) -> bool:
    matches = visible_exact_button(page, text)
    if not matches:
        print(f"button not found: {text}")
        return False
    row = matches[min(occurrence, len(matches) - 1)]
    page.mouse.click(row["x"] + row["w"] / 2, row["y"] + row["h"] / 2)
    page.wait_for_timeout(600)
    print(f"clicked button: {text}")
    return True


def dismiss_guides(page: Page) -> None:
    for label in ("开始体验", "跳过", "知道了"):
        loc = page.get_by_text(label, exact=True)
        for idx in range(loc.count()):
            try:
                if loc.nth(idx).is_visible(timeout=200):
                    loc.nth(idx).click(timeout=2000, force=True)
                    page.wait_for_timeout(700)
                    print(f"dismissed guide: {label}")
                    return
            except PlaywrightTimeoutError:
                continue


def status(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config, prefer_order=False)
    print(f"title={page.title()}")
    print(f"url={page.url}")
    print(f"file_inputs={page.locator('input[type=file]').count()}")
    for p in page.context.pages:
        if "jlc" in p.url:
            print(f"tab: {p.title()} :: {p.url}")


def has_order_tab(config: dict[str, Any]) -> bool:
    page = connect_page(config, prefer_order=False)
    return any("pcbPlaceOrder" in p.url for p in page.context.pages)


def upload(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    zip_path = resolve_path(args.zip or config.get("gerber_zip"))
    if not zip_path or not zip_path.exists():
        raise SystemExit(f"missing Gerber ZIP: {zip_path}")
    page = connect_page(config, prefer_order=False)
    if "newOnlinePlaceOrder" not in page.url:
        page.goto(CHINA_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    file_input = page.locator("input[type=file]").first
    file_input.set_input_files(str(zip_path))
    print(f"uploaded={zip_path}")
    for attempt in range(60):
        page.wait_for_timeout(2000)
        text = page.locator("body").inner_text(timeout=10000)
        if "立即下单" in text and zip_path.stem in text:
            break
        print(f"poll={attempt + 1}")
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"screenshot={args.screenshot}")


def open_order_form(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config, prefer_order=False)
    button = page.locator("button:has-text('立即下单')").last
    button.click(timeout=15000)
    page.wait_for_timeout(3000)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"url={page.url}")
    print(f"screenshot={args.screenshot}")


def set_quantity(page: Page, quantity: int) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)
    q = page.locator("input[placeholder='数量'], input.listInput").first
    q.scroll_into_view_if_needed(timeout=3000)
    q.click(timeout=5000)
    page.wait_for_timeout(500)
    # JLC uses a custom grid. Click by exact visible text first, then fall back to
    # the observed first-cell coordinates for prototype quantity 5.
    loc = page.get_by_text(str(quantity), exact=True)
    for idx in range(loc.count()):
        try:
            if loc.nth(idx).is_visible(timeout=300):
                loc.nth(idx).click(timeout=3000)
                page.wait_for_timeout(700)
                print(f"quantity={q.input_value()}")
                return
        except PlaywrightTimeoutError:
            continue
    if quantity == 5:
        page.mouse.click(442, 405)
        page.wait_for_timeout(700)
        print(f"quantity={q.input_value()}")
        return
    raise RuntimeError(f"could not select quantity {quantity}")


def fill_settings(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    order = config.get("order", {})
    page = connect_page(config)
    page.set_viewport_size({"width": 1800, "height": 1000})
    dismiss_guides(page)
    # Material chooser sometimes appears as a modal on first use.
    if "请选择板材类别" in page.locator("body").inner_text(timeout=10000):
        page.mouse.click(860, 255)
        page.wait_for_timeout(1200)
    set_quantity(page, int(order.get("quantity", 5)))
    click_button(page, "不需要", 0)  # confirm production proof: no
    click_button(page, "1.6", 0)
    click_button(page, "1盎司", 0)
    click_button(page, "绿色", 0)
    click_button(page, "白色", 0)
    page.evaluate("window.scrollTo(0, 900)")
    page.wait_for_timeout(600)
    click_button(page, order.get("surface_finish", "无铅喷锡"), 0)
    click_button(page, "按标准合同常规处理【仅赔偿PCB，但不负责PCBA移植及元器件赔偿】", 0)
    if "按标准合约常规处理" in page.locator("body").inner_text(timeout=10000):
        # JLC may open a comparison modal when switching away from the paid
        # compensation option. The left card is the normal/standard handling.
        page.mouse.click(760, 748)
        page.wait_for_timeout(1000)
    page.evaluate("window.scrollTo(0, 2760)")
    page.wait_for_timeout(600)
    click_button(page, "不需要", 0)  # SMT
    click_button(page, "不需要", 1)  # stencil
    confirm_mode = order.get("confirm_mode", "manual")
    click_button(page, "系统自动扣款并确认" if confirm_mode == "auto" else "手动确认订单", 0)
    click_button(page, "电子收据/送货单", 0)
    click_button(page, "不同交期订单一起发货(省运费)", 0)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"screenshot={args.screenshot}")


def address_frame(page: Page):
    frame = next((f for f in page.frames if "receiveAddressListForOrder" in f.url), None)
    if frame:
        return frame
    page.evaluate("window.scrollTo(0, 2920)")
    page.wait_for_timeout(500)
    page.mouse.click(1178, 910)
    page.wait_for_timeout(1500)
    return next((f for f in page.frames if "receiveAddressListForOrder" in f.url), None)


def fill_address(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    shipping = config.get("shipping", {})
    page = connect_page(config)
    page.set_viewport_size({"width": 1800, "height": 1000})
    frame = address_frame(page)
    if not frame:
        raise SystemExit("address iframe not found")
    region = shipping.get("region") or []
    detail = shipping.get("detail") or config.get("address") or ""
    recipient = shipping.get("recipient_name") or config.get("recipient_name") or ""
    phone = shipping.get("phone") or config.get("phone") or ""
    if recipient:
        fill_labeled_input(frame, "联系人：", recipient)
    if phone:
        fill_labeled_input(frame, "联系电话：", str(phone))
    if region:
        cascader = frame.locator("input[placeholder='请选择']").first
        cascader.click(timeout=5000)
        frame.wait_for_timeout(500)
        for label in region:
            loc = frame.get_by_text(label, exact=True)
            clicked = False
            for idx in range(loc.count()):
                try:
                    if loc.nth(idx).is_visible(timeout=250):
                        loc.nth(idx).click(timeout=3000)
                        frame.wait_for_timeout(500)
                        clicked = True
                        break
                except PlaywrightTimeoutError:
                    continue
            if not clicked:
                raise RuntimeError(f"region option not visible: {label}")
    if detail:
        frame.locator("input[placeholder='请填写详细地址（例如xx街xx号）']").first.fill(detail)
    if args.save_address:
        if not recipient or not phone:
            raise SystemExit("recipient_name and phone are required before --save-address")
        click = frame.get_by_text("保存", exact=True)
        click.last.click(timeout=5000)
        frame.wait_for_timeout(1500)
        print("saved address")
    else:
        print("filled address form; not saved")
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"screenshot={args.screenshot}")


def fill_labeled_input(frame, label: str, value: str) -> None:
    ok = frame.evaluate(
        """({label, value}) => {
            const items = [...document.querySelectorAll('.el-form-item')];
            const item = items.find((el) => (el.innerText || '').includes(label));
            if (!item) return false;
            const input = item.querySelector('input');
            if (!input) return false;
            input.value = value;
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }""",
        {"label": label, "value": value},
    )
    if not ok:
        raise RuntimeError(f"could not fill labeled input: {label}")


def check_order(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config)
    click_button(page, "检查订单", 0)
    page.wait_for_timeout(2500)
    page.screenshot(path=args.screenshot, full_page=False)
    text = page.locator("body").inner_text(timeout=10000)
    for line in text.splitlines():
        s = " ".join(line.split())
        if s and any(k in s for k in ["检测到", "板子数量", "收货地址", "联系方式", "快递方式", "总价", "确认并提交"]):
            print(s[:240])
    print(f"screenshot={args.screenshot}")


def submit(args: argparse.Namespace) -> None:
    if not args.allow_submit:
        raise SystemExit("refusing final submit without --allow-submit")
    config = load_config(args.config)
    page = connect_page(config)
    text = page.locator("body").inner_text(timeout=10000)
    blockers = ["去填写", "系统未检测到", "充值", "支付", "余额不足"]
    if any(blocker in text for blocker in blockers):
        raise SystemExit("submit blocked by missing data or payment/wallet state")
    click_button(page, "确认并提交", 0)
    page.wait_for_timeout(2500)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"screenshot={args.screenshot}")


def prepare(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if not has_order_tab(config):
        upload(args)
        open_order_form(args)
    fill_settings(args)
    fill_address(args)
    check_order(args)
    print("prepare complete; review order-check drawer before submit")


def post_submit_log(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config)
    text = page.locator("body").inner_text(timeout=10000)
    order = config.get("order", {})
    shipping = config.get("shipping", {})
    log_dir = args.output_dir.expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = log_dir / f"jlcpcb-order-{stamp}.md"
    visible_lines = []
    for line in text.splitlines():
        s = " ".join(line.split())
        if s and any(
            key in s
            for key in [
                "订单",
                "总价",
                "板子数量",
                "板材类别",
                "板子尺寸",
                "快递",
                "支付",
                "余额",
                "审核",
            ]
        ):
            visible_lines.append(s[:240])
    content = [
        "# JLCPCB Order Completion Log",
        "",
        f"- Created: {datetime.now().isoformat(timespec='seconds')}",
        f"- Page URL: {page.url}",
        f"- Gerber ZIP: {config.get('gerber_zip', '')}",
        f"- Quantity: {order.get('quantity', '')}",
        f"- Surface finish: {order.get('surface_finish', '')}",
        f"- Compensation: {order.get('compensation', '')}",
        f"- Confirm mode: {order.get('confirm_mode', '')}",
        f"- Shipping region: {' / '.join(shipping.get('region', []))}",
        f"- Shipping detail: {shipping.get('detail', '')}",
        "",
        "## Visible Order Lines",
        "",
        *[f"- {line}" for line in visible_lines[:80]],
        "",
        "## Follow-Up Checklist",
        "",
        "- Confirm JLC engineering review result.",
        "- Download final production files or CAM preview if JLC modifies anything.",
        "- Record payment status, tracking number, and arrival inspection notes.",
    ]
    out.write_text("\n".join(content) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)
    print(f"wrote private completion log: {out}")


def snapshot_cmd(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config, prefer_order=False)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"screenshot={args.screenshot}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--screenshot", default="/tmp/jlcpcb-order-agent.png")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=status)
    p_upload = sub.add_parser("upload")
    p_upload.add_argument("--zip")
    p_upload.set_defaults(func=upload)
    sub.add_parser("open-order-form").set_defaults(func=open_order_form)
    sub.add_parser("fill-settings").set_defaults(func=fill_settings)
    p_addr = sub.add_parser("fill-address")
    p_addr.add_argument("--save-address", action="store_true")
    p_addr.set_defaults(func=fill_address)
    sub.add_parser("check-order").set_defaults(func=check_order)
    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--zip")
    p_prepare.add_argument("--save-address", action="store_true")
    p_prepare.set_defaults(func=prepare)
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--allow-submit", action="store_true")
    p_submit.set_defaults(func=submit)
    p_log = sub.add_parser("post-submit-log")
    p_log.add_argument("--output-dir", type=Path, default=DEFAULT_LOG_DIR)
    p_log.set_defaults(func=post_submit_log)
    sub.add_parser("snapshot").set_defaults(func=snapshot_cmd)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

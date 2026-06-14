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
import re
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path("~/.config/jlcpcb-order/private.json").expanduser()
CHINA_UPLOAD_URL = "https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business"
GLOBAL_QUOTE_URL = "https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006"
DEFAULT_LOG_DIR = Path("~/.config/jlcpcb-order/submissions").expanduser()
DEFAULT_DB_PATH = Path("~/.config/jlcpcb-order/orders.sqlite3").expanduser()
_PLAYWRIGHT = None
_BROWSER = None


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def redact_phone(text: str) -> str:
    return re.sub(r"1\d{10}", lambda m: f"{m.group(0)[:3]}****{m.group(0)[-4:]}", text)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
    global _PLAYWRIGHT, _BROWSER
    port = port_from_config(config)
    if _PLAYWRIGHT is None:
        _PLAYWRIGHT = sync_playwright().start()
    if _BROWSER is None or not _BROWSER.is_connected():
        _BROWSER = _PLAYWRIGHT.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    browser = _BROWSER
    context = browser.contexts[0]
    pages = list(context.pages)
    if prefer_order:
        for page in pages:
            if "pcbPlaceOrder" in page.url:
                page.bring_to_front()
                return page
        for page in pages:
            if "pcbPlaceSuccess" in page.url:
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


def visible_contains_button(page: Page, fragments: list[str]) -> list[dict[str, Any]]:
    return page.evaluate(
        """(fragments) => [...document.querySelectorAll('button')].map((el, i) => {
            const r = el.getBoundingClientRect();
            const label = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            return {i, text: label, cls: String(el.className), x: r.x, y: r.y, w: r.width, h: r.height};
        }).filter(x => x.w > 0 && x.h > 0 && fragments.every((fragment) => x.text.includes(fragment)))""",
        fragments,
    )


def click_button_containing(page: Page, fragments: list[str], occurrence: int = 0) -> bool:
    matches = visible_contains_button(page, fragments)
    if not matches:
        print(f"button not found containing: {' / '.join(fragments)}")
        return False
    row = matches[min(occurrence, len(matches) - 1)]
    page.mouse.click(row["x"] + row["w"] / 2, row["y"] + row["h"] / 2)
    page.wait_for_timeout(600)
    print(f"clicked button containing: {row['text']}")
    return True


def click_first_button_text(page: Page, text: str) -> bool:
    buttons = page.locator("button").filter(has_text=text)
    for idx in range(buttons.count()):
        try:
            button = buttons.nth(idx)
            box = button.bounding_box(timeout=500)
            if box:
                button.scroll_into_view_if_needed(timeout=3000)
                button.click(timeout=5000, force=True)
                page.wait_for_timeout(800)
                print(f"clicked button text: {text}")
                return True
        except PlaywrightTimeoutError:
            continue
    return click_button_containing(page, [text], 0)


def select_material_modal_fr4(page: Page) -> None:
    text = page.locator("body").inner_text(timeout=10000)
    if "请选择板材类别" not in text:
        return
    rows = page.evaluate(
        """() => [...document.querySelectorAll('*')].map((el) => {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            return {text, x: r.x, y: r.y, w: r.width, h: r.height};
        }).filter((row) => row.text === 'FR-4' && row.w > 0 && row.h > 0)"""
    )
    target = next((row for row in rows if 300 < row["x"] < 1500 and 100 < row["y"] < 700), None)
    if not target and rows:
        target = rows[-1]
    if target:
        page.mouse.click(target["x"] + target["w"] / 2, target["y"] + target["h"] / 2)
        page.wait_for_timeout(1500)
        print("selected material modal: FR-4")


def select_standard_compensation(page: Page) -> None:
    label = "按标准合同常规处理【仅赔偿PCB，但不负责PCBA移植及元器件赔偿】"
    if not click_first_button_text(page, label):
        print("standard compensation button not found")
        return
    page.wait_for_timeout(1000)
    has_modal = page.evaluate(
        """() => [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper')].some((el) => {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || el.textContent || '');
            return r.width > 0 && r.height > 0 && text.includes('按标准合约常规处理') && text.includes('元器件移植全额赔付');
        })"""
    )
    if has_modal:
        # JLC opens a comparison modal. The left card is normal PCB-only
        # compensation, without component-transfer compensation.
        page.mouse.click(760, 748)
        page.wait_for_timeout(1200)
        print("confirmed standard compensation modal")


def selected_order_check_text(page: Page) -> str:
    return page.evaluate(
        """() => {
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            const drawer = [...document.querySelectorAll('.selectedParamsCompCheck,.el-drawer')]
                .find((el) => visible(el) && text(el).includes('参数检查'));
            return drawer ? text(drawer) : '';
        }"""
    )


def visible_price_text(page: Page) -> str:
    return page.evaluate(
        """() => {
            const el = document.querySelector('#rightcontent') || document.querySelector('.rightcontentBox');
            return el ? (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ') : '';
        }"""
    )


def assert_clean_for_submit(page: Page, require_surface_finish: str | None = None) -> None:
    text = page.locator("body").inner_text(timeout=10000)
    check_text = selected_order_check_text(page) or " ".join(text.split())
    blockers = ["去填写", "系统未检测到", "充值", "余额不足", "检测到您的订单还有"]
    if any(blocker in check_text for blocker in blockers):
        raise SystemExit("submit blocked: order check still shows missing fields or payment/wallet blocker")
    price_text = visible_price_text(page)
    if "品质赔付费" in price_text:
        raise SystemExit("submit blocked: paid quality compensation is still selected")
    if "品质赔付服务" in check_text and "品质赔付服务 按标准合同常规处理" not in check_text:
        raise SystemExit("submit blocked: order check does not confirm standard quality compensation")
    if require_surface_finish and require_surface_finish.upper() == "OSP":
        if "选择OSP工艺生产不能支持" in text or "当前订单尺寸过小" in text:
            raise SystemExit("submit blocked: JLC says OSP is not supported for this board size")


def shipping_mode_label(mode: str | bool | None) -> str:
    if isinstance(mode, bool):
        return "不同交期订单一起发货(省运费)" if mode else "不同交期订单不一起发货"
    normalized = str(mode or "separate").strip().lower()
    if normalized in {"separate", "split", "no-combine", "no_combine", "not-together"} or "不一起发货" in normalized:
        return "不同交期订单不一起发货"
    if normalized in {"combine", "combined", "together", "same", "省运费"} or "一起发货" in normalized:
        return "不同交期订单一起发货(省运费)"
    return "不同交期订单不一起发货"


def select_order_channel_on_page(page: Page, channel: str | None) -> None:
    if not channel:
        return
    normalized = channel.strip().lower()
    if normalized in {"assistant", "helper", "desktop", "下单助手"}:
        click_button_containing(page, ["下单助手"], 0)
    elif normalized in {"web", "browser", "网页版下单", "网页版"}:
        click_button_containing(page, ["网页版下单"], 0)
    else:
        raise RuntimeError(f"unknown order channel: {channel}")


def click_option_near_label(page: Page, label: str, option: str) -> bool:
    row = page.evaluate(
        """({label, option}) => {
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            const labelEl = [...document.querySelectorAll('label,span,div')]
                .find((el) => visible(el) && text(el) === label);
            if (!labelEl) return null;
            labelEl.scrollIntoView({block: 'center', inline: 'nearest'});
            const labelRect = labelEl.getBoundingClientRect();
            const buttons = [...document.querySelectorAll('button')]
                .map((el, i) => ({el, i, text: text(el), rect: el.getBoundingClientRect()}))
                .filter((row) => visible(row.el)
                    && row.text === option
                    && row.rect.x > labelRect.x
                    && Math.abs((row.rect.y + row.rect.height / 2) - (labelRect.y + labelRect.height / 2)) < 55)
                .sort((a, b) => a.rect.x - b.rect.x);
            if (!buttons.length) return null;
            const target = buttons[0];
            target.el.click();
            const rect = target.el.getBoundingClientRect();
            return {index: target.i, text: target.text, x: rect.x, y: rect.y, w: rect.width, h: rect.height};
        }""",
        {"label": label, "option": option},
    )
    page.wait_for_timeout(900)
    if row:
        print(f"clicked option near {label}: {option}")
        return True
    print(f"option not found near {label}: {option}")
    return False


def select_courier(page: Page, courier: str | None) -> bool:
    if not courier:
        return False
    row = page.evaluate(
        """(courier) => {
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            const label = [...document.querySelectorAll('*')]
                .find((el) => visible(el) && text(el) === '选择快递');
            if (label) label.scrollIntoView({block: 'center', inline: 'nearest'});
            const matches = [...document.querySelectorAll('div,span,label,tr')]
                .map((el, i) => ({el, i, text: text(el), rect: el.getBoundingClientRect()}))
                .filter((row) => visible(row.el) && row.text === courier)
                .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
            if (!matches.length) return null;
            const target = matches[0];
            target.el.click();
            const rect = target.el.getBoundingClientRect();
            return {index: target.i, text: target.text, x: rect.x, y: rect.y, w: rect.width, h: rect.height};
        }""",
        courier,
    )
    page.wait_for_timeout(1200)
    if row:
        print(f"selected courier: {courier}")
        return True
    print(f"courier not found: {courier}")
    return False


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
    shipping = config.get("shipping", {})
    page = connect_page(config)
    page.set_viewport_size({"width": 1800, "height": 1000})
    dismiss_guides(page)
    # Material chooser sometimes appears as a modal on first use.
    select_material_modal_fr4(page)
    set_quantity(page, int(order.get("quantity", 5)))
    click_button(page, "不需要", 0)  # confirm production proof: no
    click_button(page, "1.6", 0)
    click_button(page, "1盎司", 0)
    click_button(page, "绿色", 0)
    click_button(page, "白色", 0)
    page.evaluate("window.scrollTo(0, 900)")
    page.wait_for_timeout(600)
    surface_finish = getattr(args, "surface_finish", None) or order.get("surface_finish", "OSP")
    click_button(page, surface_finish, 0)
    if surface_finish.upper() == "OSP":
        body_text = page.locator("body").inner_text(timeout=10000)
        if "选择OSP工艺生产不能支持" in body_text or "当前订单尺寸过小" in body_text:
            raise SystemExit("OSP is not supported for this board size; choose a valid finish before submit")
    select_standard_compensation(page)
    page.evaluate("window.scrollTo(0, 2760)")
    page.wait_for_timeout(600)
    click_option_near_label(page, "是否SMT贴片", "不需要")
    click_option_near_label(page, "是否开钢网", "不需要")
    confirm_mode = getattr(args, "confirm_mode", None) or order.get("confirm_mode", "manual")
    click_button(page, "系统自动扣款并确认" if confirm_mode == "auto" else "手动确认订单", 0)
    click_button(page, "电子收据/送货单", 0)
    shipping_mode = (
        getattr(args, "shipping_mode", None)
        or order.get("shipping_mode")
        or shipping.get("shipping_mode")
        or shipping.get("combine_orders")
    )
    click_button(page, shipping_mode_label(shipping_mode), 0)
    select_order_channel_on_page(page, getattr(args, "order_channel", None) or order.get("order_channel", "web"))
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
    select_courier(page, shipping.get("courier") or config.get("courier") or "顺丰电商标快")
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
    order = config.get("order", {})
    assert_clean_for_submit(page, order.get("surface_finish"))
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


def open_site(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    current = connect_page(config, prefer_order=False)
    page = current.context.new_page()
    if args.site == "global":
        url = args.url or config.get("global_quote_url") or GLOBAL_QUOTE_URL
    else:
        url = args.url or config.get("china_upload_url") or CHINA_UPLOAD_URL
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"opened={url}")
    print(f"title={page.title()}")
    print(f"screenshot={args.screenshot}")


def global_upload(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    zip_path = resolve_path(args.zip or config.get("gerber_zip"))
    if not zip_path or not zip_path.exists():
        raise SystemExit(f"missing Gerber ZIP: {zip_path}")
    current = connect_page(config, prefer_order=False)
    page = current.context.new_page()
    page.goto(args.url or config.get("global_quote_url") or GLOBAL_QUOTE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    file_inputs = page.locator("input[type=file]")
    count = file_inputs.count()
    if count:
        file_inputs.first.set_input_files(str(zip_path))
        print(f"uploaded={zip_path}")
    else:
        print("global page has no visible file input yet; log in or choose the upload control manually")
    page.wait_for_timeout(1500)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"url={page.url}")
    print(f"file_inputs={count}")
    print(f"screenshot={args.screenshot}")


def select_finish(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config)
    page.set_viewport_size({"width": 1800, "height": 1000})
    page.evaluate("window.scrollTo(0, 900)")
    page.wait_for_timeout(600)
    click_button(page, args.finish, 0)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"surface_finish={args.finish}")
    print(f"screenshot={args.screenshot}")


def select_channel(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config)
    select_order_channel_on_page(page, args.channel)
    page.screenshot(path=args.screenshot, full_page=False)
    print(f"order_channel={args.channel}")
    print(f"screenshot={args.screenshot}")


def split_name_for_global_checkout(name: str) -> tuple[str, str]:
    name = name.strip()
    if len(name) >= 2 and all(ord(ch) > 127 for ch in name.replace(" ", "")):
        return name[1:].strip(), name[0]
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return name, name


def select_global_dropdown_option(page: Page, input_placeholder: str, option_parts: list[str]) -> None:
    field = page.locator(f"input[placeholder='{input_placeholder}']").first
    field.click(timeout=5000)
    page.wait_for_timeout(500)
    for _ in range(16):
        rows = page.evaluate(
            """(parts) => [...document.querySelectorAll('.el-select-dropdown__item')].map((el) => {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || el.textContent || '').trim();
                return {text, x: r.x, y: r.y, w: r.width, h: r.height};
            }).filter((row) => row.w > 0 && row.h > 0 && parts.every((part) => row.text.includes(part)))""",
            option_parts,
        )
        if rows:
            row = rows[0]
            page.mouse.click(row["x"] + 20, max(5, min(990, row["y"] + row["h"] / 2)))
            page.wait_for_timeout(700)
            return
        page.evaluate(
            """() => {
                const wraps = [...document.querySelectorAll('.el-select-dropdown__wrap')]
                    .filter((el) => el.getBoundingClientRect().width > 0);
                const wrap = wraps[wraps.length - 1];
                if (wrap) wrap.scrollTop += 8 * 34;
            }"""
        )
        page.wait_for_timeout(200)
    raise RuntimeError(f"could not select global dropdown option: {input_placeholder} / {option_parts}")


def global_submit_current_cart(args: argparse.Namespace) -> None:
    if not args.allow_submit:
        raise SystemExit("refusing global submit without --allow-submit")
    config = load_config(args.config)
    shipping = config.get("shipping", {})
    recipient = shipping.get("recipient_name") or config.get("recipient_name") or ""
    phone = str(shipping.get("phone") or config.get("phone") or "")
    detail = shipping.get("detail") or config.get("address") or ""
    postal_code = str(shipping.get("postal_code") or "518055")
    if not all([recipient, phone, detail]):
        raise SystemExit("global checkout requires recipient_name, phone, and address/detail in private config")
    first_name, last_name = split_name_for_global_checkout(recipient)
    current = connect_page(config, prefer_order=False)
    page = next((p for p in current.context.pages if "shopcart/cart" in p.url), None) or current.context.new_page()
    page.goto("https://cart.jlcpcb.com/shopcart/cart/", wait_until="domcontentloaded", timeout=60000)
    page.set_viewport_size({"width": 1800, "height": 1000})
    page.wait_for_timeout(3000)
    checkbox = page.locator(".data-choice-list .el-checkbox__inner").first
    checkbox.click(timeout=5000, force=True)
    page.wait_for_timeout(2000)
    text = page.locator("body").inner_text(timeout=10000)
    if "Subtotal\n$0.00" in text or "Subtotal $0.00" in text:
        raise SystemExit("global cart item was not selected; refusing empty checkout")
    page.get_by_text("Secure Checkout", exact=True).click(timeout=5000)
    page.wait_for_timeout(8000)
    page.screenshot(path=args.screenshot, full_page=False)
    text = page.locator("body").inner_text(timeout=10000)
    if "0 items" in text:
        raise SystemExit("global checkout opened with 0 items; refusing empty submit")
    if "First Name" in text:
        page.locator("input[placeholder='First Name']").first.fill(first_name)
        page.locator("input[placeholder='Last Name']").first.fill(last_name)
        country = page.locator("input[placeholder='Country / Region']").first
        if "China" not in country.input_value():
            country.click(timeout=5000)
            page.wait_for_timeout(500)
            country.press("Control+A")
            country.type("China")
            page.wait_for_timeout(500)
            page.get_by_text("China", exact=False).first.click(timeout=5000, force=True)
            page.wait_for_timeout(500)
        if not page.locator("input[placeholder='State']").first.input_value():
            select_global_dropdown_option(page, "State", ["Guangdong"])
        if not page.locator("input[placeholder='City']").first.input_value():
            select_global_dropdown_option(page, "City", ["Shenzhen"])
        page.locator("input[placeholder='Street Address']").first.fill(detail)
        page.locator("input[placeholder='Postal Code']").first.fill(postal_code)
        page.locator("input[placeholder='Cell/Mobile number']").first.fill(phone)
        page.get_by_text("Save", exact=True).click(timeout=5000)
        page.wait_for_timeout(7000)
    text = page.locator("body").inner_text(timeout=10000)
    if "Shipping Method" in text and "Submit Order" in text and "Review Before Payment" not in text:
        page.get_by_text("Continue", exact=True).click(timeout=5000)
        page.wait_for_timeout(6000)
    if page.get_by_text("Review Before Payment", exact=True).count():
        page.get_by_text("Review Before Payment", exact=True).first.click(timeout=5000)
        page.wait_for_timeout(800)
    page.get_by_text("Submit Order", exact=True).last.click(timeout=5000)
    page.wait_for_timeout(10000)
    page.screenshot(path=args.screenshot, full_page=False)
    final_text = page.locator("body").inner_text(timeout=10000)
    if "Your order has been submitted" not in final_text:
        raise SystemExit("global submit did not reach success page")
    print("global order submitted; payment still waits for review/approval")
    print(f"screenshot={args.screenshot}")


def dump_dom(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config, prefer_order=False)
    url_contains = getattr(args, "url_contains", None)
    if url_contains:
        for candidate in reversed(page.context.pages):
            if url_contains in candidate.url:
                page = candidate
                page.bring_to_front()
                break
        else:
            raise SystemExit(f"no open page URL contains: {url_contains}")
    data = page.evaluate(
        """() => {
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const label = (el) => (el.innerText || el.textContent || el.value || '').trim().replace(/\\s+/g, ' ');
            return {
                url: location.href,
                title: document.title,
                fileInputs: [...document.querySelectorAll('input[type=file]')].map((el, i) => ({
                    index: i,
                    accept: el.getAttribute('accept') || '',
                    name: el.getAttribute('name') || '',
                    visible: visible(el),
                })),
                inputs: [...document.querySelectorAll('input, textarea, select')].slice(0, 160).map((el, i) => ({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    name: el.getAttribute('name') || '',
                    value: String(el.value || '').slice(0, 80),
                    visible: visible(el),
                })),
                buttons: [...document.querySelectorAll('button')].map((el, i) => ({
                    index: i,
                    text: label(el).slice(0, 160),
                    className: String(el.className).slice(0, 160),
                    visible: visible(el),
                })).filter((row) => row.text || row.visible),
                frames: [...document.querySelectorAll('iframe')].map((el, i) => ({
                    index: i,
                    src: el.getAttribute('src') || '',
                    visible: visible(el),
                })),
            };
        }"""
    )
    output = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.expanduser().write_text(output + "\n", encoding="utf-8")
        print(f"wrote={args.output.expanduser()}")
    else:
        print(output)


def ensure_order_db(path: Path) -> sqlite3.Connection:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            project_name TEXT,
            gerber_zip TEXT,
            page_url TEXT,
            page_title TEXT,
            recipient_name TEXT,
            phone TEXT,
            region_json TEXT,
            address_detail TEXT,
            quantity INTEGER,
            material TEXT,
            layers INTEGER,
            board_size TEXT,
            thickness_mm TEXT,
            copper_weight TEXT,
            solder_mask TEXT,
            silkscreen TEXT,
            surface_finish TEXT,
            compensation TEXT,
            confirm_mode TEXT,
            smt TEXT,
            stencil TEXT,
            invoice_status TEXT,
            base_special_price TEXT,
            plating_fee TEXT,
            shipping_fee TEXT,
            web_total TEXT,
            assistant_total TEXT,
            selected_order_channel TEXT,
            price_lines_json TEXT,
            missing_count INTEGER,
            order_check_lines_json TEXT,
            visible_lines_json TEXT,
            snapshot_json TEXT NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(order_snapshots)")}
    migrations = {
        "base_special_price": "TEXT",
        "plating_fee": "TEXT",
        "shipping_fee": "TEXT",
        "web_total": "TEXT",
        "assistant_total": "TEXT",
        "selected_order_channel": "TEXT",
        "price_lines_json": "TEXT",
    }
    for column, col_type in migrations.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE order_snapshots ADD COLUMN {column} {col_type}")
    os.chmod(path, 0o600)
    return conn


def visible_order_lines(text: str) -> list[str]:
    keys = [
        "订单",
        "总价",
        "板子数量",
        "板材类别",
        "板子尺寸",
        "板子层数",
        "成品板厚",
        "外层铜厚",
        "阻焊颜色",
        "字符颜色",
        "焊盘喷镀",
        "品质赔付服务",
        "是否需要SMT",
        "是否需要钢网",
        "发票信息",
        "收货地址",
        "联系方式",
        "快递方式",
        "检测到",
        "审核",
        "支付",
        "余额",
    ]
    lines: list[str] = []
    for line in text.splitlines():
        s = " ".join(line.split())
        if s and any(key in s for key in keys):
            lines.append(s[:300])
    return lines


def infer_missing_count(text: str) -> int | None:
    match = re.search(r"检测到您的订单还有\s*(\d+)\s*项未填写", text)
    if not match:
        return None
    return int(match.group(1))


def next_line_after(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        if line == label and index + 1 < len(lines):
            return lines[index + 1]
    return ""


def extract_price_breakdown(page: Page) -> dict[str, Any]:
    text = page.evaluate(
        """() => {
            const el = document.querySelector('#rightcontent') || document.querySelector('.rightcontentBox');
            return el ? (el.innerText || el.textContent || '') : '';
        }"""
    )
    lines = [" ".join(line.split()) for line in text.splitlines() if " ".join(line.split())]
    buttons = page.evaluate(
        """() => [...document.querySelectorAll('button')].map((button) => {
            const rect = button.getBoundingClientRect();
            const text = (button.innerText || button.textContent || '').trim().replace(/\\s+/g, ' ');
            return {text, cls: String(button.className), visible: rect.width > 0 && rect.height > 0};
        }).filter((row) => row.visible && /网页版下单|下单助手/.test(row.text))"""
    )
    selected_channel = ""
    for button in buttons:
        if "checked" in button.get("cls", ""):
            selected_channel = "assistant" if "下单助手" in button.get("text", "") else "web"
            break
    joined = "\n".join(lines)
    web_match = re.search(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*网页版下单", joined)
    assistant_match = re.search(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*下单助手", joined)
    return {
        "lines": lines,
        "base_special_price": next_line_after(lines, "特价"),
        "plating_fee": next_line_after(lines, "喷镀费"),
        "shipping_fee": next_line_after(lines, "快递费"),
        "web_total": web_match.group(1) if web_match else "",
        "assistant_total": assistant_match.group(1) if assistant_match else "",
        "selected_order_channel": selected_channel,
    }


def build_order_snapshot(config: dict[str, Any], page: Page, status: str, note: str | None) -> dict[str, Any]:
    order = config.get("order", {})
    shipping = config.get("shipping", {})
    text = page.locator("body").inner_text(timeout=10000)
    lines = visible_order_lines(text)
    missing_count = infer_missing_count(text)
    price = extract_price_breakdown(page)
    snapshot = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "note": note or "",
        "project_name": config.get("project_name") or order.get("project_name") or "",
        "gerber_zip": config.get("gerber_zip", ""),
        "page_url": page.url,
        "page_title": page.title(),
        "shipping": {
            "recipient_name": shipping.get("recipient_name") or config.get("recipient_name") or "",
            "phone": str(shipping.get("phone") or config.get("phone") or ""),
            "region": shipping.get("region", []),
            "detail": shipping.get("detail") or config.get("address") or "",
        },
        "order": {
            "quantity": order.get("quantity"),
            "material": order.get("material", "FR-4"),
            "layers": order.get("layers", 2),
            "board_size": order.get("board_size", "2.4 cm x 2.4 cm"),
            "thickness_mm": order.get("thickness_mm", "1.6"),
            "copper_weight": order.get("copper_weight", "1 oz"),
            "solder_mask": order.get("solder_mask", "green"),
            "silkscreen": order.get("silkscreen", "white"),
            "surface_finish": order.get("surface_finish", "无铅喷锡"),
            "compensation": order.get("compensation", "按标准合同常规处理"),
            "confirm_mode": order.get("confirm_mode", "manual"),
            "smt": order.get("smt", "not_needed"),
            "stencil": order.get("stencil", "not_needed"),
            "invoice_status": order.get("invoice_status", "unfilled_or_not_selected"),
        },
        "jlc_validation": {
            "missing_count": missing_count,
            "visible_lines": lines[:120],
        },
        "price": price,
    }
    return snapshot


def insert_order_snapshot(db_path: Path, snapshot: dict[str, Any]) -> int:
    conn = ensure_order_db(db_path)
    shipping = snapshot["shipping"]
    order = snapshot["order"]
    validation = snapshot["jlc_validation"]
    price = snapshot["price"]
    with conn:
        cur = conn.execute(
            """
            INSERT INTO order_snapshots (
                created_at, status, note, project_name, gerber_zip, page_url, page_title,
                recipient_name, phone, region_json, address_detail, quantity, material,
                layers, board_size, thickness_mm, copper_weight, solder_mask, silkscreen,
                surface_finish, compensation, confirm_mode, smt, stencil, invoice_status,
                base_special_price, plating_fee, shipping_fee, web_total, assistant_total,
                selected_order_channel, price_lines_json, missing_count, order_check_lines_json,
                visible_lines_json, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["created_at"],
                snapshot["status"],
                snapshot["note"],
                snapshot["project_name"],
                snapshot["gerber_zip"],
                snapshot["page_url"],
                snapshot["page_title"],
                shipping["recipient_name"],
                shipping["phone"],
                json_dumps(shipping["region"]),
                shipping["detail"],
                order["quantity"],
                order["material"],
                order["layers"],
                order["board_size"],
                order["thickness_mm"],
                order["copper_weight"],
                order["solder_mask"],
                order["silkscreen"],
                order["surface_finish"],
                order["compensation"],
                order["confirm_mode"],
                order["smt"],
                order["stencil"],
                order["invoice_status"],
                price["base_special_price"],
                price["plating_fee"],
                price["shipping_fee"],
                price["web_total"],
                price["assistant_total"],
                price["selected_order_channel"],
                json_dumps(price["lines"]),
                validation["missing_count"],
                json_dumps(validation["visible_lines"]),
                json_dumps(validation["visible_lines"]),
                json_dumps(snapshot),
            ),
        )
    conn.close()
    return int(cur.lastrowid)


def record_order(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    page = connect_page(config)
    snapshot = build_order_snapshot(config, page, args.status, args.note)
    row_id = insert_order_snapshot(args.db, snapshot)
    print(f"recorded order snapshot id={row_id}")
    print(f"db={args.db.expanduser()}")
    print(f"status={snapshot['status']}")
    print(f"missing_count={snapshot['jlc_validation']['missing_count']}")
    for line in snapshot["jlc_validation"]["visible_lines"][:20]:
        print(redact_phone(line))


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
    p_open_site = sub.add_parser("open-site")
    p_open_site.add_argument("--site", choices=["china", "global"], default="china")
    p_open_site.add_argument("--url")
    p_open_site.set_defaults(func=open_site)
    p_global_upload = sub.add_parser("global-upload")
    p_global_upload.add_argument("--zip")
    p_global_upload.add_argument("--url")
    p_global_upload.set_defaults(func=global_upload)
    p_global_submit = sub.add_parser("global-submit-current-cart")
    p_global_submit.add_argument("--allow-submit", action="store_true")
    p_global_submit.set_defaults(func=global_submit_current_cart)
    p_upload = sub.add_parser("upload")
    p_upload.add_argument("--zip")
    p_upload.set_defaults(func=upload)
    sub.add_parser("open-order-form").set_defaults(func=open_order_form)
    p_fill = sub.add_parser("fill-settings")
    p_fill.add_argument("--surface-finish")
    p_fill.add_argument("--shipping-mode", choices=["separate", "combined"], default=None)
    p_fill.add_argument("--order-channel", choices=["web", "assistant"], default=None)
    p_fill.add_argument("--confirm-mode", choices=["manual", "auto"], default=None)
    p_fill.set_defaults(func=fill_settings)
    p_finish = sub.add_parser("select-finish")
    p_finish.add_argument("--finish", default="OSP")
    p_finish.set_defaults(func=select_finish)
    p_channel = sub.add_parser("select-channel")
    p_channel.add_argument("--channel", choices=["web", "assistant"], default="web")
    p_channel.set_defaults(func=select_channel)
    p_addr = sub.add_parser("fill-address")
    p_addr.add_argument("--save-address", action="store_true")
    p_addr.set_defaults(func=fill_address)
    sub.add_parser("check-order").set_defaults(func=check_order)
    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--zip")
    p_prepare.add_argument("--save-address", action="store_true")
    p_prepare.add_argument("--surface-finish")
    p_prepare.add_argument("--shipping-mode", choices=["separate", "combined"], default=None)
    p_prepare.add_argument("--order-channel", choices=["web", "assistant"], default=None)
    p_prepare.add_argument("--confirm-mode", choices=["manual", "auto"], default=None)
    p_prepare.set_defaults(func=prepare)
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--allow-submit", action="store_true")
    p_submit.set_defaults(func=submit)
    p_record = sub.add_parser("record-order")
    p_record.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    p_record.add_argument("--status", default="draft_pending_invoice")
    p_record.add_argument("--note", default="")
    p_record.set_defaults(func=record_order)
    p_log = sub.add_parser("post-submit-log")
    p_log.add_argument("--output-dir", type=Path, default=DEFAULT_LOG_DIR)
    p_log.set_defaults(func=post_submit_log)
    p_dump = sub.add_parser("dump-dom")
    p_dump.add_argument("--output", type=Path)
    p_dump.add_argument("--url-contains")
    p_dump.set_defaults(func=dump_dom)
    sub.add_parser("snapshot").set_defaults(func=snapshot_cmd)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

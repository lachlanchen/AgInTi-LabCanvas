#!/usr/bin/env python3
"""Browser-assisted Wenext 3D-print order automation.

This tool attaches to an existing Chrome profile through CDP. It is designed
for logged-in sessions that the user opened manually, so it avoids storing
cookies or passwords in the repository. Final order submission requires
``--allow-submit`` and payment buttons are never clicked by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import websocket


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path("~/.config/wenext-3d-order/private.json").expanduser()
DEFAULT_DB = Path("~/.config/wenext-3d-order/orders.sqlite3").expanduser()
DEFAULT_LOG_DIR = Path("~/.config/wenext-3d-order/submissions").expanduser()
GLOBAL_ENTRY_URL = "https://www.wenext.com/manufacture/quote?technology=3d-printing"
CHINA_ENTRY_URL = "https://www.wenext.cn/manufacture/"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str | Path) -> Path:
    path = Path(os.path.expanduser(str(value)))
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def redact(text: str) -> str:
    text = re.sub(r"1\d{10}", lambda m: f"{m.group(0)[:3]}****{m.group(0)[-4:]}", text)
    text = re.sub(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+)", r"\1@***", text)
    return text


def now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def port_from_config(config: dict[str, Any], override: int | None = None) -> int:
    return int(override or config.get("browser_debug_port") or os.environ.get("WENEXT_CDP_PORT") or 53729)


def list_targets(port: int) -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
        return json.load(response)


def new_tab(port: int, url: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(url, safe=":/?&=%")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{encoded}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def choose_target(port: int, site: str, create: bool = False) -> dict[str, Any]:
    targets = [t for t in list_targets(port) if t.get("type") == "page"]
    domain = "wenext.cn" if site == "china" else "wenext.com"
    candidates = [t for t in targets if domain in (t.get("url") or "")]
    if candidates:
        payment = [t for t in candidates if any(key in (t.get("url") or "") for key in ["checkout/payment", "cashier"])]
        checkout = [t for t in candidates if "checkout" in (t.get("url") or "")]
        return (payment or checkout or candidates)[0]
    if not create:
        raise SystemExit(f"no existing {domain} page on CDP port {port}; open/login first or pass --new-tab")
    return new_tab(port, CHINA_ENTRY_URL if site == "china" else GLOBAL_ENTRY_URL)


@dataclass
class CdpPage:
    port: int
    target: dict[str, Any]

    def __post_init__(self) -> None:
        self._next_id = 1
        self.ws = websocket.create_connection(
            self.target["webSocketDebuggerUrl"],
            timeout=30,
            origin=f"http://127.0.0.1:{self.port}",
        )
        self.call("Runtime.enable")
        self.call("Page.enable")
        self.call("DOM.enable")
        self.call("Page.bringToFront")

    def close(self) -> None:
        self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} failed: {msg['error']}")
                return msg

    def eval(self, expression: str) -> Any:
        response = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        result = response["result"]["result"]
        if "exceptionDetails" in response["result"]:
            raise RuntimeError(response["result"]["exceptionDetails"])
        return result.get("value")

    def navigate(self, url: str) -> None:
        self.call("Page.navigate", {"url": url})
        for _ in range(120):
            state = self.eval("document.readyState")
            if state in {"interactive", "complete"}:
                return
            time.sleep(0.25)

    def upload_files(self, files: list[Path]) -> None:
        missing = [str(path) for path in files if not path.exists()]
        if missing:
            raise SystemExit(f"missing upload files: {missing}")
        root = self.call("DOM.getDocument", {"depth": 1})["result"]["root"]["nodeId"]
        node = self.call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})["result"].get("nodeId")
        if not node:
            raise SystemExit("no input[type=file] found")
        self.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(path) for path in files]})

    def snapshot(self) -> dict[str, Any]:
        return self.eval(
            r"""
(() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
  };
  return {
    url: location.href,
    title: document.title,
    body: norm(document.body.innerText).slice(0, 12000),
    buttons: [...document.querySelectorAll('button')].map((el, i) => {
      const r = el.getBoundingClientRect();
      return {i, text: norm(el.innerText || el.textContent), disabled: !!el.disabled,
              className: String(el.className), x: r.x, y: r.y, w: r.width, h: r.height};
    }).filter((x) => x.w > 0 && x.h > 0),
    inputs: [...document.querySelectorAll('input')].map((el, i) => ({
      i, type: el.type, accept: el.accept || '', placeholder: el.placeholder || '',
      value: el.type === 'password' ? '***' : norm(el.value), display: getComputedStyle(el).display
    })),
    modals: [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.modal,[role=dialog]')]
      .map((el, i) => {
        const r = el.getBoundingClientRect();
        return {i, text: norm(el.innerText || el.textContent).slice(0, 2000),
                x: r.x, y: r.y, w: r.width, h: r.height};
      }).filter((x) => x.w > 0 && x.h > 0)
  };
})()
"""
        )

    def click_text(self, text: str, exact: bool = False, occurrence: int = 0) -> dict[str, Any]:
        return self.eval(
            r"""
((needle, exact, occurrence) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
  };
  const candidates = [...document.querySelectorAll('button,a,[role=button],.el-button,.el-select-dropdown__item,.el-cascader-node,li,span,div')]
    .filter((el) => visible(el))
    .map((el) => ({el, text: norm(el.innerText || el.textContent)}))
    .filter((row) => row.text && (exact ? row.text === needle : row.text.includes(needle)));
  const row = candidates[Math.min(occurrence, Math.max(candidates.length - 1, 0))];
  if (!row) return {ok: false, text: needle};
  row.el.scrollIntoView({block: 'center', inline: 'center'});
  row.el.click();
  return {ok: true, matched: row.text, tag: row.el.tagName, className: String(row.el.className)};
})(%s, %s, %s)
"""
            % (json.dumps(text, ensure_ascii=False), json.dumps(exact), occurrence)
        )

    def click_button(self, text: str, exact: bool = True, occurrence: int = 0) -> dict[str, Any]:
        return self.eval(
            r"""
((needle, exact, occurrence) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
  };
  const rows = [...document.querySelectorAll('button')]
    .filter((el) => visible(el) && !el.disabled)
    .map((el) => ({el, text: norm(el.innerText || el.textContent)}))
    .filter((row) => row.text && (exact ? row.text === needle : row.text.includes(needle)));
  const row = rows[Math.min(occurrence, Math.max(rows.length - 1, 0))];
  if (!row) return {ok: false, text: needle};
  row.el.scrollIntoView({block: 'center', inline: 'center'});
  row.el.click();
  return {ok: true, matched: row.text};
})(%s, %s, %s)
"""
            % (json.dumps(text, ensure_ascii=False), json.dumps(exact), occurrence)
        )

    def fill_visible_input(self, index: int, value: str) -> dict[str, Any]:
        return self.eval(
            r"""
((index, value) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
  };
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const el = inputs[index];
  if (!el) return {ok: false, index, count: inputs.length};
  el.focus();
  el.select?.();
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return {ok: true, index, placeholder: el.placeholder || '', value};
})(%s, %s)
"""
            % (index, json.dumps(value, ensure_ascii=False))
        )


def state_from_snapshot(snapshot: dict[str, Any], site: str) -> dict[str, Any]:
    body = snapshot.get("body") or ""
    buttons = snapshot.get("buttons") or []
    enabled = {b["text"]: not b["disabled"] for b in buttons}
    login_markers = ["您好，请登录", "密码登录", "验证码登录", "账号绑定", "微信未绑定"]
    parser_busy = "解析文件报价中" in body
    product_ready = "名称：" in body and ("产品总价" in body or "Total" in body) and not parser_busy
    payment_page = any(key in (snapshot.get("url") or "") for key in ["checkout/payment", "cashier"])
    payment_page = payment_page or "收银台支付" in body or "PayPal" in body or "Payment Link" in body
    return {
        "site": site,
        "url": snapshot.get("url"),
        "login_required": any(marker in body for marker in login_markers),
        "parser_busy": parser_busy,
        "product_ready": product_ready,
        "add_to_cart_enabled": bool(enabled.get("加入购物车")),
        "checkout_enabled": bool(enabled.get("去结账") or enabled.get("Check Out")),
        "payment_page": payment_page,
    }


def write_snapshot(snapshot: dict[str, Any], site: str, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (DEFAULT_LOG_DIR / site)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"snapshot-{now_id()}.json"
    redacted = json.loads(json.dumps(snapshot, ensure_ascii=False))
    redacted["body"] = redact(redacted.get("body") or "")
    path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def record_state(db_path: Path, site: str, status: str, snapshot: dict[str, Any], note: str = "") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        create table if not exists orders (
          id integer primary key autoincrement,
          created_at text not null,
          site text not null,
          status text not null,
          url text,
          body_excerpt text,
          note text
        )
        """
    )
    conn.execute(
        "insert into orders(created_at, site, status, url, body_excerpt, note) values (?, ?, ?, ?, ?, ?)",
        (
            datetime.now().isoformat(timespec="seconds"),
            site,
            status,
            snapshot.get("url"),
            redact((snapshot.get("body") or "")[:3000]),
            note,
        ),
    )
    conn.commit()
    conn.close()
    db_path.chmod(0o600)


def wait_for_quote(page: CdpPage, site: str, timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout
    last_snapshot = page.snapshot()
    while time.time() < deadline:
        state = state_from_snapshot(last_snapshot, site)
        if state["product_ready"] or state["login_required"]:
            return last_snapshot, state
        time.sleep(2)
        last_snapshot = page.snapshot()
    return last_snapshot, state_from_snapshot(last_snapshot, site)


def wait_for_page_state(
    page: CdpPage,
    site: str,
    timeout: int,
    *,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    url_contains: tuple[str, ...] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout
    last_snapshot = page.snapshot()
    while time.time() < deadline:
        body = last_snapshot.get("body") or ""
        url = last_snapshot.get("url") or ""
        includes_ok = all(fragment in body for fragment in include)
        excludes_ok = all(fragment not in body for fragment in exclude)
        url_ok = not url_contains or any(fragment in url for fragment in url_contains)
        if includes_ok and excludes_ok and url_ok:
            return last_snapshot, state_from_snapshot(last_snapshot, site)
        time.sleep(2)
        last_snapshot = page.snapshot()
    return last_snapshot, state_from_snapshot(last_snapshot, site)


def china_save_address_modal(page: CdpPage, shipping: dict[str, Any]) -> None:
    # Observed Element Plus modal input order:
    # 0 company, 1 recipient, 2 country, 3 province, 4 city, 5 district,
    # 6 detail address, 7 phone prefix, 8 mobile phone, 9 fixed phone.
    page.fill_visible_input(0, shipping.get("company", ""))
    page.fill_visible_input(1, shipping.get("recipient_name", ""))
    page.fill_visible_input(6, shipping.get("address_line1", ""))
    page.fill_visible_input(8, shipping.get("phone", ""))
    for index, value in [(3, "province_cn"), (4, "city_cn"), (5, "district_cn")]:
        wanted = shipping.get(value)
        if wanted:
            page.fill_visible_input(index, wanted)
            time.sleep(0.2)
            page.click_text(wanted, exact=False)
            time.sleep(0.5)
    page.click_text("保存", exact=True)
    time.sleep(1)


def china_select_rows_if_needed(page: CdpPage) -> None:
    page.eval(
        r"""
(() => {
  const body = (document.body.innerText || '').replace(/\s+/g, ' ');
  if (!/选中产品\s*0\s*款/.test(body)) return {selectedAlready: true};
  const labels = [...document.querySelectorAll('label.el-checkbox')]
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.x < 380 && r.y > 180 && !String(el.className).includes('is-checked');
    });
  labels.forEach((el) => { try { el.click(); } catch (_) {} });
  return {selectedAlready: false, clicked: labels.length};
})()
"""
    )


def china_apply_invoice(page: CdpPage, config: dict[str, Any]) -> None:
    invoice = config.get("invoice", {})
    shipping = config.get("shipping", {})
    invoice_type = str(invoice.get("type") or "none").strip().lower()
    title = invoice.get("title") or shipping.get("recipient_name") or "个人"
    email = invoice.get("email") or shipping.get("email")
    current = page.snapshot().get("body") or ""
    if invoice_type in {"pupiao", "普通发票", "数电普票"}:
        if "数电普票" in current and email and email in current:
            return
        page.click_button("修改发票信息", exact=False)
        time.sleep(1)
        page.click_text("数电普票", exact=True)
        time.sleep(1)
        body = page.snapshot().get("body") or ""
        if "暂无数据" in body:
            page.click_button("新增抬头", exact=True)
            time.sleep(1)
            page.click_text("个人", exact=True)
            time.sleep(0.5)
            page.eval(
                r"""
((title, email) => {
  const setVal = (el, value) => {
    el.focus();
    el.select?.();
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const inputs = [...document.querySelectorAll('input')].filter(visible);
  const titleInput = inputs.find((el) => el.placeholder === '发票抬头');
  const emailInput = inputs.find((el) => el.placeholder === '收票人邮箱');
  if (!titleInput || !emailInput) return {ok: false};
  setVal(titleInput, title);
  setVal(emailInput, email || '');
  return {ok: true};
})(%s, %s)
"""
                % (json.dumps(title, ensure_ascii=False), json.dumps(email or "", ensure_ascii=False))
            )
            page.click_button("保存", exact=True)
            wait_for_page_state(page, "china", 20, include=("数电普票",))
            return
        page.click_button("确认选择", exact=True)
        wait_for_page_state(page, "china", 20, include=("数电普票",))
        return

    if "不开发票" in current:
        return
    page.click_button("修改发票信息", exact=False)
    time.sleep(1)
    page.click_text("不开发票", exact=True)
    time.sleep(0.5)
    page.click_button("确认选择", exact=True)
    wait_for_page_state(page, "china", 20, include=("不开发票",))


def china_ready_for_submit(snapshot: dict[str, Any]) -> bool:
    body = snapshot.get("body") or ""
    buttons = snapshot.get("buttons") or []
    submit_enabled = any(b["text"] == "提交订单" and not b["disabled"] for b in buttons)
    return (
        submit_enabled
        and "暂无产品" not in body
        and "已选产品 0" not in body
        and "总计 (含税)" in body
    )


def command_snapshot(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    port = port_from_config(config, args.port)
    target = choose_target(port, args.site, create=args.new_tab)
    page = CdpPage(port, target)
    try:
        snapshot = page.snapshot()
        state = state_from_snapshot(snapshot, args.site)
        path = write_snapshot(snapshot, args.site, args.output_dir)
        record_state(args.db, args.site, args.status or "snapshot", snapshot, args.note or "")
        print(json.dumps({"state": state, "snapshot": str(path)}, ensure_ascii=False, indent=2))
    finally:
        page.close()


def command_upload(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    port = port_from_config(config, args.port)
    target = choose_target(port, args.site, create=args.new_tab)
    page = CdpPage(port, target)
    try:
        if args.navigate:
            page.navigate(CHINA_ENTRY_URL if args.site == "china" else GLOBAL_ENTRY_URL)
            time.sleep(2)
        files = [resolve_path(path) for path in (args.files or config.get("files", []))]
        page.upload_files(files)
        snapshot, state = wait_for_quote(page, args.site, args.timeout)
        path = write_snapshot(snapshot, args.site, args.output_dir)
        record_state(args.db, args.site, "quote_after_upload", snapshot, json.dumps(state, ensure_ascii=False))
        print(json.dumps({"state": state, "snapshot": str(path)}, ensure_ascii=False, indent=2))
        if state["login_required"]:
            raise SystemExit("login/binding overlay detected; finish login in the shared browser and retry")
        if state["parser_busy"] and not state["product_ready"]:
            raise SystemExit("quote parser is still busy/stuck; retry later or upload one file at a time")
    finally:
        page.close()


def command_china_flow(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    port = port_from_config(config, args.port)
    target = choose_target(port, "china", create=args.new_tab)
    page = CdpPage(port, target)
    try:
        initial = page.snapshot()
        if state_from_snapshot(initial, "china")["payment_page"]:
            path = write_snapshot(initial, "china", args.output_dir)
            record_state(args.db, "china", "payment_waiting", initial, "payment not clicked")
            print(json.dumps({"state": state_from_snapshot(initial, "china"), "snapshot": str(path)}, ensure_ascii=False, indent=2))
            return
        if args.navigate:
            page.navigate(CHINA_ENTRY_URL)
            time.sleep(2)
        if args.upload or args.files:
            page.upload_files([resolve_path(path) for path in (args.files or config.get("files", []))])
        snapshot = page.snapshot()
        if "manufacture/cart" in (snapshot.get("url") or ""):
            state = state_from_snapshot(snapshot, "china")
        elif "manufacture/checkout" in (snapshot.get("url") or ""):
            state = state_from_snapshot(snapshot, "china")
        else:
            snapshot, state = wait_for_quote(page, "china", args.timeout)
        if state["login_required"]:
            write_snapshot(snapshot, "china", args.output_dir)
            raise SystemExit("China page requires login/binding; scan QR or login in the same Chrome profile")
        if state["parser_busy"] or (not state["product_ready"] and "manufacture/cart" not in (snapshot.get("url") or "") and "manufacture/checkout" not in (snapshot.get("url") or "")):
            write_snapshot(snapshot, "china", args.output_dir)
            raise SystemExit("China quote is not ready; cannot add to cart or submit")
        if not args.allow_submit:
            path = write_snapshot(snapshot, "china", args.output_dir)
            record_state(args.db, "china", "ready_not_submitted", snapshot, "run again with --allow-submit after review")
            print(json.dumps({"state": state, "snapshot": str(path), "next": "review page, then pass --allow-submit"}, ensure_ascii=False, indent=2))
            return
        url = snapshot.get("url") or ""
        if "manufacture/checkout" not in url and "manufacture/cart" not in url:
            china_select_rows_if_needed(page)
            time.sleep(0.5)
            page.click_button("加入购物车", exact=True)
            wait_for_page_state(page, "china", 30, include=("我的购物车(2)",))
            page.click_button("件产品", exact=False)
            snapshot, _ = wait_for_page_state(page, "china", 45, url_contains=("manufacture/cart",))
        if "manufacture/cart" in ((snapshot.get("url") or page.snapshot().get("url") or "")):
            snapshot, _ = wait_for_page_state(
                page,
                "china",
                60,
                include=("已选产品 2", "总计 (含税)"),
                exclude=("暂无产品",),
                url_contains=("manufacture/cart",),
            )
            page.click_button("去结账", exact=True)
            snapshot, _ = wait_for_page_state(page, "china", 45, url_contains=("manufacture/checkout",))
        snapshot, _ = wait_for_page_state(
            page,
            "china",
            60,
            include=("已选产品 2", "总计 (含税)", "提交订单"),
            exclude=("暂无产品",),
            url_contains=("manufacture/checkout",),
        )
        if args.invoice != "skip":
            china_apply_invoice(page, config)
            snapshot, _ = wait_for_page_state(
                page,
                "china",
                45,
                include=("已选产品 2", "总计 (含税)", "提交订单"),
                exclude=("暂无产品",),
                url_contains=("manufacture/checkout",),
            )
        if not china_ready_for_submit(snapshot):
            path = write_snapshot(snapshot, "china", args.output_dir)
            record_state(args.db, "china", "checkout_not_ready", snapshot, "submit button disabled or product table incomplete")
            raise SystemExit(f"China checkout is not ready for submission; snapshot: {path}")
        if args.fill_address:
            try:
                page.click_text("新增收货地址", exact=False)
                time.sleep(1)
                china_save_address_modal(page, config.get("shipping", {}))
            except Exception as exc:  # noqa: BLE001 - keep browser state for manual recovery.
                print(f"address automation skipped/failed: {exc}")
        page.click_button("提交订单", exact=True)
        final_snapshot, final_state = wait_for_page_state(
            page,
            "china",
            60,
            include=(),
            url_contains=("cashier", "checkout/payment"),
        )
        if not final_state["payment_page"]:
            final_snapshot = page.snapshot()
        final_snapshot = page.snapshot()
        final_state = state_from_snapshot(final_snapshot, "china")
        path = write_snapshot(final_snapshot, "china", args.output_dir)
        record_state(args.db, "china", "payment_waiting" if final_state["payment_page"] else "submitted_or_checkout", final_snapshot, "payment not clicked")
        print(json.dumps({"state": final_state, "snapshot": str(path), "url": final_snapshot.get("url")}, ensure_ascii=False, indent=2))
    finally:
        page.close()


def command_global_flow(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    port = port_from_config(config, args.port)
    target = choose_target(port, "global", create=args.new_tab)
    page = CdpPage(port, target)
    try:
        if args.navigate:
            page.navigate(GLOBAL_ENTRY_URL)
            time.sleep(2)
        if args.upload or args.files:
            page.upload_files([resolve_path(path) for path in (args.files or config.get("files", []))])
            time.sleep(2)
        snapshot = page.snapshot()
        state = state_from_snapshot(snapshot, "global")
        if not args.allow_submit:
            path = write_snapshot(snapshot, "global", args.output_dir)
            record_state(args.db, "global", "snapshot_not_submitted", snapshot, "run with --allow-submit after review")
            print(json.dumps({"state": state, "snapshot": str(path)}, ensure_ascii=False, indent=2))
            return
        for label in ["Apply", "Check Out", "Submit Order"]:
            result = page.click_text(label, exact=False)
            time.sleep(2)
            print(json.dumps({"clicked": label, "result": result}, ensure_ascii=False))
        final_snapshot = page.snapshot()
        path = write_snapshot(final_snapshot, "global", args.output_dir)
        record_state(args.db, "global", "submitted_or_payment", final_snapshot, "payment not clicked")
        print(json.dumps({"snapshot": str(path), "url": final_snapshot.get("url")}, ensure_ascii=False, indent=2))
    finally:
        page.close()


def command_list_targets(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    port = port_from_config(config, args.port)
    domain = "wenext.cn" if args.site == "china" else "wenext.com"
    targets = [
        {"id": t.get("id"), "type": t.get("type"), "title": t.get("title"), "url": t.get("url")}
        for t in list_targets(port)
        if t.get("type") == "page" and domain in (t.get("url") or "")
    ]
    print(json.dumps(targets, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--port", type=int)
    parser.add_argument("--site", choices=["global", "china"], default="global")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--new-tab", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-targets")
    p.set_defaults(func=command_list_targets)

    p = sub.add_parser("snapshot")
    p.add_argument("--status")
    p.add_argument("--note")
    p.set_defaults(func=command_snapshot)

    p = sub.add_parser("upload")
    p.add_argument("--files", nargs="*")
    p.add_argument("--navigate", action="store_true")
    p.add_argument("--timeout", type=int, default=180)
    p.set_defaults(func=command_upload)

    p = sub.add_parser("china-flow")
    p.add_argument("--files", nargs="*")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--navigate", action="store_true")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--allow-submit", action="store_true")
    p.add_argument("--fill-address", action="store_true")
    p.add_argument("--invoice", choices=["auto", "skip"], default="auto")
    p.set_defaults(func=command_china_flow)

    p = sub.add_parser("global-flow")
    p.add_argument("--files", nargs="*")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--navigate", action="store_true")
    p.add_argument("--allow-submit", action="store_true")
    p.set_defaults(func=command_global_flow)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

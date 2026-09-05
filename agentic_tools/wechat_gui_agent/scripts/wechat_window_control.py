#!/usr/bin/env python3
"""Ask an owned WeChat auxiliary window to close without destroying its X resource."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def request_close(
    window_id: str, *, display_name: str,
    protected_window_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Send WM_DELETE_WINDOW only to a same-user WeChat client window.

    XDestroyWindow skips application close/reject handling. Never use it as a
    fallback when a modal or preview refuses the normal close protocol.
    """
    def as_id(value: str) -> int:
        return int(value, 16) if value.lower().startswith("0x") else int(value)

    try:
        wid = as_id(str(window_id))
        protected = {as_id(str(value)) for value in protected_window_ids or set()}
    except ValueError:
        return {"ok": False, "status": "invalid_window"}
    if not 0 < wid <= 0xFFFFFFFF:
        return {"ok": False, "status": "invalid_window"}
    if wid in protected:
        return {"ok": False, "status": "protected_window"}
    try:
        from Xlib import X, display, error, protocol
    except ImportError:
        return {"ok": False, "status": "missing_python_xlib"}
    connection = None
    try:
        connection = display.Display(display_name)
        window = connection.create_resource_object("window", wid)
        pid_property = window.get_full_property(
            connection.intern_atom("_NET_WM_PID", only_if_exists=True), X.AnyPropertyType,
        )
        if pid_property is None or len(pid_property.value) != 1:
            return {"ok": False, "status": "unverified_owner"}
        proc = Path("/proc") / str(int(pid_property.value[0]))
        if proc.stat().st_uid != os.getuid():
            return {"ok": False, "status": "different_user"}
        name = (proc / "comm").read_text().strip().casefold()
        if name not in {"wechat", "wechatappex", "wxplayer"}:
            return {"ok": False, "status": "not_wechat"}
        delete_atom = connection.intern_atom("WM_DELETE_WINDOW", only_if_exists=True)
        protocols = window.get_wm_protocols() or []
        if not delete_atom or delete_atom not in protocols:
            return {"ok": False, "status": "close_protocol_unavailable"}
        event = protocol.event.ClientMessage(
            window=wid, client_type=connection.intern_atom("WM_PROTOCOLS"),
            data=(32, [delete_atom, X.CurrentTime, 0, 0, 0]),
        )
        window.send_event(event, event_mask=0, propagate=False)
        connection.sync()
        return {"ok": True, "status": "close_requested", "destroyed": False}
    except (OSError, ValueError, error.XError, error.DisplayError) as exc:
        return {"ok": False, "status": "close_request_failed", "error": type(exc).__name__}
    finally:
        if connection is not None:
            connection.close()

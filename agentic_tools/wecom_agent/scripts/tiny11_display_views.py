#!/usr/bin/env python3
"""Two noVNC monitor views, one Windows input lease shared with the GUI worker."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
from pathlib import Path
import re

try:
    from aiohttp import WSMsgType, web
except ImportError:
    WSMsgType = web = None  # The optional GUI service has its own small venv.

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parents[1] / "web" / "displays"
LOCK = ROOT / "agentic_tools/wecom_agent/.private/wecom_gui_bridge.lock"
PORTS = {"wecom": 5944, "wechat": 5945}
OWNER_KEY = web.AppKey('control_owner', str) if web else None


class InputLease:
    """Nonblocking advisory lock also used by the existing WeCom bridge."""

    def __init__(self, path: Path = LOCK):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        if self.handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


async def socket_view(request: web.Request) -> web.WebSocketResponse:
    name = request.match_info["name"]
    if name not in PORTS:
        raise web.HTTPNotFound()
    # Local desktop control must not be opened by a remote website.
    if request.headers.get("Origin") != f"http://{request.host}":
        raise web.HTTPForbidden(text="Same-origin local viewer required")
    control = request.query.get("control") == "1"
    owner = request.query.get("lease", "")
    if control and not re.fullmatch(r'[a-f0-9-]{36}', owner):
        raise web.HTTPBadRequest(text="Missing input lease identity")
    lease = InputLease()
    if control and not lease.acquire():
        raise web.HTTPConflict(text="Windows input is busy")
    if control:
        request.app[OWNER_KEY] = owner
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4 * 1024 * 1024)
    writer = None
    tasks = []
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", PORTS[name]), 5)
        await ws.prepare(request)

        async def to_vnc():
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    writer.write(msg.data)
                    await writer.drain()

        async def to_browser():
            while data := await reader.read(65536):
                await ws.send_bytes(data)

        tasks = [asyncio.create_task(to_vnc()), asyncio.create_task(to_browser())]
        # A lost browser cannot hold automation indefinitely; UI uses a shorter
        # inactivity timeout. Viewing alone never takes the GUI worker lock.
        await asyncio.wait(tasks, timeout=600 if control else None,
                           return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if writer is not None:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            pass
        finally:
            lease.release()
            if control and request.app[OWNER_KEY] == owner:
                request.app[OWNER_KEY] = ''
            await ws.close()
    return ws


async def clipboard_text(request: web.Request) -> web.Response:
    if request.headers.get('Origin') != f'http://{request.host}':
        raise web.HTTPForbidden()
    body = await request.json()
    if not request.app[OWNER_KEY] or body.get('lease') != request.app[OWNER_KEY]:
        raise web.HTTPConflict(text='Take control before using the Windows clipboard')
    from wecom_tiny11_transport import Tiny11Transport, load_config, DEFAULT_CONFIG
    transport = Tiny11Transport(load_config(DEFAULT_CONFIG))
    if body.get('action') == 'write':
        value = body.get('text')
        if not isinstance(value, str) or len(value) > 65536:
            raise web.HTTPBadRequest(text='Clipboard text exceeds limit')
        await asyncio.to_thread(transport.invoke, {'action': 'set_clipboard', 'text': value})
        return web.json_response({'ok': True})
    if body.get('action') != 'read':
        raise web.HTTPBadRequest()
    text = await asyncio.to_thread(transport.invoke, {'action': 'get_clipboard'})
    return web.json_response({'text': text or ''}, headers={'Cache-Control': 'no-store'})


def app() -> web.Application:
    if web is None:
        raise RuntimeError("Install requirements-displays.txt in the display service venv")
    @web.middleware
    async def local_host(request, handler):
        if request.url.host not in {"127.0.0.1", "localhost"}:
            raise web.HTTPForbidden(text="Local host only")
        return await handler(request)

    server = web.Application(middlewares=[local_host])
    server[OWNER_KEY] = ''

    async def index(request):
        if request.match_info["name"] not in PORTS:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    server.router.add_get("/ws/{name}", socket_view)
    server.router.add_post('/clipboard', clipboard_text)
    server.router.add_get("/{name:wecom|wechat}", index)
    server.router.add_static("/assets/", STATIC)
    server.router.add_static("/novnc/", "/usr/share/novnc", follow_symlinks=True)
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=6144)
    args = parser.parse_args()
    web.run_app(app(), host="127.0.0.1", port=args.port, access_log=None)

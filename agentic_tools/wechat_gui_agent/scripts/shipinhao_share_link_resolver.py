#!/usr/bin/env python3
"""Resolve one exact WeChat Channels share link without intercepting traffic."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from typing import Any, Iterator
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CDP_URL = os.environ.get("WECHAT_YUANBAO_CDP_URL", "http://127.0.0.1:49245")
DEFAULT_COOKIE_CACHE = PRIVATE / "yuanbao-sph-cookie.txt"
DEFAULT_PROVIDER_ROOT = PRIVATE / "external" / "wx_channels_download_release"
DEFAULT_RUN_ROOT = PRIVATE / "shipinhao_share_link_resolver"
SHARE_URL_PATTERN = re.compile(
    r"https?://weixin\.qq\.com/sph/(?P<token>[A-Za-z0-9_-]{4,128})(?:[^\s<>\"']*)?",
    flags=re.I,
)
MAX_PROVIDER_RESPONSE_BYTES = 8 * 1024 * 1024


class ShareLinkResolutionError(RuntimeError):
    """Raised when an exact share link cannot be resolved safely."""

    def __init__(self, message: str, *, code: str = "share_resolution_failed"):
        super().__init__(message)
        self.error_code = code


def extract_share_urls(text: str) -> list[str]:
    """Extract canonical exact-source share links in stable input order."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in SHARE_URL_PATTERN.finditer(str(text or "")):
        token = match.group("token")
        url = f"https://weixin.qq.com/sph/{token}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def share_token(url: str) -> str:
    matches = extract_share_urls(url)
    if len(matches) != 1:
        raise ShareLinkResolutionError("expected one exact weixin.qq.com/sph share link")
    return matches[0].rsplit("/", 1)[-1]


def find_provider_binary() -> Path:
    override = os.environ.get("WECHAT_SHIPINHAO_RESOLVER_BINARY", "").strip()
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise ShareLinkResolutionError("configured Shipinhao resolver binary is unavailable")
    candidates = sorted(
        DEFAULT_PROVIDER_ROOT.glob("*/wx_video_download"),
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
        reverse=True,
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise ShareLinkResolutionError("wx_channels_download resolver binary is not installed")


def cdp_cookie_header(cdp_url: str = DEFAULT_CDP_URL, *, timeout: float = 8.0) -> str:
    """Read the logged-in Yuanbao cookie through local CDP without exposing it."""
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(version_url, timeout=timeout) as response:
            payload = json.loads(read_bounded(response, 1024 * 1024))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ShareLinkResolutionError("the logged-in Yuanbao CDP session is unavailable") from exc
    websocket_url = str(payload.get("webSocketDebuggerUrl") or "")
    if not websocket_url.startswith("ws://127.0.0.1:") and not websocket_url.startswith("ws://localhost:"):
        raise ShareLinkResolutionError("Yuanbao CDP did not expose a localhost browser endpoint")
    try:
        import websocket  # type: ignore[import-not-found]

        connection = websocket.create_connection(
            websocket_url,
            timeout=timeout,
            suppress_origin=True,
            http_proxy_host=None,
        )
        try:
            connection.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
            response = json.loads(connection.recv())
        finally:
            connection.close()
    except Exception as exc:
        raise ShareLinkResolutionError("could not read the Yuanbao login cookie through CDP") from exc
    cookies = response.get("result", {}).get("cookies", [])
    now = time.time()
    selected: dict[str, tuple[int, str]] = {}
    for cookie in cookies if isinstance(cookies, list) else []:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain") or "").lstrip(".").casefold()
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        expires = float(cookie.get("expires") or 0)
        if domain not in {"tencent.com", "yuanbao.tencent.com"} or not name or not value:
            continue
        if expires > 0 and expires <= now:
            continue
        path = str(cookie.get("path") or "/")
        rank = len(path)
        previous = selected.get(name)
        if previous is None or rank >= previous[0]:
            selected[name] = (rank, value)
    if not selected:
        raise ShareLinkResolutionError("the Yuanbao browser is not logged in")
    return "; ".join(f"{name}={selected[name][1]}" for name in sorted(selected))


def load_yuanbao_cookie(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    cache_path: Path = DEFAULT_COOKIE_CACHE,
    timeout: float = 8.0,
) -> str:
    """Prefer a fresh CDP cookie, then use the private cache if CDP is offline."""
    try:
        cookie = cdp_cookie_header(cdp_url, timeout=timeout)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(cookie, encoding="utf-8")
        cache_path.chmod(0o600)
        return cookie
    except ShareLinkResolutionError as cdp_error:
        try:
            cookie = cache_path.read_text(encoding="utf-8").strip()
            mode = cache_path.stat().st_mode & 0o777
        except OSError:
            raise cdp_error
        if not cookie or mode & 0o077:
            raise ShareLinkResolutionError("the private Yuanbao cookie cache is unavailable or unsafe") from cdp_error
        return cookie


def resolve_share_link(
    url: str,
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    timeout: float = 45.0,
    provider_binary: Path | None = None,
) -> dict[str, Any]:
    """Resolve with the owner's login, checking each upstream stage separately."""
    canonical_url = extract_share_urls(url)
    if len(canonical_url) != 1:
        raise ShareLinkResolutionError("expected one exact Shipinhao share URL")
    canonical_url = canonical_url[0]
    token = share_token(canonical_url)
    if os.geteuid() == 0:
        raise ShareLinkResolutionError("the parse-only Shipinhao resolver must not run as root")
    if Path("/sys/class/net/tun0").exists():
        raise ShareLinkResolutionError("refusing to resolve while a tun0 interceptor is active")
    cookie = load_yuanbao_cookie(cdp_url=cdp_url, timeout=min(timeout, 8.0))
    DEFAULT_RUN_ROOT.mkdir(parents=True, exist_ok=True)
    DEFAULT_RUN_ROOT.chmod(0o700)
    lock_path = DEFAULT_RUN_ROOT / ".resolver.lock"
    with exclusive_lock(lock_path):
        # Retain the explicit legacy provider override for compatibility.
        if provider_binary or os.environ.get("WECHAT_SHIPINHAO_RESOLVER_BINARY"):
            binary = (provider_binary or find_provider_binary()).expanduser().resolve()
            return run_parse_provider(binary, canonical_url, token, cookie, timeout=timeout)
        return resolve_authenticated_share(canonical_url, token, cookie, timeout=timeout)


class NoResolverRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an authenticated request to an unexpected location.
        return None


def request_resolver_json(
    url: str, payload: dict[str, Any], *, timeout: float, cookie: str = "",
    referer: str, stage: str,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "Mozilla/5.0", "Referer": referer,
        "Origin": "https://" + urllib.parse.urlsplit(url).netloc,
    }
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.build_opener(NoResolverRedirect()).open(request, timeout=timeout) as response:
            result = json.loads(read_bounded(response, MAX_PROVIDER_RESPONSE_BYTES))
    except urllib.error.HTTPError as exc:
        if stage == "yuanbao_parse" and exc.code == 401:
            raise ShareLinkResolutionError(
                "Yuanbao downloader login expired; WeChat login and the saved card are unaffected",
                code="yuanbao_login_required",
            ) from exc
        raise ShareLinkResolutionError(
            f"{stage} returned HTTP {exc.code}", code=f"{stage}_http_error",
        ) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ShareLinkResolutionError(
            f"{stage} network request failed", code=f"{stage}_network_error",
        ) from exc
    except (ValueError, UnicodeError) as exc:
        raise ShareLinkResolutionError(
            f"{stage} returned invalid JSON", code=f"{stage}_invalid_response",
        ) from exc
    if not isinstance(result, dict):
        raise ShareLinkResolutionError(f"{stage} returned a non-object response")
    return result


def resolve_authenticated_share(
    canonical_url: str, token: str, cookie: str, *, timeout: float,
) -> dict[str, Any]:
    """Same two-stage flow as wx_channels_download, without its lost auth error."""
    deadline = time.monotonic() + timeout

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise ShareLinkResolutionError("Shipinhao resolver timed out", code="resolver_timeout")
        return value

    parsed = request_resolver_json(
        "https://yuanbao.tencent.com/api/weixin/get_parse_result",
        {"type": "video_channel_url", "url": canonical_url, "scene": 1},
        cookie=cookie, referer="https://yuanbao.tencent.com/",
        timeout=remaining(), stage="yuanbao_parse",
    )
    if str(parsed.get("code", "")) != "0":
        message = str(parsed.get("msg") or "")
        if str(parsed.get("code")) == "401" or re.search(r"未登录|登录.*(?:过期|失效)|not.?log(?:ged)?|unauthorized", message, re.I):
            raise ShareLinkResolutionError("Yuanbao downloader login required", code="yuanbao_login_required")
        raise ShareLinkResolutionError("Yuanbao rejected the share-link parse request", code="yuanbao_parse_rejected")
    data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
    playable = urllib.parse.urlsplit(str(data.get("playable_url") or ""))
    query = urllib.parse.parse_qs(playable.query)
    general_token = query.get("token", [""])[0]
    export_id = query.get("eid", [""])[0]
    if (playable.scheme != "https" or playable.hostname != "channels.weixin.qq.com"
            or not general_token or not export_id):
        raise ShareLinkResolutionError("Yuanbao returned no valid playback identity", code="yuanbao_playback_identity_missing")
    feed = request_resolver_json(
        "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info",
        {"baseReq": {"generalToken": general_token}, "exportId": export_id},
        referer=urllib.parse.urlunsplit(playable), timeout=remaining(), stage="finder_feed",
    )
    result = normalize_provider_result(feed, canonical_url=canonical_url, token=token)
    result["resolver"] = "yuanbao_authenticated_share"
    return result


def run_parse_provider(
    binary: Path,
    canonical_url: str,
    token: str,
    cookie: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="run-", dir=DEFAULT_RUN_ROOT) as temporary:
        run_dir = Path(temporary).resolve()
        run_dir.chmod(0o700)
        api_port, proxy_port = reserve_distinct_ports()
        config_path = run_dir / "parse-only.yaml"
        write_provider_config(config_path, run_dir, cookie, api_port=api_port, proxy_port=proxy_port)
        log_path = run_dir / "provider.log"
        process: subprocess.Popen[bytes] | None = None
        with log_path.open("wb") as log_handle:
            try:
                process = subprocess.Popen(
                    [str(binary), "--config", str(config_path)],
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                payload = request_parse_result(
                    canonical_url,
                    api_port=api_port,
                    timeout=timeout,
                    process=process,
                )
            finally:
                terminate_provider(process)
        if Path("/sys/class/net/tun0").exists():
            raise ShareLinkResolutionError("parse-only provider unexpectedly created tun0")
        return normalize_provider_result(payload, canonical_url=canonical_url, token=token)


def write_provider_config(path: Path, run_dir: Path, cookie: str, *, api_port: int, proxy_port: int) -> None:
    output_dir = run_dir / "downloads"
    lines = [
        "debug:",
        "  error: true",
        "  echolog: false",
        f"workdir: {json.dumps(str(run_dir), ensure_ascii=False)}",
        "download:",
        "  filenameTemplate: \"{{filename}}_{{spec}}\"",
        f"  dir: {json.dumps(str(output_dir), ensure_ascii=False)}",
        "  playDoneAudio: false",
        "  defaultActionWhenExisting: error",
        "  maxRunning: 1",
        "api:",
        "  protocol: http",
        "  hostname: 127.0.0.1",
        f"  port: {api_port}",
        "mcp:",
        "  enabled: false",
        "db:",
        "  type: sqlite",
        f"  filepath: {json.dumps(str(run_dir / 'data.db'), ensure_ascii=False)}",
        "proxy:",
        "  enabled: false",
        "  system: false",
        "  hostname: 127.0.0.1",
        f"  port: {proxy_port}",
        "  tun: false",
        "  skipInstallRootCert: true",
        "channels:",
        "  enabled: true",
        "  disableLocationToHome: false",
        "  download:",
        "    defaultHighest: true",
        "    frontend: false",
        "    cover: false",
        "    pauseWhenDownload: false",
        "    forceCheckAllFeeds: false",
        "mp:",
        "  enabled: false",
        "cloudflare:",
        f"  sphCookie: {json.dumps(cookie, ensure_ascii=False)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def request_parse_result(
    canonical_url: str,
    *,
    api_port: int,
    timeout: float,
    process: subprocess.Popen[bytes],
) -> dict[str, Any]:
    endpoint = (
        f"http://127.0.0.1:{api_port}/api/channels/parse_sph?"
        + urllib.parse.urlencode({"url": canonical_url})
    )
    deadline = time.monotonic() + timeout
    last_error = "provider did not become ready"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ShareLinkResolutionError(f"parse-only provider exited with status {process.returncode}")
        try:
            with urllib.request.urlopen(endpoint, timeout=min(12.0, max(1.0, deadline - time.monotonic()))) as response:
                payload = json.loads(read_bounded(response, MAX_PROVIDER_RESPONSE_BYTES))
            if not isinstance(payload, dict):
                raise ShareLinkResolutionError("Shipinhao resolver returned a non-object response")
            if int(payload.get("code") or 0) != 0:
                raise ShareLinkResolutionError(str(payload.get("msg") or "Shipinhao resolver rejected the link"))
            return payload
        except urllib.error.URLError as exc:
            last_error = str(exc.reason or exc)
            time.sleep(0.2)
        except json.JSONDecodeError as exc:
            raise ShareLinkResolutionError("Shipinhao resolver returned malformed JSON") from exc
    raise ShareLinkResolutionError(f"Shipinhao resolver timed out: {last_error[:200]}")


def normalize_provider_result(payload: dict[str, Any], *, canonical_url: str, token: str) -> dict[str, Any]:
    if int(payload.get("errCode") or 0) != 0:
        raise ShareLinkResolutionError("Finder preview rejected the request", code="finder_feed_rejected")
    outer_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    response = outer_data.get("data") if isinstance(outer_data.get("data"), dict) else outer_data
    if int(response.get("errCode") or 0) != 0:
        raise ShareLinkResolutionError(str(response.get("errMsg") or "Finder preview rejected the link"))
    error = response.get("errMsg")
    if isinstance(error, dict):
        restricted = bool(error.get("type") or error.get("title") or error.get("content"))
    else:
        restricted = bool(error)
    if restricted:
        raise ShareLinkResolutionError("Finder preview returned a content restriction", code="finder_content_unavailable")
    feed = response.get("feedInfo") if isinstance(response.get("feedInfo"), dict) else {}
    author = response.get("authorInfo") if isinstance(response.get("authorInfo"), dict) else {}
    video_candidates = [
        nested_text(feed, "h264VideoInfo", "videoUrl"),
        str(feed.get("videoUrl") or ""),
        str(feed.get("originVideoUrl") or ""),
        nested_text(feed, "h265VideoInfo", "videoUrl"),
    ]
    media_url = next((value for value in video_candidates if value.startswith(("http://", "https://"))), "")
    if not media_url:
        raise ShareLinkResolutionError("Finder preview returned no playable video URL")
    # Match the full card identity; preview truncation can reject the right link.
    title = " ".join(str(feed.get("description") or "").split())
    nickname = " ".join(str(author.get("nickname") or "").split())
    return {
        "detected": True,
        "source_kind": "sph_share_link",
        "share_url": canonical_url,
        "share_token": token,
        "object_id": f"sph-{token}",
        "identity_key": f"sph-{token}",
        "title": title,
        "author": nickname,
        "duration_seconds": 0.0,
        "media_type": str(feed.get("mediaType") or "4"),
        "media_urls": [media_url],
        "cover_urls": [str(feed.get("coverUrl") or "")] if feed.get("coverUrl") else [],
        "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resolver": "wx_channels_download_parse_sph",
        "content_identity_verified": bool(title and nickname),
    }


def nested_text(payload: dict[str, Any], key: str, child: str) -> str:
    nested = payload.get(key)
    return str(nested.get(child) or "") if isinstance(nested, dict) else ""


def compact_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def reserve_distinct_ports() -> tuple[int, int]:
    ports: list[int] = []
    sockets: list[socket.socket] = []
    try:
        while len(ports) < 2:
            handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            handle.bind(("127.0.0.1", 0))
            sockets.append(handle)
            port = int(handle.getsockname()[1])
            if port not in ports:
                ports.append(port)
    finally:
        for handle in sockets:
            handle.close()
    return ports[0], ports[1]


def terminate_provider(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def read_bounded(response: Any, max_bytes: int) -> bytes:
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ShareLinkResolutionError("Shipinhao resolver response exceeded the safety limit")
    return data


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def safe_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a diagnostic result without cookies or signed media URLs."""
    return {
        key: value
        for key, value in payload.items()
        if key not in {"media_urls", "cover_urls"}
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = resolve_share_link(args.url, cdp_url=args.cdp_url)
    except ShareLinkResolutionError as exc:
        payload = {"status": "failed", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["error"])
        return 1
    payload = {"status": "resolved", **safe_result(result)}
    print(json.dumps(payload, ensure_ascii=False) if args.json else f"resolved: {payload.get('author')} - {payload.get('title')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

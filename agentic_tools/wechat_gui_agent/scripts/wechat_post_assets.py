"""Download original images explicitly bound to an Official Account post."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image


MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 48 * 1024 * 1024
MAX_IMAGES = 12


def trusted_image_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme in {"https", "http"}
            and not parsed.username and not parsed.password
            and parsed.port in {None, 80, 443}
            and any(host == suffix or host.endswith("." + suffix)
                    for suffix in ("qpic.cn", "qlogo.cn"))
        )
    except ValueError:
        return False


class ImageRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_image_url(newurl):
            raise ValueError("post image redirected outside its image CDN")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_post_images(
    urls: list[str], output_dir: Path, *, timeout: float = 10,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    results, used = [], 0
    for index, url in enumerate(urls):
        item = {"kind": "image", "page": index + 1, "status": "unavailable"}
        try:
            if index >= MAX_IMAGES or used >= MAX_TOTAL_BYTES:
                raise ValueError("post image budget reached; remaining pages require agent review")
            if not trusted_image_url(url):
                raise ValueError("post image URL is not an allowlisted image CDN")
            req = Request(url, headers={"Referer": "https://mp.weixin.qq.com/", "User-Agent": "MicroMessenger/8.0"})
            with build_opener(ImageRedirects()).open(req, timeout=timeout) as response:
                data = response.read(min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - used) + 1)
            if len(data) > min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - used):
                raise ValueError("post image exceeds bounded download size")
            used += len(data)
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}.get(image.format)
                if not suffix or width * height > 64_000_000:
                    raise ValueError("unsupported or oversized post image")
                image.verify()
            path = output_dir / f"page-{index + 1:02d}{suffix}"
            path.write_bytes(data)
            path.chmod(0o600)
            item.update(status="ready", path=str(path.resolve()), width=width, height=height,
                        size_bytes=len(data), sha256=sha256(data).hexdigest(), fidelity="source_original_bytes")
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        results.append(item)
    return results

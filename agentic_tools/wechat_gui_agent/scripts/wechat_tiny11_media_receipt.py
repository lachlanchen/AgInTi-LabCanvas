"""Verify Windows WeChat's remuxed video against the submitted media streams."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess


def md5_file(path):
    digest = hashlib.md5()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stream_hashes(path):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v?", "-map", "0:a?",
         "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"],
        capture_output=True, text=True, timeout=60, check=True,
    )
    rows = result.stdout.strip().splitlines()
    if not rows or any(not re.fullmatch(r"\d+,[av],SHA256=[0-9a-f]{64}", row) for row in rows):
        raise ValueError("native_video_stream_hash_unavailable")
    return rows


def verify_video(transport, source, attrs, *, created_at, cache_dir):
    digest = str(attrs.get("rawmd5") or "").lower()
    size = int(attrs.get("rawlength") or 0)
    if not re.fullmatch(r"[0-9a-f]{32}", digest) or size <= 0:
        return None
    month = datetime.fromtimestamp(created_at).strftime("%Y-%m")
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cached = cache_dir / (digest + ".mp4")
    if not cached.is_file() or cached.stat().st_size != size or md5_file(cached) != digest:
        # Only inspect this account's month of video cache. Size narrows
        # discovery; the exact native row digest, not mtime, selects the file.
        script = f"""
$c=Get-Content -LiteralPath C:\\LabCanvas\\WeChatStore\\config.json | ConvertFrom-Json
$root=Join-Path (Split-Path $c.db_dir -Parent) 'msg\\video\\{month}'
$found=Get-ChildItem -LiteralPath $root -Filter '*_raw.mp4' -File |
  Where-Object {{ $_.Length -eq {size} }} | Where-Object {{
    (Get-FileHash -LiteralPath $_.FullName -Algorithm MD5).Hash.ToLower() -eq '{digest}'
  }} | Select-Object -First 1
if($found) {{ @{{path=$found.FullName}} | ConvertTo-Json -Compress }} else {{ '{{}}' }}
"""
        remote = json.loads(transport.powershell(script, timeout=30)).get("path", "")
        # The path is supplied by our guest script, not chat text.
        if not remote or not remote.lower().endswith("_raw.mp4"):
            return None
        temporary = cached.with_suffix(".part")
        try:
            subprocess.run(
                ["scp", "-q", "-P", str(transport.ssh_port), "-o", "BatchMode=yes",
                 "-o", "ConnectTimeout=8", f"{transport.user}@{transport.host}:" + remote.replace("\\", "/"),
                 str(temporary)], capture_output=True, timeout=60, check=True,
            )
            temporary.chmod(0o600)
            if temporary.stat().st_size != size or md5_file(temporary) != digest:
                raise ValueError("native_video_receipt_hash_mismatch")
            temporary.replace(cached)
        finally:
            temporary.unlink(missing_ok=True)
    original_hashes = stream_hashes(source)
    if original_hashes != stream_hashes(cached):
        return None
    return {"method": "native_video_row_and_exact_stream_hashes", "rawmd5": digest,
            "rawlength": size, "stream_hashes": original_hashes}

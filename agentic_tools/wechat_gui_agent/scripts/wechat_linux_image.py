"""Recover Linux WeChat originals by exact native message/resource identity.

The message XML digest is not necessarily the local cache filename. Resolve
that mapping before decoding; previews and neighbouring files are never inputs.
"""

from __future__ import annotations

from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from wechat_media_sync import decode_wechat_v_container, decode_xor_dat, image_decode_keys
from wechat_tiny11_image import coalesced_image_sources, decode_wxgf, image_size


PRIVATE = Path(__file__).resolve().parents[1] / ".private"
MAX_IMAGE_BYTES = 64 * 1024 * 1024
V2 = b"\x07\x08V2\x08\x07"


def selected(task):
    source = task.get("source") or {}
    return bool(
        (source.get("kind") == "image" or coalesced_image_sources(task))
        and re.fullmatch(r"message_\d+\.db", str(source.get("message_db") or ""))
        and source.get("message_db") != "message_999998.db"
        and (PRIVATE / Path(str(source.get("config_id") or "")).name).is_file()
    )


def native_request(task):
    from wechat_direct_chatops import DECRYPTED

    source = task.get("source") or {}
    config_id = str(source.get("config_id") or "")
    if not config_id or Path(config_id).name != config_id:
        raise ValueError("image_chat_config_invalid")
    config = json.loads((PRIVATE / config_id).read_text())
    table = str(source.get("message_table") or "")
    chatroom = str(config.get("chatroom_id") or "")
    if (config.get("chat_name") != task.get("chat")
            or source.get("chat") != task.get("chat")
            or table != config.get("message_table")
            or table != "Msg_" + hashlib.md5(chatroom.encode()).hexdigest()):
        raise ValueError("image_chat_binding_mismatch")
    shard = str(source.get("message_db") or "")
    if not re.fullmatch(r"message_\d+\.db", shard) or shard == "message_999998.db":
        raise ValueError("image_message_database_mismatch")
    root = Path(DECRYPTED) / "message"
    request = {key: source[key] for key in ("local_id", "server_id", "create_time")}
    with closing(sqlite3.connect((root / shard).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        rows = conn.execute(
            f'SELECT local_type FROM "{table}" WHERE local_id=? '
            'AND CAST(server_id AS TEXT)=? AND create_time=?',
            (request["local_id"], str(request["server_id"]), request["create_time"]),
        ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) & 0xffffffff != 3:
        raise ValueError("image_native_message_mismatch")
    with closing(sqlite3.connect((root / "message_resource.db").resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        rows = conn.execute(
            'SELECT r.packed_info FROM MessageResourceInfo r '
            'JOIN ChatName2Id c ON c.rowid=r.chat_id WHERE c.user_name=? '
            'AND r.message_local_id=? AND CAST(r.message_svr_id AS TEXT)=? '
            'AND r.message_create_time=? AND (r.message_local_type & 4294967295)=3',
            (chatroom, request["local_id"], str(request["server_id"]), request["create_time"]),
        ).fetchall()
    if len(rows) != 1:
        raise ValueError("image_resource_identity_unavailable")
    tokens = set(re.findall(rb"\x12\x22\x0a\x20([0-9a-f]{32})", rows[0][0] or b""))
    if len(tokens) != 1:
        raise ValueError("image_resource_identity_ambiguous")
    decoder = json.loads((PRIVATE / "external/wechat-decrypt/config.json").read_text())
    if Path(decoder.get("decrypted_dir", "")).resolve() != Path(DECRYPTED).resolve():
        raise ValueError("image_decrypted_account_mismatch")
    account = Path(decoder["db_dir"]).resolve().parent
    if not re.fullmatch(re.escape(str(config.get("self_wxid") or "")) + r"_[0-9a-f]{4}", account.name):
        raise ValueError("image_account_identity_mismatch")
    return account, table, request, tokens.pop().decode("ascii")


def validate_key(key, samples):
    from Crypto.Cipher import AES

    if len(key) != 16:
        return False
    for data in samples:
        if not data.startswith(V2) or len(data) < 31:
            return False
        head = AES.new(key, AES.MODE_ECB).decrypt(data[15:31])
        if not (head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8", b"wxgf"))
                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
            return False
    return True


def derive_profile_key(account, xor, samples, *, timeout_seconds=30):
    # Same offline account-suffix derivation used by the existing Windows
    # exporter, bounded to one CPU and validated against full + thumbnail data.
    wxid, suffix = account.name.rsplit("_", 1)
    suffix_bytes = bytes.fromhex(suffix)
    deadline = time.monotonic() + timeout_seconds
    for counter in range(1 << 24):
        if counter % 65536 == 0 and time.monotonic() >= deadline:
            raise TimeoutError("image_key_derivation_timeout")
        code = str((counter << 8) | xor).encode("ascii")
        if hashlib.md5(code).digest()[:2] != suffix_bytes:
            continue
        key = hashlib.md5(code + wxid.encode("ascii")).hexdigest()[:16].encode("ascii")
        if validate_key(key, samples):
            return key
    raise ValueError("image_key_unavailable")


def profile_keys(account, dat):
    data = dat.read_bytes()
    if not data.startswith(V2):
        return None, 0x88
    thumb = dat.with_name(dat.stem.removesuffix("_h") + "_t.dat")
    samples = [data]
    xor = None
    if thumb.is_file() and 0 < thumb.stat().st_size <= MAX_IMAGE_BYTES:
        preview = thumb.read_bytes()
        if preview.startswith(V2) and len(preview) >= 31:
            samples.append(preview)
            if preview[-2] ^ 0xff == preview[-1] ^ 0xd9:
                xor = preview[-2] ^ 0xff
    cache = PRIVATE / "image_keys" / (hashlib.sha256(account.name.encode()).hexdigest()[:24] + ".json")
    cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with cache.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(cache.read_text())
            key = saved["image_aes_key"].encode("ascii")
            saved_xor = int(saved["image_xor_key"])
            if validate_key(key, samples):
                return key, xor if xor is not None else saved_xor
        except (OSError, ValueError, KeyError):
            pass
        key, saved_xor = image_decode_keys("", "")
        if key and validate_key(key, samples):
            xor = saved_xor if xor is None else xor
        else:
            if xor is None or len(samples) < 2:
                raise ValueError("image_key_validation_source_missing")
            key = derive_profile_key(account, xor, samples)
        temporary = cache.with_suffix(".tmp")
        try:
            temporary.touch(mode=0o600, exist_ok=True)
            temporary.chmod(0o600)
            temporary.write_text(json.dumps({"image_aes_key": key.decode("ascii"), "image_xor_key": xor}))
            temporary.replace(cache)
        finally:
            temporary.unlink(missing_ok=True)
        return key, xor


def recover_image(task, output_dir):
    account, table, request, token = native_request(task)
    base = account / "msg/attach" / table[4:]
    files = list(base.glob("*/Img/" + token + "_h.dat")) or list(base.glob("*/Img/" + token + ".dat"))
    if len(files) != 1:
        raise ValueError("exact_full_image_not_cached")
    dat = files[0]
    if dat.is_symlink() or not dat.resolve().is_relative_to(base.resolve()):
        raise ValueError("image_cache_path_escape")
    if not 0 < dat.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("image_size_out_of_bounds")
    data = dat.read_bytes()
    key, xor = profile_keys(account, dat)
    decoded = decode_wechat_v_container(data, image_aes_key=key, image_xor_key=xor)
    decoded = decoded or decode_xor_dat(data)
    if decoded is None:
        raise ValueError("image_native_decode_failed")
    fmt, payload = decoded
    if fmt not in {"jpg", "png", "gif", "webp", "bmp", "tif", "wxgf"}:
        raise ValueError("image_native_format_unsupported")
    output_dir = Path(output_dir)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = output_dir / ("wechat-image-" + str(request["server_id"]) + "." + fmt)
    target.touch(mode=0o600, exist_ok=True)
    target.chmod(0o600)
    target.write_bytes(payload)
    original = target
    if fmt == "wxgf":
        target = target.with_suffix(".png")
        dimensions = decode_wxgf(original, target)
    else:
        dimensions = image_size(target)
    manifest = output_dir / "native-image-export.json"
    manifest.touch(mode=0o600, exist_ok=True)
    manifest.chmod(0o600)
    manifest.write_text(json.dumps({
        "source": request, "resource_token": token, "native_path": str(dat),
        "container_path": str(original), "container_sha256": hashlib.sha256(payload).hexdigest(),
        "decoded_path": str(target), "decoded_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "width": dimensions[0], "height": dimensions[1], "variant": "high" if dat.stem.endswith("_h") else "full",
        "method": "linux_native_exact_message_resource", "resized": False,
    }, indent=2), encoding="utf-8")
    return {
        "mirror_path": str(target), "source_path": str(target), "suffix": target.suffix,
        "size_bytes": target.stat().st_size, "status": "copied", "score": 1000,
        "matched_by": "native-image-exact-message-resource",
        "match_reasons": ["exact_message", "resource_database"],
        "fidelity": "native_full_image", "original_resolution_verified": True,
        "source_server_id": str(request["server_id"]),
        "width": dimensions[0], "height": dimensions[1],
        "metadata": {"export_manifest": str(manifest)},
    }


def recover_images(task, output_dir):
    sources = coalesced_image_sources(task)
    if (task.get("source") or {}).get("kind") == "image":
        sources = [task["source"], *sources]
    copies = []
    seen = set()
    for source in sorted(sources, key=lambda item: (int(item.get("create_time") or 0), int(item["local_id"]))):
        identity = (source.get("message_db"), str(source.get("server_id")))
        if identity in seen:
            continue
        seen.add(identity)
        candidate = {**task, "source": {**task["source"], **source, "kind": "image", "local_type": 3}}
        copies.append(recover_image(candidate, Path(output_dir) / str(source["server_id"])))
    if len(copies) > 1:
        for index, item in enumerate(copies, start=1):
            item.update(album_index=index, album_count=len(copies))
    return copies

"""Read one account/chat/message-bound image without touching the WeChat UI.

Requires the pinned, separately installed wechat-decrypt reader/decoder. Keys
remain in the guest private workspace; stdout contains only the export receipt.
"""

import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def resource_token(blob):
    # Accept only the known nested protobuf field, not any nearby 32-char text.
    values = re.findall(rb'\x12\x22\x0a\x20([0-9a-f]{32})', blob or b'')
    if len(set(values)) != 1:
        raise ValueError('image_resource_identity_unavailable')
    return values[0].decode('ascii')


def resolve_resource(conn, request):
    table = request['table']
    if not re.fullmatch(r'Msg_[0-9a-f]{32}', table):
        raise ValueError('invalid_message_table')
    chats = [(rid, name) for rid, name in conn.execute('SELECT rowid,user_name FROM ChatName2Id')
             if 'Msg_' + hashlib.md5(name.encode()).hexdigest() == table]
    if len(chats) != 1:
        raise ValueError('image_chat_identity_mismatch')
    rows = conn.execute(
        'SELECT packed_info FROM MessageResourceInfo WHERE chat_id=? '
        'AND message_local_id=? AND message_svr_id=? AND message_create_time=? '
        'AND (message_local_type & 4294967295)=3',
        (chats[0][0], request['local_id'], int(request['server_id']), request['create_time']),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError('image_message_identity_mismatch')
    return resource_token(rows[0][0])


def image_key(dat):
    from find_all_keys import try_key
    ciphertext = dat.read_bytes()[15:31]
    key_path = ROOT / 'image-key.private.json'
    if key_path.is_file():
        saved = json.loads(key_path.read_text(encoding='utf-8'))
        key = saved.get('aes', '')
        if key and try_key(key.encode(), ciphertext):
            return key
    if '--provision-key' not in sys.argv:
        raise ValueError('image_key_provisioning_required')
    # One-time, explicit, offline provisioning. No process scanning or GUI input
    # in normal intake. Reuse the upstream account suffix / XOR derivation.
    from find_all_keys import _brute_worker
    account = dat.parents[5].name
    wxid, suffix = account.rsplit('_', 1)
    if not re.fullmatch(r'[0-9a-f]{4}', suffix):
        raise ValueError('unsupported_image_account_suffix')
    thumb = dat.with_name(dat.stem.removesuffix('_h') + '_t.dat').read_bytes()
    xor = thumb[-2] ^ 0xff
    if thumb[-1] ^ 0xd9 != xor:
        raise ValueError('image_xor_provisioning_failed')
    class Found(Exception):
        pass
    class Result:
        key = None
        def put(self, pair):
            self.key = pair[1]
            raise Found()
    result = Result()
    try:
        _brute_worker(0, 1 << 24, xor, bytes.fromhex(suffix), wxid.encode(), ciphertext, result)
    except Found:
        key_path.write_text(json.dumps({'aes': result.key}), encoding='utf-8')
        return result.key
    raise ValueError('image_key_provisioning_failed')


def decode_exact(dat, target):
    from decode_image import decrypt_dat_file
    data = dat.read_bytes()
    key = image_key(dat) if data.startswith(b'\x07\x08V2\x08\x07') else None
    # JPEG tail derives XOR for this file, not another account's Linux cache.
    xors = [0x88]
    thumb = dat.with_name(dat.stem.removesuffix('_h') + '_t.dat')
    if thumb.is_file():
        tail = thumb.read_bytes()[-2:]
        if len(tail) == 2 and tail[0] ^ 0xff == tail[1] ^ 0xd9:
            xors.insert(0, tail[0] ^ 0xff)
    if len(data) > 2 and data[-2] ^ 0xff == data[-1] ^ 0xd9:
        xors.insert(0, data[-2] ^ 0xff)
    for xor in dict.fromkeys(xors):
        result, fmt = decrypt_dat_file(str(dat), out_path=str(target), aes_key=key, xor_key=xor)
        if not result or fmt not in ('jpg', 'png', 'gif', 'webp', 'bmp', 'tif', 'hevc'):
            continue
        if fmt == 'hevc':
            fmt = 'wxgf'
        final = target.with_suffix('.' + fmt)
        Path(result).replace(final)
        return final
    target.unlink(missing_ok=True)
    raise ValueError('image_decode_failed')


def export(request):
    from wechat_store_snapshot import cached_reader, open_snapshot
    if not re.fullmatch(r'[1-9][0-9]{0,20}', str(request['server_id'])):
        raise ValueError('invalid_image_server_id')
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
    spec = importlib.util.spec_from_file_location('wechat_store_reader', ROOT / 'db.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    account = Path(cfg['db_dir']).parent
    db = cached_reader(reader, db_dir=str(account.parent), account=account.name,
                       keys_file=str(ROOT / 'reader-keys.private.json'), workdir=str(ROOT / 'cache'))
    if db.account != account.name or db.wxid != request['self_wxid']:
        raise ValueError('image_account_identity_mismatch')
    resource = next(rel for rel, path, _ in db._db_files if Path(path).name == 'message_resource.db')
    with contextlib.closing(open_snapshot(db, resource, reader)) as conn:
        token = resolve_resource(conn, request)
    base = account / 'msg' / 'attach' / request['table'][4:]
    # Native full image (_h when present); never _t, _b, or viewer screenshots.
    files = list(base.glob('*/Img/' + token + '_h.dat')) or list(base.glob('*/Img/' + token + '.dat'))
    if len(files) != 1:
        raise ValueError('exact_full_image_not_cached')
    if not 0 < files[0].stat().st_size <= 64 * 1024 * 1024:
        raise ValueError('image_size_out_of_bounds')
    out = ROOT / 'image-exports'
    out.mkdir(exist_ok=True)
    path = decode_exact(files[0], out / (request['server_id'] + '.part'))
    payload = path.read_bytes()
    return {'ok': True, 'path': str(path),
            'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
            'md5': hashlib.md5(payload).hexdigest(), 'resource_token': token,
            'source': request, 'method': 'native_exact_message_resource',
            'variant': 'high' if files[0].stem.endswith('_h') else 'full'}


if __name__ == '__main__':
    import base64
    try:
        request = json.loads(base64.b64decode(sys.argv[1]))
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            result = export(request)
    except Exception as exc:
        result = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)[:250]}
    print(json.dumps(result))

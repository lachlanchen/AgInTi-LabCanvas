"""Retrieve the exact full native Windows WeChat image over the existing SSH route."""

import base64
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET
from wechat_combined_images import combined_image_group, same_image_group

from PIL import Image


def image_request(task, config, store):
    from wechat_native_text_delivery import native_chat_binding
    from wechat_direct_chatops import decode_content
    source = task.get('source') or {}
    chat = task.get('chat')
    if chat not in config.get('targets', {}):
        raise ValueError('image_chat_not_allowlisted')
    binding = native_chat_binding(config['targets'][chat])
    table = source.get('message_table', '')
    if (table != binding['table'] or table not in config['message_tables']
            or not re.fullmatch(r'Msg_[0-9a-f]{32}', table)):
        raise ValueError('image_chat_binding_mismatch')
    if source.get('message_db') != Path(store).name:
        raise ValueError('image_message_database_mismatch')
    with closing(sqlite3.connect(Path(store).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        row = conn.execute(
            f'SELECT r.source_id,m.server_id,m.create_time,m.local_type,m.message_content,'
            f'm.compress_content,m.WCDB_CT_message_content FROM "{table}" m '
            'JOIN Tiny11Rows r ON r.table_name=? AND r.local_id=m.local_id '
            'WHERE m.local_id=? AND CAST(m.server_id AS TEXT)=?',
            (table, source['local_id'], str(source['server_id'])),
        ).fetchall()
    if len(row) != 1 or int(row[0][3]) & 0xffffffff != 3:
        raise ValueError('image_native_message_mismatch')
    row = row[0]
    text = decode_content(*row[4:])
    xml = ET.fromstring(text[text.index('<msg'):])
    img = xml.find('img')
    if img is None:
        raise ValueError('image_native_attributes_missing')
    request = {'self_wxid': config['self_wxid'], 'table': table, 'local_id': row[0],
               'server_id': str(row[1]), 'create_time': int(row[2])}
    # Signed CDN URLs and AES keys never leave the source database in this packet.
    attrs = {key: img.get(key, '') for key in ('md5', 'length', 'hdlength', 'cdnthumbwidth', 'cdnthumbheight')}
    attrs['combined_image'] = combined_image_group(text)
    return request, attrs


def verify_export(path, receipt, attrs):
    payload = path.read_bytes()
    if (len(payload) != int(receipt['bytes'])
            or hashlib.sha256(payload).hexdigest() != receipt['sha256']):
        raise ValueError('image_transfer_checksum_mismatch')
    expected = int(attrs.get('hdlength' if receipt['variant'] == 'high' else 'length') or 0)
    if expected and len(payload) != expected:
        raise ValueError('image_native_length_mismatch')
    if (receipt['variant'] != 'high' and re.fullmatch(r'[0-9a-f]{32}', attrs.get('md5', ''))
            and hashlib.md5(payload).hexdigest() != attrs['md5']):
        raise ValueError('image_native_digest_mismatch')
    if payload.startswith(b'wxgf'):
        return None
    return image_size(path)


def image_size(path):
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()
        width, height = image.size
    return width, height


def decode_wxgf(source, target):
    data = source.read_bytes()
    # wxgf wraps HEVC Annex-B. Decode at native dimensions to lossless PNG;
    # retain the exact original container as provenance, never a screenshot.
    start = data.find(b'\x00\x00\x00\x01')
    if not data.startswith(b'wxgf') or start < 0:
        raise ValueError('invalid_wxgf_container')
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-threads', '1', '-f', 'hevc',
                    '-i', 'pipe:0', '-frames:v', '1', '-threads', '1', '-y', str(target)],
                   input=data[start:], capture_output=True, timeout=30, check=True)
    target.chmod(0o600)
    return image_size(target)


def recover_image(task, output_dir, *, provision_key=False):
    from wechat_tiny11_bridge import CONFIG, STORE, load_config, Tiny11Transport
    config = load_config(CONFIG)
    request, attrs = image_request(task, config, STORE)
    transport = Tiny11Transport(config)
    packet = base64.b64encode(json.dumps(request).encode()).decode()
    # Share the existing snapshot lock with native row polling. The guest
    # snapshot filenames are stable, so concurrent decrypt writers are unsafe.
    with STORE.with_name('sync.lock').open('a') as lock:
        deadline = time.monotonic() + 45
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('native_image_snapshot_busy')
                time.sleep(0.2)
        receipt = json.loads(transport.powershell(
            '& C:/LabCanvas/Python312/python.exe C:/LabCanvas/WeChatStore/Export-WeChatImage.py ' + packet
            + (' --provision-key' if provision_key else ''),
            timeout=300 if provision_key else 45,
        ))
    if not receipt.get('ok'):
        raise ValueError(str(receipt.get('error') or 'native_image_export_failed'))
    if receipt.get('source') != request or receipt.get('variant') not in ('full', 'high'):
        raise ValueError('image_export_identity_mismatch')
    remote = PureWindowsPath(receipt['path'])
    if (remote.parent != PureWindowsPath('C:/LabCanvas/WeChatStore/image-exports')
            or remote.stem != request['server_id'] or remote.suffix not in ('.jpg', '.png', '.gif', '.webp', '.bmp', '.tif', '.wxgf')
            or not 0 < int(receipt['bytes']) <= 64 * 1024 * 1024):
        raise ValueError('invalid_image_export_path')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = output_dir / ('wechat-image-' + request['server_id'] + remote.suffix)
    temporary = target.with_suffix('.part')
    try:
        subprocess.run(['scp', '-q', '-P', str(transport.ssh_port), '-o', 'BatchMode=yes',
                        '-o', 'ConnectTimeout=8', f'{transport.user}@{transport.host}:{remote.as_posix()}',
                        str(temporary)], capture_output=True, timeout=60, check=True)
        temporary.chmod(0o600)
        dimensions = verify_export(temporary, receipt, attrs)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    if dimensions is None:
        png = target.with_suffix('.png')
        dimensions = decode_wxgf(target, png)
        receipt['decoded_path'] = str(png)
        receipt['decoded_sha256'] = hashlib.sha256(png.read_bytes()).hexdigest()
        target = png
    width, height = dimensions
    manifest = output_dir / 'native-image-export.json'
    manifest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest.chmod(0o600)
    return {'mirror_path': str(target), 'source_path': str(target), 'suffix': target.suffix,
            'size_bytes': target.stat().st_size, 'status': 'copied', 'score': 1000,
            'matched_by': 'native-image-exact-message-resource', 'match_reasons': ['exact_message', 'resource_database'],
            'fidelity': 'native_full_image', 'original_resolution_verified': True,
            'combined_image': attrs.get('combined_image'),
            'width': width, 'height': height, 'metadata': {'export_manifest': str(manifest)}}


def image_group_tasks(task, group, config, store):
    from wechat_direct_chatops import decode_content
    # Validate the anchor through the existing account/chat/message contract.
    image_request(task, config, store)
    source = task['source']
    table = source['message_table']
    with closing(sqlite3.connect(Path(store).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        anchor = conn.execute(f'SELECT real_sender_id FROM "{table}" WHERE local_id=?',
                              (source['local_id'],)).fetchone()
        rows = conn.execute(
            f'SELECT local_id,server_id,create_time,local_type,real_sender_id,'
            f'message_content,compress_content,WCDB_CT_message_content FROM "{table}" '
            'WHERE (local_type & 4294967295) IN (3,43) ORDER BY local_id DESC LIMIT 10000',
        ).fetchall()
    members = []
    for local_id, server_id, created, kind, sender, *body in rows:
        candidate = combined_image_group(decode_content(*body))
        if not candidate or candidate['id'] != group['id']:
            continue
        if not same_image_group(candidate, group) or sender != anchor[0]:
            raise ValueError('image_group_identity_mismatch')
        if int(kind) & 0xffffffff != 3:
            raise ValueError('mixed_image_video_group_requires_separate_video_intake')
        members.append({**task, 'source': {**source, 'local_id': local_id,
                                         'server_id': str(server_id), 'create_time': created,
                                         'local_type': kind}})
    members.sort(key=lambda item: item['source']['local_id'])
    if len(members) != group['count'] or len({m['source']['server_id'] for m in members}) != len(members):
        raise ValueError('combined_image_members_incomplete')
    return members


def coalesced_image_sources(task):
    """Current numbered inputs only; nearby history cannot select an image."""
    source = task.get('source') or {}
    return [entry for entry in task.get('message_ledger') or []
            if isinstance(entry, dict) and entry.get('kind') == 'image'
            and entry.get('role') == 'coalesced_source'
            and entry.get('chat') == task.get('chat')
            and entry.get('message_db') == source.get('message_db')
            and entry.get('local_id') is not None and entry.get('server_id')]


def coalesced_image_task(task, config, store):
    sources = coalesced_image_sources(task)
    if not sources:
        raise ValueError('coalesced_image_source_missing')
    candidates = []
    for source in sources:
        candidate = {**task, 'source': {**task['source'],
            **{key: source.get(key) for key in (
                'local_id', 'server_id', 'create_time', 'sender', 'sender_display')},
            'kind': 'image', 'local_type': 3}}
        _, attrs = image_request(candidate, config, store)
        candidates.append((candidate, attrs.get('combined_image')))
    if len(candidates) > 1 and not all(
            same_image_group(group, candidates[0][1]) for _, group in candidates):
        raise ValueError('ambiguous_coalesced_image_groups')
    return min(candidates, key=lambda item: int(item[0]['source']['local_id']))[0]


def recover_images(task, output_dir):
    """Recover each original in native album order, or retain an explicit blocker."""
    if coalesced_image_sources(task) and (task.get('source') or {}).get('kind') != 'image':
        from wechat_tiny11_bridge import CONFIG, STORE, load_config
        task = coalesced_image_task(task, load_config(CONFIG), STORE)
    first = recover_image(task, output_dir)
    group = first.pop('combined_image', None)
    if not group:
        return [first]
    from wechat_tiny11_bridge import CONFIG, STORE, load_config
    config = load_config(CONFIG)
    # A snapshot may contain the first row before the rest of its native album.
    # Wait only for exact group members; mismatched identity fails immediately.
    for delay in (0.25, 0.75, 2, None):
        try:
            members = image_group_tasks(task, group, config, STORE)
            break
        except ValueError as exc:
            if str(exc) != 'combined_image_members_incomplete' or delay is None:
                raise
            time.sleep(delay)
    copies = []
    for index, member in enumerate(members, start=1):
        same_source = str(member['source']['server_id']) == str(task['source']['server_id'])
        item = first if same_source else recover_image(member, Path(output_dir) / f'image-{index:03d}')
        item.pop('combined_image', None)
        item.update({'album_index': index, 'album_count': len(members),
                     'source_server_id': member['source']['server_id']})
        copies.append(item)
    manifest = Path(output_dir) / 'native-combined-image-export.json'
    manifest.write_text(json.dumps({'count': len(copies), 'images': copies}, indent=2), encoding='utf-8')
    manifest.chmod(0o600)
    return copies


def install_decoder(decoder_root):
    """Deploy the pinned decoder into the existing guest reader, not a new stack."""
    from wechat_tiny11_bridge import CONFIG, ROOT, load_config, Tiny11Transport
    decoder_root = Path(decoder_root).resolve()
    revision = '656d06a527781bc715955bdade080234a47e122b'
    observed = subprocess.check_output(['git', '-C', str(decoder_root), 'rev-parse', 'HEAD'], text=True).strip()
    if observed != revision:
        raise ValueError('image_decoder_revision_mismatch')
    names = ('decode_image.py', 'find_all_keys.py')
    subprocess.run(['git', '-C', str(decoder_root), 'diff', '--exit-code', 'HEAD', '--', *names],
                   capture_output=True, check=True)
    transport = Tiny11Transport(load_config(CONFIG))
    remote = 'C:/LabCanvas/WeChatStore/'
    transport.powershell("if (!(Test-Path 'C:/LabCanvas/WeChatStore/reader-keys.private.json')) "
                         "{ throw 'Existing native store reader must be provisioned first' }")
    for name in names:
        transport.scp_to_guest(decoder_root / name, remote + name)
    transport.scp_to_guest(ROOT / 'agentic_tools/wecom_agent/windows/Export-WeChatImage.py',
                           remote + 'Export-WeChatImage.py')
    # Provisioned keys inherit this private directory ACL, including after rotation.
    return transport.powershell(
        "$ErrorActionPreference='Stop'; "
        "icacls C:/LabCanvas/WeChatStore /inheritance:r /grant:r "
        "\"${env:USERNAME}:(OI)(CI)F\" 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null; "
        "if($LASTEXITCODE -ne 0){throw 'Image reader ACL failed'}; "
        "& C:/LabCanvas/Python312/python.exe -c \"import sys; sys.path.insert(0, 'C:/LabCanvas/WeChatStore'); "
        "from Crypto.Cipher import AES; import decode_image; print('image_decoder_ready')\"; "
        "if($LASTEXITCODE -ne 0){throw 'Install the pinned guest pycryptodome wheel first'}"
    )


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    install = sub.add_parser('install')
    install.add_argument('--decoder-root', type=Path, required=True)
    recover = sub.add_parser('recover')
    recover.add_argument('--task-id', required=True)
    recover.add_argument('--provision-key', action='store_true', help='Explicit one-time offline key setup')
    args = parser.parse_args()
    if args.action == 'install':
        print(install_decoder(args.decoder_root))
    else:
        from wechat_task_worker import DEFAULT_QUEUE, find_task, ROOT
        task = find_task(DEFAULT_QUEUE, args.task_id)
        if not task:
            parser.error('Exact task not found')
        result = recover_image(task, ROOT / 'output/wechat_worker' / str(task['id']) / 'native_image',
                               provision_key=args.provision_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))

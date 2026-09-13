#!/usr/bin/env python3
"""Personal WeChat transport on the existing KVM, separate from WeCom state."""

from __future__ import annotations

import argparse
import base64
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / 'agentic_tools/wechat_gui_agent/.private'
CONFIG = PRIVATE / 'wechat_tiny11.local.json'
STORE = PRIVATE / 'tiny11/message_999998.db'
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/scripts'))

from wecom_tiny11_gui_bridge import Tiny11WeComGuiBridge
from wecom_tiny11_transport import Tiny11Transport, load_config
from wecom_gui_bridge import (normalize_text, write_private_json, chunk_text,
                              short_hash, delivery_done, remember_delivery,
                              get_runtime, set_runtime, file_delivery_key, filename_matches_ocr)
from wechat_native_text_delivery import (native_chat_binding, pending_receipt_path,
                                         retain_pending_receipt, normalize_text as normalize_message)
from wechat_mirror import DEFAULT_DB, record_event
from wechat_message_policy import file_transport_identity

TABLE_RE = re.compile(r'Msg_[0-9a-fA-F]{32}')


def title_key(text):
    return re.sub(r'[-\u2010-\u2015\u2212\uff0d]', '-', normalize_text(text))


def title_matches(observed, expected):
    observed, expected = title_key(observed), title_key(expected)
    return len(observed) == len(expected) and all(
        left == right or (right == '-' and left == '\u4e00')
        for left, right in zip(observed, expected)
    )


def composed_filename_matches(filename, observed):
    if filename_matches_ocr(filename, observed):
        return True
    expected = normalize_text(filename)
    for line in observed.splitlines():
        line = normalize_text(line)
        suffix = Path(filename).suffix.lower()
        end = line.find(suffix) if suffix else -1
        if end >= 0:
            line = line[:end + len(suffix)]
        pieces = re.split(r'\.{3}|\u2026', line)
        if (len(pieces) == 2 and min(map(len, pieces)) >= 4
                and expected.startswith(pieces[0]) and expected.endswith(pieces[1])):
            return True
    return False


def enabled():
    try:
        return load_config(CONFIG).get('enabled') is True
    except Exception:
        return False


class Tiny11WeChatBridge(Tiny11WeComGuiBridge):
    def __init__(self, config=None):
        config = config or load_config(CONFIG)
        super().__init__(config, config_path=CONFIG)
        if self.tiny11.app != 'wechat':
            raise ValueError('Personal WeChat requires an explicitly scoped helper')

    def find_window(self, *, required=True):
        window = super().find_window(required=False)
        if window is None and required:
            self.tiny11.invoke({'action': 'restore'})
            window = super().find_window(required=False)
        if window is None and required:
            raise RuntimeError('WECHAT_WINDOW_UNAVAILABLE: no existing personal WeChat main window')
        return window

    @staticmethod
    def content_left(window):
        return window.x + 226

    def conversation_surface(self, window):
        left = self.content_left(window) + 10
        return left, window.y + 80, window.x + window.width - left - 14, window.height - 90

    def history_surface(self, window):
        left, top, width, _ = self.conversation_surface(window)
        return left, top, width, window.y + window.height - 150 - top

    def aliases(self, chat):
        target = self.config['targets'][chat]
        return list(dict.fromkeys([chat, target.get('expected_title', chat),
                                   *target.get('expected_title_aliases', [])]))

    def current_title_matches(self, window, chat):
        image = self.capture_screen('wechat-title')
        left = self.content_left(window) + 5
        crop = self.crop(image, (left, window.y + 32, min(600, window.width - 400), 40),
                         self.runtime_dir / 'wechat-title.png')
        variants = [self.ocr_scaled(crop, scale=4, psm=11)]
        variants.append(self.ocr(self.runtime_dir / 'wechat-title-scaled-ocr.png',
                                 psm=11, language='chi_tra+eng'))
        variants.append(self.ocr(self.runtime_dir / 'wechat-title-scaled-ocr.png',
                                 psm=7, language='chi_sim'))
        from PIL import Image
        with Image.open(crop) as source:
            ink = source.convert('L').point(lambda value: 255 if value < 160 else 0).getbbox()
            if ink:
                raw = source.crop((max(0, ink[0] - 8), 0, min(source.width, ink[2] + 8), source.height))
                raw = raw.resize((raw.width * 2, raw.height * 2))
                raw_path = self.runtime_dir / 'wechat-title-native-ocr.png'
                raw.save(raw_path)
                variants.append(self.ocr(raw_path, psm=7, language='chi_sim+eng'))
        for observed in variants:
            title = observed.strip().splitlines()[0] if observed.strip() else ''
            title = re.sub(r'\s*[（(]\d+[）)]\s*$', '', title)
            if any(title_matches(title, alias) for alias in self.aliases(chat)):
                return True
        return False

    def native_search_category(self, crop):
        labels = ('Most used', 'Contacts', 'Group Chats', '最常使用', '群聊', '联系人')
        # Global OCR thresholding drops the pale category labels when dark
        # thumbnails share the crop. Preserve those labels before retrying.
        from PIL import Image
        thresholded = self.runtime_dir / 'wechat-search-categories.png'
        with Image.open(crop) as source:
            source.convert('L').point(lambda value: 0 if value < 210 else 255).save(thresholded)
        for candidate in (crop, thresholded):
            for label in labels:
                match = self.find_ocr_line(candidate, label, scale=3)
                if match and match.get('similarity') == 1.0:
                    return match
        return None

    def ensure_chat(self, chat, *, operation='text'):
        if chat not in self.target_groups or chat not in self.config['targets']:
            raise RuntimeError('WeChat chat is not allowlisted')
        window = self.find_window()
        if self.current_title_matches(window, chat):
            return window
        sidebar = self.crop(self.capture_screen('wechat-sidebar'),
                            (window.x + 65, window.y + 82, 160, window.height - 160),
                            self.runtime_dir / 'wechat-sidebar.png')
        for alias in self.aliases(chat):
            match = self.find_ocr_line(sidebar, alias, scale=2, native_pixels=True)
            if match and match.get('similarity') == 1.0:
                self.click(window.x + 65 + int(match['center_x']), window.y + 82 + int(match['center_y']))
                time.sleep(.5)
                if self.current_title_matches(window, chat):
                    return window
        # Native search, followed by the exact conversation title guard. Never
        # send based solely on a partial/truncated sidebar name.
        target = self.config['targets'][chat]
        search = target.get('search_name') or target.get('query') or target.get('expected_title') or chat
        self.click(window.x + 133, window.y + 54)
        self.set_clipboard(search)
        self.key('ctrl+a')
        self.key('ctrl+v')
        time.sleep(.8)
        image = self.capture_screen('wechat-search')
        crop = self.crop(image, (window.x + 65, window.y + 82, 380, 450),
                         self.runtime_dir / 'wechat-search-results.png')
        # Never choose an Internet search suggestion with the same query.
        category = self.native_search_category(crop)
        result_left, result_base_top = window.x + 65, window.y + 82
        if not category:
            self.click(window.x + 245, window.y + 38)
            raise RuntimeError('WECHAT_GUI_TITLE_UNVERIFIED: no native contact category; no web search')
        result_top = int(category['center_y']) + 12
        crop = self.crop(image, (result_left, result_base_top + result_top, 320, 100),
                         self.runtime_dir / 'wechat-native-search-result.png')
        match = None
        for alias in [*self.aliases(chat), search]:
            candidate = self.find_ocr_line(crop, alias, scale=3)
            if candidate and candidate.get('similarity') == 1.0:
                match = candidate
                break
        if not match:
            # Search highlights distort OCR. Opening the first native result
            # is navigation only; the full title must still pass before input.
            match = {'center_x': 140, 'center_y': 30}
        self.click(result_left + int(match['center_x']), result_base_top + result_top + int(match['center_y']))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            time.sleep(.3)
            window = self.find_window()
            if self.current_title_matches(window, chat):
                return window
        raise RuntimeError('WECHAT_GUI_TITLE_UNVERIFIED: exact native chat did not open')

    def composer_keys(self, window, *keys):
        # Personal WeChat uses Enter, unlike WeCom's Alt+S.
        return super().composer_keys(window, *('Return' if key.lower() == 'alt+s' else key for key in keys))

    def poll_cycle(self):
        raise RuntimeError('WeChat intake uses the exact local store, not WeCom OCR ingestion')

    def composer_contains_filename(self, screenshot, window, filename, delivery_key):
        crop = self.crop(screenshot, (self.content_left(window) + 10,
                                     window.y + window.height - 165, 600, 130),
                         self.runtime_dir / ('wechat-file-composer-' + delivery_key + '.png'))
        return composed_filename_matches(filename, self.ocr_scaled(crop, scale=4, psm=6))

    def prepare_native_receipt(self, chat):
        sync_once(self.config)
        binding = native_chat_binding(self.config['targets'][chat])
        with closing(sqlite3.connect(STORE)) as conn:
            exists = conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (binding['table'],)).fetchone()
            cursor = conn.execute(f'SELECT COALESCE(MAX(local_id),0) FROM {binding["table"]}').fetchone()[0] if exists else 0
        return {**binding, 'after': {STORE.name: cursor}, 'started_at': int(time.time()) - 2}

    def wait_receipt(self, receipt, *, message='', file=None, timeout=25):
        deadline = time.monotonic() + timeout
        while True:
            sync_once(self.config)
            proof = find_receipt(receipt, message=message, file=file)
            if proof or time.monotonic() >= deadline:
                return proof
            time.sleep(1)

    def send_text_locked(self, chat, text, *, task_id):
        sent = []
        for index, chunk in enumerate(chunk_text(text, 1800)):
            key = short_hash(f'{chat}:{task_id}:{index}:{chunk}')
            if delivery_done(self.state_db, key, chat):
                continue
            prior = get_runtime(self.state_db, 'native-intent:' + key)
            if prior:
                proof = self.wait_receipt(json.loads(prior), message=chunk, timeout=0)
                if not proof:
                    raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: prior text submission requires reconciliation')
            else:
                window = self.ensure_chat(chat)
                if not self.composer_is_empty(window, key):
                    raise RuntimeError('WECHAT_COMPOSE_VERIFY_FAILED: refusing to overwrite an existing draft')
                receipt = self.prepare_native_receipt(chat)
                self.set_clipboard(chunk)
                self.composer_keys(window, 'ctrl+v')
                if not self.composer_text_matches(window, chunk, key):
                    raise RuntimeError('WECHAT_COMPOSE_VERIFY_FAILED: pasted text did not round-trip')
                retain_pending_receipt(pending_receipt_path(self.config['targets'][chat], chunk), receipt)
                set_runtime(self.state_db, 'native-intent:' + key, json.dumps(receipt))
                try:
                    self.composer_keys(window, 'Return')
                    proof = self.wait_receipt(receipt, message=chunk)
                    if not proof:
                        raise RuntimeError('native outgoing row not yet confirmed')
                except Exception as exc:
                    raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: ' + str(exc)) from exc
            remember_delivery(self.state_db, key, chat, chunk)
            record_event(chat_name=chat, action='send', direction='outbound', message=chunk,
                         status='sent', db_path=DEFAULT_DB, metadata={'transport': 'wechat_tiny11', 'receipt': proof})
            screen = self.capture_screen('sent-' + key)
            sent.append({'verified': True, 'receipt': proof, 'sent_evidence': str(screen)})
        return {'ok': True, 'sent_messages': sent, 'sent_files': [], 'errors': []}

    def send_files_locked(self, chat, paths, *, task_id):
        sent = []
        for source in paths:
            path = self.validate_send_file(source)
            key = file_delivery_key(chat, task_id, path)
            if delivery_done(self.state_db, key, chat):
                sent.append(str(path))
                continue
            prior = get_runtime(self.state_db, 'native-intent:' + key)
            if prior:
                proof = self.wait_receipt(json.loads(prior), file=path, timeout=0)
                if not proof:
                    raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: prior file submission requires reconciliation')
            else:
                window = self.ensure_chat(chat, operation='file')
                if not self.composer_is_empty(window, key):
                    raise RuntimeError('WECHAT_COMPOSE_VERIFY_FAILED: refusing to overwrite an existing draft')
                receipt = self.prepare_native_receipt(chat)
                staged, folder = self.stage_send_file(path, key)
                proof = None
                try:
                    self.compose_staged_file_with_picker(window, staged, folder, key)
                    composed = self.capture_screen('file-composed-' + key)
                    if not self.composer_contains_filename(composed, window, path.name, key):
                        raise RuntimeError('WECHAT_COMPOSE_VERIFY_FAILED: file not visible in native composer')
                    set_runtime(self.state_db, 'native-intent:' + key, json.dumps(receipt))
                    record_event(chat_name=chat, action='file_send_intent', direction='outbound', status='sending',
                                 db_path=DEFAULT_DB, metadata={'file_identity': file_transport_identity(path), 'transport': 'wechat_tiny11'})
                    try:
                        self.composer_keys(window, 'Return')
                        proof = self.wait_receipt(receipt, file=path, timeout=45)
                        if not proof:
                            raise RuntimeError('native outgoing file row not yet confirmed')
                    except Exception as exc:
                        raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: ' + str(exc)) from exc
                finally:
                    if proof:
                        self.cleanup_staged_file(staged_file=staged, staging_dir=folder)
            remember_delivery(self.state_db, key, chat, str(path))
            record_event(chat_name=chat, action='file_send', direction='outbound', status='sent',
                         db_path=DEFAULT_DB, metadata={'file_identity': file_transport_identity(path),
                                                       'transport': 'wechat_tiny11', 'receipt': proof})
            sent.append(str(path))
        return {'ok': True, 'sent_messages': [], 'sent_files': sent, 'errors': []}


def find_receipt(receipt, *, message='', file=None, db_path=STORE):
    from wechat_direct_chatops import decode_content

    table = receipt['table']
    if not TABLE_RE.fullmatch(table):
        raise ValueError('Invalid receipt table')
    with closing(sqlite3.connect(db_path)) as conn:
        if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            return None
        rows = conn.execute(f'''SELECT m.local_id,m.server_id,m.local_type,m.message_content,
                                       m.compress_content,m.WCDB_CT_message_content
                                FROM {table} m JOIN Name2Id n ON n.rowid=m.real_sender_id
                                WHERE m.local_id>? AND m.create_time>=? AND n.user_name=?
                                AND m.status IN (2,3) AND CAST(m.server_id AS TEXT) NOT IN ('','0')''',
                            (receipt['after'][db_path.name], receipt['started_at'], receipt['sender'])).fetchall()
    for local_id, server_id, kind, content, compressed, content_type in rows:
        text = decode_content(content, compressed, content_type)
        prefix = receipt['sender'] + ':\n'
        if text.startswith(prefix):
            text = text[len(prefix):]
        matched = int(kind) == 1 and message and normalize_message(text) == normalize_message(message)
        if file and (int(kind) & 0xffffffff) == 49:
            try:
                xml = ET.fromstring(text[text.index('<'):])
                matched = (xml.findtext('.//appmsg/title') == file.name
                           and int(xml.findtext('.//appattach/totallen') or 0) == file.stat().st_size)
            except (ValueError, ET.ParseError):
                matched = False
        if matched:
            return {'verified': True, 'method': 'native_outbound_row', 'local_id': local_id, 'server_id': str(server_id)}
    return None


def send(chat, *, message='', files=(), task_id):
    bridge = Tiny11WeChatBridge()
    if not enabled() or not bridge.config.get('delivery_verified'):
        raise RuntimeError('WECHAT_TINY11_NOT_READY: automatic delivery has not been verified')
    result = bridge.send(chat, text=message, paths=[Path(p) for p in files], task_id=task_id)
    if not result.get('ok'):
        raise RuntimeError('WECHAT_TINY11_SEND_FAILED: ' + json.dumps(result.get('errors', [])))
    return result


def ingest_export(payload, db_path=STORE):
    if payload.get('account_verified') is not True:
        raise ValueError('Account not verified')
    tables = payload.get('tables', [])
    if not all(isinstance(table, str) and TABLE_RE.fullmatch(table) for table in tables):
        raise ValueError('Invalid allowlisted table')
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    inserted = 0
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS Name2Id(user_name TEXT UNIQUE)')
        conn.execute('CREATE TABLE IF NOT EXISTS Tiny11Rows(source TEXT,source_id INTEGER,table_name TEXT,local_id INTEGER,PRIMARY KEY(source,source_id))')
        conn.execute('CREATE TABLE IF NOT EXISTS Tiny11Cursors(source TEXT PRIMARY KEY,local_id INTEGER)')
        for table in tables:
            schema = conn.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()
            if schema and re.search(r'server_id\s+TEXT\s+UNIQUE', schema[0], re.I):
                # Migrate only our private projection, never the client's DB.
                conn.execute(f'ALTER TABLE {table} RENAME TO {table}_old')
                conn.execute(re.sub(r'server_id\s+TEXT\s+UNIQUE', 'server_id TEXT', schema[0], flags=re.I))
                conn.execute(f'INSERT INTO {table} SELECT * FROM {table}_old')
                conn.execute(f'DROP TABLE {table}_old')
            # Native server_id is zero for local/system rows. Identity is the
            # source shard + local ID, not a UNIQUE constraint on server_id.
            conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ('
                         'local_id INTEGER PRIMARY KEY,server_id TEXT,local_type INTEGER,'
                         'real_sender_id INTEGER,create_time INTEGER,status INTEGER,'
                         'message_content BLOB,compress_content BLOB,WCDB_CT_message_content INTEGER)')
        for row in payload['rows']:
            table = row['table']
            if table not in tables or not row['source'].endswith(':' + table):
                raise ValueError('Row outside allowlist')
            previous = conn.execute('SELECT local_id FROM Tiny11Rows WHERE source=? AND source_id=?', (row['source'], row['local_id'])).fetchone()
            conn.execute('INSERT OR IGNORE INTO Name2Id(user_name) VALUES(?)', (row['sender'],))
            sender_id = conn.execute('SELECT rowid FROM Name2Id WHERE user_name=?', (row['sender'],)).fetchone()[0]
            local_id = previous[0] if previous else conn.execute(f'SELECT COALESCE(MAX(local_id),0)+1 FROM {table}').fetchone()[0]
            def decode(value):
                return base64.b64decode(value['base64'], validate=True) if isinstance(value, dict) else value
            conn.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?,?,?,?,?,?,?)',
                         (local_id, row['server_id'], row['local_type'], sender_id,
                          row['create_time'], row['status'], decode(row['message_content']),
                          decode(row['compress_content']), row['WCDB_CT_message_content']))
            if not previous:
                conn.execute('INSERT INTO Tiny11Rows VALUES(?,?,?,?)', (row['source'], row['local_id'], table, local_id))
                inserted += 1
        for source, cursor in payload['high_watermarks'].items():
            conn.execute('INSERT INTO Tiny11Cursors VALUES(?,?) ON CONFLICT(source) DO UPDATE SET local_id=MAX(local_id,excluded.local_id)', (source, cursor))
    db_path.chmod(0o600)
    return inserted


def sync_once(config=None):
    STORE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = STORE.parent / 'sync.lock'
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a+') as lock:
        # Polls and one-shot probes must not share or overwrite export packets.
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _sync_once(config)


def _sync_once(config=None):
    config = config or load_config(CONFIG)
    transport = Tiny11Transport(config)
    cursors = {}
    if STORE.exists():
        with closing(sqlite3.connect(STORE)) as conn:
            cursors = dict(conn.execute('SELECT source,local_id FROM Tiny11Cursors'))
    packet = {'tables': config['message_tables'], 'self_wxid': config['self_wxid'], 'cursors': cursors,
              'binding_titles': {chat: [chat, target.get('expected_title', chat), *target.get('expected_title_aliases', [])]
                                 for chat, target in config['targets'].items()}}
    local = STORE.parent / 'export-request.json'
    write_private_json(local, packet)
    transport.scp_to_guest(local, 'C:/LabCanvas/WeChatStore/request.json')
    result = transport.powershell("& 'C:/LabCanvas/Python312/python.exe' 'C:/LabCanvas/WeChatStore/Export-WeChatStore.py' 'C:/LabCanvas/WeChatStore/request.json' 'C:/LabCanvas/WeChatStore/export.json'; if($LASTEXITCODE -ne 0){throw 'WeChat store export failed'}", timeout=90)
    summary = json.loads(result)
    if not summary.get('ok'):
        raise RuntimeError('WeChat export failed: ' + str(summary.get('error', 'unknown')))
    local_export = STORE.parent / 'export.json'
    subprocess.run(['scp', '-q', '-P', str(transport.ssh_port), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                    f'{transport.user}@{transport.host}:C:/LabCanvas/WeChatStore/export.json', str(local_export)],
                   check=True, capture_output=True, timeout=30)
    local_export.chmod(0o600)
    payload = json.loads(local_export.read_text(encoding='utf-8'))
    # A contact with no local history is still a valid empty intake table.
    inserted = ingest_export({**payload, 'tables': config['message_tables']})
    bindings = {row['table'] for row in payload.get('bindings', [])}
    missing = [chat for chat, target in config['targets'].items()
               if native_chat_binding(target)['table'] not in bindings]
    state = {'ok': True, 'last_sync_epoch': time.time(), 'inserted': inserted,
             'tables': len(payload['tables']), 'expected_tables': len(config['message_tables']),
             'all_tables_available': set(config['message_tables']) <= set(payload['tables']),
             'binding_missing_chats': missing,
             'automatic_delivery_enabled': bool(config.get('enabled') and config.get('delivery_verified'))}
    write_private_json(STORE.parent / 'status.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'sync', 'probe-chat', 'send'])
    parser.add_argument('--request-file', type=Path)
    parser.add_argument('--chat')
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    if args.command == 'send':
        try:
            payload = json.loads(args.request_file.read_text())
            result = send(payload['chat'], message=payload.get('message', ''),
                          files=payload.get('files', []), task_id=payload['task_id'])
        except Exception as exc:
            result = {'ok': False, 'error': str(exc)}
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    if args.command == 'status':
        client = Tiny11WeChatBridge()
        print(json.dumps({'enabled': enabled(), 'helper': client.tiny11.health(), 'store_ready': STORE.is_file()}))
        return
    if args.command == 'probe-chat':
        client = Tiny11WeChatBridge()
        with client.serialized_gui():
            window = client.ensure_chat(args.chat)
            print(json.dumps({'ok': True, 'chat_title_verified': client.current_title_matches(window, args.chat), 'sent': False}))
        return
    while True:
        try:
            result = sync_once()
        except Exception as exc:
            result = {'ok': False, 'error': str(exc)[:500], 'last_failure_epoch': time.time()}
            write_private_json(STORE.parent / 'status.json', result)
        if not args.loop or not result['ok'] or result.get('inserted'):
            print(json.dumps(result), flush=True)
        if not args.loop:
            return 0 if result['ok'] else 1
        time.sleep(2 if result['ok'] else 30)


if __name__ == '__main__':
    raise SystemExit(main())

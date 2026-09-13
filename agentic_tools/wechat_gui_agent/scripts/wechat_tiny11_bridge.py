#!/usr/bin/env python3
"""Personal WeChat transport on the existing KVM, separate from WeCom state."""

from __future__ import annotations

import argparse
import base64
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / 'agentic_tools/wechat_gui_agent/.private'
CONFIG = PRIVATE / 'wechat_tiny11.local.json'
STORE = PRIVATE / 'tiny11/message_999998.db'
sys.path.insert(0, str(ROOT / 'agentic_tools/wecom_agent/scripts'))

from wecom_tiny11_gui_bridge import Tiny11WeComGuiBridge
from wecom_tiny11_transport import Tiny11Transport, load_config
from wecom_gui_bridge import normalize_text, write_private_json

TABLE_RE = re.compile(r'Msg_[0-9a-fA-F]{32}')


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
        crop = self.crop(image, (left, window.y + 32, min(600, window.width - 260), 40),
                         self.runtime_dir / 'wechat-title.png')
        variants = [self.ocr_scaled(crop, scale=4, psm=11)]
        variants.append(self.ocr(self.runtime_dir / 'wechat-title-scaled-ocr.png',
                                 psm=11, language='chi_tra+eng'))
        variants.append(self.ocr(self.runtime_dir / 'wechat-title-scaled-ocr.png',
                                 psm=7, language='chi_sim'))
        for observed in variants:
            title = observed.strip().splitlines()[0] if observed.strip() else ''
            title = re.sub(r'\s*[（(]\d+[）)]\s*$', '', title)
            if any(normalize_text(title) == normalize_text(alias) for alias in self.aliases(chat)):
                return True
        return False

    def ensure_chat(self, chat, *, operation='text'):
        if chat not in self.target_groups or chat not in self.config['targets']:
            raise RuntimeError('WeChat chat is not allowlisted')
        window = self.find_window()
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
        match = None
        for alias in self.aliases(chat):
            candidate = self.find_ocr_line(crop, alias, scale=3)
            if candidate and candidate.get('similarity') == 1.0:
                match = candidate
                break
        if not match:
            self.click(window.x + 245, window.y + 38)
            raise RuntimeError('WECHAT_GUI_TITLE_UNVERIFIED: no exact native search result; no web search')
        self.click(window.x + 65 + int(match['center_x']), window.y + 82 + int(match['center_y']))
        time.sleep(.5)
        window = self.find_window()
        if not self.current_title_matches(window, chat):
            raise RuntimeError('WECHAT_GUI_TITLE_UNVERIFIED: exact native chat did not open')
        return window

    def composer_keys(self, window, *keys):
        # Personal WeChat uses Enter, unlike WeCom's Alt+S.
        return super().composer_keys(window, *('Return' if key.lower() == 'alt+s' else key for key in keys))

    def poll_cycle(self):
        raise RuntimeError('WeChat intake uses the exact local store, not WeCom OCR ingestion')


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
            if conn.execute('SELECT 1 FROM Tiny11Rows WHERE source=? AND source_id=?', (row['source'], row['local_id'])).fetchone():
                continue
            conn.execute('INSERT OR IGNORE INTO Name2Id(user_name) VALUES(?)', (row['sender'],))
            sender_id = conn.execute('SELECT rowid FROM Name2Id WHERE user_name=?', (row['sender'],)).fetchone()[0]
            local_id = conn.execute(f'SELECT COALESCE(MAX(local_id),0)+1 FROM {table}').fetchone()[0]
            def decode(value):
                return base64.b64decode(value['base64'], validate=True) if isinstance(value, dict) else value
            conn.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?,?,?,?)',
                         (local_id, row['server_id'], row['local_type'], sender_id,
                          row['create_time'], row['status'], decode(row['message_content']),
                          decode(row['compress_content']), row['WCDB_CT_message_content']))
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
    packet = {'tables': config['message_tables'], 'self_wxid': config['self_wxid'], 'cursors': cursors}
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
    inserted = ingest_export(payload)
    state = {'ok': True, 'last_sync_epoch': time.time(), 'inserted': inserted,
             'tables': len(payload['tables']), 'expected_tables': len(config['message_tables']),
             'all_tables_available': set(config['message_tables']) <= set(payload['tables']),
             'automatic_delivery_enabled': bool(config.get('enabled') and config.get('delivery_verified'))}
    write_private_json(STORE.parent / 'status.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'sync', 'probe-chat'])
    parser.add_argument('--chat')
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
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
        time.sleep(10 if result['ok'] else 30)


if __name__ == '__main__':
    raise SystemExit(main())

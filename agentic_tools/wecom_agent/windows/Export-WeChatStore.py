"""Export allowlisted native rows using the separately installed read-only reader."""

import base64
from contextlib import redirect_stdout, closing
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from wechat_store_snapshot import open_snapshot


def export(request_path, output_path):
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
    request = json.loads(Path(request_path).read_text(encoding="utf-8-sig"))
    spec = importlib.util.spec_from_file_location("wechat_store_reader", ROOT / "db.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    account_dir = Path(config["db_dir"]).parent
    db = reader.WeChatDB(db_dir=str(account_dir.parent), account=account_dir.name,
                        keys_file=str(ROOT / "reader-keys.private.json"),
                        workdir=str(ROOT / "cache"))
    if db.account != account_dir.name or db.wxid != request["self_wxid"]:
        raise RuntimeError("WeChat account identity mismatch")
    # Windows real_sender_id belongs to the resource DB, not each shard's
    # Name2Id chat index. Mixing those maps silently attributes the wrong author.
    names = {}
    for rel, path, _ in db._db_files:
        if Path(path).name == 'message_resource.db':
            with closing(open_snapshot(db, rel, reader)) as conn:
                names.update(conn.execute('SELECT rowid,user_name FROM SenderName2Id'))
    result = {"account_verified": True, "rows": [], "high_watermarks": {}, "tables": []}
    for rel in db._message_dbs():
        with closing(open_snapshot(db, rel, reader)) as conn:
            conn.row_factory = sqlite3.Row
            conn.text_factory = reader._sqlite_text_factory
            # Some current builds leave SenderName2Id empty and use the shard
            # index instead. Do not mix indexes within a populated schema.
            sender_names = names or dict(conn.execute('SELECT rowid,user_name FROM Name2Id'))
            for table in request["tables"]:
                if not re.fullmatch(r"Msg_[0-9a-fA-F]{32}", table):
                    raise ValueError("Invalid allowlisted table")
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (table,)).fetchone():
                    continue
                if table not in result["tables"]:
                    result["tables"].append(table)
                key = rel.replace('\\', '/') + ':' + table
                cursor = int(request.get("cursors", {}).get(key, 0))
                columns = ('local_id', 'server_id', 'local_type', 'real_sender_id',
                           'create_time', 'status', 'message_content', 'compress_content',
                           'WCDB_CT_message_content')
                rows = conn.execute(f"SELECT {','.join(columns)} FROM {table} WHERE local_id>? ORDER BY local_id LIMIT 500", (cursor,))
                for row in rows:
                    record = dict(row)
                    record['sender'] = sender_names.get(record['real_sender_id'], '')
                    if record['real_sender_id'] == 2:
                        record['sender'] = request['self_wxid']
                    if not record['sender'] and (int(record['local_type']) & 0xffffffff) == 10000:
                        record['sender'] = 'wechat-system'
                    if not record['sender']:
                        raise RuntimeError(f"Missing native sender identity: id={record['real_sender_id']}, type={record['local_type']}")
                    if record['sender'].endswith('@chatroom'):
                        raise RuntimeError('Native sender resolved to a chat rather than a person')
                    record['source'] = key
                    record['table'] = table
                    for name in ('message_content', 'compress_content'):
                        if isinstance(record[name], bytes):
                            record[name] = {'base64': base64.b64encode(record[name]).decode('ascii')}
                    result['rows'].append(record)
                    cursor = int(row['local_id'])
                result['high_watermarks'][key] = cursor
    target = Path(output_path)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(target)
    return {"ok": True, "rows": len(result['rows']), "tables": len(result['tables'])}


if __name__ == '__main__':
    with (ROOT / 'export.private.log').open('w', encoding='utf-8') as log, redirect_stdout(log):
        try:
            result = export(sys.argv[1], sys.argv[2])
        except Exception as exc:
            import traceback
            traceback.print_exc(file=log)
            result = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)[:500]}
    print(json.dumps(result))

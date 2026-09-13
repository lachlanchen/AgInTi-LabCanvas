"""Run the existing read-only Windows key reader in a private guest workspace."""

from contextlib import redirect_stdout, closing
import importlib.util
import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from wechat_store_snapshot import open_snapshot
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
if not Path(config["db_dir"]).is_dir():
    raise SystemExit("Configured WeChat store does not exist")

# Import only the reviewed read-only database module, not the upstream GUI driver.
spec = importlib.util.spec_from_file_location("wechat_store_reader", ROOT / "db.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
account_dir = Path(config["db_dir"]).parent
with (ROOT / "store-probe.private.log").open("w", encoding="utf-8") as log:
    with redirect_stdout(log):
        db = reader.WeChatDB(db_dir=str(account_dir.parent), account=account_dir.name,
                            keys_file=str(ROOT / "reader-keys.private.json"),
                            workdir=str(ROOT / "cache"))
        if db.account != account_dir.name:
            raise RuntimeError("Account identity changed; refusing another store")
        sessions = db.get_sessions()
        checks = {}
        for rel, path, _ in db._db_files:
            if Path(path).name not in ('message_0.db', 'message_resource.db'):
                continue
            with closing(open_snapshot(db, rel, reader)) as conn:
                checks[rel] = {'integrity': conn.execute('PRAGMA quick_check').fetchall(), 'tables': {}}
                for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    if name in ('Name2Id', 'SenderName2Id'):
                        checks[rel]['tables'][name] = {'schema': conn.execute(f'PRAGMA table_info({name})').fetchall(),
                                                     'count': conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]}
print(json.dumps({"ok": bool(sessions), "database_keys": len(db._keys),
                  "sessions": len(sessions), "base_checks": checks}))

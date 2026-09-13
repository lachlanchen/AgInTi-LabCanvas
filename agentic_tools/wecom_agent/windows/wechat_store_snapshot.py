"""Validated private SQLCipher snapshots; never modify the live WeChat store."""

from pathlib import Path
from contextlib import closing
import json
import shutil
import sqlite3
import struct
import time


def cached_reader(reader, *, db_dir, account, keys_file, workdir):
    """Use one account's provisioned keys, never runtime extraction/fallback."""
    class CachedReader(reader.WeChatDB):
        def _load_or_extract_keys(self, master_key=None):
            try:
                cached = json.loads(Path(self.keys_file).read_text(encoding='utf-8-sig'))
            except (OSError, ValueError):
                raise RuntimeError('WeChat key cache unavailable; explicit provisioning required') from None
            if not isinstance(cached, dict):
                raise RuntimeError('Invalid WeChat key cache; explicit provisioning required')
            self._keys = {}
            for rel, _path, _size in self._db_files:
                try:
                    key = bytes.fromhex(cached.get(rel, ''))
                except (ValueError, TypeError):
                    continue
                if len(key) != 32:
                    continue
                self._keys[rel] = key
                if not self._key_works(rel):
                    del self._keys[rel]
            self.unkeyed = [rel for rel, _, _ in self._db_files if rel not in self._keys]
            if not self._keys:
                raise RuntimeError('No valid cached WeChat keys; explicit provisioning required')

    return CachedReader(db_dir=db_dir, account=account, keys_file=keys_file, workdir=workdir)


def checksum(data, state=(0, 0), endian='<'):
    if len(data) % 8:
        raise ValueError('WAL checksum input must be a multiple of eight bytes')
    s0, s1 = state
    for x0, x1 in struct.iter_unpack(endian + 'II', data):
        s0 = (s0 + x0 + s1) & 0xffffffff
        s1 = (s1 + x1 + s0) & 0xffffffff
    return s0, s1


def committed_frames(wal_path, page_size=4096):
    """SQLite WAL salt/checksum chain, stopping at the last valid commit."""
    frames = []
    committed_count = 0
    database_pages = 0
    with Path(wal_path).open('rb') as stream:
        header = stream.read(32)
        if not header:
            return [], 0
        if len(header) != 32:
            raise ValueError('Incomplete WAL header')
        magic, version, size = struct.unpack('>III', header[:12])
        if magic not in (0x377f0682, 0x377f0683) or version != 3007000 or size != page_size:
            raise ValueError('Unsupported WAL header')
        endian = '<' if magic == 0x377f0682 else '>'
        state = checksum(header[:24], endian=endian)
        if state != struct.unpack('>II', header[24:32]):
            raise ValueError('Invalid WAL header checksum')
        while True:
            offset = stream.tell()
            frame = stream.read(24)
            page = stream.read(page_size)
            if len(frame) != 24 or len(page) != page_size or frame[8:16] != header[16:24]:
                break
            page_number, commit_pages = struct.unpack('>II', frame[:8])
            if not 0 < page_number <= 1000000 or commit_pages > 1000000:
                break
            expected = checksum(frame[:8] + page, state, endian)
            if expected != struct.unpack('>II', frame[16:24]):
                break
            state = expected
            frames.append((page_number, offset + 24))
            if commit_pages:
                committed_count = len(frames)
                database_pages = commit_pages
    return frames[:committed_count], database_pages


def source_stamp(path):
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return None


def open_snapshot(db, rel, reader):
    if rel not in db._keys:
        raise RuntimeError('Required WeChat key is not cached; explicit provisioning required')
    source = Path(db._db_path(rel))
    wal = Path(str(source) + '-wal')
    root = Path(db.workdir) / 'validated'
    root.mkdir(exist_ok=True)
    stem = rel.replace('\\', '_').replace('/', '_')
    encrypted = root / (stem + '.encrypted')
    wal_copy = root / (stem + '.wal-copy')
    output = root / stem
    stamp_path = root / (stem + '.stamp')
    current = repr((source_stamp(source), source_stamp(wal)))
    if output.exists() and stamp_path.exists() and stamp_path.read_text() == current:
        return sqlite3.connect('file:' + str(output) + '?mode=ro', uri=True)
    for _ in range(3):
        before = (source_stamp(source), source_stamp(wal))
        shutil.copyfile(source, encrypted)
        if before[1]:
            shutil.copyfile(wal, wal_copy)
        if before != (source_stamp(source), source_stamp(wal)):
            time.sleep(.1)
            continue
        temp = output.with_suffix('.tmp')
        db._decrypt_file(str(encrypted), str(temp), db._keys[rel])
        if before[1]:
            frames, pages = committed_frames(wal_copy)
            with wal_copy.open('rb') as incoming, temp.open('r+b') as target:
                for page_number, offset in frames:
                    incoming.seek(offset)
                    plain = reader._decrypt_page(db._keys[rel], incoming.read(4096), page_number)
                    target.seek((page_number - 1) * 4096)
                    target.write(plain)
                if pages:
                    target.truncate(pages * 4096)
        with closing(sqlite3.connect(temp)) as check:
            valid = check.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        if not valid:
            raise RuntimeError('WeChat snapshot failed SQLite integrity validation')
        temp.replace(output)
        stamp_path.write_text(repr(before))
        encrypted.unlink(missing_ok=True)
        wal_copy.unlink(missing_ok=True)
        return sqlite3.connect('file:' + str(output) + '?mode=ro', uri=True)
    raise RuntimeError('WeChat store changed during snapshot; retry later')

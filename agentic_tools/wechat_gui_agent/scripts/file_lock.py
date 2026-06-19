"""Small cross-platform exclusive file lock helper."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, TextIO

if hasattr(__import__("os"), "fork"):
    import fcntl  # type: ignore[import-not-found]
else:
    import msvcrt


@contextmanager
def exclusive_lock(handle: TextIO) -> Iterator[None]:
    if "fcntl" in globals():
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
        return

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    try:
        yield
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

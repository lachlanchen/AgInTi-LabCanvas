"""Small cross-platform file locking helper for WeChat automation scripts."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, TextIO

try:  # Unix, Linux, WSL.
    import fcntl as _fcntl
except ModuleNotFoundError:  # Windows Python.
    _fcntl = None
    import msvcrt


LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(handle: TextIO, flags: int) -> None:
    """Compatibility subset of fcntl.flock for exclusive one-byte locks."""
    if _fcntl is not None:
        _fcntl.flock(handle, flags)
        return

    handle.seek(0)
    if flags & LOCK_UN:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    mode = msvcrt.LK_NBLCK if flags & LOCK_NB else msvcrt.LK_LOCK
    try:
        msvcrt.locking(handle.fileno(), mode, 1)
    except OSError as exc:
        if flags & LOCK_NB:
            raise BlockingIOError(str(exc)) from exc
        raise


class _FcntlCompat:
    LOCK_EX = LOCK_EX
    LOCK_NB = LOCK_NB
    LOCK_UN = LOCK_UN

    @staticmethod
    def flock(handle: TextIO, flags: int) -> None:
        flock(handle, flags)


fcntl_compat = _fcntl if _fcntl is not None else _FcntlCompat()


@contextmanager
def exclusive_lock(handle: TextIO, *, blocking: bool = True) -> Iterator[None]:
    flags = LOCK_EX if blocking else LOCK_EX | LOCK_NB
    flock(handle, flags)
    try:
        yield
    finally:
        flock(handle, LOCK_UN)

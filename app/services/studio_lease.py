"""OS-backed ownership, automatically released if a worker process exits."""
import os
from pathlib import Path


def acquire(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    try:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError as exc:
        handle.close()
        if exc.errno in (11, 13, 35, 36):
            raise ValueError('Esta produção já está em execução ou na fila.') from exc
        raise


def release(handle):
    # Closing releases the OS lock on both supported platforms.
    handle.close()


def is_locked(path):
    try:
        handle = acquire(path)
    except ValueError:
        return True
    release(handle)
    return False

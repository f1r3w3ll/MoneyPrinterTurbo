"""Atomic JSON writes shared by productions and their artifact manifests."""
import json
import os
import tempfile
import time
from pathlib import Path


def write_json(filename, data):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    # A fixed ``production.tmp`` collides when a stale Streamlit process and
    # the current process both update the same production. Keep the temporary
    # file in the target directory so replacement remains atomic, but give each
    # write a private name.
    descriptor, temporary_name = tempfile.mkstemp(
        dir=filename.parent,
        prefix=f'{filename.stem}.',
        suffix='.tmp',
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(4):
            try:
                os.replace(temporary, filename)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.05 * (2 ** attempt))
    finally:
        if temporary.exists():
            temporary.unlink()

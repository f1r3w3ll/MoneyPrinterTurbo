"""Atomic JSON writes shared by productions and their artifact manifests."""
import json
import os
from pathlib import Path


def write_json(filename, data):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_suffix('.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, filename)
    finally:
        if temporary.exists():
            temporary.unlink()

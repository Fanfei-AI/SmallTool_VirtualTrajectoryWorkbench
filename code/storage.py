"""Small JSON files with Windows sharing-error handling."""
import json
import os
import tempfile
import time
from pathlib import Path


def save_json(path, value):
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    fd, name = tempfile.mkstemp(prefix=path.stem + '-', suffix='.tmp', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(payload)
        for attempt in range(4):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt < 3:
                    time.sleep(0.01)
        # Some Windows ACLs permit writing but deny replacing an existing file.
        # Readers retry incomplete JSON during this short fallback write.
        with path.open('w', encoding='utf-8') as stream:
            stream.write(payload)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def read_json(path, default):
    for attempt in range(4):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            if attempt < 3:
                time.sleep(0.01)
    return default

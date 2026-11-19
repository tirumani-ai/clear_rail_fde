"""Fingerprints and a disk cache for model answers.

Each answer is its own small file, written to a temporary name and then renamed into place. A rename is
all-or-nothing, so two runs at once, or a crash mid-write, can never leave a half answer or lose another's.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

CACHE = Path(os.environ.get("CLEARRAIL_CACHE", "data/cache"))  # git-ignored; delete it to start from nothing


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cached(group: str, key: str, make):
    """The saved answer for `key`, or make() it once and save it. Returns (value, was_saved)."""
    path = CACHE / group / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text()), True
        except json.JSONDecodeError:
            pass  # unreadable: make it again
    value = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as out:
        json.dump(value, out, ensure_ascii=False)
    os.replace(tmp, path)
    return value, False

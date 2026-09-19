"""Test-build hooks the start consults (DEV-NOTES §12.2).

``inject gate-failure`` has to reach the *next* start, which runs in another
process. The marker lives **outside** the store — never in it, where it would
be entity state — keyed by the store's real path, and a start consumes it.
A production build has no ``fsp_testing``, so nothing here exists there; and
the only thing a marker can do is make a gate fail.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

TOKENS = ("passive", "crash", "structural", "binding", "authorization", "index")


def _marker(root: str) -> str:
    key = hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()
    return os.path.join(tempfile.gettempdir(), "fsp-testing", key + ".json")


def add_gate_failure(root: str, token: str) -> None:
    if token not in TOKENS:
        raise ValueError("unknown gate token %r" % token)
    path = _marker(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tokens = set(_read(path))
    tokens.add(token)
    with open(path, "w") as f:
        json.dump(sorted(tokens), f)


def consume_gate_failures(root: str):
    path = _marker(root)
    tokens = _read(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return tokens


def _read(path):
    try:
        with open(path) as f:
            return [t for t in json.load(f) if t in TOKENS]
    except (FileNotFoundError, ValueError):
        return []

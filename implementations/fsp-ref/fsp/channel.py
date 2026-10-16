# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The Operator Channel's hold in a main session: the asker the UI registers
and the extensions the Operator's answers leave, in the process only (D99,
D66). It writes nothing."""

from __future__ import annotations

import threading

from . import sil

ANSWERS = ("once", "chat", "allowlist", "deny")

_LOCK = threading.Lock()
_ASKER = None
_ONCE = set()
_CHAT = set()


class Held(Exception):
    """An act stopped at a hold. ``hold`` is ``{id, op, target, resolved,
    asker, kind, check, rule, key}`` (D99)."""

    def __init__(self, hold):
        super().__init__(hold.get("resolved"))
        self.hold = hold


def register(asker):
    """Register the function that answers a hold: it takes the hold and
    returns one of ``ANSWERS``."""
    global _ASKER
    with _LOCK:
        _ASKER = asker


def unregister():
    global _ASKER
    with _LOCK:
        _ASKER = None


def can_ask():
    """Whether a hold can be put to the Operator: an asker is registered and
    the act runs in a cycle's dispatch (D99)."""
    with _LOCK:
        registered = _ASKER is not None
    return registered and sil.current_cycle() is not None


def allowed(key) -> bool:
    """Whether an extension lets ``key`` pass: the chat's, or the once set's
    (D99)."""
    with _LOCK:
        return key in _CHAT or key in _ONCE


def allow_once(key):
    with _LOCK:
        _ONCE.add(key)


def allow_chat(key):
    with _LOCK:
        _CHAT.add(key)


def end_intent():
    """End the once extensions of the intent being dispatched (D99)."""
    with _LOCK:
        _ONCE.clear()


def clear():
    """End every extension (D99)."""
    with _LOCK:
        _ONCE.clear()
        _CHAT.clear()


def ask(hold) -> str:
    """The registered asker's answer to ``hold``, one of ``ANSWERS``."""
    with _LOCK:
        asker = _ASKER
    if asker is None:
        raise RuntimeError("no asker is registered")
    answer = asker(hold)
    if answer not in ANSWERS:
        raise ValueError("unknown answer %r" % (answer,))
    return answer

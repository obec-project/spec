# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The implementation's clock. Timestamps are for humans and audit; nothing
verified depends on one (they vary, so they stay out of outcomes, ADAPTER §2.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime = None) -> str:
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def grant_now(root: str) -> datetime:
    """The clock by which standing grants are judged (D59).

    In a test build this incorporates the store's test clock offset outside
    the store. Without fsp_testing, it is now().
    """
    try:
        from fsp_testing import hooks

        offset = hooks.clock_offset(root)
    except ImportError:
        offset = 0
    if not offset:
        return now()
    return now() + timedelta(seconds=offset)

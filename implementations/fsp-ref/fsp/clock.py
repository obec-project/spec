# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The implementation's clock. Timestamps are for humans and audit; nothing
verified depends on one (they vary, so they stay out of outcomes, ADAPTER §2.3)."""

from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime = None) -> str:
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")

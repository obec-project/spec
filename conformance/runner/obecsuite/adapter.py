# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Invocation of an implementation's conformance adapter.

The contract is in ../../ADAPTER.md: one executable, subcommands, JSON on
stdout, and three meaningful exit codes.
"""

import json
import subprocess
from typing import Any

from .result import StepUnestablished


class AdapterError(Exception):
    pass


class Result:
    """One adapter result object."""

    def __init__(self, raw: dict, argv: list):
        self.raw = raw
        self.argv = argv

    @property
    def outcome(self) -> str:
        return self.raw.get("outcome", "")

    @property
    def refusal(self) -> dict:
        return self.raw.get("refusal") or {}

    @property
    def log_records(self) -> list:
        return self.raw.get("log_records") or []

    @property
    def detail(self) -> dict:
        return self.raw.get("detail") or {}

    def __getitem__(self, key: str) -> Any:
        # Result data lives in `detail` (ADAPTER.md §2.2). Reading anywhere
        # else would let an adapter pass by accident of placement.
        return self.detail.get(key)

    def __repr__(self) -> str:
        return f"<Result {' '.join(self.argv[1:])} -> {self.outcome or '?'}>"


class Adapter:
    def __init__(self, executable: str, timeout: int = 60):
        self.executable = executable
        self.timeout = timeout
        self.calls: list = []

    def call(self, cls: str, command: str, **flags) -> Result:
        """Invoke `<exe> <cls> <command> --flag value ...`.

        A flag whose value is True becomes a bare `--flag`; False or None is
        omitted. Underscores in names become hyphens.
        """
        argv = [self.executable, cls, command]
        for name, value in flags.items():
            if value is None or value is False:
                continue
            argv.append("--" + name.replace("_", "-"))
            if value is not True:
                argv.append(str(value))

        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            raise AdapterError(f"timed out after {self.timeout}s: {' '.join(argv)}")
        except FileNotFoundError:
            raise AdapterError(f"adapter not found: {self.executable}")

        self.calls.append(" ".join(argv))

        if proc.returncode == 2:
            raise StepUnestablished(f"not implemented: {cls} {command}")
        if proc.returncode not in (0, 1):
            raise AdapterError(
                f"exit {proc.returncode}: {' '.join(argv)}\n{proc.stderr.strip()}"
            )

        text = proc.stdout.strip()
        if not text:
            raise AdapterError(f"no JSON on stdout: {' '.join(argv)}")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"unparseable stdout: {' '.join(argv)}: {exc}")
        if not isinstance(raw, dict):
            raise AdapterError(f"stdout is not a JSON object: {' '.join(argv)}")

        # Exit 1 means the command could not be attempted; the result object
        # carries why. This is not an outcome about the implementation.
        if proc.returncode == 1:
            raw.setdefault("outcome", "aborted")

        return Result(raw, argv)

    def drain_calls(self) -> list:
        calls, self.calls = self.calls, []
        return calls

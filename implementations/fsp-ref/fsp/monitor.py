# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""Monitoring a skill: a picture of the store under the lock before the launch
and after the reaping, compared class by class (D2, D73)."""

from __future__ import annotations

import json
import os

from . import chain, lifecycle, sil
from .digest import sha256, sha256_file
from .store import TEMP_NAME, datum_of
from .verify import Finding, Report, _unclassified, sweep_log, verify

TAIL = 4096  # the bytes at the end of an append-only file a picture hashes (D73)
# Data a picture hashes whole: any change to them is a structural divergence.
FIXED = (
    "store-marker",
    "head",
    "structural-content",
    "integrity-chain",
    "integrity-documents",
)


def picture(store) -> dict:
    """The hashes of the store's data, by class, and the position of the last
    record of the log (D73)."""
    fixed, append, replace = {}, {}, {}
    for dirpath, dirnames, filenames in os.walk(store.root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, store.root).replace(os.sep, "/")
        for name in sorted(filenames):
            rel = name if rel_dir == "." else rel_dir + "/" + name
            if TEMP_NAME.match(name):
                continue
            d = datum_of(rel)
            if d is None or d.form == "lock" or rel == sil.LOG:
                continue
            if d.name in FIXED:
                fixed[rel] = sha256_file(store.path(rel))
            elif d.form == "append":
                size = os.path.getsize(store.path(rel))
                start = max(0, size - TAIL)
                tail = store.read_range(rel, start, size - start)
                append[rel] = [size, start, sha256(tail)]
            else:
                replace[rel] = sha256_file(store.path(rel))
    return {
        "head": fixed.get(chain.HEAD),
        "fixed": fixed,
        "append": append,
        "replace": replace,
        "log": _log_picture(store),
    }


def _log_picture(store) -> dict:
    size = os.path.getsize(store.path(sil.LOG)) if store.exists(sil.LOG) else 0
    position = None
    line = store.read_last_line(sil.LOG)
    if (
        line is not None
        and size > 0
        and store.read_range(sil.LOG, size - 1, 1) == b"\n"
    ):
        try:
            rec = json.loads(line.decode("utf-8"))
        except ValueError:
            rec = None
        if isinstance(rec, dict) and isinstance(rec.get("id"), str):
            position = {
                "id": rec["id"],
                "offset": size - len(line) - 1,
                "sha256": sha256(line),
            }
    return {"size": size, "position": position}


def compare(store, before) -> list:
    """The Findings for every divergence between ``before`` and the store now.
    An append-only or replaced datum may change only with a record in the log
    written after the first picture (D73)."""
    after = picture(store)
    grew = after["log"]["size"] > before["log"]["size"]
    findings = []
    _compare_log(store, before["log"], after["log"], findings)
    _compare_structural(store, before, after, findings)
    _compare_append(store, before, after, grew, findings)
    _compare_replace(before, after, grew, findings)
    report = Report()
    _unclassified(store, report)
    findings.extend(report.findings)
    return findings


def _found(rel, cls, problem):
    return Finding("skill-monitor", rel, "exec", {"class": cls, "problem": problem})


def _compare_log(store, before, after, findings):
    if after["size"] < before["size"]:
        findings.append(_found(sil.LOG, "log", "truncated"))
    elif before["position"] is not None or after["size"] > 0:
        pos = before["position"]
        start = pos["offset"] if pos is not None else 0
        finding, _, reset = sweep_log(store, pos, max(1, after["size"] - start))
        if reset is not None:
            findings.append(_found(sil.LOG, "log", "rewritten"))
        if finding is not None:
            findings.append(finding)


def _compare_structural(store, before, after, findings):
    if after["head"] != before["head"]:
        findings.extend(verify(store.root).findings)
        return
    for rel in sorted(set(before["fixed"]) | set(after["fixed"])):
        old = before["fixed"].get(rel)
        new = after["fixed"].get(rel)
        if old == new:
            continue
        if old is None:
            problem = "added"
        elif new is None:
            problem = "removed"
        else:
            problem = "changed"
        findings.append(_found(rel, "structural", problem))


def _compare_append(store, before, after, grew, findings):
    for rel in sorted(before["append"]):
        size, start, digest = before["append"][rel]
        if rel not in after["append"]:
            problem = "removed"
        elif after["append"][rel][0] < size:
            problem = "truncated"
        elif sha256(store.read_range(rel, start, size - start)) != digest:
            problem = "rewritten"
        elif after["append"][rel][0] > size and not grew:
            problem = "grew-without-record"
        else:
            continue
        findings.append(_found(rel, "append", problem))
    for rel in sorted(set(after["append"]) - set(before["append"])):
        if not grew:
            findings.append(_found(rel, "append", "added-without-record"))


def _compare_replace(before, after, grew, findings):
    for rel in sorted(set(before["replace"]) | set(after["replace"])):
        old = before["replace"].get(rel)
        new = after["replace"].get(rel)
        if old == new:
            continue
        if rel == lifecycle.CREDENTIAL and new is None:
            continue
        if not grew:
            findings.append(_found(rel, "replace", "changed-without-record"))

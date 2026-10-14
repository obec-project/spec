# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""The configuration surface (Profile Appendix A, ``describe config``).

Every setting here is a runtime setting (D33): the Operator's, per host,
bounded by a fixed range. None of them can skip, reorder or soften a start
gate — there is no such setting to add (OC-010).
"""

from __future__ import annotations

from .store import Store

OPERATIONAL = "integrity/operational.json"


class Setting:
    __slots__ = ("name", "default", "range", "governs")

    def __init__(self, name, default, range_, governs):
        self.name = name
        self.default = default
        self.range = range_
        self.governs = governs

    def as_dict(self):
        return {
            "name": self.name,
            "default": self.default,
            "range": list(self.range),
            "governs": self.governs,
        }


SETTINGS = (
    Setting(
        "n_boot",
        3,
        (1, 10),
        "consecutive crash recoveries before the passive signal is written and "
        "the entity halts (OP-018(b))",
    ),
    Setting(
        "n_channel",
        3,
        (1, 10),
        "live delivery attempts to the Operator before the passive signal is "
        "written (OP-008(b))",
    ),
    Setting(
        "pending_cap",
        10,
        (1, 100),
        "evolution proposals pending at once, approved or not, past which a "
        "new proposal is refused (D52)",
    ),
    Setting(
        "vital_interval_s",
        60,
        (10, 3600),
        "seconds after which the next act of the entity runs a Vital Check "
        "first (OP-003(a), D65)",
    ),
    Setting(
        "vital_activity_n",
        20,
        (1, 1000),
        "acts of the entity after which the next one runs a Vital Check first "
        "(OP-003(a), D65)",
    ),
    Setting(
        "n_corrections",
        1,
        (1, 2),
        "corrections the owner of a finding may attempt before it escalates to "
        "Critical (D40)",
    ),
    Setting(
        "http_timeout_s",
        30,
        (1, 300),
        "seconds a fetch may take in all, its redirects included; reaching them "
        "is the result timeout (D75)",
    ),
    Setting(
        "pointer_map_limit",
        20,
        (0, 200),
        "records the working set of a Closure Payload may name, the Resumption "
        "Record's pointer map (OP-009(e), D84)",
    ),
    Setting(
        "model_timeout_s",
        120,
        (5, 900),
        "seconds one call to the model may take before it fails (OC-006, D87)",
    ),
)

_BY_NAME = {s.name: s for s in SETTINGS}


def value(store: Store, name: str):
    """The setting in force: the Operator's value when present and in range,
    the default otherwise."""
    s = _BY_NAME[name]
    try:
        chosen = store.read_json(OPERATIONAL).get(name)
    except (FileNotFoundError, ValueError, AttributeError):
        chosen = None
    lo, hi = s.range
    if isinstance(chosen, int) and not isinstance(chosen, bool) and lo <= chosen <= hi:
        return chosen
    return s.default

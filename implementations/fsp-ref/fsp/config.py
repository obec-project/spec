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
        "pulse_interval_s",
        600,
        (60, 86400),
        "how long a session stays live without activity: a credential with no "
        "lock holder, no residue and an older PULSE is a crash, not a live "
        "session (D25, D47; ADAPTER.md 2.5)",
    ),
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

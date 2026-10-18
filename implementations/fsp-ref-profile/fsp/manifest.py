# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""A skill's manifest and digest (D51, D16, DESIGN §5)."""

from __future__ import annotations

import re

from .digest import canonical, sha256, valid_relpath

PLACEHOLDERS = ("skill", "workspace", "target")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
TIMEOUT_RANGE = (1, 600)
ARG_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}\Z")
ARG_KEYS = {
    "string": {"type", "max_length"},
    "integer": {"type", "min", "max"},
    "boolean": {"type"},
    "choice": {"type", "values"},
    "path": {"type"},
}
STRING_MAX = 4096


def _has_placeholder(text: str) -> bool:
    return _PLACEHOLDER.search(text) is not None


def _has_control(text: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_marked_path(value) -> bool:
    """Whether ``value`` is a marked path, ``{"path": <str>}``: the only form in
    which an invocation passes a path to a skill (D71)."""
    return (
        isinstance(value, dict)
        and set(value) == {"path"}
        and isinstance(value["path"], str)
    )


def _schema_problems(args) -> list[str]:
    """The rules of a skill's ``args`` schema (D71): each name, each type, the
    keys its type allows and the values those keys take."""
    if not isinstance(args, dict):
        return ["args is not an object"]
    found = []
    for name in sorted(args, key=str):
        spec = args[name]
        if not isinstance(name, str) or not ARG_NAME.match(name):
            found.append("args names the invalid argument %r" % (name,))
        if not isinstance(spec, dict) or not (
            isinstance(spec.get("type"), str) and spec["type"] in ARG_KEYS
        ):
            found.append("argument %r has no valid type" % (name,))
            continue
        kind = spec["type"]
        for key in sorted(set(spec) - ARG_KEYS[kind], key=str):
            found.append("argument %r has the unknown key %r" % (name, key))
        if kind == "string" and "max_length" in spec:
            limit = spec["max_length"]
            if not _is_int(limit) or not 1 <= limit <= STRING_MAX:
                found.append("argument %r has an invalid max_length" % name)
        if kind == "integer":
            for key in ("min", "max"):
                if key in spec and not _is_int(spec[key]):
                    found.append(
                        "argument %r has a %s that is not an integer" % (name, key)
                    )
            if (
                _is_int(spec.get("min"))
                and _is_int(spec.get("max"))
                and spec["min"] > spec["max"]
            ):
                found.append("argument %r has min above max" % name)
        if kind == "choice":
            values = spec.get("values")
            if not isinstance(values, list) or not values:
                found.append("argument %r has no valid values" % name)
            elif not all(isinstance(v, str) for v in values):
                found.append("argument %r has a value that is not a string" % name)
            else:
                if len(set(values)) != len(values):
                    found.append("argument %r repeats a value" % name)
                if any(_has_control(v) for v in values):
                    found.append(
                        "argument %r has a value with a control character" % name
                    )
    return found


def _value_problems(name: str, spec: dict, value) -> list[str]:
    """The problems of one invoked value against its declared type (D71)."""
    kind = spec["type"]
    if kind == "path":
        if is_marked_path(value):
            return []
        return ["argument %r is not a marked path" % name]
    if is_marked_path(value):
        return ["%r is a path, not a %s" % (name, kind)]
    if kind == "string":
        if not isinstance(value, str):
            return ["argument %r is not a string" % name]
        if value.startswith("-"):
            return ["argument %r begins with '-'" % name]
        if _has_control(value):
            return ["argument %r has a control character" % name]
        limit = spec.get("max_length", STRING_MAX)
        if len(value) > limit:
            return ["argument %r is longer than %d characters" % (name, limit)]
        return []
    if kind == "integer":
        if not _is_int(value):
            return ["argument %r is not an integer" % name]
        found = []
        if "min" in spec and value < spec["min"]:
            found.append("argument %r is below its minimum %d" % (name, spec["min"]))
        if "max" in spec and value > spec["max"]:
            found.append("argument %r is above its maximum %d" % (name, spec["max"]))
        return found
    if kind == "boolean":
        if isinstance(value, bool):
            return []
        return ["argument %r is not a boolean" % name]
    if not isinstance(value, str) or value not in spec["values"]:
        return ["argument %r is not one of its values" % name]
    return []


def invocation_problems(schema, args) -> list[str]:
    """The problems of an invocation's ``args`` against the valid ``schema``:
    exactly the declared names, each with a value of its type (D71). ``None``
    stands for no arguments."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return ["the arguments are not an object"]
    found = []
    for name in sorted(schema):
        if name not in args:
            found.append("missing argument %r" % name)
    for name in sorted(args, key=str):
        if name not in schema:
            found.append("unknown argument %r" % name)
    for name in sorted(schema):
        if name in args:
            found.extend(_value_problems(name, schema[name], args[name]))
    return found


def problems(manifest, name: str) -> list[str]:
    """The rules of DESIGN §5 that ``manifest`` breaks for the skill ``name``.
    An empty list means the manifest is valid."""
    if not isinstance(manifest, dict):
        return ["the manifest is not an object"]
    found = []
    if manifest.get("name") != name:
        found.append("it names %r, not %r" % (manifest.get("name"), name))
    if not isinstance(manifest.get("description"), str):
        found.append("description is not a string")
    argv = manifest.get("argv")
    argv_ok = (
        isinstance(argv, list)
        and len(argv) > 0
        and all(isinstance(a, str) for a in argv)
    )
    schema = manifest.get("args")
    allowed = set(PLACEHOLDERS)
    if isinstance(schema, dict):
        allowed.update("args." + k for k in schema if isinstance(k, str))
    if not argv_ok:
        found.append("argv is not a non-empty list of strings")
    else:
        head = argv[0]
        if not head or "/" in head or _has_placeholder(head):
            found.append("argv[0] is not a command name")
        for a in argv:
            for m in _PLACEHOLDER.finditer(a):
                if m.group(1) not in allowed:
                    found.append("argv names the unknown placeholder %r" % m.group(1))
    timeout = manifest.get("timeout_s")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not TIMEOUT_RANGE[0] <= timeout <= TIMEOUT_RANGE[1]
    ):
        found.append("timeout_s is not an integer from 1 to 600")
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not all(
        isinstance(t, str) and valid_relpath(t) for t in targets
    ):
        found.append("targets is not a list of paths relative to the workspace")
    if not isinstance(manifest.get("irreversible"), bool):
        found.append("irreversible is not a boolean")
    if "args" in manifest:
        found.extend(_schema_problems(manifest["args"]))
    return found


def fill(text: str, values) -> str:
    """Fill every placeholder of ``text`` from ``values`` in one pass, so a value
    is never read as a placeholder (D71)."""
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def skill_digest(files) -> str:
    """The digest of a skill: the hash of the canonical list of its
    ``{path, sha256, exec}`` entries in the Skill Index, sorted by path. An
    allowlist rule fixes this digest (D16)."""
    return sha256(canonical(sorted(files, key=lambda f: f["path"])))

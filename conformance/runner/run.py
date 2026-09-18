#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
"""OBEC conformance suite.

    python3 run.py --adapter ./obec-adapter

Drives an implementation's conformance adapter through the ten tests and emits
a claim. Standard library only, so that being testable costs an implementer no
toolchain they do not already have.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obecsuite import SUITE_VERSION, TARGETS                    # noqa: E402
from obecsuite.adapter import Adapter                            # noqa: E402
from obecsuite.claim import conformant, exit_code, write         # noqa: E402
from obecsuite.harness import Context, Runner                    # noqa: E402
from obecsuite.result import Outcome                             # noqa: E402
from obecsuite.store import Stores                               # noqa: E402
from obecsuite.tests import TESTS                                # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--adapter", required=True,
                   help="the implementation's conformance adapter executable")
    p.add_argument("--implementation", default=None,
                   help="name and revision under test, recorded in the claim")
    p.add_argument("--only", default=None,
                   help="comma-separated rules, e.g. OC-003,OC-008")
    p.add_argument("--host-b", default=None,
                   help="a path on a second host for the OC-003(b) relocation test")
    p.add_argument("--adapter-b", default=None,
                   help="an adapter running on a second host (an ssh wrapper "
                        "will do). Without it step 3.2 reports unestablished: "
                        "a copy verified on the same machine cannot fail on "
                        "host coupling")
    p.add_argument("--out", default="claim",
                   help="output prefix (writes <prefix>.md and <prefix>.json)")
    p.add_argument("--keep-stores", action="store_true",
                   help="do not delete the disposable stores, for debugging")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)

    only = {r.strip() for r in args.only.split(",")} if args.only else None

    adapter = Adapter(args.adapter, timeout=args.timeout)
    stores = Stores(adapter, keep=args.keep_stores)
    adapter_b = Adapter(args.adapter_b, timeout=args.timeout) if args.adapter_b else None
    ctx = Context(adapter, stores, host_b=args.host_b, adapter_b=adapter_b)
    if adapter_b:
        ctx.note(f"OC-003(b) verified the relocated copy with `{args.adapter_b}`. "
                 "The strength of that step depends on this adapter running on "
                 "a genuinely different host: on one machine the hostname, the "
                 "keystore and the hardware are shared, and a host-coupled "
                 "implementation is indistinguishable from a portable one.")

    if not args.quiet:
        print(f"OBEC conformance suite {SUITE_VERSION} — targets {TARGETS}")
        print(f"adapter: {args.adapter}")
        print(f"stores:  {stores.root}\n")

    try:
        results = Runner(ctx, TESTS).run(only=only, verbose=not args.quiet)
    finally:
        stores.cleanup()

    meta = {"adapter": args.adapter, "adapter_b": args.adapter_b,
            "implementation": args.implementation}
    write(results, ctx, meta, args.out + ".md", args.out + ".json")

    ok = conformant(results)
    if not args.quiet:
        counts = {o.value: 0 for o in Outcome}
        for r in results:
            for k, v in r.tally().items():
                counts[k] += v
        print(f"\n{'conformant' if ok else 'NOT conformant'} — "
              f"{counts['pass']} pass, {counts['fail']} fail, "
              f"{counts['attested']} attested, "
              f"{counts['unestablished']} unestablished, "
              f"{counts['error']} error")
        print(f"claim: {args.out}.md, {args.out}.json")

    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())

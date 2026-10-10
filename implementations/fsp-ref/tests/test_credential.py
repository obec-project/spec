# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Jonas Orrico
import itertools
import unittest

import helpers  # noqa: F401  (puts the implementation on sys.path)

from fsp.sil import LOCK_FREE, LOCK_HELD, LOCK_UNKNOWN, classify_credential


class CredentialAtStart(unittest.TestCase):
    """D25: the operating system's lock takes absolute precedence."""

    def test_a_held_or_unknown_lock_is_always_a_conflict(self):
        for lock, residue, process_holder in itertools.product(
            (LOCK_HELD, LOCK_UNKNOWN), (True, False), (True, False)
        ):
            with self.subTest(lock=lock, residue=residue, process_holder=process_holder):
                self.assertEqual(
                    classify_credential(
                        lock, residue=residue, process_holder=process_holder
                    ),
                    "conflict",
                )

    def test_with_the_lock_free_a_process_holder_or_residue_is_a_crash(self):
        cases = {
            (True, True): "crash",
            (True, False): "crash",
            (False, True): "crash",
            (False, False): "conflict",
        }
        for (residue, process_holder), expected in cases.items():
            with self.subTest(residue=residue, process_holder=process_holder):
                self.assertEqual(
                    classify_credential(
                        LOCK_FREE, residue=residue, process_holder=process_holder
                    ),
                    expected,
                )

    def test_no_other_lock_state(self):
        for bad in (None, True, "", "stale"):
            with self.assertRaises(ValueError):
                classify_credential(bad, residue=False, process_holder=False)

import unittest
from uuid import UUID

from tests.virtual_traders import COHORT_SIZES, build_cohort


class VirtualTraderCohortTests(unittest.TestCase):
    def test_supported_cohorts_are_deterministic_unique_and_isolated_per_run(self):
        run_id = UUID("19a3c40e-1cbb-4c34-9ff0-2a1a9740f71d")
        for size in COHORT_SIZES:
            first = build_cohort(run_id, size)
            second = build_cohort(str(run_id), size)
            self.assertEqual(first, second)
            self.assertEqual(len(first.traders), size)
            self.assertEqual([row.ordinal for row in first.traders], list(range(1, size + 1)))
            for field in ("identity_key", "workspace_key", "method_id", "session_id", "command_id", "email"):
                values = [getattr(row, field) for row in first.traders]
                self.assertEqual(len(values), len(set(values)), field)
            self.assertEqual(first.flow[-3:], ("CONFIRM", "RECEIPT_LOOKUP", "JOURNAL_READ"))
            self.assertTrue(all(row.email.endswith("@example.com") for row in first.traders))
        other = build_cohort(UUID("868c0c1b-7d24-4eb9-a571-7d3aaf799c37"), 5)
        self.assertNotEqual(build_cohort(run_id, 5).traders, other.traders)

    def test_invalid_run_or_unapproved_size_fails_closed(self):
        for invalid in (0, 2, 1000, True, 1.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                build_cohort(UUID("19a3c40e-1cbb-4c34-9ff0-2a1a9740f71d"), invalid)
        with self.assertRaises(ValueError):
            build_cohort("not-a-uuid", 1)

    def test_generator_contains_no_credentials_or_runtime_side_effects(self):
        cohort = build_cohort(UUID("19a3c40e-1cbb-4c34-9ff0-2a1a9740f71d"), 1)
        self.assertFalse(hasattr(cohort.traders[0], "password"))
        self.assertFalse(hasattr(cohort.traders[0], "access_token"))
        self.assertEqual(cohort.requested_users, 1)


if __name__ == "__main__":
    unittest.main()

"""Fixture/mock-DB tests for the artist reconciliation migration (Plan 08-02).

These tests run entirely against an in-memory fake DB layer mirroring the repo's
unittest + unittest.mock pattern (see tests/test_charts.py,
tests/test_backfill_guardrail.py). They make NO real database connection and NO
network calls. The real-DB validation (dry-run -> pg_dump snapshot -> apply ->
rebuild stats -> verify) is carried by docs/RECONCILIATION.md as operator steps.

The alias-module cases live under names matching ``-k alias`` so Task 1's verify
(`pytest -k alias`) selects them.
"""

import unittest

from billboard_stats.etl import artist_aliases


# ----------------------------------------------------------------------------
# Task 1: ETL genuine-alias map (moved from src/lib/artist-identity.ts)
# ----------------------------------------------------------------------------
class AliasModuleTests(unittest.TestCase):
    def test_alias_janet_resolves_to_canonical(self):
        self.assertEqual(artist_aliases.canonicalize("Janet"), "Janet Jackson")

    def test_alias_kesha_dollar_resolves_to_canonical(self):
        self.assertEqual(artist_aliases.canonicalize("Ke$ha"), "Kesha")

    def test_alias_unknown_name_unchanged(self):
        self.assertEqual(artist_aliases.canonicalize("Drake"), "Drake")

    def test_alias_lookup_is_case_insensitive(self):
        self.assertEqual(artist_aliases.canonicalize("janet"), "Janet Jackson")
        self.assertEqual(artist_aliases.canonicalize("KE$HA"), "Kesha")

    def test_alias_lookup_is_whitespace_normalized(self):
        self.assertEqual(artist_aliases.canonicalize("  Janet  "), "Janet Jackson")

    def test_alias_is_deterministic(self):
        first = artist_aliases.canonicalize("Janet")
        second = artist_aliases.canonicalize("Janet")
        self.assertEqual(first, second)

    def test_canonical_name_itself_is_stable(self):
        # Passing the canonical name returns the same canonical name.
        self.assertEqual(artist_aliases.canonicalize("Janet Jackson"), "Janet Jackson")
        self.assertEqual(artist_aliases.canonicalize("Kesha"), "Kesha")

    def test_genuine_alias_set_contains_aliases_not_fragments(self):
        genuine = artist_aliases.genuine_alias_names()
        # Genuine alternate spellings survive reconciliation.
        self.assertIn("janet", genuine)
        self.assertIn("ke$ha", genuine)
        # Split fragments are NOT genuine aliases — they are healed by
        # reconciliation, so they must never appear in the genuine-alias set.
        self.assertNotIn("earth", genuine)
        self.assertNotIn("wind", genuine)
        self.assertNotIn("fire", genuine)

    def test_earth_wind_fire_pieces_are_not_genuine_aliases(self):
        # canonicalize must NOT collapse a split fragment to the group name —
        # that healing is reconciliation's job, not the alias map's.
        self.assertEqual(artist_aliases.canonicalize("Earth"), "Earth")
        self.assertEqual(artist_aliases.canonicalize("Wind"), "Wind")
        self.assertEqual(artist_aliases.canonicalize("Fire"), "Fire")

    def test_is_genuine_alias_helper(self):
        self.assertTrue(artist_aliases.is_genuine_alias("Janet"))
        self.assertTrue(artist_aliases.is_genuine_alias("janet jackson"))
        self.assertFalse(artist_aliases.is_genuine_alias("Earth"))
        self.assertFalse(artist_aliases.is_genuine_alias("Drake"))


if __name__ == "__main__":
    unittest.main()

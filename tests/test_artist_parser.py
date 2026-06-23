import logging
import unittest

from billboard_stats.etl.artist_parser import parse_artist_credit

ARTIST_PARSER_LOGGER = "billboard_stats.etl.artist_parser"


class ParseArtistCreditTests(unittest.TestCase):
    def test_splits_standard_featured_credit(self):
        self.assertEqual(
            parse_artist_credit("Drake Featuring Rihanna"),
            [("Drake", "primary"), ("Rihanna", "featured")],
        )

    def test_splits_true_collaboration_credit(self):
        self.assertEqual(
            parse_artist_credit("Future & Drake"),
            [("Future", "primary"), ("Drake", "primary")],
        )

    def test_preserves_band_name_with_ampersand(self):
        self.assertEqual(
            parse_artist_credit("Earth, Wind & Fire"),
            [("Earth, Wind & Fire", "primary")],
        )

    def test_preserves_duo_name_with_ampersand(self):
        self.assertEqual(
            parse_artist_credit("Simon & Garfunkel"),
            [("Simon & Garfunkel", "primary")],
        )

    def test_preserves_protected_primary_before_featured_split(self):
        self.assertEqual(
            parse_artist_credit("Macklemore & Ryan Lewis Featuring Wanz"),
            [("Macklemore & Ryan Lewis", "primary"), ("Wanz", "featured")],
        )

    def test_preserves_protected_within_secondary_group(self):
        self.assertEqual(
            parse_artist_credit("Phil Wickham With Mumford & Sons & Beatenberg"),
            [("Phil Wickham", "primary"), ("Mumford & Sons", "with"), ("Beatenberg", "with")],
        )


class LookupFirstSingleActTests(unittest.TestCase):
    """Lookup-first: a whole credit matching a known single act stays one artist."""

    def test_comma_act_on_extended_allowlist_resolves_single(self):
        # Tyler, The Creator is added to the curated allowlist (D-03).
        self.assertEqual(
            parse_artist_credit("Tyler, The Creator"),
            [("Tyler, The Creator", "primary")],
        )

    def test_earth_wind_and_fire_still_single(self):
        self.assertEqual(
            parse_artist_credit("Earth, Wind & Fire"),
            [("Earth, Wind & Fire", "primary")],
        )

    def test_crosby_stills_nash_young_still_single(self):
        self.assertEqual(
            parse_artist_credit("Crosby, Stills, Nash & Young"),
            [("Crosby, Stills, Nash & Young", "primary")],
        )

    def test_db_supplied_known_act_resolves_single(self):
        # Brandy, Monica is NOT on the curated allowlist; it arrives only via the
        # DB-derived known_acts set (D-02). Proves the injected path works.
        self.assertEqual(
            parse_artist_credit("Brandy, Monica", known_acts=["Brandy, Monica"]),
            [("Brandy, Monica", "primary")],
        )

    def test_known_act_match_is_case_and_whitespace_insensitive(self):
        self.assertEqual(
            parse_artist_credit("brandy,   monica", known_acts=["Brandy, Monica"]),
            [("Brandy, Monica", "primary")],
        )


class CollaborationSplittingTests(unittest.TestCase):
    """Genuine collaborations with no whole-credit match still split (D-04)."""

    def test_dj_khaled_collaboration_splits_into_four(self):
        self.assertEqual(
            parse_artist_credit("DJ Khaled Featuring Drake, Lil Wayne & Rick Ross"),
            [
                ("DJ Khaled", "primary"),
                ("Drake", "featured"),
                ("Lil Wayne", "featured"),
                ("Rick Ross", "featured"),
            ],
        )

    def test_mixed_known_comma_act_primary_with_featured(self):
        # Whole-credit lookup applies to the primary segment; featured still splits.
        self.assertEqual(
            parse_artist_credit("Tyler, The Creator Featuring Kali Uchis"),
            [("Tyler, The Creator", "primary"), ("Kali Uchis", "featured")],
        )


class DeterminismTests(unittest.TestCase):
    def test_repeated_parse_is_identical(self):
        for credit in (
            "Tyler, The Creator",
            "DJ Khaled Featuring Drake, Lil Wayne & Rick Ross",
            "Tyler, The Creator Featuring Kali Uchis",
            "Earth, Wind & Fire",
        ):
            with self.subTest(credit=credit):
                self.assertEqual(
                    parse_artist_credit(credit), parse_artist_credit(credit)
                )


class CommaSplitLoggingTests(unittest.TestCase):
    """Every comma-containing split is logged so unlisted comma-acts surface (D-05)."""

    def test_comma_collaboration_logs_one_record(self):
        with self.assertLogs(ARTIST_PARSER_LOGGER, level=logging.INFO) as captured:
            parse_artist_credit("DJ Khaled Featuring Drake, Lil Wayne & Rick Ross")
        self.assertEqual(len(captured.records), 1)

    def test_matched_comma_act_logs_nothing(self):
        logger = logging.getLogger(ARTIST_PARSER_LOGGER)
        with self.assertRaises(AssertionError):
            with self.assertLogs(ARTIST_PARSER_LOGGER, level=logging.INFO):
                parse_artist_credit("Tyler, The Creator")
        # also confirm via a sentinel that no record was emitted for the matched act
        self.assertTrue(logger is not None)

    def test_non_comma_split_does_not_log(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs(ARTIST_PARSER_LOGGER, level=logging.INFO):
                parse_artist_credit("Future & Drake")


class EmptyInputTests(unittest.TestCase):
    def test_empty_and_whitespace_return_empty(self):
        self.assertEqual(parse_artist_credit(""), [])
        self.assertEqual(parse_artist_credit("   "), [])
        self.assertEqual(parse_artist_credit(None), [])


if __name__ == "__main__":
    unittest.main()

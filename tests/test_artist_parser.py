import unittest

from billboard_stats.etl.artist_parser import parse_artist_credit


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


if __name__ == "__main__":
    unittest.main()

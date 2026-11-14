import unittest

from timekit import duration


class ParseDurationAcceptanceTest(unittest.TestCase):
    def test_single_and_combined_units(self):
        self.assertEqual(duration.parse_duration("1h30m"), 5400)
        self.assertEqual(duration.parse_duration("45s"), 45)
        self.assertEqual(duration.parse_duration("2h"), 7200)
        self.assertEqual(duration.parse_duration("1h2m3s"), 3723)

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(duration.parse_duration(" 10m "), 600)

    def test_round_trips_with_format(self):
        self.assertEqual(duration.parse_duration(duration.format_duration(3723)), 3723)

    def test_invalid_input_raises_value_error(self):
        for text in ("", "5d", "h", "5m1h", "1m1m", "1.5h", "-1h"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                duration.parse_duration(text)

import unittest

from timekit.duration import format_duration


class FormatDurationTest(unittest.TestCase):
    def test_mixed_parts(self):
        self.assertEqual(format_duration(3723), "1h2m3s")

    def test_zero_is_zero_seconds(self):
        self.assertEqual(format_duration(0), "0s")

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            format_duration(-1)

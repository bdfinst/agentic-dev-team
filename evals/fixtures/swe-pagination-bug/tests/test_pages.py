import unittest

from listing.pages import page_count


class PageCountTest(unittest.TestCase):
    def test_exact_multiple(self):
        self.assertEqual(page_count(20, 10), 2)

    def test_size_below_one_raises(self):
        with self.assertRaises(ValueError):
            page_count(5, 0)

import unittest

from listing.pages import page, page_count

ITEMS = list(range(1, 26))


class PaginationAcceptanceTest(unittest.TestCase):
    def test_first_page_starts_at_the_first_item(self):
        self.assertEqual(page(ITEMS, 1, 10), list(range(1, 11)))

    def test_last_page_holds_the_remainder(self):
        self.assertEqual(page(ITEMS, 3, 10), [21, 22, 23, 24, 25])

    def test_page_count_rounds_up(self):
        self.assertEqual(page_count(25, 10), 3)
        self.assertEqual(page_count(0, 10), 0)

    def test_page_past_the_end_is_empty(self):
        self.assertEqual(page(ITEMS, 4, 10), [])

    def test_invalid_page_or_size_raises(self):
        for number, size in ((0, 10), (-1, 10), (1, 0)):
            with self.subTest(number=number, size=size), self.assertRaises(ValueError):
                page(ITEMS, number, size)

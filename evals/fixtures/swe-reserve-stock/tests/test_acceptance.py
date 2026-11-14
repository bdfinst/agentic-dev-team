import unittest

from stock.inventory import InsufficientStock, Inventory


class ReserveAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.inventory = Inventory({"A": 5, "B": 0})

    def test_reserve_reduces_available_not_on_hand(self):
        self.inventory.reserve("A", 2)
        self.assertEqual(self.inventory.available("A"), 3)
        self.assertEqual(self.inventory.on_hand("A"), 5)

    def test_reserving_everything_available_succeeds(self):
        self.inventory.reserve("A", 5)
        self.assertEqual(self.inventory.available("A"), 0)

    def test_over_reservation_raises_and_changes_nothing(self):
        self.inventory.reserve("A", 4)
        with self.assertRaises(InsufficientStock):
            self.inventory.reserve("A", 2)
        self.assertEqual(self.inventory.available("A"), 1)

    def test_non_positive_quantity_raises_and_changes_nothing(self):
        for quantity in (0, -3):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.inventory.reserve("A", quantity)
        self.assertEqual(self.inventory.available("A"), 5)

    def test_unknown_sku_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.inventory.reserve("Z", 1)

    def test_out_of_stock_sku_cannot_be_reserved(self):
        with self.assertRaises(InsufficientStock):
            self.inventory.reserve("B", 1)

    def test_release_returns_at_most_what_was_reserved(self):
        self.inventory.reserve("A", 2)
        self.inventory.release("A", 10)
        self.assertEqual(self.inventory.available("A"), 5)

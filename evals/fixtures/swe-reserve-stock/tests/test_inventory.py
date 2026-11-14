import unittest

from stock.inventory import Inventory


class ReceiveTest(unittest.TestCase):
    def test_receive_adds_to_on_hand_and_available(self):
        inventory = Inventory({"A": 2})
        inventory.receive("A", 3)
        self.assertEqual(inventory.on_hand("A"), 5)
        self.assertEqual(inventory.available("A"), 5)

    def test_receive_new_sku(self):
        inventory = Inventory({})
        inventory.receive("B", 1)
        self.assertEqual(inventory.available("B"), 1)

    def test_release_without_reservation_is_a_no_op(self):
        inventory = Inventory({"A": 2})
        inventory.release("A", 1)
        self.assertEqual(inventory.available("A"), 2)

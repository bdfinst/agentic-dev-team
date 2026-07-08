import unittest

from pricing.engine import PricingEngine


class TestPricingEngine(unittest.TestCase):
    def test_computes_discount_tier_via_name_mangled_attribute(self):
        engine = PricingEngine()

        # Reaches around encapsulation instead of testing through the public API
        tier = getattr(engine, "_PricingEngine__compute_discount_tier")(450)

        self.assertEqual(tier, "gold")

    def test_applies_discount_through_public_api(self):
        engine = PricingEngine()

        total = engine.apply_discount(450)

        self.assertAlmostEqual(total, 382.5)

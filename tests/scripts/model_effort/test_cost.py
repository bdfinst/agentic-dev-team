"""Cost summing (model_effort.cost)."""

from __future__ import annotations

from model_effort.cost import total_cost_usd


class TestTotalCost:
    def test_ten_tenths_sum_to_exactly_one(self):
        assert total_cost_usd([0.1] * 10) == 1.0

    def test_no_amounts_sum_to_zero(self):
        assert total_cost_usd([]) == 0.0

import unittest
from decimal import Decimal

from utils.stock_pricing import calculate_retail_price, calculate_weighted_average


class StockPricingTests(unittest.TestCase):
    def test_first_income_uses_incoming_price(self):
        self.assertEqual(
            calculate_weighted_average(0, 1000, 5, 1200),
            Decimal("1200.00"),
        )

    def test_income_recalculates_moving_average(self):
        self.assertEqual(
            calculate_weighted_average(10, 1000, 5, 1200),
            Decimal("1066.67"),
        )

    def test_average_uses_only_stock_still_on_hand(self):
        self.assertEqual(
            calculate_weighted_average(1, 1000, 10, 1200),
            Decimal("1181.82"),
        )

    def test_retail_uses_latest_price_and_category_markup(self):
        self.assertEqual(calculate_retail_price(1200, 30), Decimal("1560"))

    def test_retail_rounds_up_to_whole_tenge(self):
        self.assertEqual(calculate_retail_price(1000, 12.5), Decimal("1125"))

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_weighted_average(10, 1000, 0, 1200)


if __name__ == "__main__":
    unittest.main()

"""Regression coverage for catalog-to-retail discount prices (no network)."""
import unittest
from decimal import Decimal

from utils.sale_amounts import normalize_discounted_sale_line


class SaleDiscountsTest(unittest.TestCase):
    def test_catalog_discount_is_charged_once(self):
        result = normalize_discounted_sale_line(
            {"base_price": 2000, "discount_percent": 10, "price": 1800, "qty": 2}, "шт"
        )
        self.assertEqual(result, (Decimal("1800.00"), Decimal("2"), Decimal("3600.00")))

    def test_cashier_override_uses_original_catalog_price(self):
        result = normalize_discounted_sale_line(
            {"base_price": "1000.00", "discount_percent": 25, "price": "750.00", "qty": 1}
        )
        self.assertEqual(result[2], Decimal("750.00"))

    def test_invalid_or_mismatched_discounts_are_rejected(self):
        for raw in (-1, 101, "nan", "2.5", None):
            with self.subTest(discount=raw), self.assertRaises(ValueError):
                normalize_discounted_sale_line(
                    {"base_price": 1000, "discount_percent": raw, "price": 1000, "qty": 1}
                )
        with self.assertRaises(ValueError):
            normalize_discounted_sale_line(
                {"base_price": 1000, "discount_percent": 20, "price": 1000, "qty": 1}
            )
        with self.assertRaises(ValueError):
            normalize_discounted_sale_line(
                {"base_price": 1000, "price": 800, "qty": 1}
            )

    def test_measured_amount_respects_rounding(self):
        _, qty, net = normalize_discounted_sale_line(
            {"base_price": 3010, "discount_percent": 10,
             "price": "2709.00", "qty": 0.369, "line_total": 1000}, "кг"
        )
        self.assertEqual(qty, Decimal("0.369"))
        self.assertEqual(net, Decimal("1000"))

    def test_offline_replay_has_unchanged_charged_snapshot(self):
        cart = {"base_price": "1500", "discount_percent": 15, "price": "1275",
                "qty": "2", "line_total": None}
        self.assertEqual(normalize_discounted_sale_line(cart)[2], Decimal("2550.00"))
        self.assertEqual(normalize_discounted_sale_line(cart)[2], Decimal("2550.00"))

    def test_legacy_food_or_old_clients_unchanged(self):
        self.assertEqual(normalize_discounted_sale_line({"price": 3010, "qty": 0.333}, "кг")[2],
                         Decimal("1002"))


if __name__ == "__main__":
    unittest.main()

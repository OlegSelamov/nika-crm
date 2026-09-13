import unittest

from utils.sale_amounts import normalize_sale_line


class SaleAmountsTest(unittest.TestCase):
    def test_measured_total_is_rounded_to_whole_tenge(self):
        price, quantity, total = normalize_sale_line(
            {"price": 3010, "qty": 0.333},
            "кг",
        )

        self.assertEqual(str(price), "3010")
        self.assertEqual(str(quantity), "0.333")
        self.assertEqual(str(total), "1002")

    def test_exact_amount_is_kept_when_weight_rounding_explains_difference(self):
        _, _, total = normalize_sale_line(
            {"price": 3010, "qty": 0.332, "line_total": 1000},
            "кг",
        )

        self.assertEqual(str(total), "1000")

    def test_unreasonable_exact_amount_is_ignored(self):
        _, _, total = normalize_sale_line(
            {"price": 3010, "qty": 0.332, "line_total": 500},
            "кг",
        )

        self.assertEqual(str(total), "999")

    def test_piece_goods_keep_tiyin_precision(self):
        _, _, total = normalize_sale_line(
            {"price": "10.25", "qty": 2},
            "шт",
        )

        self.assertEqual(str(total), "20.50")


if __name__ == "__main__":
    unittest.main()

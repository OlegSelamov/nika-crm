import unittest

from utils.product_codes import parse_scanned_product_code


class ScannedProductCodeTest(unittest.TestCase):
    def test_regular_ean_is_unchanged(self):
        code = parse_scanned_product_code("4870001234567")
        self.assertEqual(code.lookup_code, "4870001234567")
        self.assertEqual(code.lookup_candidates, ("4870001234567",))
        self.assertFalse(code.is_marking_code)

    def test_compact_gs1_extracts_ean_and_gtin(self):
        raw = "010487000123456721SERIAL\x1d91CRYPTO"
        code = parse_scanned_product_code(raw)
        self.assertEqual(code.gtin, "04870001234567")
        self.assertEqual(code.ean13, "4870001234567")
        self.assertEqual(
            code.lookup_candidates,
            ("4870001234567", "04870001234567"),
        )
        self.assertEqual(code.marking_code, raw)

    def test_aim_prefix_is_not_part_of_marking_payload(self):
        code = parse_scanned_product_code("]d2010487000123456721SERIAL")
        self.assertEqual(code.lookup_code, "4870001234567")
        self.assertEqual(code.marking_code, "010487000123456721SERIAL")

    def test_parenthesized_gs1_is_supported(self):
        code = parse_scanned_product_code("(01)04870001234567(21)SERIAL")
        self.assertEqual(code.gtin, "04870001234567")
        self.assertTrue(code.is_marking_code)


if __name__ == "__main__":
    unittest.main()

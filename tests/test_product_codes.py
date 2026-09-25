import unittest

from utils.product_codes import normalize_scanned_payload, parse_scanned_product_code


class ProductCodesTest(unittest.TestCase):
    def test_aim_prefix_is_removed_but_internal_gs_is_preserved(self):
        value = "]d2010460123456789021SERIAL123\x1d91ABCD\x1d92CRYPTO\r\n"
        parsed = parse_scanned_product_code(value)

        self.assertEqual(parsed.gtin, "04601234567890")
        self.assertEqual(parsed.ean13, "4601234567890")
        self.assertEqual(
            parsed.marking_code,
            "010460123456789021SERIAL123\x1d91ABCD\x1d92CRYPTO",
        )
        self.assertIn("\x1d", parsed.marking_code)

    def test_trailing_group_separator_is_not_trimmed(self):
        value = "010460123456789021ABC\x1d"
        self.assertEqual(
            normalize_scanned_payload(value),
            "010460123456789021ABC\x1d",
        )

    def test_plain_ean_is_not_mistaken_for_marking(self):
        parsed = parse_scanned_product_code("4601234567890\r")
        self.assertEqual(parsed.payload, "4601234567890")
        self.assertIsNone(parsed.marking_code)
        self.assertEqual(parsed.lookup_code, "4601234567890")

    def test_parenthesized_ai_keeps_crypto_tail(self):
        parsed = parse_scanned_product_code(
            "(01)04601234567890(21)ABC123\x1d91KEY"
        )
        self.assertEqual(parsed.gtin, "04601234567890")
        self.assertEqual(
            parsed.marking_code,
            "(01)04601234567890(21)ABC123\x1d91KEY",
        )


if __name__ == "__main__":
    unittest.main()

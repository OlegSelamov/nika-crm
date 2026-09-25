import unittest

from utils.product_codes import normalize_scanned_payload, parse_scanned_product_code


class ProductCodesTest(unittest.TestCase):
    def test_raw_marking_is_preserved_exactly_for_rekassa(self):
        value = "]d2010460043993125621JgXJ5.T\x1d930001\x1d923zbrLA==\x1d24014276281"
        parsed = parse_scanned_product_code(value)

        self.assertEqual(parsed.raw, value)
        self.assertEqual(parsed.marking_code, value)
        self.assertEqual(parsed.gtin, "04600439931256")
        self.assertEqual(parsed.ean13, "4600439931256")

    def test_lookup_copy_can_drop_aim_but_keeps_internal_gs(self):
        value = "]d2010460043993125621ABC\x1d930001\x1d92XYZ"
        normalized = normalize_scanned_payload(value)
        self.assertEqual(
            normalized,
            "010460043993125621ABC\x1d930001\x1d92XYZ",
        )
        self.assertIn("\x1d", normalized)

    def test_plain_ean_is_not_marking(self):
        parsed = parse_scanned_product_code("4600439931256")
        self.assertIsNone(parsed.marking_code)
        self.assertEqual(parsed.lookup_code, "4600439931256")


if __name__ == "__main__":
    unittest.main()

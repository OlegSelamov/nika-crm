import unittest

from utils.stock_balance import (
    backfill_legacy_stock_movements,
    stock_balance_sql,
    sync_item_quantities,
)


class FakeCursor:
    def __init__(self, updated_count=0):
        self.updated_count = updated_count
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return {
            "updated_count": self.updated_count,
            "inserted_count": self.updated_count,
        }


class StockBalanceTests(unittest.TestCase):
    def test_balance_uses_all_stock_movement_directions(self):
        sql = stock_balance_sql("item")
        self.assertIn("'income', 'refund'", sql)
        self.assertIn("'sale', 'writeoff'", sql)
        self.assertIn("sm.company_id = item.company_id", sql)
        self.assertIn("sm.item_id = item.id", sql)

    def test_service_balance_is_zero(self):
        sql = stock_balance_sql("item")
        self.assertIn("item.item_type", sql)
        self.assertIn("= 'service' THEN 0", sql)

    def test_items_without_movements_keep_their_legacy_quantity(self):
        sql = stock_balance_sql("item")
        self.assertIn("item.quantity, 0", sql)

    def test_invalid_alias_is_rejected(self):
        with self.assertRaises(ValueError):
            stock_balance_sql("items; DROP TABLE items")

    def test_sync_can_be_scoped_to_one_company_item(self):
        cur = FakeCursor(updated_count=2)
        updated = sync_item_quantities(cur, company_id=7, item_id=15)
        self.assertEqual(updated, 2)
        self.assertEqual(cur.params, (7, 15))
        self.assertIn("i.company_id = %s", cur.query)
        self.assertIn("i.id = %s", cur.query)
        self.assertIn("IS DISTINCT FROM", cur.query)

    def test_legacy_quantity_is_preserved_as_a_stock_movement(self):
        cur = FakeCursor(updated_count=3)
        inserted = backfill_legacy_stock_movements(cur)
        self.assertEqual(inserted, 3)
        self.assertEqual(cur.params, ())
        self.assertIn("NOT EXISTS", cur.query)
        self.assertIn("ABS(i.quantity)", cur.query)
        self.assertIn("'writeoff' ELSE 'refund'", cur.query)


if __name__ == "__main__":
    unittest.main()

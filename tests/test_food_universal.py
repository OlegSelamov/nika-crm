"""Static regression guards for universal POS + food order checkout."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UniversalFoodCheckoutTests(unittest.TestCase):
    def test_universal_has_order_controls_and_workspaces(self):
        template = (ROOT / "templates/sales.html").read_text()
        self.assertEqual(template.count("{% if business_mode in ('foodservice', 'universal') %}"), 2)
        for item in ("foodOrderSave", "foodOrderDetails", "foodOrdersWorkspace", "foodTicketModal"):
            self.assertIn(item, template)

    def test_food_routes_allow_universal_company(self):
        source = (ROOT / "routes/food_orders.py").read_text()
        self.assertIn('row["business_mode"] in ("foodservice", "universal")', source)

    def test_selected_sales_mode_drives_history_and_checkout(self):
        sales_js = (ROOT / "static/js/sales.js").read_text()
        food_js = (ROOT / "static/js/food_sales.js").read_text()
        self.assertIn("isFoodCheckout", sales_js)
        self.assertIn("food_mode: isFoodCheckout", sales_js)
        self.assertIn("food_order_id: isFoodCheckout", sales_js)
        self.assertIn('isFoodMode: () => currentMode() === "food"', food_js)
        self.assertIn('foodWorkspace.hidden = !showHistory || !isFood', sales_js)
        self.assertIn('historyBtn.textContent = next === "food"', food_js)

    def test_actual_payment_route_handles_dishes_and_orders(self):
        app = (ROOT / "app.py").read_text()
        self.assertIn('app.view_functions["sales.pay_sale"] = pay_sale_comrun', app)
        source = (ROOT / "routes/rekassa_comrun.py").read_text()
        ast.parse(source)
        for needle in (
            'item_type = raw_item_type if raw_item_type in ("service", "dish")',
            "verify_payment_order(cur, company_id, food_order_id, cart)",
            "process_sale(conn, sale_id)",
            "json.dumps(item.get(\"modifiers\") or [], ensure_ascii=False)",
            "UPDATE food_orders SET status='paid'",
            "cash_received, change_amount",
        ):
            self.assertIn(needle, source)


if __name__ == "__main__":
    unittest.main()

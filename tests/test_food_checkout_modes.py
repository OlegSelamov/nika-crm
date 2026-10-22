"""Configuration, precheck and external-cashier safety checks."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FoodCheckoutModesTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_profile_has_three_modes(self):
        tpl = self.read("templates/profile.html")
        for mode in ("fast", "orders", "external"):
            self.assertIn('value="' + mode + '"', tpl)
        self.assertIn('name="food_checkout_mode"', tpl)
        self.assertIn('UPDATE companies SET food_checkout_mode=%s', self.read("routes/auth.py"))

    def test_server_renders_company_selection(self):
        route = self.read("routes/sales.py")
        self.assertIn('food_checkout_mode=food_checkout_mode', route)
        self.assertIn('NIKA_FOOD_CHECKOUT_MODE', self.read("templates/sales.html"))
        self.assertIn('food_checkout_mode TEXT NOT NULL DEFAULT', self.read("app.py"))

    def test_precheck_does_not_use_sale_payment(self):
        js = self.read("static/js/food_sales.js")
        create = js.split('async function createFoodPrecheck()', 1)[1].split('async function payExistingFoodOrder()', 1)[0]
        self.assertIn('await saveFoodOrder()', create)
        self.assertIn('await printBothFoodTickets(saved, {manualAllowed: true})', create)
        self.assertNotIn('pay()', create)
        self.assertNotIn('submitSalePayment', create)

    def test_paid_sale_uses_existing_pay_flow(self):
        js = self.read("static/js/food_sales.js")
        pay = js.split('async function payExistingFoodOrder()', 1)[1].split('function newFoodOrder()', 1)[0]
        self.assertIn('if (!isFoodTicketCurrent())', pay)
        self.assertIn('if (!isFoodTicketCurrent())', pay)
        self.assertIn('await saveFoodOrder()', pay)
        self.assertIn('await printBothFoodTickets(saved)', pay)
        self.assertIn('if (!await printBothFoodTickets(saved))', pay)
        self.assertIn('lastFoodPrintUiSignature === currentFoodUiSignature()', js)
        self.assertIn('pay()', pay)
        self.assertIn('openCashChangeModal()', pay)
        self.assertIn('food_order_id:', self.read("static/js/sales.js"))

    def test_precheck_remembers_payment_without_registering_sale(self):
        js = self.read("static/js/food_sales.js")
        backend = self.read("routes/food_orders.py")
        sales_js = self.read("static/js/sales.js")
        tpl = self.read("templates/food_order_ticket.html")
        self.assertIn("planned_payment_method: selectedFoodPaymentMethod()", js)
        self.assertIn('payment: order.planned_payment_method || "cash"', js)
        self.assertIn('planned_payment_method TEXT NOT NULL DEFAULT', backend)
        self.assertIn('planned_payment_method=%s', backend)
        self.assertIn('planned_payment_method FROM food_orders', backend)
        self.assertIn('order["planned_payment_method"] != payment_method', backend)
        self.assertIn('food_config["food_checkout_mode"] == "orders"', self.read("routes/rekassa_comrun.py"))
        self.assertIn("Оплата:", tpl)
        self.assertNotIn("Планируемая оплата", tpl)
        self.assertNotIn("НЕ ФИСКАЛЬНЫЙ ЧЕК", tpl)
        self.assertIn("fiscalization_skipped === true", sales_js)
        self.assertIn('if (isFoodCheckout && data.fiscalization_skipped === true)', sales_js)
        self.assertIn("openSaleModal(data.sale_id, { autoPrint: true });", sales_js)

    def test_external_kassa_never_fakes_internal_sale(self):
        route = self.read("routes/food_orders.py")
        endpoint = route.split('def food_order_external_payment(', 1)[1].split('@food_orders_bp.route("/food/orders/', 1)[0]
        self.assertIn("external_paid", endpoint)
        self.assertIn("status='open' AND sale_id IS NULL", endpoint)
        self.assertNotIn("process_sale(", endpoint)
        self.assertNotIn("fiscalize_sale(", endpoint)
        self.assertNotIn("INSERT INTO sales", endpoint)
        self.assertIn('food_config["food_checkout_mode"] == "external"', self.read("routes/rekassa_comrun.py"))
        self.assertIn('external_receipt_number', route)

    def test_ticket_uses_electron_receipt_printer(self):
        js = self.read("static/js/food_sales.js")
        self.assertIn('printers?.printKitchen', js)
        self.assertIn('printMethod({html, title})', js)
        self.assertIn('printers.printFoodOrder({', js)
        self.assertIn('frame.contentWindow?.print()', js)
        self.assertIn('frame.onload =', js)
        self.assertIn('if (autoPrint && kind === "precheck")', js)
        self.assertIn('void printFoodTicketFromModal()', js)

    def test_all_edited_python_modules_parse(self):
        for path in ("app.py", "models.py", "routes/auth.py", "routes/sales.py",
                     "routes/food_orders.py", "routes/rekassa_comrun.py"):
            with self.subTest(path=path):
                ast.parse(self.read(path))


if __name__ == "__main__":
    unittest.main()

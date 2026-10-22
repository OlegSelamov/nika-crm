"""Restaurant dual-receipt printer configuration and safety regression checks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FoodDualPrintTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_kitchen_and_receipt_are_separate_configurations(self):
        src = self.read("desktop/main.js")
        for name in ("kitchen_printer", "kitchen_paper_width", "kitchen_offset_mm",
                     "kitchen_copies", "receipt_printer", "document_printer"):
            self.assertIn(name, src)
        self.assertIn('kind === "kitchen"', src)
        self.assertIn('paper.width', src)
        self.assertIn('kind: "kitchen"', src)

    def test_printing_one_order_sends_two_distinct_documents(self):
        js = self.read("static/js/food_sales.js")
        self.assertIn('getSavedFoodTicketHtml(order.id, "precheck")', js)
        self.assertIn('getSavedFoodTicketHtml(order.id, "kitchen")', js)
        self.assertIn('printBothFoodTickets(saved)', js)
        self.assertIn('printFoodOrder({', js)
        self.assertIn('orderId: order.id', js)
        self.assertIn('fingerprint,', js)
        self.assertNotIn('"/sales/pay"', js[js.index('async function printBothFoodTickets('):js.index('async function createFoodPrecheck(')])

    def test_receipt_printer_ui_has_a_third_printer(self):
        html = self.read("templates/settings/printers.html")
        for phrase in ("Принтер кухни", 'id="kitchenPrinter"', 'id="kitchenCopies"',
                       'id="kitchenOffset"', 'id="testKitchenBtn"', 'name="kitchenPaperWidth"'):
            self.assertIn(phrase, html)
        for field in ("kitchen_printer:", "kitchen_paper_width:", "kitchen_offset_mm:", "kitchen_copies:"):
            self.assertIn(field, html)
        self.assertIn("print-food-order", self.read("desktop/preload.js"))

    def test_auto_print_does_not_fiscalize(self):
        js = self.read("static/js/food_sales.js")
        code = js[js.index('async function printBothFoodTickets('):js.index('async function createFoodPrecheck(')]
        self.assertNotIn("submitSalePayment(", code)
        self.assertNotIn("pay()", code)
        self.assertNotIn("fiscalize", code)
        receipt = self.read("templates/food_order_ticket.html")
        self.assertIn('{% if kind == "precheck" %}', receipt)
        self.assertIn('{% if kind == "kitchen" %}', receipt)


if __name__ == "__main__":
    unittest.main()

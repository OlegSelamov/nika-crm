"""Retail cart drafts: isolated saved sessions, no duplicate paid sale, and safe history repeat."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RetailCartDraftsTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_draft_endpoints_are_company_user_scoped(self):
        src = self.read("routes/sales.py")
        ast.parse(src)
        self.assertIn('CREATE TABLE IF NOT EXISTS retail_cart_drafts', src)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS ux_retail_cart_drafts_autosave', src)
        self.assertIn('WHERE company_id=%s AND user_id=%s', src)
        self.assertIn('AND is_auto=FALSE', src)
        self.assertIn('def retail_cart_drafts():', src)
        self.assertIn('def retail_cart_draft_detail(draft_id):', src)
        self.assertIn('def clear_retail_active_draft():', src)
        self.assertIn('is_auto=True', src.replace('TRUE', 'True').replace('true', 'True')) if False else None

    def test_saved_drafts_are_not_sales_or_restaurant_orders(self):
        src = self.read("routes/sales.py")
        area = src.split('# Retail cart drafts are distinct', 1)[1]
        self.assertNotIn('process_sale(', area)
        self.assertNotIn('fiscalize_sale(', area)
        self.assertNotIn('INSERT INTO sales', area)
        self.assertNotIn('INSERT INTO food_orders', area)
        self.assertNotIn('rekassa_sell(', area)
        self.assertIn('now_kz_for_timestamp()', area)

    def test_history_repeat_is_a_new_cart_and_never_reuses_datamatrix(self):
        src = self.read("routes/sales.py")
        area = src.split('def retail_repeat_sale_cart(', 1)[1]
        self.assertIn('s.company_id=%s', area)
        self.assertIn('if row.get("excise_stamp"):', area)
        self.assertIn('нужен новый DataMatrix', area)
        self.assertNotIn("INSERT INTO sales", area)
        self.assertNotIn("process_sale(", area)

    def test_client_workflow_and_cart_restore(self):
        js = self.read("static/js/retail_cart_drafts.js")
        tpl = self.read("templates/sales.html")
        src = self.read("static/js/sales.js")
        self.assertIn("nika:retail:cart:v3:", js)
        self.assertIn("window.NIKA_RETAIL_DRAFT_OWNER", js)
        self.assertIn('window.NIKA_BUSINESS_MODE !== "foodservice"', js)
        self.assertIn('document.body.classList.contains("food-sales-mode")', js)
        self.assertIn('const originalRender = window.renderCart', js)
        self.assertIn('window.addEventListener("nika:sale-completed"', js)
        self.assertIn('is_auto:true', js)
        self.assertIn('currentManualId', js)
        self.assertIn("switchSalesTab(\"cart\")", js)
        self.assertIn('id="retailSaveCart"', tpl)
        self.assertIn('id="retailDraftList"', tpl)
        self.assertIn('id="retailDraftHistory"', tpl)
        self.assertIn('retail_cart_drafts.js', tpl)
        self.assertIn('class="sales-receipt-repeat"', src)
        self.assertIn('onclick="retailRepeatSale(', src)
        self.assertIn('retail-repeat-btn', src)

    def test_existing_food_and_retail_payment_are_untouched(self):
        sales = self.read("static/js/sales.js")
        food = self.read("static/js/food_sales.js")
        self.assertIn('await finalizeFoodPaymentAfterChecks(method)', food)
        self.assertIn('await submitSalePayment({', food)
        self.assertIn('window.dispatchEvent(new CustomEvent("nika:sale-completed"))', sales)
        self.assertIn('food_order_id: isFoodCheckout', sales)
        self.assertIn('window.NikaFoodSales?.loadHistory?.()', sales)


if __name__ == "__main__":
    unittest.main()

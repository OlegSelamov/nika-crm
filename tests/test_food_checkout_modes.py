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
        create = js.split('async function createFoodPrecheck()', 1)[1].split('async function finalizeFoodPaymentAfterChecks(', 1)[0]
        self.assertIn('await saveFoodOrder()', create)
        self.assertIn('await printBothFoodTickets(saved)', create)
        self.assertIn('autoPrint !== true', create)
        self.assertIn('await foodAutoPrintPreference()', create)
        self.assertNotIn('pay()', create)
        self.assertNotIn('submitSalePayment', create)

    def test_confirm_payment_prints_only_if_needed(self):
        js = self.read("static/js/food_sales.js")
        finalize = js.split('async function finalizeFoodPaymentAfterChecks(', 1)[1].split('async function payExistingFoodOrder()', 1)[0]
        pay = js.split('async function payExistingFoodOrder()', 1)[1].split('function newFoodOrder()', 1)[0]
        self.assertIn('const needsFreshTickets = !isFoodTicketCurrent()', finalize)
        self.assertIn('const websiteMode = !isElectronFoodCheckout()', finalize)
        self.assertIn('await saveFoodOrder()', finalize)
        self.assertIn('if (!websiteMode && autoPrint === true)', finalize)
        self.assertIn('autoPrint === false', finalize)
        self.assertIn('await foodAutoPrintPreference()', finalize)
        self.assertIn('await printBothFoodTickets(saved)', finalize)
        self.assertIn('submitSalePayment({', finalize)
        self.assertIn('openCashChangeModal()', pay)
        self.assertNotIn('else pay()', pay)
        self.assertIn('window.nikaConfirmNegativeStockSale', pay)
        self.assertIn('lastFoodPrintUiSignature === currentFoodUiSignature()', js)
        self.assertIn('state?.settings?.auto_print_receipt', js)
        self.assertIn('auto_print_receipt', self.read("desktop/main.js"))
        self.assertIn('food_order_id:', self.read("static/js/sales.js"))

    def test_retail_stock_guard_never_captures_food_buttons(self):
        patch = self.read("static/js/sales_cash_change_patch.js")
        self.assertIn("document.getElementById('normalCheckoutButton')", patch)
        self.assertNotIn(".payment-actions .pay-btn:not(.invoice-pay-btn):not(.kaspi-pay-btn)", patch)

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
        self.assertIn("receipt_label('payment')", tpl)
        self.assertNotIn("Планируемая оплата", tpl)
        self.assertNotIn("НЕ ФИСКАЛЬНЫЙ ЧЕК", tpl)
        self.assertIn('if (isFoodCheckout) {', sales_js)
        self.assertIn('const realFiscalTicket = data.fiscalized === true', sales_js)
        self.assertIn('fiscalTicket.ticket_id || fiscalTicket.ticket_number', sales_js)
        self.assertIn('if (!realFiscalTicket)', sales_js)
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
        self.assertIn('if (autoPrint && kind === "precheck" && isElectronFoodCheckout())', js)
        self.assertIn('void printFoodTicketFromModal()', js)


    def test_browser_dual_preview_does_not_require_printers(self):
        js = self.read("static/js/food_sales.js")
        tpl = self.read("templates/sales.html")
        route = self.read("routes/food_orders.py")
        print_section = js.split('async function printBothFoodTickets(', 1)[1].split('async function createFoodPrecheck()', 1)[0]
        self.assertIn('if (!isElectronFoodCheckout())', print_section)
        self.assertIn('openFoodTicketPair(order.id)', print_section)
        self.assertIn('await openFoodTicketPair(order.id, {', print_section)
        self.assertIn('waitForPreview: true', print_section)
        self.assertIn('setFoodPairAutoPrinting(true)', print_section)
        self.assertIn('if (!printers?.printFoodOrder)', print_section)
        self.assertIn('printers.printFoodOrder({', print_section)
        self.assertIn('getFoodDesktopBridge()?.isElectron === true', js)
        for marker in ('foodGuestTicketFrame', 'foodKitchenTicketFrame', 'foodTicketPair',
                       'data-food-ticket-action="share"', 'data-food-ticket-action="save"'):
            self.assertIn(marker, tpl)
        self.assertIn('def food_order_ticket_pdf(', route)
        self.assertIn('food_order_ticket(order_id, kind)', route)
        self.assertIn('openFoodTicketPair(saved.id)', js)
        self.assertIn('previewAfterPaymentOrderId = saved.id', js)
        self.assertIn('cash_received', js)
        self.assertIn('navigator.share', js)
        self.assertIn("saveTicketFile('share')", self.read("templates/food_order_ticket.html"))

    def test_food_order_cancel_only_if_unpaid(self):
        route = self.read("routes/food_orders.py")
        detail = route.split('def food_order_detail(order_id):', 1)[1].split(
            '@food_orders_bp.route("/api/food/orders/<int:order_id>/external-payment"', 1
        )[0]
        frontend = self.read("static/js/food_sales.js")
        history = frontend.split('async function loadFoodOrderHistory(', 1)[1].split(
            'function initFoodOrderControls()', 1
        )[0]
        cancel = frontend.split('async function cancelFoodOrder(', 1)[1].split(
            'async function loadFoodOrderHistory(', 1
        )[0]
        self.assertIn('action != "cancel"', detail)
        self.assertIn("status='open'", detail)
        self.assertIn("sale_id IS NULL AND external_receipt_number IS NULL", detail)
        self.assertNotIn("INSERT INTO sales", detail)
        self.assertNotIn("stock_movements", detail)
        self.assertNotIn("fiscalize_sale(", detail)
        self.assertIn('JSON.stringify({action: "cancel"})', cancel)
        self.assertIn("clearFoodCart();", cancel)
        self.assertIn('if (order.status === "open")', history)
        self.assertIn('cancelFoodOrder(order.id, cancel)', history)
        self.assertIn('foodOrderHistoryNotice', self.read("templates/sales.html"))

    def test_paid_food_refunds_use_linked_sale_and_update_status(self):
        backend = self.read("routes/food_orders.py")
        sales = self.read("routes/sales.py")
        ui = self.read("static/js/food_sales.js")
        shared = self.read("static/js/sales.js")
        html = self.read("templates/sales.html")
        list_route = backend.split('def food_orders():', 1)[1].split(
            '@food_orders_bp.route("/api/food/orders/<int:order_id>"', 1
        )[0]
        refund_route = sales.split("def refund_sale(sale_id):", 1)[1].split(
            '@sales_bp.route("/api/gtin"', 1
        )[0]
        food_refund = ui.split('async function refundPaidFoodOrder(', 1)[1].split(
            'async function cancelFoodOrder(', 1
        )[0]
        self.assertIn("s.is_refunded", list_route)
        self.assertIn("refunded", list_route)
        self.assertIn("LEFT JOIN sales s ON s.id=fo.sale_id AND s.company_id=fo.company_id", list_route)
        self.assertIn("SET status='refunded', updated_at=%s", refund_route)
        self.assertIn("WHERE company_id=%s AND sale_id=%s AND status='paid'", refund_route)
        self.assertIn("await refundSale(Number(order.sale_id), button)", food_refund)
        self.assertNotIn("fetch(", food_refund)
        self.assertIn('"nika:sale-refunded"', ui)
        self.assertIn('"nika:sale-refunded"', shared)
        self.assertIn('className = "food-history-refund"', ui)
        self.assertIn('order.status === "paid" && Number(order.sale_id) > 0', ui)
        self.assertIn('option value="refunded"', html)
        self.assertIn('food-history-badge-refunded', self.read("static/css/food_sales.css"))

    def test_all_edited_python_modules_parse(self):
        for path in ("app.py", "models.py", "routes/auth.py", "routes/sales.py",
                     "routes/food_orders.py", "routes/rekassa_comrun.py"):
            with self.subTest(path=path):
                ast.parse(self.read(path))


if __name__ == "__main__":
    unittest.main()

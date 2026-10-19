"""Regression guards for Kaspi POS payment reconciliation (no database required)."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KaspiPosGuardTests(unittest.TestCase):
    def test_pos_path_never_calls_generic_dispatcher(self):
        js = (ROOT / "static/js/sales.js").read_text(encoding="utf-8-sig")
        start = js.index("function monitorKaspiPayment(checkout)")
        end = js.index("async function waitKaspiPosProcess", start)
        monitor = js[start:end]
        self.assertIn('paymentMethod: "kaspi"', monitor)
        self.assertIn("checkoutCart: checkout.cart", monitor)
        self.assertIn("checkoutClientId: checkout.clientId", monitor)
        self.assertNotIn("\npay();", monitor)
        self.assertIn("setKaspiPosCheckoutLocked(null)", monitor)

    def test_invoice_cannot_start_during_pos_payment(self):
        js = (ROOT / "static/js/sales.js").read_text(encoding="utf-8-sig")
        start = js.index("function createInvoiceSale()")
        end = js.index("let codeReader", start)
        self.assertIn("window.nikaKaspiPosActive || invoiceCreationBusy || salePaymentBusy",
                      js[start:end])

    def test_fiscal_retry_guarded_for_manual_receipt(self):
        retry = (ROOT / "routes/rekassa_comrun.py").read_text()
        self.assertIn('manual.get("manual_fiscalized_at")', retry)
        direct = (ROOT / "routes/rekassa.py").read_text()
        self.assertIn('sale.get("manual_fiscalized_at")', direct)

    def test_reconciliation_keeps_sale_stock_unchanged(self):
        sql = (ROOT / "scripts/reconcile_manual_rekassa_sale_842.sql").read_text()
        self.assertIn("manual_fiscalized_at", sql)
        self.assertIn("is_processed IS DISTINCT FROM TRUE", sql)
        self.assertNotIn("UPDATE items", sql)
        self.assertNotIn("UPDATE stock_movements", sql)
        self.assertNotIn("rekassa_ticket_id = '270766593555'", sql)


if __name__ == "__main__":
    unittest.main()

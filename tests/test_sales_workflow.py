"""Regression checks for configurable sales-only checkout."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SalesWorkflowTests(unittest.TestCase):
    def test_profile_has_two_workflows(self):
        template = (ROOT / "templates/profile.html").read_text()
        self.assertIn('name="sales_workflow"', template)
        self.assertIn('value="sales_only"', template)
        self.assertIn('value="sales_documents"', template)

    def test_default_preserves_existing_documents(self):
        for path in ("app.py", "models.py"):
            self.assertIn("DEFAULT 'sales_documents'", (ROOT / path).read_text())

    def test_invoice_hidden_and_rejected_for_sales_only(self):
        template = (ROOT / "templates/sales.html").read_text()
        self.assertIn("{% if sales_workflow != 'sales_only' %}", template)
        route = (ROOT / "routes/sales.py").read_text()
        self.assertIn('access_row["sales_workflow"] == "sales_only"', route)

    def test_receipts_and_refunds_stay_accessible(self):
        js = (ROOT / "static/js/sales.js").read_text()
        self.assertIn("const nikaSalesDocumentsEnabled", js)
        self.assertIn('openSaleModal(${id})', js)
        self.assertIn('refundSale(${id})', js)
        self.assertIn('const center = nikaSalesDocumentsEnabled ? ', js)


if __name__ == "__main__":
    unittest.main()

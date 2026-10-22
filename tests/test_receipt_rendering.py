"""Receipt regressions: template context, old sales, and Gunicorn schema."""
import ast
from pathlib import Path
import unittest

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]


class ReceiptRenderingTests(unittest.TestCase):
    def test_cash_receipt_renders_tender_and_change(self):
        template = Environment(loader=FileSystemLoader(str(ROOT / "templates"))).get_template("docs/check.html")
        html = template.render(
            company={"name": "Test", "bin": "000000000000", "address": ""},
            sale={"id": 123, "sale_number": 12, "sale_type": "cash",
                  "total_amount": 1650, "cash_amount": 1650,
                  "rekassa_ticket_number": None, "rekassa_qr": None,
                  "kaspi_method": None},
            items=[{"name": "Шаурма", "quantity": 1, "unit": "шт",
                    "price": 1650, "total": 1650, "gtin": "", "ntin": ""}],
            client=None, check_date="22.10.2026 09:30", cash=1650, card=0,
            kaspi=0, cash_received=2000, change_amount=350,
        )
        self.assertIn("Получено", html)
        self.assertIn("2000.00", html)
        self.assertIn("Сдача", html)
        self.assertIn("350.00", html)

    def test_check_route_passes_cash_context_from_saved_sale(self):
        source = (ROOT / "routes/sales.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check")
        render_calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "render_template"
        ]
        self.assertEqual(len(render_calls), 1)
        params = {kw.arg for kw in render_calls[0].keywords}
        self.assertTrue({"cash_received", "change_amount", "cash", "card", "kaspi"} <= params)

    def test_prod_gunicorn_adds_sale_item_type_column(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS item_type TEXT", source)
        self.assertIn("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS modifiers", source)


if __name__ == "__main__":
    unittest.main()

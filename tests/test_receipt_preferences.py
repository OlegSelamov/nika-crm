"""Company-isolated receipt display configuration and language regression."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), undefined=StrictUndefined)

# Exercise the real mapping/function without importing DB or Pillow in CI.
source = ast.parse((ROOT / "services/receipt_settings.py").read_text(encoding="utf8"))
mapping_ast = next(stmt.value for stmt in source.body if isinstance(stmt, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "LABELS" for t in stmt.targets))
LABELS = ast.literal_eval(mapping_ast)
label_node = next(node for node in source.body if isinstance(node, ast.FunctionDef)
                  and node.name == "receipt_label")
namespace = {"LABELS": LABELS}
exec(compile(ast.Module(body=[label_node], type_ignores=[]), str(ROOT), "exec"), namespace)
label = namespace["receipt_label"]


def context(language, *, logo=None, footer=""):
    return {"receipt_preferences": {"language": language, "logo_data_url": logo,
                                    "footer_text": footer},
            "receipt_label": lambda key: label(key, language)}


class ReceiptPreferencesTests(unittest.TestCase):
    def test_all_languages_have_required_labels(self):
        for language, expected in (("ru", "Получено"),
                                   ("kk", "Алынды"),
                                   ("bilingual", "Алынды / Получено")):
            self.assertEqual(label("received", language), expected)
        self.assertEqual(label("shift", "kk"), "Ауысым")
        self.assertEqual(label("receipt", "ru"), "Чек")

    def test_logo_and_kazakh_labels_on_retail_receipt(self):
        html = env.get_template("docs/check.html").render(
            **context("kk", logo="data:image/png;base64,dGVzdA=="),
            company={"name":"Тест","bin":"123456789012","address":""},
            sale={"id":15,"sale_number":2,"sale_type":"cash","total_amount":1500,
                  "rekassa_ticket_number":None,"rekassa_qr":None,"kaspi_method":None},
            items=[{"name":"Нан","quantity":1,"unit":"шт","price":1500,"total":1500,
                    "gtin":None,"ntin":None}],
            client=None, check_date="28.10.2026 12:00",
            cash=1500,card=0,kaspi=0,cash_received=2000,change_amount=500
        )
        self.assertIn('class="receipt-logo"', html)
        self.assertIn("data:image/png;base64,dGVzdA==", html)
        self.assertIn("Алынды", html)
        self.assertIn("Қайтарым", html)
        self.assertNotIn("<span>Получено</span>", html)
        self.assertIn("БСН/ЖСН", html)

    def test_bilingual_food_precheck_and_footer(self):
        html = env.get_template("food_order_ticket.html").render(
            **context("bilingual", footer="Рақмет! Спасибо!"),
            kind="precheck",
            company={"name":"Тест","bin":"123","legal_form":"ip","address":"",
                     "phone":""},
            order={"id":42,"status":"open","cashier_name":"Асем","table_name":"2",
                   "guest_name":"","note":"","total_amount":1200,
                   "planned_payment_method":"cash",
                   "cart":[{"name":"Шай","qty":1,"unit":"шт","price":1200,
                            "line_total":1200,"modifiers":[],"excluded_ingredients":[]}]},
            money=lambda n:str(n),qty_text=str,ticket_date="28.10.26 12:00",
            cash_preview_received=None,cash_preview_change=None,
            request=SimpleNamespace(args={"embed":"1"})
        )
        self.assertIn("Тапсырыс / Заказ №42", html)
        self.assertIn("Төлем / Оплата:", html)
        self.assertIn("Рақмет! Спасибо!", html)
        self.assertNotIn("Приятного аппетита!", html)

    def test_kitchen_is_always_price_free_and_without_logo(self):
        html = env.get_template("food_order_ticket.html").render(
            **context("kk",logo="data:image/png;base64,dGVzdA=="),
            kind="kitchen",
            company={"name":"Тест","bin":"123","legal_form":"ip","address":"",
                     "phone":""},
            order={"id":42,"status":"open","cashier_name":"Асем","table_name":"2",
                   "guest_name":"","note":"","total_amount":1200,
                   "planned_payment_method":"cash",
                   "cart":[{"name":"Шай","qty":1,"unit":"шт","price":1200,
                            "line_total":1200,"modifiers":[],"excluded_ingredients":[]}]},
            money=lambda n:str(n),qty_text=str,ticket_date="28.10.26 12:00",
            cash_preview_received=None,cash_preview_change=None,
            request=SimpleNamespace(args={"embed":"1"})
        )
        self.assertIn("АСҮЙГЕ ТАПСЫРЫС", html)
        self.assertNotIn("1 200 ₸", html)
        self.assertNotIn('class="ticket-logo"', html)

    def test_settings_stay_company_scoped(self):
        backend=(ROOT/"services/receipt_settings.py").read_text(encoding="utf8")
        route=(ROOT/"routes/settings.py").read_text(encoding="utf8")
        self.assertIn("WHERE company_id = %s", backend)
        self.assertIn("ON CONFLICT (company_id)", backend)
        self.assertIn("receipt_preferences_csrf", route)
        self.assertIn("normalize_logo(uploaded_logo)", backend)
        self.assertIn("ImageOps.exif_transpose", backend)
        self.assertIn("MAX_LOGO_UPLOAD", backend)
        self.assertIn("receipt_context(session.get(\"company_id\"))",
                      (ROOT/"routes/sales.py").read_text(encoding="utf8"))
        self.assertIn("receipt_context(company_id)",
                      (ROOT/"routes/food_orders.py").read_text(encoding="utf8"))


if __name__=="__main__":
    unittest.main()

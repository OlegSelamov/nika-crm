"""Render thermal kitchen and guest tickets with real payment state scenarios."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), undefined=StrictUndefined)


def sample_order(**overrides):
    order = {
        "id": 20, "created_at": "2026-10-22T19:46:00",
        "cashier_name": "Асем", "table_name": "5", "guest_name": "Гость",
        "status": "open", "note": "Острый соус отдельно",
        "total_amount": 1550, "payment_method": None,
        "planned_payment_method": "cash",
        "cash_amount": 0, "cash_received": 0, "change_amount": 0,
        "card_amount": 0, "kaspi_amount": 0, "external_receipt_number": None,
        "cart": [
            {"name": "Хот-дог", "qty": 1, "unit": "шт", "price": 1550,
             "line_total": 1550,
             "modifiers": [{"name": "Соус BBQ", "price_delta": 200}],
             "excluded_ingredients": [{"name": "Горчица"}]}
        ]
    }
    order.update(overrides)
    return order


def render(kind, **changes):
    company = {"name": "ИП ТЕСТ", "bin": "123456789012",
               "legal_form": "ip", "address": "Усть-Каменогорск", "phone": "123"}
    return env.get_template("food_order_ticket.html").render(
        order=sample_order(**changes), kind=kind, company=company,
        money=lambda value: f"{float(value):,.0f}".replace(",", " "),
        qty_text=lambda value: str(int(value)) if float(value).is_integer() else str(value),
        ticket_date="22.10.26 19:46", request=SimpleNamespace(args={"embed": "1"})
    )


class FoodTicketLayoutTests(unittest.TestCase):
    def test_jinja_compiles_and_order_information_is_readable(self):
        html = render("precheck")
        for text in ("Заказ №20", "22.10.26 19:46", "Кассир: Асем",
                     "Стол №5", "КВИТАНЦИЯ К ЗАКАЗУ", "Хот-дог",
                     "1 шт", "× 1 550", "+ Соус BBQ", "БЕЗ: Горчица",
                     "ИТОГО К ОПЛАТЕ", "1 550 ₸", "Приятного аппетита!"):
            self.assertIn(text, html)
        self.assertIn("ОЖИДАЕТ ОПЛАТЫ", html)
        self.assertNotIn("Сдача", html)
        self.assertNotIn("Kaspi оплата", html)

    def test_unpaid_precheck_shows_chosen_payment_but_not_paid(self):
        for method, label in (("cash", "Наличные"), ("card", "Карта"), ("kaspi", "Kaspi")):
            with self.subTest(method=method):
                html = render("precheck", planned_payment_method=method)
                self.assertIn("Планируемая оплата", html)
                self.assertIn(label, html)
                self.assertIn("ОЖИДАЕТ ОПЛАТЫ", html)
                self.assertNotIn("КВИТАНЦИЯ ОБ ОПЛАТЕ", html)

    def test_paid_cash_displays_received_and_correct_change(self):
        html = render("precheck", status="paid", payment_method="cash",
                      cash_amount=1550, cash_received=2000, change_amount=450)
        for text in ("КВИТАНЦИЯ ОБ ОПЛАТЕ", "Наличные", "Получено",
                     "2 000 ₸", "Сдача", "450 ₸"):
            self.assertIn(text, html)
        self.assertNotIn("ОЖИДАЕТ ОПЛАТЫ", html)

    def test_paid_card_and_kaspi_are_distinct(self):
        card = render("precheck", status="paid", payment_method="card", card_amount=1550)
        kaspi = render("precheck", status="paid", payment_method="kaspi", kaspi_amount=1550)
        self.assertIn("Оплата картой", card)
        self.assertNotIn("Kaspi оплата", card)
        self.assertIn("Kaspi оплата", kaspi)
        self.assertNotIn("Оплата картой", kaspi)

    def test_kitchen_ticket_is_large_and_never_prints_guest_prices(self):
        html = render("kitchen", status="paid", payment_method="cash",
                      cash_received=2000, change_amount=450)
        for text in ("ЗАКАЗ НА КУХНЮ", "Кассир: Асем", "Стол №5",
                     "1 шт", "+ Соус BBQ", "БЕЗ: Горчица", "Комментарий:"):
            self.assertIn(text, html)
        for absent in ("1 550 ₸", "ИТОГО К ОПЛАТЕ", "Сдача", "Наличные",
                       "КВИТАНЦИЯ ОБ ОПЛАТЕ"):
            self.assertNotIn(absent, html)
        self.assertIn(".kitchen-ticket .item-name { font-size: 14px; font-weight: 600; }", html)
        self.assertEqual(html.count("1 шт"), 1, "Кол-во на кухне должно быть только один раз")
        self.assertNotIn("×1", html)
        self.assertNotIn('class="item-meta"', html)
        self.assertIn('class="item-qty"', html)

    def test_compact_typography_is_not_all_bold(self):
        for kind in ("kitchen", "precheck"):
            html = render(kind)
            self.assertIn("font: 400 13px/1.3 Arial", html)
            self.assertIn(".item-mod { font-size: 12.5px;", html)
            self.assertNotIn("font-weight: 900", html)
            self.assertNotIn("font-weight: 800", html)
            self.assertIn('class="item-head"', html)
        guest = render("precheck")
        self.assertEqual(guest.count("1 шт"), 1, "Гостю единица количества нужна только один раз")
        self.assertIn('class="item-meta"', guest)
        self.assertNotIn('class="item-qty"', guest)

    def test_external_payment_is_not_mislabelled_as_kaspi(self):
        html = render("precheck", status="external_paid", external_receipt_number="K-125")
        self.assertIn("ОПЛАЧЕНО ЧЕРЕЗ ВНЕШНЮЮ ККМ", html)
        self.assertIn("Чек №K-125", html)
        self.assertNotIn("Kaspi оплата", html)

    def test_server_uses_persisted_payment_not_untrusted_browser_values(self):
        source = (ROOT / "routes/food_orders.py").read_text(encoding="utf-8")
        ast.parse(source)
        for token in ("fo.created_by", "u.full_name", "s.sale_type AS payment_method",
                      "s.cash_received", "s.change_amount", "s.card_amount", "s.kaspi_amount",
                      "money=receipt_money", "ticket_date="):
            self.assertIn(token, source)
        self.assertIn('WHERE fo.id=%s AND fo.company_id=%s', source)


if __name__ == "__main__":
    unittest.main()

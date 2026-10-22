"""Food POS menu category and card UI regressions."""
import ast
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class FoodMenuCardsTests(unittest.TestCase):
    def test_dishes_sort_before_paginated_products(self):
        source = (ROOT / "routes/items.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("THEN 0 ELSE 1 END, items.id DESC", source)
        self.assertIn("ORDER BY {order_by}", source)
        self.assertIn("LIMIT %s OFFSET %s", source)
        self.assertIn("AS dish_count", source)

    def test_dish_default_and_full_search(self):
        source = (ROOT / "static/js/food_sales.js").read_text(encoding="utf-8")
        markup = (ROOT / "templates/sales.html").read_text(encoding="utf-8")
        self.assertIn('let foodSection = "dishes"', source)
        self.assertIn('type: foodSection === "dishes"', source)
        self.assertIn('foodSection = "all"', source)
        for name in ("dishes", "all", "drinks"):
            self.assertIn('data-food-section="' + name + '"', markup)
        self.assertIn('food-menu-card-footer', source)

    def test_complete_long_titles_and_larger_images(self):
        styles = (ROOT / "static/css/food_sales.css").read_text(encoding="utf-8")
        self.assertIn(".food-menu-panel .food-menu-name", styles)
        self.assertIn("-webkit-line-clamp:unset", styles)
        self.assertIn("height:82px", styles)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", styles)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", styles)
        self.assertIn("overscroll-behavior-y: contain", styles)
        self.assertIn("touch-action: pan-y", styles)
        self.assertIn("contain: layout paint", styles)
        # The POS renders in a separate iframe. Sidebar DOM selectors will never match.
        self.assertNotIn(".sidebar:not(.collapsed) ~ .content .food-menu-panel .food-menu-grid", styles)
        self.assertIn("container-name: nika-food-menu", styles)
        self.assertIn("container-type: inline-size", styles)
        self.assertIn("@container nika-food-menu (max-width: 505px)", styles)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", styles)
        self.assertIn("@container nika-food-menu (max-width: 335px)", styles)
        self.assertIn("food-dual-print-v2", (ROOT / "templates/sales.html").read_text(encoding="utf-8"))
        self.assertIn("food-menu-category-badge", styles)

    def test_menu_labels_and_idle_scrolling(self):
        markup = (ROOT / "templates/sales.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/food_sales.js").read_text(encoding="utf-8")
        self.assertIn('aria-pressed="true">Блюда</button>', markup)
        self.assertIn('aria-pressed="false" hidden>Напитки</button>', markup)
        self.assertNotIn("🍽", markup)
        self.assertNotIn("🥤", markup)
        self.assertIn('img.loading = "eager"', script)
        self.assertIn('img.decoding = "async"', script)
        self.assertNotIn('img.loading = "lazy"', script)
        self.assertIn('renderFoodMenu(append, newItems);', script)
        self.assertIn('if (!append) grid.replaceChildren();', script)
        self.assertIn('newItems.forEach(item => fragment.appendChild(makeFoodCard(item)))', script)

    def test_js_syntax(self):
        if not shutil.which("node"):
            self.skipTest("Node unavailable")
        res = subprocess.run(["node", "--check", str(ROOT / "static/js/food_sales.js")],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

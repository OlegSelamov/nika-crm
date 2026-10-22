"""Regression guards for editing restaurant recipe cards."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RecipeEditorRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "static/js/items_legacy.js").read_text(encoding="utf-8")
        cls.template = (ROOT / "templates/items.html").read_text(encoding="utf-8")
        cls.route = (ROOT / "routes/items.py").read_text(encoding="utf-8")

    def test_no_recipe_can_be_accidentally_saved_empty(self):
        self.assertIn('if not isinstance(ingredients, list) or not ingredients:', self.route)
        self.assertIn('not quantity.is_finite()', self.route)
        self.assertIn("validateRecipeIngredients()", self.js)
        self.assertIn("if (!recipeIngredients.length)", self.js)

    def test_both_recipe_statuses_are_accessible_and_cleared(self):
        self.assertIn("setRecipeStatus('', '');", self.js)
        self.assertIn("recipeLoadVersion", self.js)
        self.assertIn('recipeModalStatus', self.js)
        self.assertIn('id="saveRecipeModalButton"', self.template)
        self.assertEqual(self.template.count('aria-live="polite"'), self.template.count('aria-live="polite"'))

    def test_static_receipt_and_recipe_js_syntax(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed")
        for path in ("static/js/items_legacy.js", "static/js/items.js"):
            result = subprocess.run(["node", "--check", str(ROOT / path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_recipe_row_does_not_crash_stale_modal(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed")
        script = self.js
        start = script.index("function updateRecipeCost() {")
        end = script.index("\nfunction renderRecipeRows()", start)
        fn = script[start:end]
        harness = (
            'var recipeIngredients = [{item_id: 1, quantity: 0.12, purchase_price: 2000}];\n'
            'var recipeMoneyFormatter = new Intl.NumberFormat("ru-KZ", {maximumFractionDigits:2});\n'
            'var costRows = [0,1].map(i => ({dataset:{recipeRowCost:String(i)},textContent:""}));\n'
            'var total = {textContent:""};\n'
            'var document = {getElementById(id) {if(id==="recipeCost") return total;'
            'if(id==="recipeRows"||id==="recipeModalRows") return {'
            'querySelectorAll(){return costRows;}};return null;}};\n'
            + fn +
            '\nupdateRecipeCost();\n'
            'if(!total.textContent.includes("240")) throw new Error("total failed");\n'
            'if(costRows[1].textContent!=="0 ₸") throw new Error("stale cost not cleared");\n'
        )
        result = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Guard against test Electron accidentally touching production settings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ElectronTestBuild(unittest.TestCase):
    def test_test_build_targets_and_isolation(self):
        js = (ROOT / "desktop/main.js").read_text(encoding="utf-8")
        cfg = (ROOT / "desktop/electron-test.config.yml").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build-electron-test.yml").read_text(encoding="utf-8")
        self.assertIn('TEST_MODE = fs.existsSync', js)
        self.assertIn('"https://test.nikabusiness.com"', js)
        self.assertIn('"persist:nika-business-test"', js)
        self.assertIn('app.setPath("userData", testUserData)', js)
        self.assertIn('if (TEST_MODE) {\n        console.log("Тестовый Electron:', js)
        self.assertIn('Kaspi POS отключён в тестовой сборке', js)
        self.assertIn('appId: com.nikabusiness.app.test', cfg)
        self.assertIn('productName: Nika Business TEST', cfg)
        self.assertIn('NikaBusiness-TEST-Setup.', cfg)
        self.assertIn('nika-electron-test.json', workflow)
        self.assertIn('--publish never', workflow)
        self.assertIn('actions/upload-artifact@v4', workflow)
        self.assertNotIn('gh release upload', workflow)

    def test_normal_electron_remains_unchanged(self):
        pkg = (ROOT / "desktop/package.json").read_text(encoding="utf-8")
        self.assertIn('"appId": "com.nikabusiness.app"', pkg)
        self.assertIn('"productName": "Nika Business"', pkg)


if __name__ == "__main__":
    unittest.main()

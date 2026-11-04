"""Offline tests: auto-load existing accounting figures, never invent an ISNA FNO."""
import unittest

from services.isna_auto_reporting import (
    AutomaticFnoError, NOT_MAPPED_CODE, build_accounting_fno_snapshot,
)

COMPANY = {"name": "TEST TOO", "bin": "000000000000"}


def report_910():
    return {
        "form_type": "910", "ready": True,
        "period_label": "I полугодие 2026", "checks": [{"ok": True}],
        "income": 125000, "refunds": 5000,
        "taxable_income": 120000, "rate": 4,
        "tax_amount": 4800,
        "months": [{"period": "2026-01", "income": 125000, "refunds": 5000,
                    "taxable_income": 120000}],
    }


def report_200():
    return {
        "form_type": "200", "ready": True,
        "period_label": "2 квартал 2026",
        "employee_count": 2,
        "totals": {"salary": 780000, "opv": 78000, "vosms": 15600,
                   "ipn": 32000, "so": 39000, "osms": 23400, "opvr": 19500},
        "months": [{"period": "2026-04", "salary": 260000,
                    "opv": 26000, "vosms": 5200, "ipn": 10000,
                    "so": 13000, "osms": 7800, "opvr": 6500}],
    }


class AccountingAutoFnoTests(unittest.TestCase):
    def test_910_from_current_organization_without_manual_json(self):
        data = build_accounting_fno_snapshot(
            company=COMPANY, report=report_910(), year=2026, period="1",
        )
        self.assertTrue(data["sourceLoaded"])
        self.assertEqual(data["source"], "nika-business-accounting")
        self.assertEqual(data["formCode"], "910.00")
        self.assertEqual(data["summary"]["taxAmount"], "4800")
        self.assertEqual(data["summary"]["taxableIncome"], "120000")
        self.assertFalse(data["officialMappingReady"])
        self.assertFalse(data["readyToSign"])
        self.assertFalse(data["readyToSubmit"])
        self.assertIsNone(data["unsignedXml"])
        self.assertEqual(data["blockCode"], NOT_MAPPED_CODE)
        self.assertNotIn("fnoDto", data)
        self.assertNotIn("signature", data)
        self.assertNotIn("signedXml", data)
        self.assertEqual(len(data["sourceSha256"]), 64)

    def test_200_from_existing_payroll(self):
        data = build_accounting_fno_snapshot(
            company=COMPANY, report=report_200(), year=2026, period="2",
        )
        self.assertEqual(data["formCode"], "200.00")
        self.assertEqual(data["summary"]["employeeCount"], 2)
        self.assertEqual(data["summary"]["salary"], "780000")
        self.assertFalse(data["readyToSign"])
        self.assertTrue(any("ИИН" in issue for issue in data["issues"]))

    def test_fail_closed_on_invalid_period_and_missing_bin(self):
        with self.assertRaises(AutomaticFnoError):
            build_accounting_fno_snapshot(
                company=COMPANY, report=report_910(), year=2026, period="3",
            )
        with self.assertRaises(AutomaticFnoError):
            build_accounting_fno_snapshot(
                company=COMPANY, report=report_200(), year=2026, period="5",
            )
        data = build_accounting_fno_snapshot(
            company={"name": "TEST TOO", "bin": "wrong"},
            report=report_910(), year=2026, period="2",
        )
        self.assertTrue(any("БИН" in issue for issue in data["issues"]))
        self.assertFalse(data["readyToSubmit"])

    def test_unready_calculation_never_becomes_filable(self):
        report = report_910()
        report["ready"] = False
        report["checks"] = [{"ok": False, "message": "Проверьте налоговую ставку"}]
        data = build_accounting_fno_snapshot(
            company=COMPANY, report=report, year=2026, period="1",
        )
        self.assertFalse(data["sourceCalculationReady"])
        self.assertIn("Проверьте налоговую ставку", data["issues"])

    def test_invalid_financial_data_rejected(self):
        report = report_910()
        report["income"] = "NaN"
        with self.assertRaises(AutomaticFnoError):
            build_accounting_fno_snapshot(
                company=COMPANY, report=report, year=2026, period="1",
            )

    def test_snapshot_digest_changes_when_figures_change(self):
        left = build_accounting_fno_snapshot(
            company=COMPANY, report=report_910(), year=2026, period="1",
        )
        new_report = report_910()
        new_report["tax_amount"] = 4801
        right = build_accounting_fno_snapshot(
            company=COMPANY, report=new_report, year=2026, period="1",
        )
        self.assertNotEqual(left["sourceSha256"], right["sourceSha256"])


if __name__ == "__main__":
    unittest.main()

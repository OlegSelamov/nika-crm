"""Auto-prefill ISNA from Nika Business' existing accounting reports.

NO user-pasted JSON and NO fabricated fnoDto fields. This is a read-only
source snapshot: the provider's exact, versioned FNO JSON schema / FLC
has not yet been integrated. This module must never silently claim an
internal report is a submittable FNO.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SUPPORTED_FORMS = frozenset({"910", "200"})
NOT_MAPPED_CODE = "OFFICIAL_FNO_JSON_MAPPING_NOT_VERIFIED"


class AutomaticFnoError(ValueError):
    pass


def _number(value) -> str:
    """Lossless, canonical decimal for a source snapshot. No float rounding."""
    try:
        amount = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError, TypeError):
        raise AutomaticFnoError("В отчёте обнаружена некорректная сумма.") from None
    if not amount.is_finite():
        raise AutomaticFnoError("В отчёте обнаружена неконечная сумма.")
    return format(amount, "f")


def _period_check(form_type: str, period: str) -> bool:
    return (period in {"1", "2"} if form_type == "910"
            else period in {"1", "2", "3", "4"})


def build_accounting_fno_snapshot(*, company: dict, report: dict,
                                  year: int, period: str) -> dict:
    """Return an authenticated, tenant-scoped, automatically populated preview.

    The caller MUST independently enforce session + active company + TEST mode.
    This function NEVER returns an officially signed-ready FNO JSON/XML.
    """
    code = str(report.get("form_type") or "")
    if code not in SUPPORTED_FORMS:
        raise AutomaticFnoError("Форма не поддерживается.")
    if not isinstance(year, int) or not 2025 <= year <= 2100:
        raise AutomaticFnoError("Неверный отчётный год.")
    period = str(period)
    if not _period_check(code, period):
        raise AutomaticFnoError("Неверный период ФНО.")
    if not isinstance(company, dict) or not isinstance(report, dict):
        raise AutomaticFnoError("Нет данных организации или отчёта.")

    bin_value = re.sub(r"\s", "", str(company.get("bin") or ""))
    name = str(company.get("name") or "").strip()
    issues = []
    if not re.fullmatch(r"\d{12}", bin_value):
        issues.append("У активной организации отсутствует корректный 12-значный БИН/ИИН.")
    if not name:
        issues.append("Не заполнено название организации.")
    if not report.get("ready"):
        issues.extend(str(c.get("message") or c.get("label") or "Не заполнены данные.")
                      for c in report.get("checks", []) if not c.get("ok"))
        if not report.get("checks"):
            issues.append("Бухгалтерский расчёт не прошёл предварительную проверку.")

    details = {}
    if code == "910":
        details = {
            "income": _number(report.get("income")),
            "refunds": _number(report.get("refunds")),
            "taxableIncome": _number(report.get("taxable_income")),
            "rate": _number(report.get("rate")),
            "taxAmount": _number(report.get("tax_amount")),
            "months": [
                {
                    "period": str(x.get("period", "")),
                    "income": _number(x.get("income")),
                    "refunds": _number(x.get("refunds")),
                    "taxableIncome": _number(x.get("taxable_income")),
                } for x in report.get("months", [])
            ],
        }
        issues.append(
            "Доход пока рассчитан по продажам Nika; проверьте прочие поступления "
            "и применимость СНР/ставки для выбранного периода."
        )
        issues.append(
            "В текущей 910.00 нет полного расчёта по работникам и всех приложений ФНО."
        )
    else:
        totals = report.get("totals") or {}
        keys = ("salary", "opv", "vosms", "ipn", "so", "osms", "opvr")
        details = {
            "employeeCount": int(report.get("employee_count") or 0),
            "totals": {key: _number(totals.get(key)) for key in keys},
            "months": [
                {
                    "period": str(x.get("period", "")),
                    **{key: _number(x.get(key)) for key in keys},
                } for x in report.get("months", [])
            ],
        }
        issues.append(
            "Нужны проверенные ИИН работников, помесячные данные и полный "
            "официальный состав приложений 200.00."
        )

    snapshot = {
        "source": "nika-business-accounting",
        "formType": code,
        "formCode": code + ".00",
        "year": year,
        "period": period,
        "periodLabel": str(report.get("period_label") or ""),
        "company": {"name": name, "bin": bin_value},
        "details": details,
    }
    digest = hashlib.sha256(json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest().upper()
    return {
        "source": "nika-business-accounting",
        "sourceLoaded": True,
        "sourceCalculationReady": bool(report.get("ready")),
        "companyName": name,
        "companyBin": bin_value,
        "formCode": code + ".00",
        "year": year,
        "period": period,
        "periodLabel": snapshot["periodLabel"],
        "summary": (
            {"income": details["income"], "refunds": details["refunds"],
             "taxableIncome": details["taxableIncome"],
             "taxAmount": details["taxAmount"]}
            if code == "910" else
            {"employeeCount": details["employeeCount"],
             "salary": details["totals"]["salary"],
             "ipn": details["totals"]["ipn"]}
        ),
        "sourceSha256": digest,
        "issues": issues,
        "officialMappingReady": False,
        "officialContractValidated": False,
        "readyToSign": False,
        "readyToSubmit": False,
        "unsignedXml": None,
        "blockCode": NOT_MAPPED_CODE,
        "message": (
            "Данные ФНО автоматически прочитаны из бухгалтерии Nika Business. "
            "Подпись и отправка закрыты, пока не реализованы официальный "
            "JSON fnoDto для формы/периода и полный ФЛК."
        ),
    }

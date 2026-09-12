"""Helpers for product identifiers returned by barcode and DataMatrix scanners."""

from dataclasses import dataclass
import re


_LEADING_CONTROL_CHARS = re.compile(r"^[\x00-\x20\x7f]+")
_AIM_PREFIX = re.compile(r"^\][A-Za-z0-9]{2}")
_PARENTHESIZED_GTIN = re.compile(r"^\(01\)(\d{14})")
_COMPACT_GTIN = re.compile(r"^01(\d{14})")


@dataclass(frozen=True)
class ScannedProductCode:
    raw: str
    payload: str
    gtin: str | None
    ean13: str | None
    marking_code: str | None

    @property
    def lookup_code(self) -> str:
        return self.ean13 or self.gtin or self.payload

    @property
    def lookup_candidates(self) -> tuple[str, ...]:
        values = (
            (self.ean13, self.gtin)
            if self.gtin
            else (self.payload,)
        )
        return tuple(dict.fromkeys(value for value in values if value))

    @property
    def is_marking_code(self) -> bool:
        return self.marking_code is not None


def parse_scanned_product_code(value) -> ScannedProductCode:
    """Extract GTIN/EAN used for lookup while retaining the marking payload.

    GS1 DataMatrix normally begins with application identifier 01 followed by
    a 14-digit GTIN. Scanners may also prepend the AIM identifier ``]d2``.
    """

    raw = str(value or "").strip()
    payload = _LEADING_CONTROL_CHARS.sub("", raw)
    payload = _AIM_PREFIX.sub("", payload, count=1)
    payload = _LEADING_CONTROL_CHARS.sub("", payload)

    match = _PARENTHESIZED_GTIN.match(payload) or _COMPACT_GTIN.match(payload)
    gtin = match.group(1) if match else None
    ean13 = gtin[1:] if gtin and gtin.startswith("0") else None
    marking_code = payload if match and len(payload) > match.end() else None

    return ScannedProductCode(
        raw=raw,
        payload=payload,
        gtin=gtin,
        ean13=ean13,
        marking_code=marking_code,
    )

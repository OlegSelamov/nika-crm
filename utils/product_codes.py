"""Helpers for product identifiers returned by barcode and DataMatrix scanners."""

from dataclasses import dataclass
import re


# ASCII GS (0x1D) is meaningful inside a GS1 DataMatrix and MUST survive.
# Strip keyboard/scanner transport controls around the payload, but never GS.
_LEADING_TRANSPORT_CHARS = re.compile(r"^[\x00-\x1c\x1e-\x20\x7f]+")
_TRAILING_TRANSPORT_CHARS = re.compile(r"[\x00-\x1c\x1e-\x20\x7f]+$")
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


def normalize_scanned_payload(value) -> str:
    """Return scanner payload without keyboard/AIM framing.

    Internal ASCII Group Separator (0x1D) bytes are preserved verbatim.
    JSON transports them as a Unicode escape and restores them on receipt.
    """
    raw = "" if value is None else str(value)
    payload = _LEADING_TRANSPORT_CHARS.sub("", raw)
    payload = _AIM_PREFIX.sub("", payload, count=1)
    payload = _LEADING_TRANSPORT_CHARS.sub("", payload)
    payload = _TRAILING_TRANSPORT_CHARS.sub("", payload)
    return payload


def parse_scanned_product_code(value) -> ScannedProductCode:
    """Extract GTIN/EAN for lookup while retaining the complete DataMatrix.

    GS1 DataMatrix normally begins with AI 01 + a 14-digit GTIN. Hardware
    scanners may prepend an AIM identifier such as ]d2. We remove only
    scanner framing and keep every internal ASCII 29 separator and crypto tail.
    """

    raw = "" if value is None else str(value)
    payload = normalize_scanned_payload(raw)

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

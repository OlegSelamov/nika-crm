"""Canonical Kazakhstan measurement units used by Nika integrations."""

UNIT_CODES = {
    "шт": "796",
    "кг": "166",
    "г": "163",
    "мг": "161",
    "л": "112",
    "мл": "111",
    "м": "006",
    "м²": "055",
    "м³": "113",
    "час": "356",
    "день": "359",
    "месяц": "362",
    "год": "366",
    "пар": "715",
    "услуга": "5114",
    "порция": "796",
}

ALIASES = {
    "шт.": "шт", "штука": "шт", "штук": "шт",
    "килограмм": "кг", "грамм": "г", "гр": "г", "миллиграмм": "мг",
    "литр": "л", "миллилитр": "мл",
    "метр": "м", "м2": "м²", "кв.м": "м²", "м3": "м³", "куб.м": "м³",
    "ч": "час", "сут": "день", "сутки": "день", "мес": "месяц",
    "пара": "пар", "порц": "порция", "порц.": "порция", "услуги": "услуга", "одна услуга": "услуга",
}

def normalize_unit(unit, item_type=None):
    raw = str(unit or "").strip().lower().replace("ё", "е")
    raw = ALIASES.get(raw, raw)
    if item_type == "service" and not raw:
        return "услуга"
    return raw if raw in UNIT_CODES else "шт"

def measure_code(unit, item_type=None):
    return UNIT_CODES[normalize_unit(unit, item_type)]

def rekassa_unit(unit, item_type=None):
    normalized = normalize_unit(unit, item_type)
    # UNIT_TYPE is auxiliary; classifier code is authoritative.
    unit_type = "PIECE" if normalized == "шт" else "OTHER"
    return measure_code(normalized, item_type), unit_type

"""Company-specific receipt branding and language for Nika Business.

Preferences are stored in PostgreSQL rather than local/static files, so a
company's checkout, PDF output and all Electron workstations agree.
Fiscal payloads, fiscal QR codes and tax labels are not altered here.
"""
import base64
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from models import get_db, pool

LANGUAGES = {"ru", "kk", "bilingual"}
MAX_LOGO_UPLOAD = 1024 * 1024
DEFAULTS = {"language": "ru", "footer_text": "", "show_logo": True, "logo_data_url": None,
            "logo_preview_data_url": None}

# (Kazakh, Russian). Full bilingual strings remain legible on 58mm paper.
LABELS = {
    "receipt": ("Түбіртек", "Чек"),
    "order": ("Тапсырыс", "Заказ"),
    "cashier": ("Кассир", "Кассир"),
    "table": ("Үстел", "Стол"),
    "guest": ("Қонақ", "Гость"),
    "kitchen_order": ("АСҮЙГЕ ТАПСЫРЫС", "ЗАКАЗ НА КУХНЮ"),
    "payment_receipt": ("ТӨЛЕМ ТҮБІРТЕГІ", "КВИТАНЦИЯ ОБ ОПЛАТЕ"),
    "order_receipt": ("ТАПСЫРЫС ТҮБІРТЕГІ", "КВИТАНЦИЯ К ЗАКАЗУ"),
    "without": ("ҚОСПАҢЫЗ", "БЕЗ"),
    "comment": ("Түсініктеме", "Комментарий"),
    "total_to_pay": ("ТӨЛЕНЕТІН СОМА", "ИТОГО К ОПЛАТЕ"),
    "total": ("БАРЛЫҒЫ", "ИТОГО"),
    "paid": ("ТӨЛЕНДІ", "ОПЛАЧЕНО"),
    "external_paid": ("СЫРТҚЫ ККМ АРҚЫЛЫ ТӨЛЕНДІ", "ОПЛАЧЕНО ЧЕРЕЗ ВНЕШНЮЮ ККМ"),
    "payment": ("Төлем", "Оплата"),
    "cash": ("Қолма-қол", "Наличные"),
    "card": ("Карта", "Карта"),
    "bank_card": ("Банк картасы", "Банковская карта"),
    "card_payment": ("Картамен төлем", "Оплата картой"),
    "kaspi_payment": ("Kaspi арқылы төлем", "Kaspi оплата"),
    "received": ("Алынды", "Получено"),
    "change": ("Қайтарым", "Сдача"),
    "thanks": ("Сатып алғаныңызға рақмет!", "Спасибо за покупку"),
    "bon_appetit": ("Асыңыз дәмді болсын!", "Приятного аппетита!"),
    "iin": ("ЖСН", "ИИН"),
    "bin": ("БСН", "БИН"),
    "bin_iin": ("БСН/ЖСН", "БИН/ИИН"),
    "phone": ("Тел.", "Тел."),
    "sale": ("Сату", "Продажа"),
    "shift": ("Ауысым", "Смена"),
    "buyer": ("Сатып алушы", "Покупатель"),
    "paid_amount": ("Төленді", "Оплачено"),
    "type": ("Түрі", "Тип"),
    "refund_receipt": ("ҚАЙТАРУ ТҮБІРТЕГІ", "ЧЕК ВОЗВРАТА"),
    "refund_income": ("ТАУАР ҚАЙТАРУ", "ВОЗВРАТ ПРИХОДА"),
    "refund": ("ҚАЙТАРУ", "ВОЗВРАТ"),
    "sale_date": ("Сату күні", "Дата продажи"),
    "refund_date": ("Қайтару күні", "Дата возврата"),
    "method": ("Тәсіл", "Способ"),
    "fiscal_document": ("Фискалдық құжат", "Фискальный документ"),
    "refund_done": ("Қайтару орындалды", "Возврат выполнен"),
    "refund_transaction": ("Қайтару транзакциясы", "Транзакция возврата"),
    "fiscal_refund": ("ФИСКАЛДЫҚ ЧЕК reKassa", "ФИСКАЛЬНЫЙ ЧЕК reKassa"),
}


def receipt_label(code, language="ru"):
    kk, ru = LABELS[code]
    if language == "kk":
        return kk
    if language == "bilingual" and kk != ru:
        return kk + " / " + ru
    return ru


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_receipt_settings (
            company_id INTEGER PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'ru',
            footer_text VARCHAR(160) NOT NULL DEFAULT '',
            show_logo BOOLEAN NOT NULL DEFAULT TRUE,
            logo_png BYTEA,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _read_settings(company_id, *, include_logo=True):
    if not company_id:
        return dict(DEFAULTS)
    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        conn.commit()  # Startup under Gunicorn does not invoke models.init_db().
        cur.execute("""
            SELECT language, footer_text, show_logo, logo_png
            FROM company_receipt_settings
            WHERE company_id = %s
        """, (company_id,))
        row = cur.fetchone()
        if not row:
            return dict(DEFAULTS)
        config = {
            "language": row["language"] if row["language"] in LANGUAGES else "ru",
            "footer_text": row["footer_text"] or "",
            "show_logo": bool(row["show_logo"]),
            "logo_data_url": None,
            "logo_preview_data_url": None,
        }
        if include_logo and row["logo_png"]:
            png = bytes(row["logo_png"])
            data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            config["logo_preview_data_url"] = data_url
            if config["show_logo"]:
                config["logo_data_url"] = data_url
        return config
    finally:
        pool.putconn(conn)


def get_receipt_settings(company_id):
    return _read_settings(company_id)


def receipt_context(company_id):
    prefs = get_receipt_settings(company_id)
    language = prefs["language"]
    return {
        "receipt_preferences": prefs,
        "receipt_label": lambda code: receipt_label(code, language),
    }


def normalize_logo(upload):
    """Validate a small image and convert it to a compact RGB grayscale PNG.

    Never store uploaded SVG/HTML or unbounded dimensions in a receipt.
    """
    raw = upload.stream.read(MAX_LOGO_UPLOAD + 1)
    if not raw or len(raw) > MAX_LOGO_UPLOAD:
        raise ValueError("Логотип должен быть изображением PNG, JPG или WebP до 1 МБ")
    try:
        source = Image.open(BytesIO(raw))
        if source.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Поддерживаются только PNG, JPG и WebP")
        source.verify()
        source = Image.open(BytesIO(raw))
        if source.width * source.height > 8_000_000:
            raise ValueError("Слишком большое разрешение логотипа")
        source = ImageOps.exif_transpose(source)
        source.thumbnail((420, 160), Image.Resampling.LANCZOS)
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        output = BytesIO()
        background.convert("L").save(output, format="PNG", optimize=True)
        return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Файл не является корректным изображением") from error


def save_receipt_settings(company_id, *, language, footer_text, show_logo,
                          uploaded_logo=None, remove_logo=False):
    if language not in LANGUAGES:
        raise ValueError("Выберите доступный язык чека")
    footer_text = (footer_text or "").strip()
    if len(footer_text) > 160:
        raise ValueError("Текст внизу чека — не более 160 символов")
    logo = normalize_logo(uploaded_logo) if uploaded_logo and uploaded_logo.filename else None
    conn = get_db()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        cur.execute("""
            INSERT INTO company_receipt_settings
                (company_id, language, footer_text, show_logo, logo_png)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE SET
                language=EXCLUDED.language,
                footer_text=EXCLUDED.footer_text,
                show_logo=EXCLUDED.show_logo,
                logo_png=CASE
                    WHEN %s THEN NULL
                    WHEN %s THEN EXCLUDED.logo_png
                    ELSE company_receipt_settings.logo_png
                END,
                updated_at=NOW()
        """, (company_id, language, footer_text, show_logo, logo,
              remove_logo, logo is not None))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

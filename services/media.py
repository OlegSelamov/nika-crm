import io
import mimetypes
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import boto3
from PIL import Image, ImageOps
from botocore.config import Config
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

ALLOWED_FILE_EXTENSIONS = {"pdf","doc","docx","xls","xlsx","ppt","pptx","jpg","jpeg","png","webp"}
MAX_FILE_UPLOAD_BYTES = int(os.getenv("MEDIA_MAX_FILE_UPLOAD_MB", "30")) * 1024 * 1024
MAX_UPLOAD_BYTES = int(os.getenv("MEDIA_MAX_UPLOAD_MB", "15")) * 1024 * 1024
MAX_IMAGE_SIDE = int(os.getenv("MEDIA_MAX_IMAGE_SIDE", "1600"))
WEBP_QUALITY = int(os.getenv("MEDIA_WEBP_QUALITY", "82"))
_R2_CLIENT = None


def _backend():
    return (os.getenv("MEDIA_BACKEND") or "local").strip().lower()


def _public_base():
    return (os.getenv("R2_PUBLIC_BASE_URL") or "").rstrip("/")


def _r2_ready():
    return all(
        (os.getenv(name) or "").strip()
        for name in (
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET",
            "R2_PUBLIC_BASE_URL",
        )
    )


def _r2_client():
    global _R2_CLIENT
    if _R2_CLIENT is None:
        _R2_CLIENT = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=2,
                read_timeout=8,
                max_pool_connections=20,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
    return _R2_CLIENT


def _normalized_image(file_storage):
    filename = secure_filename(file_storage.filename or "")
    if "." not in filename:
        raise ValueError("Не удалось определить формат изображения.")

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Разрешены только JPG, JPEG, PNG и WEBP.")

    file_storage.stream.seek(0)
    raw = file_storage.stream.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"Изображение слишком большое. Максимум {MAX_UPLOAD_BYTES // 1024 // 1024} МБ."
        )

    try:
        image = Image.open(io.BytesIO(raw))

        if (
            (image.format or "").upper() == "WEBP"
            and image.width <= MAX_IMAGE_SIDE
            and image.height <= MAX_IMAGE_SIDE
        ):
            return raw, "image/webp", "webp"

        image = ImageOps.exif_transpose(image)
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)

        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")

        output = io.BytesIO()
        image.save(
            output,
            format="WEBP",
            quality=WEBP_QUALITY,
            method=2,
        )
        return output.getvalue(), "image/webp", "webp"
    except Exception as exc:
        raise ValueError("Файл не удалось обработать как изображение.") from exc

def _key(company_id, namespace, ext="webp", name=None):
    safe_namespace = "/".join(
        part for part in str(namespace or "misc").strip("/").split("/") if part
    )
    safe_name = secure_filename(str(name or "")) or uuid.uuid4().hex
    if "." in safe_name:
        safe_name = safe_name.rsplit(".", 1)[0]
    return f"companies/{int(company_id)}/{safe_namespace}/{safe_name}.{ext}"


def upload_image(file_storage, *, company_id, namespace, name=None):
    """Store an uploaded image and return the URL saved in business tables.

    R2 is used when MEDIA_BACKEND=r2 and all R2 settings are present.
    Otherwise local storage remains a safe fallback, so enabling cloud storage
    never blocks the current production workflow.
    """
    if not file_storage or not file_storage.filename:
        return None

    payload, content_type, ext = _normalized_image(file_storage)
    object_key = _key(company_id, namespace, ext=ext, name=name)

    if _backend() == "r2":
        if not _r2_ready():
            if (os.getenv("MEDIA_ALLOW_LOCAL_FALLBACK") or "true").lower() != "true":
                raise RuntimeError("R2 не настроен полностью.")
        else:
            _r2_client().put_object(
                Bucket=os.environ["R2_BUCKET"],
                Key=object_key,
                Body=payload,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
            return f"{_public_base()}/{object_key}"

    root = Path(os.getenv("MEDIA_LOCAL_ROOT") or "static/uploads/media")
    target = root / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return "/" + target.as_posix().lstrip("/")


def upload_file(file_storage, *, company_id, namespace, name=None):
    """Store a general business attachment (PDF/Office/image) in R2 or local media."""
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename or "")
    if "." not in filename:
        raise ValueError("Не удалось определить формат файла.")

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValueError("Разрешены PDF, Word, Excel, PowerPoint и изображения.")

    file_storage.stream.seek(0)
    payload = file_storage.stream.read()
    if len(payload) > MAX_FILE_UPLOAD_BYTES:
        raise ValueError(
            f"Файл слишком большой. Максимум {MAX_FILE_UPLOAD_BYTES // 1024 // 1024} МБ."
        )

    content_type = file_storage.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    object_key = _key(company_id, namespace, ext=ext, name=name or f"{uuid.uuid4().hex}_{filename}")

    if _backend() == "r2" and _r2_ready():
        _r2_client().put_object(
            Bucket=os.environ["R2_BUCKET"],
            Key=object_key,
            Body=payload,
            ContentType=content_type,
            CacheControl="private, max-age=3600",
        )
        return f"{_public_base()}/{object_key}"

    if _backend() == "r2" and (os.getenv("MEDIA_ALLOW_LOCAL_FALLBACK") or "true").lower() != "true":
        raise RuntimeError("R2 не настроен полностью.")

    root = Path(os.getenv("MEDIA_LOCAL_ROOT") or "static/uploads/media")
    target = root / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return "/" + target.as_posix().lstrip("/")


def upload_local_path(path, *, company_id, namespace, name=None):
    """Migration helper for existing local images."""
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(str(source))

    class _Upload:
        filename = source.name
        stream = None

    holder = _Upload()
    holder.stream = source.open("rb")
    try:
        return upload_image(
            holder,
            company_id=company_id,
            namespace=namespace,
            name=name,
        )
    finally:
        holder.stream.close()


def delete_media(url):
    if not url:
        return

    public_base = _public_base()
    if public_base and str(url).startswith(public_base + "/") and _r2_ready():
        key = str(url)[len(public_base) + 1 :]
        try:
            _r2_client().delete_object(Bucket=os.environ["R2_BUCKET"], Key=key)
        except Exception:
            # File cleanup should never break a sale/catalog operation.
            pass
        return

    parsed = urlparse(str(url))
    local = (parsed.path or str(url)).lstrip("/")
    if local.startswith("static/"):
        try:
            path = Path(local)
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass

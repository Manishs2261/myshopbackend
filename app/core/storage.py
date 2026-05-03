from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image

from app.core.config import settings


class StorageUploadError(Exception):
    pass


def supabase_storage_enabled() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY and settings.SUPABASE_STORAGE_BUCKET)


def _compress_image(content: bytes, filename: str) -> tuple[bytes, str, str]:
    source_name = Path(filename or "upload").name
    stem = Path(source_name).stem or "image"

    with Image.open(BytesIO(content)) as image:
        output = BytesIO()
        image_format = (image.format or "").upper()

        if image_format == "PNG":
            image.save(output, format="PNG", optimize=True)
            extension = "png"
            content_type = "image/png"
        elif image_format == "WEBP":
            image.save(output, format="WEBP", lossless=True, method=6)
            extension = "webp"
            content_type = "image/webp"
        else:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=95, optimize=True, progressive=True)
            extension = "jpg"
            content_type = "image/jpeg"

    output.seek(0)
    compressed = output.read()
    file_name = f"{stem}.{extension}"
    return compressed, file_name, content_type


async def upload_product_image(file_bytes: bytes, original_filename: str, vendor_id: int) -> str:
    if not supabase_storage_enabled():
        raise StorageUploadError("Supabase Storage is not configured")

    compressed_bytes, normalized_filename, content_type = _compress_image(file_bytes, original_filename)
    object_path = f"vendors/{vendor_id}/{uuid4().hex}_{normalized_filename}"
    base_url = settings.SUPABASE_URL.rstrip("/")
    upload_url = f"{base_url}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"
    public_url = f"{base_url}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"

    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(upload_url, headers=headers, content=compressed_bytes)

    if response.status_code >= 400:
        raise StorageUploadError(f"Supabase upload failed: {response.status_code} {response.text}")

    return public_url

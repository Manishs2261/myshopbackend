from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, unquote
from uuid import uuid4

import httpx
from PIL import Image

from app.core.config import settings


class StorageUploadError(Exception):
    pass


def supabase_storage_enabled() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY and settings.SUPABASE_STORAGE_BUCKET)


def _supabase_object_path_from_public_url(file_url: str) -> str | None:
    base_url = settings.SUPABASE_URL.rstrip("/")
    public_prefix = f"{base_url}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/"
    if not file_url.startswith(public_prefix):
        return None
    return unquote(file_url[len(public_prefix):])


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


async def delete_product_images(image_urls: list[str]) -> None:
    if not image_urls:
        return

    if supabase_storage_enabled():
        object_paths = [
            object_path
            for url in image_urls
            if (object_path := _supabase_object_path_from_public_url(url))
        ]
        if not object_paths:
            return

        base_url = settings.SUPABASE_URL.rstrip("/")
        delete_url = f"{base_url}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request("DELETE", delete_url, headers=headers, json={"prefixes": object_paths})

        if response.status_code >= 400:
            raise StorageUploadError(f"Supabase delete failed: {response.status_code} {response.text}")
        return

    for url in image_urls:
        parsed = urlparse(url)
        path = Path(unquote(parsed.path.lstrip("/")))
        if path.parts[:2] == ("uploads", "products"):
            file_path = Path(*path.parts)
            if file_path.exists():
                file_path.unlink()

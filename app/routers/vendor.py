from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Body, Form, Request
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, DataError, StatementError
from typing import List
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.storage import upload_product_image, delete_product_images, supabase_storage_enabled, StorageUploadError
from app.core.security import require_role
from app.models.user import User, Vendor, Shop, Product, ProductVariant, Order, OrderItem, Payout, Category, MarketplaceSettings
from app.schemas.schemas import (
    VendorCreate, VendorUpdate, VendorResponse,
    ShopCreate, ShopUpdate, ShopResponse,
    ProductCreate, ProductUpdate, ProductResponse,
    OrderResponse, OrderStatusUpdate, PaginatedResponse,
    PayoutRequest, PayoutResponse, VendorDashboard, VendorDashboardOverview, VendorAnalyticsOverview,
    MarketplaceSettingsUpdate, MarketplaceSettingsResponse
)
from slugify import slugify
import math
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import json

router = APIRouter(prefix="/vendor", tags=["Vendor"])
get_vendor_user = require_role("VENDOR", "ADMIN")


def merge_dict(base: dict, override: dict | None) -> dict:
    data = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = merge_dict(data[key], value)
        else:
            data[key] = value
    return data


def build_storefront_defaults(vendor: Vendor | None = None, shop: Shop | None = None, products: list[Product] | None = None) -> dict:
    store_name = (shop.name if shop and shop.name else (vendor.business_name if vendor else "BazaarCraft Store")) or "BazaarCraft Store"
    store_tagline = (shop.description if shop and shop.description else "Handmade pieces with a story in every stitch") or ""
    product_ids = [product.id for product in (products or []) if getattr(product, "is_featured", False)]
    slug_source = store_name if store_name else f"vendor-{vendor.id if vendor else 'store'}"
    return {
        "branding": {
            "storeName": store_name,
            "tagline": store_tagline[:90],
            "logoUrl": shop.logo_url if shop else "",
            "faviconUrl": shop.logo_url if shop else "",
            "shippingMessage": "Free shipping on orders above ₹999",
            "contactEmail": (vendor.business_email if vendor else "") or "",
            "contactHours": "Mon-Sat: 9am - 7pm",
        },
        "theme": {
            "primaryColor": "#1a1208",
            "accentColor": "#c8a96e",
            "backgroundColor": "#faf8f5",
            "fontFamily": "DM Sans",
        },
        "banner": {
            "slidesCount": 2,
            "slides": [
                {
                    "tag": "New Arrivals",
                    "title": f"Shop {store_name}",
                    "subtext": "A curated storefront shaped around artisan-made pieces and everyday rituals.",
                    "ctaLabel": "Shop Collection",
                    "ctaLink": "#featured-products",
                    "imageUrl": shop.banner_url if shop else "",
                },
                {
                    "tag": "Made with Care",
                    "title": "Crafted by independent makers",
                    "subtext": "Discover small-batch products, warm materials, and thoughtful finishing details.",
                    "ctaLabel": "Explore Now",
                    "ctaLink": "#recent-products",
                    "imageUrl": "",
                },
            ],
        },
        "layout": {
            "style": "Modern",
            "showFeaturedProducts": True,
            "productsPerRow": 4,
            "displayMode": "Grid",
            "featuredProductIds": product_ids[:8],
        },
        "about": {
            "text": store_tagline or f"{store_name} celebrates thoughtful design, honest materials, and a slower way to shop.",
        },
        "promo": {
            "headline": "Refer a Friend, Earn ₹200 Credits",
            "subtext": "Share your unique link. When they shop, both of you win.",
            "ctaLabel": "Get My Code",
            "ctaLink": "#",
        },
        "social": {
            "website": "",
            "instagram": "",
            "facebook": "",
            "twitter": "",
            "whatsapp": "",
            "email": (vendor.business_email if vendor else "") or "",
        },
        "seo": {
            "metaTitle": store_name,
            "metaDescription": f"Browse {store_name} on BazaarCraft.",
            "slug": slugify(slug_source) or f"vendor-{vendor.id if vendor else 'store'}",
        },
    }


def normalize_storefront_payload(settings: MarketplaceSettings | None, vendor: Vendor | None = None, shop: Shop | None = None, products: list[Product] | None = None, published: bool = False) -> dict:
    defaults = build_storefront_defaults(vendor, shop, products)
    payload = {}
    if settings:
        payload = settings.storefront_published if published and settings.storefront_published else settings.storefront_draft
    merged = merge_dict(defaults, payload or {})
    slides = merged["banner"].get("slides", [])
    merged["banner"]["slides"] = slides[:6] if slides else defaults["banner"]["slides"][:1]
    merged["banner"]["slidesCount"] = max(1, min(6, int(merged["banner"].get("slidesCount", len(merged["banner"]["slides"]) or 1))))
    return merged


def sync_legacy_marketplace_fields(settings: MarketplaceSettings, payload: dict) -> None:
    branding = payload.get("branding", {})
    theme = payload.get("theme", {})
    banner = payload.get("banner", {})
    social = payload.get("social", {})
    seo = payload.get("seo", {})
    first_slide = (banner.get("slides") or [{}])[0]
    settings.primary_color = theme.get("accentColor", "#c8a96e")
    settings.secondary_color = theme.get("primaryColor", "#1a1208")
    settings.background_color = theme.get("backgroundColor", "#faf8f5")
    settings.banner_text = first_slide.get("title", branding.get("storeName", "Welcome to Our Store"))
    settings.banner_subtext = first_slide.get("subtext", branding.get("tagline", "Discover amazing products"))
    settings.show_banner = True
    settings.products_per_page = payload.get("layout", {}).get("productsPerRow", 4) * 2
    settings.facebook_url = social.get("facebook") or None
    settings.instagram_url = social.get("instagram") or None
    settings.twitter_url = social.get("twitter") or None
    settings.whatsapp_number = social.get("whatsapp") or None
    settings.meta_title = seo.get("metaTitle") or branding.get("storeName")
    settings.meta_description = seo.get("metaDescription")
    settings.storefront_status = "live" if settings.storefront_published else "draft"


def serialize_editor_state(settings: MarketplaceSettings, vendor: Vendor, shop: Shop | None = None, products: list[Product] | None = None) -> dict:
    draft = normalize_storefront_payload(settings, vendor, shop, products, published=False)
    published = normalize_storefront_payload(settings, vendor, shop, products, published=True) if settings.storefront_published else None
    has_unpublished_changes = bool(settings.storefront_published) and json.dumps(draft, sort_keys=True) != json.dumps(published, sort_keys=True)
    return {
        "id": settings.id,
        "vendor_id": vendor.id,
        "draft": draft,
        "published": published,
        "status": "live" if settings.storefront_published else "draft",
        "has_unpublished_changes": has_unpublished_changes or not bool(settings.storefront_published),
        "published_at": settings.published_at.isoformat() if settings.published_at else None,
        "slug": draft.get("seo", {}).get("slug"),
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


# ─── Vendor Profile ──────────────────────────────────────────────────────────

@router.get("/me", response_model=VendorResponse)
async def get_vendor_profile(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")
    return vendor


@router.put("/me", response_model=VendorResponse)
async def update_vendor_profile(
    payload: VendorUpdate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(vendor, field, value)
    await db.commit()
    await db.refresh(vendor)
    return vendor


# ─── Shop ────────────────────────────────────────────────────────────────────

@router.post("/shop", response_model=ShopResponse, status_code=201)
async def create_shop(
    payload: ShopCreate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")
    if vendor.status == "suspended":
        raise HTTPException(status_code=403, detail="Vendor account suspended. Contact support.")

    # Check if shop already exists
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Shop already exists. Use PUT to update.")

    shop = Shop(vendor_id=vendor.id, **payload.model_dump())
    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    return shop


@router.get("/shop", response_model=ShopResponse)
async def get_shop(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Shop).join(Vendor).where(Vendor.user_id == current_user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.put("/shop", response_model=ShopResponse)
async def update_shop(
    payload: ShopUpdate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Shop).join(Vendor).where(Vendor.user_id == current_user.id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(shop, field, value)
    await db.commit()
    await db.refresh(shop)
    return shop


# Media Upload Endpoints

async def _save_shop_media(file: UploadFile, vendor_id: int, subfolder: str, base_url: str) -> str:
    max_size = 5 * 1024 * 1024
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    content = await file.read()
    safe_name = Path(file.filename or "image").name
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="Image too large. Maximum allowed size is 5MB.")
    if supabase_storage_enabled():
        try:
            return await upload_product_image(content, safe_name, vendor_id)
        except StorageUploadError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    uploads_dir = Path(f"uploads/{subfolder}")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{vendor_id}_{uuid4().hex}_{safe_name}"
    with open(uploads_dir / filename, "wb") as f:
        f.write(content)
    return f"{base_url}/uploads/{subfolder}/{filename}"


@router.post("/shop/logo", response_model=dict)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    base_url = str(request.base_url).rstrip("/")
    logo_url = await _save_shop_media(file, vendor.id, "logos", base_url)
    shop.logo_url = logo_url
    await db.commit()
    await db.refresh(shop)
    return {"url": shop.logo_url}


@router.post("/shop/banner", response_model=dict)
async def upload_banner(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    base_url = str(request.base_url).rstrip("/")
    banner_url = await _save_shop_media(file, vendor.id, "banners", base_url)
    shop.banner_url = banner_url
    await db.commit()
    await db.refresh(shop)
    return {"url": shop.banner_url}


@router.post("/shop/gallery", response_model=dict)
async def upload_gallery(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    base_url = str(request.base_url).rstrip("/")
    urls = []
    for file in files:
        urls.append(await _save_shop_media(file, vendor.id, "gallery", base_url))
    shop.gallery = (shop.gallery or []) + urls
    await db.commit()
    return {"urls": urls}


@router.delete("/shop/gallery")
async def remove_gallery_image(
    url: str = Body(..., embed=True),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    
    # Get shop
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Remove URL from gallery (assign new list so SQLAlchemy detects the change)
    if shop.gallery and url in shop.gallery:
        shop.gallery = [u for u in shop.gallery if u != url]
        await db.commit()
    
    return {"message": "Image removed from gallery"}


# ─── Products ────────────────────────────────────────────────────────────────

async def get_vendor(user: User, db: AsyncSession) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


def _normalize_product_payload(product_data: dict) -> dict:
    if not isinstance(product_data, dict):
        raise HTTPException(status_code=400, detail="Product data must be a JSON object")

    if not product_data.get("name"):
        raise HTTPException(status_code=400, detail="Product name is required")
    if product_data.get("price") in (None, ""):
        raise HTTPException(status_code=400, detail="Product price is required")
    if product_data.get("category_id") in (None, ""):
        raise HTTPException(status_code=400, detail="Product category is required")

    normalized = dict(product_data)
    if normalized.get("category_id") not in (None, ""):
        normalized["category_id"] = int(normalized["category_id"])
    if normalized.get("price") not in (None, ""):
        normalized["price"] = float(normalized["price"])
    if normalized.get("original_price") not in (None, ""):
        normalized["original_price"] = float(normalized["original_price"])
    if normalized.get("discount_percentage") not in (None, ""):
        normalized["discount_percentage"] = int(normalized["discount_percentage"])
    if normalized.get("stock") not in (None, ""):
        normalized["stock"] = int(normalized["stock"])
    else:
        normalized["stock"] = 0

    tags = normalized.get("tags")
    if isinstance(tags, str):
        normalized["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
    elif tags is None:
        normalized["tags"] = []

    variants = normalized.get("variants")
    if variants is None:
        normalized["variants"] = []

    return normalized


async def _validate_product_payload(db: AsyncSession, product_data: dict) -> None:
    if product_data["price"] <= 0:
        raise HTTPException(status_code=400, detail="Product price must be greater than 0")
    if product_data.get("original_price") is not None and product_data["original_price"] <= 0:
        raise HTTPException(status_code=400, detail="Original price must be greater than 0")
    if product_data.get("original_price") is not None and product_data["original_price"] < product_data["price"]:
        raise HTTPException(status_code=400, detail="Original price must be greater than or equal to selling price")
    if product_data.get("discount_percentage") is not None and not 0 <= product_data["discount_percentage"] <= 100:
        raise HTTPException(status_code=400, detail="Discount percentage must be between 0 and 100")
    if product_data["stock"] < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")

    category = await db.execute(select(Category.id).where(Category.id == product_data["category_id"]))
    if category.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Selected category does not exist")

    variants = product_data.get("variants", [])
    if not isinstance(variants, list):
        raise HTTPException(status_code=400, detail="Variants must be a list")
    for index, variant in enumerate(variants, start=1):
        if not isinstance(variant, dict):
            raise HTTPException(status_code=400, detail=f"Variant #{index} must be an object")
        if variant.get("stock") not in (None, "") and int(variant.get("stock", 0)) < 0:
            raise HTTPException(status_code=400, detail=f"Variant #{index} stock cannot be negative")
        if variant.get("price") not in (None, "") and float(variant.get("price")) <= 0:
            raise HTTPException(status_code=400, detail=f"Variant #{index} price must be greater than 0")


def _product_error_message(exc: Exception, action: str) -> str:
    if isinstance(exc, IntegrityError):
        msg = str(exc.orig).lower()
        if "product_variants_sku_key" in msg or "sku" in msg:
            return f"Could not {action} product because one variant SKU already exists. Please use a unique SKU."
        if "products_slug_key" in msg or "slug" in msg:
            return f"Could not {action} product because another product already uses this name/slug."
        if "foreign key" in msg or "category_id" in msg:
            return f"Could not {action} product because the selected category is invalid."
        return f"Could not {action} product because of a database constraint error."
    if isinstance(exc, (DataError, StatementError, ValueError, TypeError)):
        return f"Could not {action} product because one or more fields have an invalid value."
    return f"Could not {action} product right now. Please check the form values and try again."


async def _parse_product_request(request: Request) -> tuple[dict, List[UploadFile], UploadFile | None]:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        data_field = form.get("data")
        if data_field in (None, ""):
            raise HTTPException(
                status_code=400,
                detail="Missing 'data' form field. Send product details as a JSON string.",
            )

        if isinstance(data_field, (UploadFile, StarletteUploadFile)):
            raw_data = (await data_field.read()).decode("utf-8")
        elif isinstance(data_field, (bytes, bytearray)):
            raw_data = data_field.decode("utf-8")
        else:
            raw_data = str(data_field)

        try:
            product_data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in 'data' field: {e.msg}") from e

        images = [
            file for file in form.getlist("images")
            if isinstance(file, (UploadFile, StarletteUploadFile)) and file.filename
        ]
        video = form.get("video")
        if not isinstance(video, (UploadFile, StarletteUploadFile)):
            video = None
        return _normalize_product_payload(product_data), images, video

    if "application/json" in content_type:
        try:
            product_data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {str(e)}") from e
        return _normalize_product_payload(product_data), [], None

    try:
        form = await request.form()
    except Exception:
        form = None

    if form:
        raw_data = form.get("data")
        if raw_data:
            try:
                return _normalize_product_payload(json.loads(str(raw_data))), [], None
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in 'data' field: {e.msg}") from e

    raise HTTPException(
        status_code=415,
        detail="Unsupported content type. Use application/json or multipart/form-data.",
    )


async def _save_product_images(vendor: Vendor, images: List[UploadFile], base_url: str) -> List[str]:
    max_image_size = 5 * 1024 * 1024
    image_urls = []
    uploads_dir = Path("uploads/products")
    if not supabase_storage_enabled():
        uploads_dir.mkdir(parents=True, exist_ok=True)

    for image in images:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image files are allowed")

        content = await image.read()
        safe_name = Path(image.filename or "product-image").name
        if len(content) > max_image_size:
            raise HTTPException(
                status_code=400,
                detail=f"Image '{safe_name}' is too large. Maximum allowed size is 5MB.",
            )

        if supabase_storage_enabled():
            try:
                image_urls.append(await upload_product_image(content, safe_name, vendor.id))
                continue
            except StorageUploadError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        filename = f"{vendor.id}_{uuid4().hex}_{safe_name}"
        file_path = uploads_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        image_urls.append(f"{base_url}/uploads/products/{filename}")

    return image_urls


async def _generate_unique_product_slug(
    db: AsyncSession,
    name: str,
    vendor_id: int,
    exclude_product_id: int | None = None,
) -> str:
    base_slug = slugify(name) or "product"
    candidate = f"{base_slug}-{vendor_id}"
    counter = 1

    while True:
        query = select(Product.id).where(Product.slug == candidate)
        if exclude_product_id is not None:
            query = query.where(Product.id != exclude_product_id)
        existing = await db.execute(query)
        if existing.scalar_one_or_none() is None:
            return candidate
        counter += 1
        candidate = f"{base_slug}-{vendor_id}-{counter}"


def _serialize_product(product: Product) -> dict:
    normalized_status = {
        "pending": "active",
        "approved": "active",
        "rejected": "inactive",
    }.get((product.status or "").lower(), product.status)

    return {
        "id": product.id,
        "vendor_id": product.vendor_id,
        "category_id": product.category_id,
        "category_name": product.category.name if getattr(product, "category", None) else None,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "brand": product.brand,
        "price": float(product.price),
        "original_price": float(product.original_price) if product.original_price else None,
        "discount_percentage": product.discount_percentage,
        "stock": product.stock,
        "unit": product.unit,
        "status": normalized_status,
        "rating": product.rating,
        "review_count": product.review_count,
        "images": product.images or [],
        "tags": product.tags or [],
        "specifications": product.specifications or {},
        "is_featured": product.is_featured,
        "view_count": product.view_count,
        "variants": [
            {
                "id": v.id,
                "size": v.size,
                "color": v.color,
                "sku": v.sku,
                "price": float(v.price) if v.price else None,
                "stock": v.stock,
                "images": v.images or [],
            }
            for v in product.variants
        ],
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


def _normalize_vendor_product_status_input(status: str | None) -> str:
    normalized = (status or "active").lower()
    return {
        "pending": "active",
        "approved": "active",
        "rejected": "inactive",
    }.get(normalized, normalized)


def _parse_filter_datetime(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date filter: {value}") from e
    if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0:
        parsed = parsed + timedelta(days=1)
    return parsed


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    request: Request,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    product_data, images, video = await _parse_product_request(request)
    await _validate_product_payload(db, product_data)
    base_url = str(request.base_url).rstrip("/")
    image_urls = await _save_product_images(vendor, images, base_url)
    unique_slug = await _generate_unique_product_slug(db, product_data["name"], vendor.id)
    
    # Extract variants before creating product
    variants = product_data.get("variants", [])
    
    # Create product with only valid Product fields
    product_dict = {
        "vendor_id": vendor.id,
        "slug": unique_slug,
        "status": _normalize_vendor_product_status_input(product_data.get("status")),
        "images": image_urls,
        "name": product_data.get("name"),
        "description": product_data.get("description"),
        "brand": product_data.get("brand"),
        "category_id": product_data.get("category_id"),
        "price": product_data.get("price"),
        "original_price": product_data.get("original_price"),
        "discount_percentage": product_data.get("discount_percentage"),
        "stock": product_data.get("stock", 0),
        "unit": product_data.get("unit"),
        "tags": product_data.get("tags", []),
        "specifications": product_data.get("specifications") or {},
    }

    try:
        product = Product(**product_dict)
        db.add(product)
        await db.flush()

        for v in variants:
            variant_data = {
                "product_id": product.id,
                "size": v.get("size"),
                "color": v.get("color"),
                "sku": v.get("sku"),
                "price": float(v.get("price", 0)) if v.get("price") else None,
                "stock": int(v.get("stock", 0)),
                "images": v.get("images", []),
            }
            if variant_data["color"] or variant_data["stock"] > 0:
                variant = ProductVariant(**variant_data)
                db.add(variant)

        await db.commit()
        result = await db.execute(
            select(Product)
            .where(Product.id == product.id)
            .options(selectinload(Product.variants), selectinload(Product.category))
        )
        return _serialize_product(result.scalar_one())
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=_product_error_message(e, "create")) from e


@router.get("/products", response_model=PaginatedResponse)
async def list_vendor_products(
    search: str = None,
    status: str = None,
    category_id: int = None,
    stock_filter: str = None,
    stock_min: int = Query(default=None, ge=0),
    stock_max: int = Query(default=None, ge=0),
    min_price: float = Query(default=None, ge=0),
    max_price: float = Query(default=None, ge=0),
    discount_only: bool = False,
    created_from: str = None,
    created_to: str = None,
    updated_from: str = None,
    updated_to: str = None,
    sort_by: str = "recent",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    latest_activity = func.coalesce(Product.updated_at, Product.created_at)
    conditions = [Product.vendor_id == vendor.id]

    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Product.name.ilike(term),
                Product.description.ilike(term),
                Product.brand.ilike(term),
                cast(Product.tags, String).ilike(term),
            )
        )
    if status:
        conditions.append(Product.status == status)
    if category_id:
        conditions.append(Product.category_id == category_id)
    if min_price is not None:
        conditions.append(Product.price >= min_price)
    if max_price is not None:
        conditions.append(Product.price <= max_price)
    if discount_only:
        conditions.append(Product.discount_percentage.is_not(None))
        conditions.append(Product.discount_percentage > 0)
    if stock_min is not None:
        conditions.append(Product.stock >= stock_min)
    if stock_max is not None:
        conditions.append(Product.stock <= stock_max)

    if stock_filter == "in_stock":
        conditions.append(Product.stock > 0)
    elif stock_filter == "low_stock":
        conditions.append(Product.stock > 0)
        conditions.append(Product.stock <= 5)
    elif stock_filter == "out_of_stock":
        conditions.append(Product.stock <= 0)
    elif stock_filter == "overstock":
        conditions.append(Product.stock >= 100)

    parsed_created_from = _parse_filter_datetime(created_from)
    parsed_created_to = _parse_filter_datetime(created_to, end_of_day=True)
    parsed_updated_from = _parse_filter_datetime(updated_from)
    parsed_updated_to = _parse_filter_datetime(updated_to, end_of_day=True)

    if parsed_created_from:
        conditions.append(Product.created_at >= parsed_created_from)
    if parsed_created_to:
        conditions.append(Product.created_at < parsed_created_to)
    if parsed_updated_from:
        conditions.append(Product.updated_at >= parsed_updated_from)
    if parsed_updated_to:
        conditions.append(Product.updated_at < parsed_updated_to)

    sort_map = {
        "recent": latest_activity.desc(),
        "newest": Product.created_at.desc(),
        "oldest": Product.created_at.asc(),
        "price_asc": Product.price.asc(),
        "price_desc": Product.price.desc(),
        "stock_asc": Product.stock.asc(),
        "stock_desc": Product.stock.desc(),
        "name_asc": Product.name.asc(),
        "name_desc": Product.name.desc(),
    }
    order_clause = sort_map.get(sort_by, latest_activity.desc())
    query = select(Product).where(*conditions).order_by(order_clause)

    offset = (page - 1) * limit
    result = await db.execute(
        query.offset(offset).limit(limit).options(selectinload(Product.variants), selectinload(Product.category))
    )
    products = result.scalars().all()
    
    total_query = select(func.count()).select_from(Product).where(*conditions)
    total = (await db.execute(total_query)).scalar() or 0
    items = [_serialize_product(product) for product in products]

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit,
        pages=math.ceil(total / limit) if total else 0
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_vendor_product(
    product_id: int,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_product(product)


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    request: Request,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product_data, images, video = await _parse_product_request(request)
    await _validate_product_payload(db, product_data)
    base_url = str(request.base_url).rstrip("/")
    new_images = await _save_product_images(vendor, images, base_url)
    next_slug = product.slug
    if product_data.get("name"):
        next_slug = await _generate_unique_product_slug(db, product_data["name"], vendor.id, exclude_product_id=product.id)

    updatable_fields = [
        "category_id", "name", "description", "brand", "price", "original_price",
        "discount_percentage",
        "stock", "unit", "tags", "specifications", "status"
    ]
    try:
        previous_images = list(product.images or [])

        for field in updatable_fields:
            if field in product_data:
                if field == "status":
                    setattr(product, field, _normalize_vendor_product_status_input(product_data[field]))
                else:
                    setattr(product, field, product_data[field])

        kept_images = product_data.get("images") if isinstance(product_data.get("images"), list) else None
        if new_images and kept_images is not None:
            product.images = kept_images + new_images
        elif new_images:
            product.images = new_images
        elif kept_images is not None:
            product.images = kept_images

        product.slug = next_slug
        removed_images = [url for url in previous_images if url not in (product.images or [])]

        if "variants" in product_data:
            await db.execute(
                ProductVariant.__table__.delete().where(ProductVariant.product_id == product.id)
            )
            for v in product_data.get("variants", []):
                variant_data = {
                    "product_id": product.id,
                    "size": v.get("size"),
                    "color": v.get("color"),
                    "sku": v.get("sku"),
                    "price": float(v.get("price", 0)) if v.get("price") else None,
                    "stock": int(v.get("stock", 0)),
                    "images": v.get("images", []),
                }
                if variant_data["color"] or variant_data["stock"] > 0:
                    db.add(ProductVariant(**variant_data))

        await db.commit()
        result = await db.execute(
            select(Product)
            .where(Product.id == product.id)
            .options(selectinload(Product.variants), selectinload(Product.category))
        )
        if removed_images:
            await delete_product_images(removed_images)
        return _serialize_product(result.scalar_one())
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=_product_error_message(e, "update")) from e


@router.delete("/products/{product_id}", response_model=dict)
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = "inactive"
    await db.commit()
    return {"message": "Product deactivated"}


# ─── Orders ─────────────────────────────────────────────────────────────────

@router.get("/orders", response_model=PaginatedResponse)
async def get_vendor_orders(
    status: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    query = select(Order).join(OrderItem).where(OrderItem.vendor_id == vendor.id).distinct()
    if status:
        query = query.where(Order.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(
        query.offset(offset).limit(limit)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    items = result.scalars().all()

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit,
        pages=math.ceil(total / limit)
    )


@router.put("/orders/{order_id}", response_model=dict)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Order).join(OrderItem).where(
            Order.id == order_id, OrderItem.vendor_id == vendor.id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    valid_transitions = {
        "confirmed": ["processing"],
        "processing": ["shipped"],
        "shipped": ["delivered"],
    }
    allowed = valid_transitions.get(order.status, [])
    if payload.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{order.status}' to '{payload.status}'"
        )

    order.status = payload.status
    await db.commit()
    return {"message": f"Order status updated to {payload.status}"}


# ─── Analytics ──────────────────────────────────────────────────────────────

def _calculate_vendor_completion_score(user: User, vendor: Vendor, shop: Shop | None, total_products: int) -> int:
    checks = [
        bool(vendor.business_name),
        bool(vendor.business_email),
        bool(vendor.business_phone),
        bool(vendor.gst_number or vendor.pan_number),
        bool(shop and shop.name),
        bool(shop and shop.logo_url),
        bool(shop and shop.address),
        bool(user.is_email_verified),
        bool(user.is_phone_verified),
        total_products >= 5,
    ]
    return round((sum(1 for item in checks if item) / len(checks)) * 100)


@router.get("/dashboard", response_model=VendorDashboardOverview)
@router.get("/analytics/dashboard", response_model=VendorDashboardOverview)
async def vendor_dashboard(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)

    total_views_result = await db.execute(
        select(func.sum(Product.view_count)).where(Product.vendor_id == vendor.id)
    )
    total_views = total_views_result.scalar() or 0

    total_orders_result = await db.execute(
        select(func.count(Order.id.distinct()))
        .join(OrderItem)
        .where(OrderItem.vendor_id == vendor.id)
    )
    total_orders = total_orders_result.scalar() or 0

    revenue_result = await db.execute(
        select(func.sum(OrderItem.price * OrderItem.quantity))
        .join(Order)
        .where(OrderItem.vendor_id == vendor.id, Order.payment_status == "paid")
    )
    revenue = revenue_result.scalar() or Decimal("0")

    pending_result = await db.execute(
        select(func.count(Order.id.distinct()))
        .join(OrderItem)
        .where(OrderItem.vendor_id == vendor.id, Order.status == "pending")
    )
    pending_orders = pending_result.scalar() or 0

    products_result = await db.execute(
        select(func.count(Product.id)).where(Product.vendor_id == vendor.id)
    )
    total_products = products_result.scalar() or 0

    return VendorDashboardOverview(
        total_views=total_views,
        total_orders=total_orders,
        revenue=revenue,
        pending_orders=pending_orders,
        total_products=total_products,
    )


@router.get("/analytics", response_model=VendorAnalyticsOverview)
async def vendor_analytics(
    period: str = Query(default="30d"),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    days_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
    days = days_map.get(period, 30)
    now = datetime.utcnow()
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    total_views = (
        await db.execute(select(func.sum(Product.view_count)).where(Product.vendor_id == vendor.id))
    ).scalar() or 0

    total_orders = (
        await db.execute(
            select(func.count(Order.id.distinct()))
            .join(OrderItem)
            .where(OrderItem.vendor_id == vendor.id, Order.created_at >= current_start)
        )
    ).scalar() or 0

    revenue_estimate = (
        await db.execute(
            select(func.sum(OrderItem.price * OrderItem.quantity))
            .join(Order)
            .where(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == "paid",
                Order.created_at >= current_start,
            )
        )
    ).scalar() or Decimal("0")

    current_period_updates = (
        await db.execute(
            select(func.count(Product.id))
            .where(Product.vendor_id == vendor.id, func.coalesce(Product.updated_at, Product.created_at) >= current_start)
        )
    ).scalar() or 0
    previous_period_updates = (
        await db.execute(
            select(func.count(Product.id))
            .where(
                Product.vendor_id == vendor.id,
                func.coalesce(Product.updated_at, Product.created_at) >= previous_start,
                func.coalesce(Product.updated_at, Product.created_at) < current_start,
            )
        )
    ).scalar() or 0
    growth_rate = 0.0 if previous_period_updates == 0 else round(((current_period_updates - previous_period_updates) / previous_period_updates) * 100, 2)

    top_products_result = await db.execute(
        select(Product)
        .where(Product.vendor_id == vendor.id)
        .order_by(Product.view_count.desc(), func.coalesce(Product.updated_at, Product.created_at).desc())
        .limit(5)
    )
    top_products = top_products_result.scalars().all()

    recent_products_result = await db.execute(
        select(Product)
        .where(Product.vendor_id == vendor.id, func.coalesce(Product.updated_at, Product.created_at) >= current_start)
        .order_by(func.coalesce(Product.updated_at, Product.created_at).asc())
    )
    recent_products = recent_products_result.scalars().all()

    views_by_day = [
        {
            "date": product.updated_at.strftime("%d %b") if product.updated_at else product.created_at.strftime("%d %b"),
            "value": int(product.view_count or 0),
        }
        for product in recent_products[-12:]
    ]
    clicks_by_day = [
        {
            "date": point["date"],
            "value": 1,
        }
        for point in views_by_day
    ]

    return VendorAnalyticsOverview(
        total_views=int(total_views),
        total_clicks=int(total_orders),
        total_searches=0,
        revenue_estimate=revenue_estimate,
        growth_rate=growth_rate,
        views_by_day=views_by_day,
        clicks_by_day=clicks_by_day,
        top_products=[
            {
                "product_id": product.id,
                "name": product.name,
                "image": (product.images or [None])[0],
                "views": int(product.view_count or 0),
                "clicks": 0,
                "searches": 0,
            }
            for product in top_products
        ],
        top_cities=[],
    )
    total_products = products_result.scalar() or 0

    active_products_result = await db.execute(
        select(func.count(Product.id)).where(Product.vendor_id == vendor.id, Product.status == "active")
    )
    active_products = active_products_result.scalar() or 0
    inactive_products = max(total_products - active_products, 0)

    shop_result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = shop_result.scalar_one_or_none()
    completion_score = _calculate_vendor_completion_score(current_user, vendor, shop, total_products)

    recent_products_result = await db.execute(
        select(Product)
        .where(Product.vendor_id == vendor.id)
        .options(selectinload(Product.category))
        .order_by(func.coalesce(Product.updated_at, Product.created_at).desc())
        .limit(5)
    )
    recent_products = recent_products_result.scalars().all()

    return VendorDashboardOverview(
        total_products=total_products,
        active_products=active_products,
        inactive_products=inactive_products,
        total_views=total_views,
        total_orders=total_orders,
        pending_orders=pending_orders,
        revenue=revenue,
        completion_score=completion_score,
        recent_products=[
            {
                "id": product.id,
                "name": product.name,
                "category_name": product.category.name if product.category else None,
                "price": product.price,
                "status": product.status,
                "click_count": product.view_count or 0,
                "images": product.images or [],
                "created_at": product.created_at,
                "updated_at": product.updated_at,
            }
            for product in recent_products
        ],
    )


# ─── Payouts ─────────────────────────────────────────────────────────────────

@router.get("/payouts", response_model=list[PayoutResponse])
async def get_payouts(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Payout).where(Payout.vendor_id == vendor.id)
        .order_by(Payout.requested_at.desc())
    )
    return result.scalars().all()


@router.post("/payout/request", response_model=PayoutResponse, status_code=201)
async def request_payout(
    payload: PayoutRequest,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if payload.amount > vendor.total_earnings:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    payout = Payout(
        vendor_id=vendor.id,
        amount=payload.amount,
        notes=payload.notes,
        status="pending",
    )
    db.add(payout)
    vendor.total_earnings -= payload.amount
    await db.commit()
    await db.refresh(payout)

    return PayoutResponse.from_orm(payout)


# ─── Marketplace Settings ────────────────────────────────────────────────────────

async def _load_vendor_context(vendor_id: int, db: AsyncSession):
    """Explicitly load shop and products for a vendor — avoids async lazy-load errors."""
    shop_res = await db.execute(select(Shop).where(Shop.vendor_id == vendor_id))
    shop = shop_res.scalar_one_or_none()
    products_res = await db.execute(select(Product).where(Product.vendor_id == vendor_id))
    products = list(products_res.scalars().all())
    return shop, products


async def _get_or_create_settings(vendor_id: int, db: AsyncSession) -> MarketplaceSettings:
    result = await db.execute(
        select(MarketplaceSettings).where(MarketplaceSettings.vendor_id == vendor_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = MarketplaceSettings(vendor_id=vendor_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("/marketplace-settings")
async def get_marketplace_settings(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    shop, products = await _load_vendor_context(vendor.id, db)
    settings = await _get_or_create_settings(vendor.id, db)

    if not settings.storefront_draft:
        settings.storefront_draft = build_storefront_defaults(vendor, shop, products)
        sync_legacy_marketplace_fields(settings, settings.storefront_draft)
        await db.commit()
        await db.refresh(settings)

    return serialize_editor_state(settings, vendor, shop, products)


@router.put("/marketplace-settings")
async def update_marketplace_settings(
    payload: dict = Body(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    shop, products = await _load_vendor_context(vendor.id, db)
    settings = await _get_or_create_settings(vendor.id, db)

    settings.storefront_draft = merge_dict(build_storefront_defaults(vendor, shop, products), payload or {})
    sync_legacy_marketplace_fields(settings, settings.storefront_draft)
    settings.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(settings)

    return {
        "message": "Draft saved",
        "settings": serialize_editor_state(settings, vendor, shop, products),
    }


@router.post("/marketplace-settings/publish")
async def publish_marketplace_settings(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    shop, products = await _load_vendor_context(vendor.id, db)
    settings = await _get_or_create_settings(vendor.id, db)

    settings.storefront_draft = settings.storefront_draft or build_storefront_defaults(vendor, shop, products)
    settings.storefront_published = settings.storefront_draft
    settings.storefront_status = "live"
    settings.published_at = datetime.utcnow()
    sync_legacy_marketplace_fields(settings, settings.storefront_draft)
    settings.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(settings)

    return {
        "message": "Storefront published successfully",
        "settings": serialize_editor_state(settings, vendor, shop, products),
    }


@router.post("/marketplace-settings/reset")
async def reset_marketplace_settings(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    shop, products = await _load_vendor_context(vendor.id, db)
    settings = await _get_or_create_settings(vendor.id, db)

    settings.theme = "default"
    settings.storefront_draft = build_storefront_defaults(vendor, shop, products)
    sync_legacy_marketplace_fields(settings, settings.storefront_draft)
    settings.custom_css = None
    settings.enable_reviews = True
    settings.enable_wishlist = True
    settings.enable_sharing = True
    settings.meta_keywords = None
    settings.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(settings)

    return {
        "message": "Marketplace settings reset to default successfully",
        "settings": serialize_editor_state(settings, vendor, shop, products),
    }

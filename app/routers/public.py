from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from pathlib import Path
from slugify import slugify
import math

from app.core.database import get_db
from app.models.user import User, Vendor, Product, Category, Shop, ProductVariant, MarketplaceSettings, WebsiteSettings
from app.schemas.schemas import WebsiteSettingsGeneralResponse, WebsiteSettingsAppearanceResponse, WebsiteSettingsBannerResponse, WebsiteSettingsPromoResponse, WebsiteSettingsBlogResponse, WebsiteSettingsNavResponse, WebsiteSettingsBrowseCategoriesResponse, WebsiteSettingsShippingResponse, WebsiteSettingsSocialResponse, WebsiteSettingsMaintenanceResponse, WebsiteSettingsHomeResponse

router = APIRouter(prefix="/public", tags=["public"])

CATEGORY_PALETTE = [
    "#f5ede0", "#fef0f8", "#f0f4fe", "#f5f0e8",
    "#eef8ee", "#ede8f8", "#fff4e8", "#fde8f0",
]


def _category_bg(index: int) -> str:
    return CATEGORY_PALETTE[index % len(CATEGORY_PALETTE)]


def _shop_snapshot(vendor, shop) -> dict:
    if not vendor:
        return {}
    return {
        "vendor_id": vendor.id,
        "shop_name": (shop.name if shop and shop.name else vendor.business_name) or "",
        "shop_phone": vendor.business_phone or "",
        "shop_lat": float(shop.latitude) if shop and shop.latitude else None,
        "shop_lng": float(shop.longitude) if shop and shop.longitude else None,
        "shop_city": shop.city if shop else None,
        "shop_address": shop.address if shop else None,
        "shop_state": shop.state if shop else None,
        "shop_logo": shop.logo_url if shop else None,
        "opening_time": str(shop.opening_time) if shop and shop.opening_time else None,
        "closing_time": str(shop.closing_time) if shop and shop.closing_time else None,
        "working_days": shop.working_days if shop else [],
    }


def frontend_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / filename


def merge_dict(base: dict, override: dict | None) -> dict:
    data = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = merge_dict(data[key], value)
        else:
            data[key] = value
    return data


def build_storefront_defaults(vendor: Vendor, shop: Shop | None, products: list[Product]) -> dict:
    store_name = (shop.name if shop and shop.name else vendor.business_name) or "BazaarCraft Store"
    store_tagline = (shop.description if shop and shop.description else "Handmade pieces with a story in every stitch") or ""
    featured_ids = [product.id for product in products if getattr(product, "is_featured", False)]
    return {
        "branding": {
            "storeName": store_name,
            "tagline": store_tagline[:90],
            "logoUrl": shop.logo_url if shop else "",
            "faviconUrl": shop.logo_url if shop else "",
            "shippingMessage": "Free shipping on orders above ₹999",
            "contactEmail": vendor.business_email or "",
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
            "featuredProductIds": featured_ids[:8],
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
            "email": vendor.business_email or "",
        },
        "seo": {
            "metaTitle": store_name,
            "metaDescription": f"Browse {store_name} on BazaarCraft.",
            "slug": slugify(store_name) or f"vendor-{vendor.id}",
        },
    }


def effective_storefront_payload(vendor: Vendor, shop: Shop | None, products: list[Product]) -> dict:
    settings = vendor.marketplace_settings
    defaults = build_storefront_defaults(vendor, shop, products)
    published = settings.storefront_published if settings and settings.storefront_published else None
    draft = settings.storefront_draft if settings and settings.storefront_draft else None
    payload = published or draft or {}
    return merge_dict(defaults, payload)


@router.get("/categories")
async def get_public_categories(db: AsyncSession = Depends(get_db)):
    """Return all active categories ordered by sort_order."""
    result = await db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.sort_order, Category.name)
    )
    categories = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "description": c.description,
            "image_url": c.image_url,
            "sort_order": c.sort_order,
        }
        for c in categories
    ]


@router.get("/products")
async def get_public_products(
    # Search
    search: Optional[str] = Query(None, description="Search by name, brand or description"),
    # Filters
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    category_slug: Optional[str] = Query(None, description="Filter by category slug"),
    min_price: Optional[float] = Query(None, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    in_stock: Optional[bool] = Query(None, description="Only show in-stock products"),
    featured: Optional[bool] = Query(None, description="Only show featured products"),
    brand: Optional[str] = Query(None, description="Filter by brand name"),
    # Sort
    sort: Optional[str] = Query("newest", description="Sort: newest | price_asc | price_desc | rating | popular"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(12, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    base_query = (
        select(Product)
        .where(func.lower(Product.status) == "approved")
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.vendor).selectinload(Vendor.shop),
        )
    )

    # ── Filters ────────────────────────────────────────────────────────────────
    if search:
        term = f"%{search.lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(Product.name).like(term),
                func.lower(Product.brand).like(term),
                func.lower(Product.description).like(term),
            )
        )

    if category_id:
        base_query = base_query.where(Product.category_id == category_id)
    elif category_slug:
        cat_result = await db.execute(select(Category).where(Category.slug == category_slug))
        cat = cat_result.scalar_one_or_none()
        if cat:
            base_query = base_query.where(Product.category_id == cat.id)

    if min_price is not None:
        base_query = base_query.where(Product.price >= min_price)
    if max_price is not None:
        base_query = base_query.where(Product.price <= max_price)

    if in_stock is True:
        base_query = base_query.where(Product.stock > 0)

    if featured is True:
        base_query = base_query.where(Product.is_featured == True)

    if brand:
        base_query = base_query.where(func.lower(Product.brand) == brand.lower())

    # ── Sort ───────────────────────────────────────────────────────────────────
    if sort == "price_asc":
        base_query = base_query.order_by(Product.price.asc())
    elif sort == "price_desc":
        base_query = base_query.order_by(Product.price.desc())
    elif sort == "rating":
        base_query = base_query.order_by(Product.rating.desc())
    elif sort == "popular":
        base_query = base_query.order_by(Product.view_count.desc())
    else:
        base_query = base_query.order_by(Product.created_at.desc())

    # ── Total count ────────────────────────────────────────────────────────────
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0
    total_pages = math.ceil(total / limit) if total else 1

    # ── Paginate ───────────────────────────────────────────────────────────────
    offset = (page - 1) * limit
    paged_query = base_query.offset(offset).limit(limit)
    result = await db.execute(paged_query)
    products = result.scalars().all()

    # ── Format ─────────────────────────────────────────────────────────────────
    formatted = []
    for p in products:
        discounted_price = float(p.price)
        if p.discount_percentage and p.discount_percentage > 0:
            discounted_price = round(float(p.price) * (1 - p.discount_percentage / 100), 2)
        shop = p.vendor.shop if p.vendor else None
        formatted.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "brand": p.brand or "",
            "description": p.description or "",
            "price": float(p.price),
            "original_price": float(p.original_price) if p.original_price else None,
            "discount_percentage": p.discount_percentage,
            "discounted_price": discounted_price,
            "images": p.images or [],
            "tags": p.tags or [],
            "unit": p.unit or "",
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else "Uncategorized",
            "category_slug": p.category.slug if p.category else None,
            "rating": p.rating or 0,
            "review_count": p.review_count or 0,
            "stock": p.stock,
            "in_stock": (p.stock or 0) > 0,
            "is_featured": p.is_featured or False,
            "view_count": p.view_count or 0,
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
                for v in p.variants
            ],
            "created_at": p.created_at.isoformat() if p.created_at else None,
            **_shop_snapshot(p.vendor, shop),
        })

    return {
        "products": formatted,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "filters_applied": {
            "search": search,
            "category_id": category_id,
            "category_slug": category_slug,
            "min_price": min_price,
            "max_price": max_price,
            "in_stock": in_stock,
            "featured": featured,
            "brand": brand,
            "sort": sort,
        },
    }


@router.get("/products/suggestions")
async def get_product_suggestions(
    q: str = Query("", description="Search query"),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return lightweight product suggestions for autocomplete (name + brand + image + price)."""
    q = q.strip()
    if len(q) < 2:
        return []

    term = f"%{q.lower()}%"
    result = await db.execute(
        select(Product.id, Product.name, Product.brand, Product.images, Product.price, Product.original_price, Product.discount_percentage, Product.slug)
        .where(func.lower(Product.status) == "approved")
        .where(
            or_(
                func.lower(Product.name).like(term),
                func.lower(Product.brand).like(term),
            )
        )
        .order_by(Product.view_count.desc(), Product.rating.desc())
        .limit(limit)
    )
    rows = result.all()
    suggestions = []
    for r in rows:
        price = float(r.price or 0)
        if r.discount_percentage and r.discount_percentage > 0:
            price = round(price * (1 - r.discount_percentage / 100), 2)
        suggestions.append({
            "id": r.id,
            "name": r.name,
            "brand": r.brand,
            "image": (r.images or [None])[0],
            "price": price,
            "slug": r.slug,
        })
    return suggestions


@router.get("/products/{product_id}/related")
async def get_related_products(product_id: int, limit: int = 6, db: AsyncSession = Depends(get_db)):
    # Get current product's category
    cur = await db.execute(select(Product.category_id).where(Product.id == product_id))
    category_id = cur.scalar_one_or_none()

    query = (
        select(Product)
        .where(func.lower(Product.status) == "approved")
        .where(Product.id != product_id)
        .options(selectinload(Product.category), selectinload(Product.variants))
        .order_by(Product.rating.desc())
        .limit(limit)
    )
    if category_id:
        query = query.where(Product.category_id == category_id)

    result = await db.execute(query)
    products = result.scalars().all()

    related = []
    for p in products:
        discounted_price = float(p.price)
        if p.discount_percentage and p.discount_percentage > 0:
            discounted_price = round(float(p.price) * (1 - p.discount_percentage / 100), 2)
        related.append({
            "id": p.id, "name": p.name, "slug": p.slug, "brand": p.brand or "",
            "price": float(p.price),
            "original_price": float(p.original_price) if p.original_price else None,
            "discount_percentage": p.discount_percentage,
            "discounted_price": discounted_price,
            "images": p.images or [],
            "category_name": p.category.name if p.category else "Uncategorized",
            "rating": p.rating or 0, "review_count": p.review_count or 0,
            "stock": p.stock, "in_stock": (p.stock or 0) > 0,
        })
    return related


@router.get("/products/{product_id}")
async def get_public_product_by_id(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(func.lower(Product.status) == "approved")
        .options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.vendor).selectinload(Vendor.shop),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    discounted_price = float(product.price)
    if product.discount_percentage and product.discount_percentage > 0:
        discounted_price = round(float(product.price) * (1 - product.discount_percentage / 100), 2)

    shop = product.vendor.shop if product.vendor else None
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "brand": product.brand or "",
        "description": product.description or "",
        "price": float(product.price),
        "original_price": float(product.original_price) if product.original_price else None,
        "discount_percentage": product.discount_percentage,
        "discounted_price": discounted_price,
        "images": product.images or [],
        "tags": product.tags or [],
        "specifications": product.specifications or {},
        "unit": product.unit or "",
        "category_id": product.category_id,
        "category_name": product.category.name if product.category else "Uncategorized",
        "category_slug": product.category.slug if product.category else None,
        "rating": product.rating or 0,
        "review_count": product.review_count or 0,
        "stock": product.stock,
        "in_stock": (product.stock or 0) > 0,
        "is_featured": product.is_featured or False,
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
        **_shop_snapshot(product.vendor, shop),
    }


@router.get("/products/{product_id}/shops")
async def get_product_shops(product_id: int, db: AsyncSession = Depends(get_db)):
    """Return all shops that carry a specific product (approved products only)."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(func.lower(Product.status) == "approved")
        .options(selectinload(Product.vendor).selectinload(Vendor.shop))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    vendor = product.vendor
    shop = vendor.shop if vendor else None
    snap = _shop_snapshot(vendor, shop)
    if not snap:
        return []

    discounted_price = float(product.price)
    if product.discount_percentage and product.discount_percentage > 0:
        discounted_price = round(float(product.price) * (1 - product.discount_percentage / 100), 2)

    return [{
        **snap,
        "product_id": product.id,
        "price": float(product.price),
        "discounted_price": discounted_price,
        "stock": product.stock,
        "in_stock": (product.stock or 0) > 0,
    }]


@router.get("/shops")
async def get_public_shops(
    search: Optional[str] = Query(None, description="Search shop name, city, state, address, description"),
    city: Optional[str] = Query(None, description="Filter by city (case-insensitive)"),
    state: Optional[str] = Query(None, description="Filter by state (case-insensitive)"),
    pincode: Optional[str] = Query(None, description="Filter by pincode"),
    verified: Optional[bool] = Query(None, description="Only show verified shops"),
    lat: Optional[float] = Query(None, description="User latitude for distance sorting"),
    lng: Optional[float] = Query(None, description="User longitude for distance sorting"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Server-side search, filter, and paginate all approved shops."""
    # ── Build base query ──────────────────────────────────────────────────────
    base_q = (
        select(Vendor)
        .join(Shop, Shop.vendor_id == Vendor.id)
        .where(Vendor.status == "approved")
        .options(selectinload(Vendor.shop))
    )

    if search:
        term = f"%{search.lower()}%"
        base_q = base_q.where(
            or_(
                func.lower(Shop.name).like(term),
                func.lower(Vendor.business_name).like(term),
                func.lower(Shop.city).like(term),
                func.lower(Shop.state).like(term),
                func.lower(Shop.address).like(term),
                func.lower(Shop.description).like(term),
            )
        )

    if city:
        base_q = base_q.where(func.lower(Shop.city).like(f"%{city.lower()}%"))

    if state:
        base_q = base_q.where(func.lower(Shop.state).like(f"%{state.lower()}%"))

    if pincode:
        base_q = base_q.where(Shop.pincode == pincode)

    if verified is True:
        base_q = base_q.where(Vendor.verified == True)

    # ── Count ─────────────────────────────────────────────────────────────────
    count_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_result.scalar() or 0
    total_pages = math.ceil(total / limit) if total else 1

    # ── Product counts per vendor ─────────────────────────────────────────────
    prod_count_result = await db.execute(
        select(Product.vendor_id, func.count(Product.id).label("cnt"))
        .where(func.lower(Product.status) == "approved")
        .group_by(Product.vendor_id)
    )
    product_counts = {row.vendor_id: row.cnt for row in prod_count_result.all()}

    # ── Fetch page (no distance sort in SQL — done in Python) ─────────────────
    if lat and lng:
        # fetch all matching rows, sort by distance, then slice
        result = await db.execute(base_q)
        all_vendors = result.scalars().all()

        def _dist(v):
            s = v.shop
            if s and s.latitude and s.longitude:
                dlat = math.radians(float(s.latitude) - lat)
                dlng = math.radians(float(s.longitude) - lng)
                a = (math.sin(dlat / 2) ** 2 +
                     math.cos(math.radians(lat)) * math.cos(math.radians(float(s.latitude))) *
                     math.sin(dlng / 2) ** 2)
                return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return 9999

        all_vendors.sort(key=_dist)
        offset = (page - 1) * limit
        vendors = all_vendors[offset: offset + limit]
    else:
        base_q = base_q.order_by(Vendor.created_at.desc())
        result = await db.execute(base_q.offset((page - 1) * limit).limit(limit))
        vendors = result.scalars().all()

    # ── Format ────────────────────────────────────────────────────────────────
    shops = []
    for vendor in vendors:
        shop = vendor.shop
        if not shop:
            continue

        shop_lat = float(shop.latitude) if shop.latitude else None
        shop_lng = float(shop.longitude) if shop.longitude else None

        distance_km = None
        if lat and lng and shop_lat and shop_lng:
            dlat = math.radians(shop_lat - lat)
            dlng = math.radians(shop_lng - lng)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat)) * math.cos(math.radians(shop_lat)) *
                 math.sin(dlng / 2) ** 2)
            distance_km = round(6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

        shops.append({
            "vendor_id": vendor.id,
            "shop_name": shop.name or vendor.business_name or "",
            "description": shop.description or "",
            "logo_url": shop.logo_url,
            "banner_url": shop.banner_url,
            "city": shop.city,
            "state": shop.state,
            "address": shop.address,
            "pincode": shop.pincode,
            "shop_phone": vendor.business_phone or "",
            "shop_lat": shop_lat,
            "shop_lng": shop_lng,
            "verified": vendor.verified or False,
            "opening_time": str(shop.opening_time) if shop.opening_time else None,
            "closing_time": str(shop.closing_time) if shop.closing_time else None,
            "working_days": shop.working_days or [],
            "total_products": product_counts.get(vendor.id, 0),
            "distance_km": distance_km,
        })

    return {
        "shops": shops,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


@router.get("/test")
async def test_endpoint():
    """Simple test endpoint to verify the router is working"""
    return {"message": "Public router is working", "status": "ok"}


@router.get("/showcase-page", response_class=HTMLResponse)
async def get_showcase_page():
    """Serve the eye-catching showcase HTML page"""
    html_path = frontend_path("showcase.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


@router.get("/vendor/{vendor_id}")
async def get_vendor_public_profile(vendor_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get public vendor profile with shop information and products
    This endpoint is publicly accessible and shows only approved vendors
    """
    try:
        # Get vendor by ID, or by user_id if not found
        result = await db.execute(
            select(Vendor)
            .where(Vendor.id == vendor_id)
            .options(selectinload(Vendor.shop), selectinload(Vendor.marketplace_settings))
        )
        vendor = result.scalar_one_or_none()
        
        if not vendor:
            # Fallback: try by user_id
            result = await db.execute(
                select(Vendor)
                .where(Vendor.user_id == vendor_id)
                .options(selectinload(Vendor.shop), selectinload(Vendor.marketplace_settings))
            )
            vendor = result.scalar_one_or_none()
        
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        # Only show approved vendors publicly (temporarily allow all for testing)
        # if vendor.status != "approved":
        #     raise HTTPException(status_code=404, detail="Vendor not approved")
        
        # Get vendor's user
        result = await db.execute(select(User).where(User.id == vendor.user_id))
        user = result.scalar_one_or_none()
        
        # Get vendor's active products
        products_result = await db.execute(
            select(Product)
            .where(
                Product.vendor_id == vendor.id,
                func.lower(Product.status) == "approved"
            )
            .options(selectinload(Product.category), selectinload(Product.variants))
            .order_by(Product.created_at.desc())
        )
        products = products_result.scalars().all()
        
        # Format products for response
        formatted_products = []
        for product in products:
            # Calculate discounted price
            discounted_price = float(product.price)
            if product.discount_percentage and product.discount_percentage > 0:
                discounted_price = round(
                    float(product.price) * (1 - product.discount_percentage / 100), 2
                )
            
            formatted_products.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": float(product.price),
                "original_price": float(product.original_price) if product.original_price else None,
                "discount_percentage": product.discount_percentage,
                "discounted_price": discounted_price,
                "category_name": product.category.name if product.category else "Uncategorized",
                "images": product.images or [],
                "status": product.status,
                "stock": product.stock,
                "brand": product.brand,
                "unit": product.unit,
                "rating": product.rating,
                "review_count": product.review_count,
                "variants": [
                    {
                        "id": v.id,
                        "size": v.size,
                        "color": v.color,
                        "sku": v.sku,
                        "price": float(v.price) if v.price else None,
                        "stock": v.stock,
                    }
                    for v in product.variants
                ],
                "created_at": product.created_at.isoformat() if product.created_at else None,
            })
        
        storefront = effective_storefront_payload(vendor, vendor.shop, products)
        categories = []
        seen_categories = set()
        for product in products:
            category_name = product.category.name if product.category else "Uncategorized"
            if category_name not in seen_categories:
                seen_categories.add(category_name)
                categories.append(category_name)

        # Format shop data
        shop = vendor.shop
        shop_data = {
            "id": shop.id if shop else None,
            "name": shop.name if shop else vendor.business_name,
            "description": shop.description if shop else None,
            "logo_url": shop.logo_url if shop else None,
            "banner_url": shop.banner_url if shop else None,
            "gallery": shop.gallery if shop else [],
            "address": shop.address if shop else None,
            "city": shop.city if shop else None,
            "state": shop.state if shop else None,
            "postal_code": shop.pincode if shop else None,
            "latitude": float(shop.latitude) if shop and shop.latitude else None,
            "longitude": float(shop.longitude) if shop and shop.longitude else None,
            "contact_phone": vendor.business_phone or (user.phone if user else None),
            "contact_email": vendor.business_email or (user.email if user else None),
            "opening_time": str(shop.opening_time) if shop and shop.opening_time else None,
            "closing_time": str(shop.closing_time) if shop and shop.closing_time else None,
            "working_days": shop.working_days if shop else [],
        }
        
        # Format vendor data
        vendor_data = {
            "id": vendor.id,
            "user_id": vendor.user_id,
            "business_name": vendor.business_name,
            "business_email": vendor.business_email,
            "business_phone": vendor.business_phone,
            "gst_number": vendor.gst_number,
            "pan_number": vendor.pan_number,
            "status": vendor.status,
            "verified": vendor.verified,
        }
        
        return {
            "vendor": vendor_data,
            "shop": shop_data,
            "storefront": storefront,
            "categories": categories,
            "products": formatted_products,
            "total_products": len(formatted_products),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load vendor profile: {str(e)}")


@router.get("/vendor/storefront/{vendor_slug}")
async def get_vendor_storefront_by_slug(vendor_slug: str, db: AsyncSession = Depends(get_db)):
    """
    Resolve a vendor storefront by slug.
    """
    vendors_result = await db.execute(
        select(Vendor)
        .options(selectinload(Vendor.shop), selectinload(Vendor.marketplace_settings))
        .order_by(Vendor.created_at.desc())
    )
    vendors = vendors_result.scalars().all()

    for vendor in vendors:
        shop_name = vendor.shop.name if vendor.shop else vendor.business_name
        payload = effective_storefront_payload(vendor, vendor.shop, [])
        candidate_slugs = {
            slugify(shop_name or ""),
            slugify(vendor.business_name or ""),
            payload.get("seo", {}).get("slug"),
            str(vendor.id),
        }
        if vendor_slug in {slug for slug in candidate_slugs if slug}:
            return await get_vendor_public_profile(vendor.id, db)

    raise HTTPException(status_code=404, detail="Vendor not found")


@router.get("/vendor/{vendor_id}/marketplace-settings")
async def get_vendor_marketplace_settings(vendor_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get vendor marketplace settings for public preview
    This endpoint applies custom settings to vendor's storefront
    """
    try:
        # Get vendor by ID
        result = await db.execute(
            select(Vendor)
            .where(Vendor.id == vendor_id)
            .options(selectinload(Vendor.marketplace_settings))
        )
        vendor = result.scalar_one_or_none()
        
        if not vendor:
            result = await db.execute(
                select(Vendor)
                .where(Vendor.user_id == vendor_id)
                .options(selectinload(Vendor.marketplace_settings))
            )
            vendor = result.scalar_one_or_none()
        
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        # Only show approved vendors publicly (temporarily allow all for testing)
        # if vendor.status != "approved":
        #     raise HTTPException(status_code=404, detail="Vendor not approved")
        
        products_result = await db.execute(
            select(Product)
            .where(
                Product.vendor_id == vendor.id,
                func.lower(Product.status) == "approved"
            )
            .options(selectinload(Product.category))
        )
        products = products_result.scalars().all()

        settings = vendor.marketplace_settings
        payload = effective_storefront_payload(vendor, vendor.shop, products)
        return {
            "status": "live" if settings and settings.storefront_published else "draft",
            "published_at": settings.published_at.isoformat() if settings and settings.published_at else None,
            "payload": payload,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load marketplace settings: {str(e)}")


@router.get("/showcase")
async def get_vendors_showcase(db: AsyncSession = Depends(get_db)):
    """
    Get all approved vendors with their products for the showcase page
    This endpoint returns a marketplace view of all vendors
    """
    try:
        # Get all approved vendors
        vendors_result = await db.execute(
            select(Vendor)
            .where(Vendor.status == "approved")
            .options(selectinload(Vendor.shop), selectinload(Vendor.marketplace_settings))
            .order_by(Vendor.created_at.desc())
        )
        vendors = vendors_result.scalars().all()
        
        showcase_data = []
        
        for vendor in vendors:
            # Get user
            user_result = await db.execute(select(User).where(User.id == vendor.user_id))
            user = user_result.scalar_one_or_none()
            
            # Get vendor's active products
            products_result = await db.execute(
                select(Product)
                .where(
                    Product.vendor_id == vendor.id,
                    func.lower(Product.status) == "approved"
                )
                .options(selectinload(Product.category), selectinload(Product.variants))
                .order_by(Product.created_at.desc())
            )
            products = products_result.scalars().all()
            
            # Format products
            formatted_products = []
            for product in products:
                discounted_price = float(product.price)
                if product.discount_percentage and product.discount_percentage > 0:
                    discounted_price = round(
                        float(product.price) * (1 - product.discount_percentage / 100), 2
                    )
                
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "price": float(product.price),
                    "original_price": float(product.original_price) if product.original_price else None,
                    "discount_percentage": product.discount_percentage,
                    "discounted_price": discounted_price,
                    "category_name": product.category.name if product.category else "Uncategorized",
                    "images": product.images or [],
                    "status": product.status,
                    "stock": product.stock,
                    "brand": product.brand,
                    "rating": product.rating,
                })
            
            shop = vendor.shop
            storefront = effective_storefront_payload(vendor, shop, products)
            categories = []
            seen_categories = set()
            for product in products:
                category_name = product.category.name if product.category else "Uncategorized"
                if category_name not in seen_categories:
                    seen_categories.add(category_name)
                    categories.append(category_name)
            
            vendor_showcase = {
                "vendor_id": vendor.id,
                "user_id": vendor.user_id,
                "business_name": vendor.business_name,
                "owner_name": user.name if user else vendor.business_name,
                "description": shop.description if shop else f"Shop by {vendor.business_name}",
                "address": shop.address if shop else None,
                "city": shop.city if shop else None,
                "state": shop.state if shop else None,
                "latitude": float(shop.latitude) if shop and shop.latitude else None,
                "longitude": float(shop.longitude) if shop and shop.longitude else None,
                "contact_phone": vendor.business_phone or (user.phone if user else None),
                "contact_email": vendor.business_email or (user.email if user else None),
                "status": vendor.status,
                "verified": vendor.verified,
                "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                "banner_url": shop.banner_url if shop else None,
                "logo_url": shop.logo_url if shop else None,
                "opening_time": str(shop.opening_time) if shop and shop.opening_time else None,
                "closing_time": str(shop.closing_time) if shop and shop.closing_time else None,
                "working_days": shop.working_days if shop else [],
                "total_products": len(formatted_products),
                "products": formatted_products,
                "categories": categories,
                "storefront": storefront,
                "slug": storefront.get("seo", {}).get("slug"),
                "has_unpublished_changes": bool(vendor.marketplace_settings and (not vendor.marketplace_settings.storefront_published or vendor.marketplace_settings.storefront_draft != vendor.marketplace_settings.storefront_published)),
            }
            
            showcase_data.append(vendor_showcase)
        
        return {
            "vendors": showcase_data,
            "total_vendors": len(showcase_data),
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to load showcase data",
            "vendors": [],
            "total_vendors": 0
        }


@router.get("/website-settings/home", response_model=WebsiteSettingsHomeResponse)
async def get_public_home_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsHomeResponse.model_validate(settings)


@router.get("/website-settings/maintenance", response_model=WebsiteSettingsMaintenanceResponse)
async def get_public_maintenance_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsMaintenanceResponse.model_validate(settings)


@router.get("/website-settings/social-links", response_model=WebsiteSettingsSocialResponse)
async def get_public_social_links(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsSocialResponse.model_validate(settings)


@router.get("/website-settings/shipping", response_model=WebsiteSettingsShippingResponse)
async def get_public_shipping_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsShippingResponse.model_validate(settings)


@router.get("/website-settings/browse-categories", response_model=WebsiteSettingsBrowseCategoriesResponse)
async def get_public_browse_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsBrowseCategoriesResponse.model_validate(settings)


@router.get("/website-settings/top-navigation", response_model=WebsiteSettingsNavResponse)
async def get_public_top_navigation(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsNavResponse.model_validate(settings)


@router.get("/website-settings/blog-posts", response_model=WebsiteSettingsBlogResponse)
async def get_public_blog_posts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsBlogResponse.model_validate(settings)


@router.get("/website-settings/promo-sections", response_model=WebsiteSettingsPromoResponse)
async def get_public_promo_sections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsPromoResponse.model_validate(settings)


@router.get("/website-settings/banner-slider", response_model=WebsiteSettingsBannerResponse)
async def get_public_banner_slider(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsBannerResponse.model_validate(settings)


@router.get("/website-settings/appearance", response_model=WebsiteSettingsAppearanceResponse)
async def get_public_appearance_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsAppearanceResponse.model_validate(settings)


@router.get("/website-settings/general", response_model=WebsiteSettingsGeneralResponse)
async def get_public_general_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return WebsiteSettingsGeneralResponse.model_validate(settings)

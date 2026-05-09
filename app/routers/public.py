from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
from pathlib import Path
from slugify import slugify

from app.core.database import get_db
from app.models.user import User, Vendor, Product, Category, Shop, ProductVariant, MarketplaceSettings, WebsiteSettings
from app.schemas.schemas import WebsiteSettingsGeneralResponse

router = APIRouter(prefix="/public", tags=["public"])

CATEGORY_PALETTE = [
    "#f5ede0", "#fef0f8", "#f0f4fe", "#f5f0e8",
    "#eef8ee", "#ede8f8", "#fff4e8", "#fde8f0",
]


def _category_bg(index: int) -> str:
    return CATEGORY_PALETTE[index % len(CATEGORY_PALETTE)]


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
    category_id: int | None = None,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """Return active products, optionally filtered by category_id."""
    query = (
        select(Product)
        .where(func.lower(Product.status) == "active")
        .options(selectinload(Product.category), selectinload(Product.variants))
        .order_by(Product.created_at.desc())
    )
    if category_id:
        query = query.where(Product.category_id == category_id)
    query = query.limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    formatted = []
    for p in products:
        discounted_price = float(p.price)
        if p.discount_percentage and p.discount_percentage > 0:
            discounted_price = round(float(p.price) * (1 - p.discount_percentage / 100), 2)
        formatted.append({
            "id": p.id,
            "name": p.name,
            "brand": p.brand or "",
            "price": float(p.price),
            "original_price": float(p.original_price) if p.original_price else None,
            "discount_percentage": p.discount_percentage,
            "discounted_price": discounted_price,
            "images": p.images or [],
            "category_name": p.category.name if p.category else "Uncategorized",
            "category_id": p.category_id,
            "rating": p.rating or 0,
            "review_count": p.review_count or 0,
            "stock": p.stock,
        })

    return {"products": formatted, "total": len(formatted)}


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
                func.lower(Product.status) == "active"
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
            "contact_phone": vendor.business_phone or (user.phone if user else None),
            "contact_email": vendor.business_email or (user.email if user else None),
            "opening_time": shop.opening_time if shop else None,
            "closing_time": shop.closing_time if shop else None,
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
                func.lower(Product.status) == "active"
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
                    func.lower(Product.status) == "active"
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
                "contact_phone": vendor.business_phone or (user.phone if user else None),
                "contact_email": vendor.business_email or (user.email if user else None),
                "status": vendor.status,
                "verified": vendor.verified,
                "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                "banner_url": shop.banner_url if shop else None,
                "logo_url": shop.logo_url if shop else None,
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

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Body, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User, Vendor, Shop, Product, ProductVariant, Order, OrderItem, Payout
from app.schemas.schemas import (
    VendorCreate, VendorUpdate, VendorResponse,
    ShopCreate, ShopUpdate, ShopResponse,
    ProductCreate, ProductUpdate, ProductResponse,
    OrderResponse, OrderStatusUpdate, PaginatedResponse,
    PayoutRequest, PayoutResponse, VendorDashboard
)
from slugify import slugify
import math
from decimal import Decimal

router = APIRouter(prefix="/vendor", tags=["Vendor"])
get_vendor_user = require_role("VENDOR", "ADMIN")


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

@router.post("/shop/logo", response_model=dict)
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    
    # Get shop
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    # Save file (in production, use cloud storage)
    # For now, return a mock URL
    logo_url = f"http://localhost:8000/uploads/logos/{vendor.id}_{file.filename}"
    
    # Update shop
    shop.logo_url = logo_url
    await db.commit()
    
    return {"url": logo_url}


@router.post("/shop/banner", response_model=dict)
async def upload_banner(
    file: UploadFile = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    
    # Get shop
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    # Save file (in production, use cloud storage)
    # For now, return a mock URL
    banner_url = f"http://localhost:8000/uploads/banners/{vendor.id}_{file.filename}"
    
    # Update shop
    shop.banner_url = banner_url
    await db.commit()
    
    return {"url": banner_url}


@router.post("/shop/gallery", response_model=dict)
async def upload_gallery(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    
    # Get shop
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Validate files
    urls = []
    current_gallery = shop.gallery or []
    
    for file in files:
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Only image files are allowed")
        
        # Save file (in production, use cloud storage)
        # For now, return a mock URL
        url = f"http://localhost:8000/uploads/gallery/{vendor.id}_{file.filename}"
        urls.append(url)
    
    # Update shop gallery
    shop.gallery = current_gallery + urls
    await db.commit()
    
    return {"urls": urls}


@router.delete("/shop/gallery")
async def remove_gallery_image(
    url: str = Body(...),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    
    # Get shop
    result = await db.execute(select(Shop).where(Shop.vendor_id == vendor.id))
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Remove URL from gallery
    if shop.gallery and url in shop.gallery:
        shop.gallery.remove(url)
        await db.commit()
    
    return {"message": "Image removed from gallery"}


# ─── Products ────────────────────────────────────────────────────────────────

async def get_vendor(user: User, db: AsyncSession) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    data: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    video: UploadFile = File(None),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)

    # Parse JSON data from form
    import json
    product_data = json.loads(data)
    
    # Handle image uploads - save actual files
    image_urls = []
    import os
    from pathlib import Path
    
    # Create uploads directory if it doesn't exist
    uploads_dir = Path("uploads/products")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    for i, image in enumerate(images):
        # Generate unique filename
        filename = f"{vendor.id}_{i}_{image.filename}"
        file_path = uploads_dir / filename
        
        # Save the file
        content = await image.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Create URL for the saved image
        image_url = f"http://localhost:8000/uploads/products/{filename}"
        image_urls.append(image_url)
    
    # Handle video upload
    video_url = None
    if video:
        video_url = f"http://localhost:8000/uploads/products/{vendor.id}_video_{video.filename}"

    # Generate unique slug
    base_slug = slugify(product_data["name"])
    unique_slug = f"{base_slug}-{vendor.id}"
    
    # Check if slug exists and add timestamp if needed
    existing_slug = await db.execute(
        select(Product).where(Product.slug == unique_slug)
    )
    if existing_slug.scalar_one_or_none():
        import time
        unique_slug = f"{base_slug}-{vendor.id}-{int(time.time())}"
    
    # Extract variants before creating product
    variants = product_data.get("variants", [])
    
    # Create product with only valid Product fields
    product_dict = {
        "vendor_id": vendor.id,
        "slug": unique_slug,
        "status": "active",
        "images": image_urls,
        # Only include fields that exist in Product model
        "name": product_data.get("name"),
        "description": product_data.get("description"),
        "brand": product_data.get("brand"),
        "category_id": int(product_data.get("category_id", 0)) if product_data.get("category_id") else None,
        "price": float(product_data.get("price", 0)),
        "stock": int(product_data.get("stock", 0)),
        "tags": product_data.get("tags", []),
    }
    
    try:
        product = Product(**product_dict)
        db.add(product)
        await db.flush()

        # Add variants with proper data handling
        if variants:
            for v in variants:
                # Ensure variant data is properly structured
                variant_data = {
                    "product_id": product.id,
                    "size": v.get("size"),
                    "color": v.get("color"),
                    "sku": v.get("sku"),  # Add SKU field
                    "price": float(v.get("price", 0)) if v.get("price") else None,
                    "stock": int(v.get("stock", 0)),
                    "images": v.get("images", []),
                }
                # Only add variant if it has meaningful data
                if variant_data["color"] or variant_data["stock"] > 0:
                    variant = ProductVariant(**variant_data)
                    db.add(variant)

        await db.commit()
        await db.refresh(product)
    except Exception as e:
        await db.rollback()
        print(f"Error creating product: {e}")
        print(f"Product data: {product_dict}")
        raise HTTPException(status_code=500, detail=f"Failed to create product: {str(e)}")

    result = await db.execute(
        select(Product).where(Product.id == product.id).options(selectinload(Product.variants))
    )
    return result.scalar_one()


@router.get("/products", response_model=PaginatedResponse)
async def list_vendor_products(
    status: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    query = select(Product).where(Product.vendor_id == vendor.id)
    if status:
        query = query.where(Product.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(
        query.offset(offset).limit(limit).options(selectinload(Product.variants))
    )
    products = result.scalars().all()
    
    # Convert Product objects to dictionaries for serialization
    items = []
    for product in products:
        product_dict = {
            "id": product.id,
            "vendor_id": product.vendor_id,
            "category_id": product.category_id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "brand": product.brand,
            "price": float(product.price),
            "original_price": float(product.original_price) if product.original_price else None,
            "stock": product.stock,
            "unit": product.unit,
            "status": product.status,
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
                    "images": v.images or []
                }
                for v in product.variants
            ],
            "created_at": product.created_at.isoformat() if product.created_at else None
        }
        items.append(product_dict)

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit,
        pages=math.ceil(total / limit)
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
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    if payload.name:
        product.slug = slugify(payload.name)

    # Reset to pending review on price/description change
    if payload.price or payload.description:
        product.status = "pending"

    await db.commit()
    await db.refresh(product)
    return product


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

@router.get("/analytics/dashboard", response_model=VendorDashboard)
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

    conversion_rate = (total_orders / max(total_views, 1)) * 100

    return VendorDashboard(
        total_views=total_views,
        total_orders=total_orders,
        revenue=revenue,
        conversion_rate=round(conversion_rate, 2),
        pending_orders=pending_orders,
        total_products=total_products,
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
    return payout

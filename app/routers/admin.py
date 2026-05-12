from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import require_role
from app.models.user import (
    User, Vendor, Shop, Product, Order, OrderItem,
    Category, Coupon, Payout, Event, VendorFeedback, WebsiteSettings
)
from app.schemas.schemas import (
    UserResponse, VendorResponse, ProductResponse, CategoryCreate,
    CategoryUpdate, CategoryResponse, CouponCreate, CouponUpdate,
    CouponResponse, AdminAnalytics, PaginatedResponse, PayoutResponse,
    FeedbackResponse, AdminFeedbackUpdate,
    WebsiteSettingsUpdate, WebsiteSettingsResponse, WebsiteSettingsGeneralResponse
)
from slugify import slugify
import math
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import base64
import binascii
import re

router = APIRouter(prefix="/admin", tags=["Admin"])
get_admin = require_role("ADMIN")
DATA_IMAGE_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)


# ─── User Management ─────────────────────────────────────────────────────────

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    role: str = None,
    status: str = None,
    search: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if search:
        query = query.where(
            User.name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
        )
    query = query.order_by(User.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total, page=page, limit=limit,
        pages=math.ceil(total / limit)
    )


@router.put("/users/{user_id}/block", response_model=dict)
async def block_user(
    user_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "ADMIN":
        raise HTTPException(status_code=403, detail="Cannot block admin user")
    user.status = "blocked" if user.status == "active" else "active"
    await db.commit()
    return {"message": f"User {user.status}", "user_id": user_id}


# ─── Vendor Management ───────────────────────────────────────────────────────

@router.get("/vendors", response_model=PaginatedResponse)
async def list_vendors(
    status: str = None,
    verified: bool = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Vendor)
    if status:
        query = query.where(Vendor.status == status)
    if verified is not None:
        query = query.where(Vendor.verified == verified)
    query = query.order_by(Vendor.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return PaginatedResponse(
        items=[VendorResponse.model_validate(v) for v in items],
        total=total, page=page, limit=limit,
        pages=math.ceil(total / limit)
    )


async def _update_vendor_status(vendor_id: int, status: str, db: AsyncSession) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    vendor.status = status
    if status == "approved":
        vendor.verified = True
        # Update user role
        result = await db.execute(select(User).where(User.id == vendor.user_id))
        user = result.scalar_one_or_none()
        if user:
            user.role = "VENDOR"
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.put("/vendors/{vendor_id}/approve", response_model=VendorResponse)
async def approve_vendor(
    vendor_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _update_vendor_status(vendor_id, "approved", db)


@router.put("/vendors/{vendor_id}/reject", response_model=VendorResponse)
async def reject_vendor(
    vendor_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _update_vendor_status(vendor_id, "rejected", db)


@router.put("/vendors/{vendor_id}/suspend", response_model=VendorResponse)
async def suspend_vendor(
    vendor_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _update_vendor_status(vendor_id, "suspended", db)


# ─── Product Approval ────────────────────────────────────────────────────────

@router.get("/products", response_model=PaginatedResponse)
async def list_products_admin(
    status: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Product)
    if status:
        query = query.where(Product.status == status)
    query = query.order_by(Product.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(
        query.offset(offset).limit(limit).options(selectinload(Product.variants))
    )
    items = result.scalars().all()

    return PaginatedResponse(
        items=[ProductResponse.model_validate(p) for p in items],
        total=total, page=page, limit=limit,
        pages=math.ceil(total / limit)
    )


@router.put("/products/{product_id}/approve", response_model=dict)
async def approve_product(
    product_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.status = "approved"
    await db.commit()
    return {"message": "Product approved", "product_id": product_id}


@router.put("/products/{product_id}/reject", response_model=dict)
async def reject_product(
    product_id: int,
    reason: str = Query(default=""),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.status = "rejected"
    await db.commit()
    return {"message": "Product rejected", "product_id": product_id, "reason": reason}


@router.delete("/products/{product_id}", response_model=dict)
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(product)
    await db.commit()
    return {"message": "Product deleted", "product_id": product_id}


@router.put("/products/{product_id}/feature", response_model=dict)
async def feature_product(
    product_id: int,
    payload: dict,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_featured = bool(payload.get("is_featured", False))
    await db.commit()
    return {"message": "Product updated", "product_id": product_id, "is_featured": product.is_featured}


@router.post("/products", response_model=ProductResponse, status_code=201)
async def admin_create_product(
    payload: dict,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin creates a product directly (JSON body, images as URL list, auto-approved)."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Product name is required")
    price = payload.get("price")
    if price is None:
        raise HTTPException(status_code=400, detail="Price is required")
    category_id = payload.get("category_id")
    if not category_id:
        raise HTTPException(status_code=400, detail="Category is required")
    vendor_id = payload.get("vendor_id")
    if not vendor_id:
        raise HTTPException(status_code=400, detail="Vendor is required")

    # Verify vendor exists
    vr = await db.execute(select(Vendor).where(Vendor.id == int(vendor_id)))
    if not vr.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Generate unique slug
    from slugify import slugify as _sl
    base = _sl(name)
    slug = base
    i = 1
    while (await db.execute(select(Product.id).where(Product.slug == slug))).scalar_one_or_none():
        slug = f"{base}-{i}"; i += 1

    tags = payload.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    images = payload.get("images", [])
    if isinstance(images, str):
        images = [u.strip() for u in images.split("\n") if u.strip()]

    product = Product(
        vendor_id=int(vendor_id),
        category_id=int(category_id),
        name=name,
        slug=slug,
        description=payload.get("description"),
        brand=payload.get("brand"),
        price=float(price),
        original_price=float(payload["original_price"]) if payload.get("original_price") else None,
        discount_percentage=int(payload["discount_percentage"]) if payload.get("discount_percentage") else None,
        stock=int(payload.get("stock") or 0),
        unit=payload.get("unit"),
        status=payload.get("status", "approved"),
        is_featured=bool(payload.get("is_featured", False)),
        images=images,
        tags=tags,
        specifications=payload.get("specifications") or {},
    )
    db.add(product)
    await db.commit()
    result = await db.execute(
        select(Product).where(Product.id == product.id)
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    return ProductResponse.model_validate(result.scalar_one())


@router.put("/products/{product_id}", response_model=ProductResponse)
async def admin_update_product(
    product_id: int,
    payload: dict,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    updatable = ["name", "description", "brand", "price", "original_price",
                 "discount_percentage", "stock", "unit", "status", "is_featured",
                 "images", "tags", "specifications", "category_id"]
    for field in updatable:
        if field in payload:
            val = payload[field]
            if field in ("price", "original_price") and val is not None:
                val = float(val)
            elif field in ("discount_percentage", "stock", "category_id") and val is not None:
                val = int(val)
            elif field == "tags" and isinstance(val, str):
                val = [t.strip() for t in val.split(",") if t.strip()]
            elif field == "images" and isinstance(val, str):
                val = [u.strip() for u in val.split("\n") if u.strip()]
            setattr(product, field, val)

    await db.commit()
    result = await db.execute(
        select(Product).where(Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    return ProductResponse.model_validate(result.scalar_one())


@router.get("/vendors/list", response_model=list[dict])
async def admin_list_vendors_simple(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight vendor list for dropdowns."""
    result = await db.execute(
        select(Vendor.id, Vendor.business_name).where(Vendor.status == "approved").order_by(Vendor.business_name)
    )
    return [{"id": r.id, "business_name": r.business_name} for r in result.all()]


# ─── Categories ──────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryResponse])
async def admin_list_categories(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).options(selectinload(Category.children))
        .order_by(Category.sort_order)
    )
    return result.scalars().all()


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    category = Category(
        **payload.model_dump(),
        slug=slugify(payload.name),
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(category, field, value)
    if payload.name:
        category.slug = slugify(payload.name)

    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", response_model=dict)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    category.is_active = False
    await db.commit()
    return {"message": "Category deactivated"}


# ─── Analytics ───────────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AdminAnalytics)
async def system_analytics(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)).where(User.role == "USER"))).scalar()
    total_vendors = (await db.execute(select(func.count(Vendor.id)))).scalar()
    total_products = (await db.execute(select(func.count(Product.id)).where(Product.status == "approved"))).scalar()
    total_orders = (await db.execute(select(func.count(Order.id)))).scalar()

    revenue_result = await db.execute(
        select(func.sum(Order.final_amount)).where(Order.payment_status == "paid")
    )
    revenue = revenue_result.scalar() or Decimal("0")

    # Top products by order count
    top_products_result = await db.execute(
        select(
            Product.id, Product.name,
            func.count(OrderItem.id).label("order_count")
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .group_by(Product.id, Product.name)
        .order_by(func.count(OrderItem.id).desc())
        .limit(10)
    )
    top_products = [
        {"id": row.id, "name": row.name, "order_count": row.order_count}
        for row in top_products_result
    ]

    # Cart abandonment: carts with items but no corresponding order
    total_carts = (await db.execute(select(func.count(User.id)))).scalar()
    orders_with_payment = (await db.execute(
        select(func.count(Order.id)).where(Order.payment_status == "paid")
    )).scalar()
    cart_abandonment_rate = round(
        (1 - (orders_with_payment / max(total_carts, 1))) * 100, 2
    )

    pending_vendor_approvals = (await db.execute(
        select(func.count(Vendor.id)).where(Vendor.status == "pending")
    )).scalar()
    pending_product_approvals = (await db.execute(
        select(func.count(Product.id)).where(Product.status == "pending")
    )).scalar()

    return AdminAnalytics(
        total_users=total_users,
        total_vendors=total_vendors,
        total_products=total_products,
        total_orders=total_orders,
        revenue=revenue,
        top_products=top_products,
        cart_abandonment_rate=cart_abandonment_rate,
        pending_vendor_approvals=pending_vendor_approvals,
        pending_product_approvals=pending_product_approvals,
    )


# ─── Coupons ─────────────────────────────────────────────────────────────────

@router.get("/coupons", response_model=list[CouponResponse])
async def list_coupons(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Coupon).order_by(Coupon.created_at.desc()))
    return result.scalars().all()


@router.post("/coupons", response_model=CouponResponse, status_code=201)
async def create_coupon(
    payload: CouponCreate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    # Check duplicate code
    result = await db.execute(select(Coupon).where(Coupon.code == payload.code.upper()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Coupon code already exists")

    coupon = Coupon(**payload.model_dump(), code=payload.code.upper())
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)
    return coupon


@router.put("/coupons/{coupon_id}", response_model=CouponResponse)
async def update_coupon(
    coupon_id: int,
    payload: CouponUpdate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(coupon, field, value)
    await db.commit()
    await db.refresh(coupon)
    return coupon


@router.delete("/coupons/{coupon_id}", response_model=dict)
async def delete_coupon(
    coupon_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
    coupon = result.scalar_one_or_none()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    coupon.is_active = False
    await db.commit()
    return {"message": "Coupon deactivated"}


# ─── Payout Management ───────────────────────────────────────────────────────

@router.get("/payouts", response_model=list[PayoutResponse])
async def list_payouts(
    status: str = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Payout)
    if status:
        query = query.where(Payout.status == status)
    query = query.order_by(Payout.requested_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.put("/payouts/{payout_id}/process", response_model=PayoutResponse)
async def process_payout(
    payout_id: int,
    utr_number: str = Query(...),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    payout.status = "completed"
    payout.utr_number = utr_number
    payout.processed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(payout)
    return payout


# ─── Help & Feedback Management ──────────────────────────────────────────────

VALID_FEEDBACK_STATUSES = {"open", "in_progress", "resolved", "closed"}
VALID_FEEDBACK_PRIORITIES = {"low", "medium", "high"}


@router.get("/feedback", response_model=PaginatedResponse)
async def list_all_feedback(
    type: str = None,
    status: str = None,
    priority: str = None,
    vendor_id: int = None,
    search: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(VendorFeedback)
    if type:
        query = query.where(VendorFeedback.type == type)
    if status:
        query = query.where(VendorFeedback.status == status)
    if priority:
        query = query.where(VendorFeedback.priority == priority)
    if vendor_id:
        query = query.where(VendorFeedback.vendor_id == vendor_id)
    if search:
        query = query.where(
            VendorFeedback.subject.ilike(f"%{search}%") |
            VendorFeedback.description.ilike(f"%{search}%")
        )
    query = query.order_by(VendorFeedback.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    rows = await db.execute(query.offset(offset).limit(limit))
    items = rows.scalars().all()

    return PaginatedResponse(
        items=[FeedbackResponse.model_validate(f) for f in items],
        total=total, page=page, limit=limit,
        pages=math.ceil(total / limit) if total else 1,
    )


@router.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(
    feedback_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(VendorFeedback).where(VendorFeedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackResponse.model_validate(feedback)


@router.put("/feedback/{feedback_id}", response_model=FeedbackResponse)
async def update_feedback(
    feedback_id: int,
    payload: AdminFeedbackUpdate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(VendorFeedback).where(VendorFeedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if payload.status is not None:
        if payload.status not in VALID_FEEDBACK_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(VALID_FEEDBACK_STATUSES)}")
        feedback.status = payload.status

    if payload.priority is not None:
        if payload.priority not in VALID_FEEDBACK_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"Invalid priority. Must be one of: {', '.join(VALID_FEEDBACK_PRIORITIES)}")
        feedback.priority = payload.priority

    if payload.admin_response is not None:
        feedback.admin_response = payload.admin_response
        feedback.admin_response_at = datetime.utcnow()

    await db.commit()
    await db.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)


# ─── Website Settings ─────────────────────────────────────────────────────────

async def _get_or_create_website_settings(db: AsyncSession) -> WebsiteSettings:
    result = await db.execute(select(WebsiteSettings).where(WebsiteSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = WebsiteSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


def _save_settings_data_image(value: str, base_url: str) -> str:
    match = DATA_IMAGE_RE.match(value)
    if not match:
        return value

    mime_type, encoded = match.groups()
    extension = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/x-icon": "ico",
        "image/vnd.microsoft.icon": "ico",
    }.get(mime_type.lower())
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported image data URL type")

    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image data URL") from exc

    max_image_size = 5 * 1024 * 1024
    if len(content) > max_image_size:
        raise HTTPException(status_code=400, detail="Image too large. Maximum allowed size is 5MB.")

    uploads_dir = Path("uploads/settings")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    with open(uploads_dir / filename, "wb") as f:
        f.write(content)
    return f"{base_url}/uploads/settings/{filename}"


def _materialize_settings_images(value, base_url: str):
    if isinstance(value, str):
        return _save_settings_data_image(value.strip(), base_url) if value.strip().startswith("data:image/") else value
    if isinstance(value, list):
        return [_materialize_settings_images(item, base_url) for item in value]
    if isinstance(value, dict):
        return {key: _materialize_settings_images(item, base_url) for key, item in value.items()}
    return value


@router.get("/website-settings", response_model=WebsiteSettingsResponse)
async def get_website_settings(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_website_settings(db)
    return WebsiteSettingsResponse.model_validate(settings)


@router.get("/website-settings/general", response_model=WebsiteSettingsGeneralResponse)
async def get_general_settings(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_website_settings(db)
    return WebsiteSettingsGeneralResponse.model_validate(settings)


@router.put("/website-settings", response_model=WebsiteSettingsResponse)
async def update_website_settings(
    request: Request,
    payload: WebsiteSettingsUpdate,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_or_create_website_settings(db)
    base_url = str(request.base_url).rstrip("/")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, field, _materialize_settings_images(value, base_url))
    await db.commit()
    await db.refresh(settings)
    return WebsiteSettingsResponse.model_validate(settings)

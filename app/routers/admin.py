from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import require_role
from app.models.user import (
    User, Vendor, Shop, Product, Order, OrderItem,
    Category, Coupon, Payout, Event
)
from app.schemas.schemas import (
    UserResponse, VendorResponse, ProductResponse, CategoryCreate,
    CategoryUpdate, CategoryResponse, CouponCreate, CouponUpdate,
    CouponResponse, AdminAnalytics, PaginatedResponse, PayoutResponse
)
from slugify import slugify
import math
from decimal import Decimal
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["Admin"])
get_admin = require_role("ADMIN")


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
    else:
        query = query.where(Product.status == "pending")
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

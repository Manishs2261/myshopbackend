from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
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
    if vendor.status != "approved":
        raise HTTPException(status_code=403, detail="Vendor not approved yet")

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


# ─── Products ────────────────────────────────────────────────────────────────

async def get_vendor(user: User, db: AsyncSession) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    vendor = await get_vendor(current_user, db)

    product_data = payload.model_dump(exclude={"variants"})
    product_data["vendor_id"] = vendor.id
    product_data["slug"] = slugify(payload.name)
    product_data["status"] = "pending"

    product = Product(**product_data)
    db.add(product)
    await db.flush()

    if payload.variants:
        for v in payload.variants:
            variant = ProductVariant(product_id=product.id, **v.model_dump())
            db.add(variant)

    await db.commit()
    await db.refresh(product)

    result = await db.execute(
        select(Product).where(Product.id == product.id)
        .options(selectinload(Product.variants))
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
    items = result.scalars().all()

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

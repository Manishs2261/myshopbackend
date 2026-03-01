from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Order, OrderItem, Cart, CartItem, Product, Coupon
from app.schemas.schemas import OrderCreate, OrderResponse, PaginatedResponse
from decimal import Decimal
import math
from datetime import datetime

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get cart
    result = await db.execute(
        select(Cart).where(Cart.user_id == current_user.id)
        .options(selectinload(Cart.items).selectinload(CartItem.product))
    )
    cart = result.scalar_one_or_none()
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Validate stock and calculate total
    total = Decimal("0")
    for item in cart.items:
        if not item.product or item.product.status != "approved":
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} not available")
        if item.product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {item.product.name}"
            )
        total += item.product.price * item.quantity

    # Apply coupon
    discount = Decimal("0")
    coupon_id = None
    if payload.coupon_code:
        now = datetime.utcnow()
        result = await db.execute(
            select(Coupon).where(
                Coupon.code == payload.coupon_code,
                Coupon.is_active == True,
            )
        )
        coupon = result.scalar_one_or_none()
        if coupon:
            if coupon.valid_from and coupon.valid_from > now:
                raise HTTPException(status_code=400, detail="Coupon not yet valid")
            if coupon.valid_to and coupon.valid_to < now:
                raise HTTPException(status_code=400, detail="Coupon has expired")
            if total < (coupon.min_order_amount or 0):
                raise HTTPException(
                    status_code=400,
                    detail=f"Minimum order amount ₹{coupon.min_order_amount} required"
                )
            if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
                raise HTTPException(status_code=400, detail="Coupon usage limit reached")

            if coupon.type == "percentage":
                discount = total * coupon.value / 100
                if coupon.max_discount:
                    discount = min(discount, coupon.max_discount)
            else:
                discount = min(coupon.value, total)

            coupon.used_count += 1
            coupon_id = coupon.id
        else:
            raise HTTPException(status_code=400, detail="Invalid coupon code")

    final_amount = total - discount

    # Create order
    order = Order(
        user_id=current_user.id,
        total_amount=total,
        discount_amount=discount,
        final_amount=final_amount,
        status="pending",
        payment_status="pending",
        coupon_id=coupon_id,
        shipping_address=payload.shipping_address.model_dump(),
        notes=payload.notes,
    )
    db.add(order)
    await db.flush()

    # Create order items and reduce stock
    for item in cart.items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            vendor_id=item.product.vendor_id,
            quantity=item.quantity,
            price=item.product.price,
            status="pending",
        )
        db.add(order_item)
        item.product.stock -= item.quantity

    # Clear cart
    for item in cart.items:
        await db.delete(item)

    await db.commit()
    await db.refresh(order)

    result = await db.execute(
        select(Order).where(Order.id == order.id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    return result.scalar_one()


@router.get("", response_model=PaginatedResponse)
async def get_my_orders(
    status: str = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.user_id == current_user.id)
    if status:
        query = query.where(Order.status == status)
    query = query.order_by(Order.created_at.desc())

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


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/{order_id}/cancel", response_model=dict)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in ("pending", "confirmed"):
        raise HTTPException(status_code=400, detail="Order cannot be cancelled at this stage")

    order.status = "cancelled"
    await db.commit()
    return {"message": "Order cancelled successfully"}

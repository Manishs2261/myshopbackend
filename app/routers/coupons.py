from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Coupon
from app.schemas.schemas import CouponValidate
from datetime import datetime
from decimal import Decimal

router = APIRouter(prefix="/coupons", tags=["Coupons"])


@router.post("/validate", response_model=dict)
async def validate_coupon(
    payload: CouponValidate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a coupon code and return discount amount."""
    now = datetime.utcnow()
    result = await db.execute(
        select(Coupon).where(Coupon.code == payload.code.upper(), Coupon.is_active == True)
    )
    coupon = result.scalar_one_or_none()
    if not coupon:
        raise HTTPException(status_code=404, detail="Invalid coupon code")

    if coupon.valid_from and coupon.valid_from > now:
        raise HTTPException(status_code=400, detail="Coupon not yet valid")
    if coupon.valid_to and coupon.valid_to < now:
        raise HTTPException(status_code=400, detail="Coupon has expired")
    if payload.order_amount < (coupon.min_order_amount or 0):
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount ₹{coupon.min_order_amount} required"
        )
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    # Calculate discount
    if coupon.type == "percentage":
        discount = payload.order_amount * coupon.value / 100
        if coupon.max_discount:
            discount = min(discount, coupon.max_discount)
    else:
        discount = min(coupon.value, payload.order_amount)

    return {
        "valid": True,
        "code": coupon.code,
        "discount_amount": discount,
        "final_amount": payload.order_amount - discount,
        "description": coupon.description,
    }

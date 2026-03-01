import hmac
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User, Order, Payment, Vendor
from app.schemas.schemas import (
    PaymentCreateRequest, PaymentVerifyRequest, PaymentResponse
)
from decimal import Decimal

router = APIRouter(prefix="/payments", tags=["Payments"])


def get_razorpay_client():
    try:
        import razorpay
        return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    except Exception:
        return None


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    payload: PaymentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Razorpay payment order."""
    result = await db.execute(
        select(Order).where(Order.id == payload.order_id, Order.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Order already paid")

    amount_paise = int(order.final_amount * 100)  # Razorpay uses smallest currency unit

    client = get_razorpay_client()
    if not client:
        # Mock for development
        razorpay_order_id = f"order_mock_{order.id}"
    else:
        rp_order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"order_{order.id}",
            "notes": {"order_id": order.id},
        })
        razorpay_order_id = rp_order["id"]

    # Save payment record
    result = await db.execute(select(Payment).where(Payment.order_id == order.id))
    payment = result.scalar_one_or_none()
    if not payment:
        payment = Payment(
            order_id=order.id,
            amount=order.final_amount,
            currency="INR",
            status="pending",
        )
        db.add(payment)

    payment.razorpay_order_id = razorpay_order_id
    await db.commit()

    return PaymentResponse(
        razorpay_order_id=razorpay_order_id,
        amount=amount_paise,
        currency="INR",
        key_id=settings.RAZORPAY_KEY_ID,
        order_id=order.id,
    )


@router.post("/verify", response_model=dict)
async def verify_payment(
    payload: PaymentVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify Razorpay payment signature and confirm order."""
    result = await db.execute(
        select(Payment).where(Payment.razorpay_order_id == payload.razorpay_order_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")

    # Verify signature
    if settings.RAZORPAY_KEY_SECRET:
        expected_sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, payload.razorpay_signature):
            payment.status = "failed"
            await db.commit()
            raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Update payment
    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature
    payment.status = "paid"

    # Update order
    result = await db.execute(select(Order).where(Order.id == payment.order_id))
    order = result.scalar_one_or_none()
    if order:
        order.payment_status = "paid"
        order.status = "confirmed"

    await db.commit()
    return {"message": "Payment verified successfully", "order_id": payment.order_id}


@router.get("/status/{order_id}", response_model=dict)
async def get_payment_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payment)
        .join(Order)
        .where(Payment.order_id == order_id, Order.user_id == current_user.id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {
        "order_id": order_id,
        "status": payment.status,
        "amount": payment.amount,
        "razorpay_payment_id": payment.razorpay_payment_id,
    }

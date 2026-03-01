from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.firebase import verify_firebase_token
from app.models.user import User, Vendor
from app.schemas.schemas import (
    FirebaseLoginRequest, TokenResponse, RefreshTokenRequest
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: FirebaseLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Verify Firebase token and return JWT tokens.
    If user doesn't exist, creates one automatically.
    """
    firebase_data = verify_firebase_token(payload.firebase_token)
    firebase_uid = firebase_data["uid"]

    # Get or create user
    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if not user:
        role = payload.role if payload.role in ("USER", "VENDOR", "ADMIN") else "USER"
        user = User(
            firebase_uid=firebase_uid,
            name=firebase_data.get("name"),
            email=firebase_data.get("email"),
            phone=firebase_data.get("phone_number"),
            role=role,
            status="active",
        )
        db.add(user)
        await db.flush()

        # Auto-create vendor record if role is VENDOR
        if role == "VENDOR":
            vendor = Vendor(
                user_id=user.id,
                business_name=firebase_data.get("name", "My Shop"),
                business_email=firebase_data.get("email"),
                status="pending",
                verified=False,
            )
            db.add(vendor)

        await db.commit()
        await db.refresh(user)

    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="Account is blocked")

    token_data = {"sub": str(user.id), "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        role=user.role,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid refresh token")

    user_id = decoded.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token_data = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        user_id=user.id,
        role=user.role,
    )

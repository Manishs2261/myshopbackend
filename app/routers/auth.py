"""
Auth Router — All registration and login flows:

CUSTOMER:
  POST /auth/register/customer       → email + password signup
  POST /auth/login/customer          → email + password login

VENDOR:
  POST /auth/register/vendor         → email + password + business info signup
  POST /auth/login/vendor            → email + password login

PHONE OTP (works for both USER and VENDOR):
  POST /auth/otp/send                → send OTP to phone
  POST /auth/otp/verify              → verify OTP → returns tokens

FIREBASE (Flutter/social login):
  POST /auth/login                   → Firebase token → JWT

SHARED:
  POST /auth/refresh                 → refresh access token
  POST /auth/forgot-password         → send reset email
  POST /auth/reset-password          → set new password with token
  POST /auth/change-password         → change password (logged in)
  GET  /auth/me                      → get current user info
"""

import secrets
import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from app.core.firebase import verify_firebase_token
from app.models.user import User, Vendor
from app.schemas.schemas import (
    FirebaseLoginRequest, TokenResponse, RefreshTokenRequest,
    CustomerRegisterRequest, CustomerLoginRequest,
    VendorRegisterRequest, VendorLoginRequest,
    SendOTPRequest, SendEmailOTPRequest, VerifyOTPRequest, FirebaseVerifyPhoneRequest,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
    UserResponse,
)
from app.services.mail import mail_service

router = APIRouter(prefix="/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def can_claim_phone_placeholder(user: User) -> bool:
    """
    OTP flow creates a minimal user row with only a phone number.
    Allow email/password signup to complete that placeholder account.
    """
    return (
        user.email is None
        and user.hashed_password is None
        and user.name is None
    )


def make_tokens(user: User) -> TokenResponse:
    data = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(data),
        user_id=user.id,
        role=user.role,
    )


def generate_otp(length: int = 6) -> str:
    return str(random.randint(10 ** (length - 1), 10**length - 1))


async def send_otp_sms(phone: str, otp: str):
    """
    Replace with your SMS provider (MSG91, Fast2SMS, Twilio).
    """
    print(f"[SMS] OTP {otp} → {phone}")


async def send_reset_email(email: str, token: str):
    await mail_service.send_password_reset_email(email, token)


# ─── CUSTOMER Registration & Login ───────────────────────────────────────────

@router.post("/register/customer", response_model=TokenResponse, status_code=201,
             summary="Register Customer")
async def register_customer(
    payload: CustomerRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new customer with email + password.

    **Body:**
    ```json
    {
      "name": "Rahul Sharma",
      "email": "rahul@gmail.com",
      "phone": "9876543210",
      "password": "rahul123"
    }
    ```
    Returns JWT tokens immediately — user is logged in after registration.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered. Please login.")

    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()
    if user:
        if not can_claim_phone_placeholder(user):
            raise HTTPException(status_code=409, detail="Phone number already registered.")

        user.name = payload.name
        user.email = payload.email
        user.hashed_password = hash_password(payload.password)
        user.role = "USER"
        user.status = user.status or "active"
        user.is_email_verified = False
    else:
        user = User(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            hashed_password=hash_password(payload.password),
            role="USER",
            status="active",
            is_email_verified=False,
            is_phone_verified=False,
        )
        db.add(user)
    await db.commit()
    await db.refresh(user)
    return make_tokens(user)


@router.post("/login/customer", response_model=TokenResponse, summary="Login Customer")
async def login_customer(
    payload: CustomerLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login customer with email + password.

    **Body:**
    ```json
    {
      "email": "rahul@gmail.com",
      "password": "rahul123"
    }
    ```
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="Account blocked. Contact support.")
    if user.role not in ("USER", "ADMIN"):
        raise HTTPException(status_code=403, detail="Please use vendor login.")

    return make_tokens(user)


# ─── VENDOR Registration & Login ─────────────────────────────────────────────

@router.post("/register/vendor", response_model=TokenResponse, status_code=201,
             summary="Register Vendor")
async def register_vendor(
    payload: VendorRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new vendor/shop owner.

    **Body:**
    ```json
    {
      "name": "Suresh Kumar",
      "email": "suresh@gmail.com",
      "phone": "9812345678",
      "password": "suresh123",
      "business_name": "Kumar General Store",
      "business_email": "store@gmail.com",
      "business_phone": "9812345678",
      "gst_number": "27AAPFU0939F1ZV",
      "pan_number": "ABCDE1234F"
    }
    ```

    **What happens after registration:**
    1. Vendor account is **PENDING** — admin must approve it
    2. Admin approves at `PUT /admin/vendors/{id}/approve`
    3. Once **APPROVED**, vendor can create a shop & add products
    4. Products need admin approval before going live

    Returns JWT tokens so vendor can complete their profile while waiting for approval.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered. Please login.")

    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()
    if user:
        if not can_claim_phone_placeholder(user):
            raise HTTPException(status_code=409, detail="Phone number already registered.")

        user.name = payload.name
        user.email = payload.email
        user.hashed_password = hash_password(payload.password)
        user.role = "VENDOR"
        user.status = user.status or "active"
        user.is_email_verified = False
    else:
        # Create user
        user = User(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            hashed_password=hash_password(payload.password),
            role="VENDOR",
            status="active",
            is_email_verified=False,
            is_phone_verified=False,
        )
        db.add(user)
    await db.flush()

    result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
    vendor = result.scalar_one_or_none()
    if vendor:
        vendor.business_name = payload.business_name or vendor.business_name
        vendor.business_email = payload.business_email or payload.email
        vendor.business_phone = payload.business_phone or payload.phone
        vendor.gst_number = payload.gst_number
        vendor.pan_number = payload.pan_number
        vendor.status = "pending"
        vendor.verified = False
    else:
        # Create vendor record (PENDING approval)
        vendor = Vendor(
            user_id=user.id,
            business_name=payload.business_name or "My Shop",
            business_email=payload.business_email or payload.email,
            business_phone=payload.business_phone or payload.phone,
            gst_number=payload.gst_number,
            pan_number=payload.pan_number,
            status="pending",
            verified=False,
        )
        db.add(vendor)
    await db.commit()
    await db.refresh(user)
    return make_tokens(user)


@router.post("/login/vendor", response_model=TokenResponse, summary="Login Vendor")
async def login_vendor(
    payload: VendorLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login vendor with email + password.

    **Body:**
    ```json
    {
      "email": "suresh@gmail.com",
      "password": "suresh123"
    }
    ```
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="Account blocked. Contact support.")
    if user.role not in ("VENDOR", "ADMIN"):
        raise HTTPException(status_code=403, detail="Vendor access required. Please use vendor login.")

    result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
    vendor = result.scalar_one_or_none()
    if vendor and vendor.status == "suspended":
        raise HTTPException(status_code=403, detail="Vendor account suspended. Contact support.")

    return make_tokens(user)


# ─── PHONE OTP Auth ───────────────────────────────────────────────────────────

@router.post("/otp/send", response_model=dict, summary="Send OTP")
async def send_otp(
    payload: SendOTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a 6-digit OTP to a phone number.
    Works for both new signup and existing user login.
    OTP is valid for 10 minutes.

    **Body:**
    ```json
    { "phone": "9876543210" }
    ```
    """
    otp = generate_otp(6)
    expires = datetime.utcnow() + timedelta(minutes=10)

    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()

    if user:
        user.otp_code = otp
        user.otp_expires_at = expires
    else:
        user = User(
            phone=payload.phone,
            otp_code=otp,
            otp_expires_at=expires,
            role="USER",
            status="active",
        )
        db.add(user)

    await db.commit()
    background_tasks.add_task(send_otp_sms, payload.phone, otp)

    return {
        "message": f"OTP sent to {payload.phone[:4]}****{payload.phone[-2:]}",
        "expires_in_seconds": 600,
        # ⚠️ REMOVE IN PRODUCTION:
        "__dev_otp": otp,
    }


@router.post("/otp/verify", response_model=TokenResponse, summary="Verify OTP")
async def verify_otp(
    payload: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify OTP and get JWT tokens.
    Automatically registers user if they're new.

    **Body:**
    ```json
    {
      "phone": "9876543210",
      "otp": "847261",
      "role": "USER"
    }
    ```

    Set `role` to `"VENDOR"` if the user wants to register as a shop owner.
    """
    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Phone not found. Request OTP first.")
    if not user.otp_code:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")

    # Check expiry
    if user.otp_expires_at:
        expires = user.otp_expires_at
        if hasattr(expires, 'tzinfo') and expires.tzinfo:
            from datetime import timezone
            now = datetime.now(timezone.utc)
        else:
            now = datetime.utcnow()
        if now > expires:
            raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")

    if user.otp_code != payload.otp:
        raise HTTPException(status_code=400, detail="Wrong OTP. Try again.")
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="Account blocked.")

    # Clear OTP
    user.otp_code = None
    user.otp_expires_at = None
    user.is_phone_verified = True

    # For new users, set role
    if not user.name:
        user.role = payload.role if payload.role in ("USER", "VENDOR") else "USER"

    # Create vendor record for new vendor signups
    if user.role == "VENDOR":
        result = await db.execute(select(Vendor).where(Vendor.user_id == user.id))
        if not result.scalar_one_or_none():
            vendor = Vendor(
                user_id=user.id,
                business_name="My Shop",
                business_phone=user.phone,
                status="pending",
                verified=False,
            )
            db.add(vendor)

    await db.commit()
    await db.refresh(user)
    return make_tokens(user)


# ─── FIREBASE Login ───────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Firebase Login")
async def firebase_login(
    payload: FirebaseLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login via Firebase (Google Sign-in, Apple, Facebook, etc.)
    Used primarily by Flutter app.

    **Body:**
    ```json
    {
      "firebase_token": "<id_token_from_firebase_sdk>",
      "role": "USER"
    }
    ```
    """
    firebase_data = verify_firebase_token(payload.firebase_token)
    firebase_uid = firebase_data["uid"]

    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if not user:
        role = payload.role if payload.role in ("USER", "VENDOR") else "USER"
        user = User(
            firebase_uid=firebase_uid,
            name=firebase_data.get("name"),
            email=firebase_data.get("email"),
            phone=firebase_data.get("phone_number"),
            role=role,
            status="active",
            is_email_verified=True,
            is_phone_verified=bool(firebase_data.get("phone_number")),
        )
        db.add(user)
        await db.flush()

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
        raise HTTPException(status_code=403, detail="Account blocked.")

    return make_tokens(user)


# ─── Token Refresh ────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse, summary="Refresh Token")
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Use refresh token to get a new access token."""
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")

    result = await db.execute(select(User).where(User.id == int(decoded["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return make_tokens(user)


# ─── Password Reset ───────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=dict, summary="Forgot Password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Request a password reset link to be sent to email.

    **Body:**
    ```json
    { "email": "rahul@gmail.com" }
    ```
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user and user.hashed_password:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()
        background_tasks.add_task(send_reset_email, payload.email, token)

    return {"message": "If this email is registered, a reset link has been sent."}


@router.post("/reset-password", response_model=dict, summary="Reset Password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Set a new password using the token from the reset email.

    **Body:**
    ```json
    {
      "token": "<token_from_email>",
      "new_password": "newpass123"
    }
    ```
    """
    result = await db.execute(
        select(User).where(User.password_reset_token == payload.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    expires = user.password_reset_expires
    if expires:
        exp = expires.replace(tzinfo=None) if hasattr(expires, 'tzinfo') and expires.tzinfo else expires
        if datetime.utcnow() > exp:
            raise HTTPException(status_code=400, detail="Token expired. Request a new reset link.")

    user.hashed_password = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await db.commit()

    return {"message": "Password reset successful. Please login with your new password."}


@router.post("/change-password", response_model=dict, summary="Change Password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change password while logged in.

    **Body:**
    ```json
    {
      "old_password": "currentpass123",
      "new_password": "newpass456"
    }
    ```
    """
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="No password set. Use OTP or social login.")
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


# ─── Whoami ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse, summary="Get Current User")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently logged-in user's info."""
    return current_user


# ─── Authenticated Email / Phone Verification ─────────────────────────────────

@router.post("/verify/email/send", response_model=dict)
async def send_email_verification_otp(
    payload: Optional[SendEmailOTPRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_email = payload.email if payload and payload.email else current_user.email
    
    if not target_email:
        raise HTTPException(status_code=400, detail="No email address provided")
        
    otp = generate_otp(6)
    expires = datetime.utcnow() + timedelta(minutes=10)
    current_user.otp_code = otp
    current_user.otp_expires_at = expires
    # Temporarily store the email being verified if it's different
    if payload and payload.email:
        current_user.unverified_email = payload.email
        
    await db.commit()
    background_tasks.add_task(mail_service.send_otp_email, target_email, otp)
    return {"message": f"OTP sent to {target_email}", "expires_in_seconds": 600}


@router.post("/verify/email/confirm", response_model=dict)
async def confirm_email_verification(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    otp = payload.get("otp", "")
    if not current_user.otp_code:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")

    # Check expiry
    if current_user.otp_expires_at:
        expires = current_user.otp_expires_at
        if hasattr(expires, 'tzinfo') and expires.tzinfo:
            from datetime import timezone
            now = datetime.now(timezone.utc)
        else:
            now = datetime.utcnow()
        if now > expires:
            raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")

    if current_user.otp_code != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    # If a new email was being verified, update it
    if hasattr(current_user, 'unverified_email') and current_user.unverified_email:
        current_user.email = current_user.unverified_email
        current_user.unverified_email = None

    current_user.is_email_verified = True
    current_user.otp_code = None
    current_user.otp_expires_at = None
    await db.commit()
    return {"message": "Email verified successfully"}


@router.post("/verify/phone/send", response_model=dict)
async def send_phone_verification_otp(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.phone:
        raise HTTPException(status_code=400, detail="No phone number on account")
    otp = generate_otp(6)
    expires = datetime.utcnow() + timedelta(minutes=10)
    current_user.otp_code = otp
    current_user.otp_expires_at = expires
    await db.commit()
    background_tasks.add_task(send_otp_sms, current_user.phone, otp)
    return {"message": f"OTP sent to phone", "expires_in_seconds": 600, "__dev_otp": otp}


@router.post("/verify/phone/confirm", response_model=dict)
async def confirm_phone_verification(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    otp = payload.get("otp", "")
    if not current_user.otp_code:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one.")
    if datetime.utcnow() > current_user.otp_expires_at:
        raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")
    if current_user.otp_code != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    current_user.is_phone_verified = True
    current_user.otp_code = None
    current_user.otp_expires_at = None
    await db.commit()
    return {"message": "Phone verified successfully"}


@router.post("/verify/phone/firebase", response_model=dict)
async def verify_phone_with_firebase(
    payload: FirebaseVerifyPhoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify phone number using a Firebase ID token.
    The client should have already verified the phone via Firebase SDK.
    """
    firebase_data = verify_firebase_token(payload.firebase_token)
    phone_number = firebase_data.get("phone_number")

    if not phone_number:
        raise HTTPException(
            status_code=400, 
            detail="Firebase token does not contain a verified phone number. Make sure you use Phone Auth in Firebase."
        )

    current_user.phone = phone_number
    current_user.is_phone_verified = True
    await db.commit()

    return {"message": "Phone number verified successfully via Firebase", "phone": phone_number}

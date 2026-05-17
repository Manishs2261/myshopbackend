import math
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.storage import supabase_storage_enabled
from app.models.user import Vendor, VendorRating, VendorReview, VendorReviewHelpful, User, Shop
from app.schemas.schemas import VendorRatingSummary, VendorReviewCreate, VendorReviewResponse, VendorReviewUpdate

router = APIRouter(prefix="/vendor-reviews", tags=["Vendor Reviews"])

_SORT_MAP = {
    "latest": desc(VendorReview.created_at),
    "highest": desc(VendorReview.rating),
    "lowest": asc(VendorReview.rating),
}

_STAR_COLS = {5: "five_star", 4: "four_star", 3: "three_star", 2: "two_star", 1: "one_star"}


async def _recalculate_vendor_rating(vendor_id: int, db: AsyncSession) -> None:
    agg = await db.execute(
        select(func.count(VendorReview.id), func.avg(VendorReview.rating))
        .where(VendorReview.vendor_id == vendor_id)
    )
    total, avg = agg.one()
    total = total or 0
    avg = round(float(avg or 0), 2)

    dist_rows = await db.execute(
        select(VendorReview.rating, func.count(VendorReview.id))
        .where(VendorReview.vendor_id == vendor_id)
        .group_by(VendorReview.rating)
    )
    breakdown = {r: c for r, c in dist_rows}

    existing = await db.get(VendorRating, vendor_id)
    if existing:
        existing.average_rating = avg
        existing.total_reviews = total
        existing.five_star = breakdown.get(5, 0)
        existing.four_star = breakdown.get(4, 0)
        existing.three_star = breakdown.get(3, 0)
        existing.two_star = breakdown.get(2, 0)
        existing.one_star = breakdown.get(1, 0)
    else:
        db.add(VendorRating(
            vendor_id=vendor_id,
            average_rating=avg,
            total_reviews=total,
            five_star=breakdown.get(5, 0),
            four_star=breakdown.get(4, 0),
            three_star=breakdown.get(3, 0),
            two_star=breakdown.get(2, 0),
            one_star=breakdown.get(1, 0),
        ))


# ─── Authenticated "my" Endpoints (must come before /{vendor_id} wildcard) ───

@router.get("/my-reviews", response_model=list)
async def get_my_vendor_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(VendorReview, Vendor, Shop)
        .join(Vendor, VendorReview.vendor_id == Vendor.id)
        .outerjoin(Shop, Shop.vendor_id == Vendor.id)
        .where(VendorReview.user_id == current_user.id)
        .order_by(desc(VendorReview.created_at))
    )
    result = []
    for review, vendor, shop in rows.all():
        result.append({
            "id": review.id,
            "vendor_id": review.vendor_id,
            "rating": review.rating,
            "comment": review.comment,
            "images": review.images or [],
            "helpful_count": review.helpful_count,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "updated_at": review.updated_at.isoformat() if review.updated_at else None,
            "shop_name": shop.name if shop else vendor.business_name,
            "shop_logo_url": shop.logo_url if shop else None,
        })
    return result


@router.get("/my-review/{vendor_id}", response_model=VendorReviewResponse)
async def get_my_vendor_review(
    vendor_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VendorReview)
        .where(VendorReview.vendor_id == vendor_id, VendorReview.user_id == current_user.id)
        .options(selectinload(VendorReview.user))
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="No review found")
    return review


# ─── Public Endpoints ────────────────────────────────────────────────────────

@router.get("/{vendor_id}", response_model=dict)
async def list_vendor_reviews(
    vendor_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    sort: str = Query(default="latest", pattern="^(latest|highest|lowest)$"),
    db: AsyncSession = Depends(get_db),
):
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    base_q = select(VendorReview).where(VendorReview.vendor_id == vendor_id)
    count_res = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_res.scalar() or 0

    offset = (page - 1) * limit
    rows = await db.execute(
        base_q
        .options(selectinload(VendorReview.user))
        .order_by(_SORT_MAP[sort])
        .offset(offset)
        .limit(limit)
    )
    reviews = rows.scalars().all()

    rating_row = await db.get(VendorRating, vendor_id)
    summary = VendorRatingSummary.model_validate(rating_row) if rating_row else None

    return {
        "reviews": [VendorReviewResponse.model_validate(r) for r in reviews],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total else 1,
        "summary": summary.model_dump() if summary else None,
    }


@router.get("/{vendor_id}/summary", response_model=VendorRatingSummary)
async def get_vendor_rating_summary(
    vendor_id: int,
    db: AsyncSession = Depends(get_db),
):
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    rating_row = await db.get(VendorRating, vendor_id)
    if not rating_row:
        return VendorRatingSummary(
            vendor_id=vendor_id,
            average_rating=0.0,
            total_reviews=0,
            five_star=0, four_star=0, three_star=0, two_star=0, one_star=0,
        )
    return rating_row


@router.post("", response_model=VendorReviewResponse, status_code=201)
async def create_vendor_review(
    payload: VendorReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5")

    vendor = await db.get(Vendor, payload.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    existing = await db.execute(
        select(VendorReview).where(
            VendorReview.vendor_id == payload.vendor_id,
            VendorReview.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You have already reviewed this shop")

    review = VendorReview(
        vendor_id=payload.vendor_id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
        images=payload.images,
    )
    db.add(review)
    await db.flush()
    await _recalculate_vendor_rating(payload.vendor_id, db)
    await db.commit()
    await db.refresh(review)

    result = await db.execute(
        select(VendorReview)
        .where(VendorReview.id == review.id)
        .options(selectinload(VendorReview.user))
    )
    return result.scalar_one()


@router.put("/{review_id}", response_model=VendorReviewResponse)
async def update_vendor_review(
    review_id: int,
    payload: VendorReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VendorReview)
        .where(VendorReview.id == review_id)
        .options(selectinload(VendorReview.user))
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this review")

    if payload.rating is not None:
        review.rating = payload.rating
    if payload.comment is not None:
        review.comment = payload.comment
    if payload.images is not None:
        review.images = payload.images

    await db.flush()
    await _recalculate_vendor_rating(review.vendor_id, db)
    await db.commit()
    await db.refresh(review)
    return review


@router.delete("/{review_id}", response_model=dict)
async def delete_vendor_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VendorReview).where(VendorReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Not authorized to delete this review")

    vendor_id = review.vendor_id
    await db.delete(review)
    await db.flush()
    await _recalculate_vendor_rating(vendor_id, db)
    await db.commit()
    return {"message": "Review deleted"}


@router.post("/upload-image", response_model=dict)
async def upload_vendor_review_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB")

    if supabase_storage_enabled():
        from app.core.storage import _compress_image
        compressed, fname, ctype = _compress_image(content, file.filename or "review.jpg")
        object_path = f"reviews/vendor/{current_user.id}/{uuid4().hex}_{fname}"
        base_url = settings.SUPABASE_URL.rstrip("/")
        upload_url = f"{base_url}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"
        public_url = f"{base_url}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{object_path}"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": ctype,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(upload_url, headers=headers, content=compressed)
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail="Image upload failed")
        return {"url": public_url}

    upload_dir = Path("uploads/reviews/vendor")
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "review.jpg").suffix or ".jpg"
    fname = f"{current_user.id}_{uuid4().hex}{ext}"
    (upload_dir / fname).write_bytes(content)
    return {"url": f"/uploads/reviews/vendor/{fname}"}


@router.post("/{review_id}/helpful", response_model=dict)
async def toggle_helpful(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(VendorReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    existing = await db.execute(
        select(VendorReviewHelpful).where(
            VendorReviewHelpful.review_id == review_id,
            VendorReviewHelpful.user_id == current_user.id,
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        await db.delete(record)
        review.helpful_count = max(0, (review.helpful_count or 0) - 1)
        action = "removed"
    else:
        db.add(VendorReviewHelpful(review_id=review_id, user_id=current_user.id))
        review.helpful_count = (review.helpful_count or 0) + 1
        action = "added"

    await db.commit()
    return {"action": action, "helpful_count": review.helpful_count}


@router.post("/{review_id}/report", response_model=dict)
async def report_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(VendorReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot report your own review")

    review.report_count = (review.report_count or 0) + 1
    await db.commit()
    return {"message": "Review reported"}

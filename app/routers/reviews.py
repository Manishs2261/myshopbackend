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
from app.models.user import Order, OrderItem, Product, Review, User
from app.schemas.schemas import ReviewCreate, ReviewResponse, ReviewUpdate
import math

router = APIRouter(prefix="/reviews", tags=["Reviews"])

_SORT_MAP = {
    "latest": desc(Review.created_at),
    "highest": desc(Review.rating),
    "lowest": asc(Review.rating),
}


@router.get("/products/{product_id}", response_model=dict)
async def get_product_reviews(
    product_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    sort: str = Query(default="latest", pattern="^(latest|highest|lowest)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    base_query = select(Review).where(Review.product_id == product_id)
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(
        base_query
        .options(selectinload(Review.user))
        .order_by(_SORT_MAP[sort])
        .offset(offset)
        .limit(limit)
    )
    reviews = result.scalars().all()

    dist_result = await db.execute(
        select(Review.rating, func.count(Review.id))
        .where(Review.product_id == product_id)
        .group_by(Review.rating)
    )
    distribution = {row[0]: row[1] for row in dist_result}

    return {
        "reviews": [ReviewResponse.model_validate(r) for r in reviews],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total else 1,
        "average_rating": product.rating,
        "rating_distribution": distribution,
    }


@router.get("/my-reviews", response_model=dict)
async def get_my_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Review)
        .where(Review.user_id == current_user.id)
        .options(selectinload(Review.product))
        .order_by(desc(Review.created_at))
    )
    reviews = result.scalars().all()

    items = []
    for r in reviews:
        product = r.product
        first_image = (product.images or [None])[0] if product else None
        items.append({
            "id": r.id,
            "product_id": r.product_id,
            "product_name": product.name if product else "Unknown Product",
            "product_image": first_image,
            "product_slug": product.slug if product else None,
            "rating": r.rating,
            "comment": r.comment,
            "images": r.images,
            "is_verified_purchase": r.is_verified_purchase,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })

    return {"reviews": items, "total": len(items)}


@router.get("/my-review/{product_id}", response_model=dict)
async def get_my_review(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Review)
        .where(Review.product_id == product_id, Review.user_id == current_user.id)
        .options(selectinload(Review.user))
    )
    review = result.scalar_one_or_none()
    if review is None:
        return {"review": None}
    return {"review": ReviewResponse.model_validate(review)}


@router.post("", response_model=ReviewResponse, status_code=201)
async def add_review(
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == payload.product_id, Product.status == "approved")
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    result = await db.execute(
        select(Review).where(
            Review.product_id == payload.product_id,
            Review.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You've already reviewed this product")

    result = await db.execute(
        select(OrderItem).join(Order).where(
            OrderItem.product_id == payload.product_id,
            Order.user_id == current_user.id,
            Order.status == "delivered",
        )
    )
    is_verified = result.scalar_one_or_none() is not None

    review = Review(
        product_id=payload.product_id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
        images=payload.images,
        is_verified_purchase=is_verified,
    )
    db.add(review)
    await db.flush()

    avg_result = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.product_id == payload.product_id)
    )
    avg_rating, count = avg_result.one()
    product.rating = round(float(avg_rating or 0), 1)
    product.review_count = count

    await db.commit()
    await db.refresh(review)
    await db.refresh(review, ["user"])
    return review


@router.put("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: int,
    payload: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Review)
        .where(Review.id == review_id, Review.user_id == current_user.id)
        .options(selectinload(Review.user))
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if payload.rating is not None:
        review.rating = payload.rating
    if payload.comment is not None:
        review.comment = payload.comment
    if payload.images is not None:
        review.images = payload.images

    await db.flush()

    result = await db.execute(select(Product).where(Product.id == review.product_id))
    product = result.scalar_one_or_none()
    if product:
        avg_result = await db.execute(
            select(func.avg(Review.rating), func.count(Review.id))
            .where(Review.product_id == review.product_id)
        )
        avg_rating, count = avg_result.one()
        product.rating = round(float(avg_rating or 0), 1)
        product.review_count = count

    await db.commit()
    await db.refresh(review)
    return review


@router.delete("/{review_id}", response_model=dict)
async def delete_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Review).where(
            Review.id == review_id,
            Review.user_id == current_user.id,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    product_id = review.product_id
    await db.delete(review)
    await db.flush()

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        avg_result = await db.execute(
            select(func.avg(Review.rating), func.count(Review.id))
            .where(Review.product_id == product_id)
        )
        avg_rating, count = avg_result.one()
        product.rating = round(float(avg_rating or 0), 1)
        product.review_count = count or 0

    await db.commit()
    return {"message": "Review deleted"}


@router.post("/upload-image", response_model=dict)
async def upload_review_image(
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
        object_path = f"reviews/{current_user.id}/{uuid4().hex}_{fname}"
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

    # Local fallback
    upload_dir = Path("uploads/reviews")
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "review.jpg").suffix or ".jpg"
    fname = f"{current_user.id}_{uuid4().hex}{ext}"
    (upload_dir / fname).write_bytes(content)
    return {"url": f"/uploads/reviews/{fname}"}

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Review, Product, Order, OrderItem
from app.schemas.schemas import ReviewCreate, ReviewResponse
import math

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/products/{product_id}", response_model=dict)
async def get_product_reviews(
    product_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    query = select(Review).where(Review.product_id == product_id)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(
        query.offset(offset).limit(limit).options(selectinload(Review.user))
        .order_by(Review.created_at.desc())
    )
    reviews = result.scalars().all()

    # Rating distribution
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
        "pages": math.ceil(total / limit),
        "average_rating": product.rating,
        "rating_distribution": distribution,
    }


@router.post("", response_model=ReviewResponse, status_code=201)
async def add_review(
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check product exists
    result = await db.execute(
        select(Product).where(Product.id == payload.product_id, Product.status == "approved")
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already reviewed
    result = await db.execute(
        select(Review).where(
            Review.product_id == payload.product_id,
            Review.user_id == current_user.id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You've already reviewed this product")

    # Check if verified purchase
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

    # Update product rating
    avg_result = await db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.product_id == payload.product_id)
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
            Review.user_id == current_user.id
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    product_id = review.product_id
    await db.delete(review)
    await db.flush()

    # Recalculate rating
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

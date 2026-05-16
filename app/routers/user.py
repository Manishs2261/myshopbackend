from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import get_current_user, get_current_customer
from app.models.user import User, Product, Vendor, Shop, Category
from app.schemas.schemas import (
    UserResponse, UserUpdate, ProductResponse, ProductListResponse,
    ShopResponse, CategoryResponse, PaginatedResponse
)
from typing import Optional
from slugify import slugify
import math

router = APIRouter(tags=["Users"])


# ─── Profile ────────────────────────────────────────────────────────────────

@router.get("/users/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/users/me", response_model=UserResponse)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ─── Categories ─────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    parent_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Category).where(Category.is_active == True)
    if parent_id is not None:
        query = query.where(Category.parent_id == parent_id)
    else:
        query = query.where(Category.parent_id == None)
    query = query.order_by(Category.sort_order)
    result = await db.execute(query)
    categories = result.scalars().all()
    
    # Manually build response to avoid circular reference
    response = []
    for cat in categories:
        response.append({
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "description": cat.description,
            "image_url": cat.image_url,
            "parent_id": cat.parent_id,
            "is_active": cat.is_active,
            "sort_order": cat.sort_order,
            "children": []
        })
    return response


# ─── Products ────────────────────────────────────────────────────────────────

@router.get("/products", response_model=PaginatedResponse)
async def list_products(
    category_id: Optional[int] = None,
    subcategory_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    brand: Optional[str] = None,
    rating: Optional[float] = None,
    sort_by: Optional[str] = "created_at",  # price_asc, price_desc, rating, newest
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import Product as ProductModel
    query = select(ProductModel).where(ProductModel.status == "approved")

    if category_id:
        query = query.where(ProductModel.category_id == category_id)
    if subcategory_id:
        query = query.where(ProductModel.category_id == subcategory_id)
    if min_price is not None:
        query = query.where(ProductModel.price >= min_price)
    if max_price is not None:
        query = query.where(ProductModel.price <= max_price)
    if brand:
        query = query.where(ProductModel.brand.ilike(f"%{brand}%"))
    if rating is not None:
        query = query.where(ProductModel.rating >= rating)

    # Sorting
    sort_map = {
        "price_asc": ProductModel.price.asc(),
        "price_desc": ProductModel.price.desc(),
        "rating": ProductModel.rating.desc(),
        "newest": ProductModel.created_at.desc(),
        "popular": ProductModel.view_count.desc(),
    }
    query = query.order_by(sort_map.get(sort_by, ProductModel.created_at.desc()))

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Paginate
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return PaginatedResponse(
        items=[ProductListResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit),
    )


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.user import Product as ProductModel
    result = await db.execute(
        select(ProductModel)
        .where(ProductModel.id == product_id, ProductModel.status == "approved")
        .options(selectinload(ProductModel.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Increment view count
    product.view_count += 1
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/search", response_model=PaginatedResponse)
async def search_products(
    q: str = Query(..., min_length=1),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Full-text product search with optional filters.
    In production, connect this to Meilisearch for better performance.
    """
    from app.models.user import Product as ProductModel
    query = select(ProductModel).where(
        ProductModel.status == "approved",
        or_(
            ProductModel.name.ilike(f"%{q}%"),
            ProductModel.description.ilike(f"%{q}%"),
            ProductModel.brand.ilike(f"%{q}%"),
        )
    )
    if min_price:
        query = query.where(ProductModel.price >= min_price)
    if max_price:
        query = query.where(ProductModel.price <= max_price)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return PaginatedResponse(
        items=[ProductListResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit),
    )


@router.get("/vendors/{vendor_id}", response_model=dict)
async def get_vendor_profile(vendor_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Vendor)
        .where(Vendor.id == vendor_id, Vendor.status == "approved")
        .options(selectinload(Vendor.shop))
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {
        "id": vendor.id,
        "business_name": vendor.business_name,
        "verified": vendor.verified,
        "shop": ShopResponse.model_validate(vendor.shop) if vendor.shop else None,
    }

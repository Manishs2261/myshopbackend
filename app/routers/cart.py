from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Cart, CartItem, Wishlist, Product
from app.schemas.schemas import (
    CartItemCreate, CartItemUpdate, CartResponse, WishlistResponse,
    CartItemResponse, ProductListResponse
)
from decimal import Decimal

router = APIRouter(tags=["Cart & Wishlist"])


# ─── Cart ────────────────────────────────────────────────────────────────────

async def get_or_create_cart(user: User, db: AsyncSession) -> Cart:
    result = await db.execute(
        select(Cart).where(Cart.user_id == user.id).options(
            selectinload(Cart.items).selectinload(CartItem.product)
        )
    )
    cart = result.scalar_one_or_none()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
    return cart


@router.get("/cart", response_model=CartResponse)
async def get_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Cart).where(Cart.user_id == current_user.id)
        .options(selectinload(Cart.items).selectinload(CartItem.product))
    )
    cart = result.scalar_one_or_none()
    if not cart:
        return {"id": 0, "user_id": current_user.id, "items": [], "total": Decimal("0")}

    total = sum(
        (item.product.price or Decimal("0")) * item.quantity
        for item in cart.items
        if item.product
    )
    return {
        "id": cart.id,
        "user_id": cart.user_id,
        "items": cart.items,
        "total": total,
    }


@router.post("/cart", response_model=dict, status_code=201)
async def add_to_cart(
    payload: CartItemCreate,
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
    if product.stock < payload.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    cart = await get_or_create_cart(current_user, db)

    # Check if item already in cart
    result = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == payload.product_id,
            CartItem.variant_id == payload.variant_id,
        )
    )
    item = result.scalar_one_or_none()

    if item:
        item.quantity += payload.quantity
    else:
        item = CartItem(
            cart_id=cart.id,
            product_id=payload.product_id,
            variant_id=payload.variant_id,
            quantity=payload.quantity,
        )
        db.add(item)

    await db.commit()
    return {"message": "Item added to cart", "item_id": item.id}


@router.put("/cart/{item_id}", response_model=dict)
async def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CartItem)
        .join(Cart)
        .where(CartItem.id == item_id, Cart.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    item.quantity = payload.quantity
    await db.commit()
    return {"message": "Cart item updated"}


@router.delete("/cart/{item_id}", response_model=dict)
async def remove_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CartItem)
        .join(Cart)
        .where(CartItem.id == item_id, Cart.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    await db.delete(item)
    await db.commit()
    return {"message": "Item removed from cart"}


@router.delete("/cart", response_model=dict)
async def clear_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Cart).where(Cart.user_id == current_user.id))
    cart = result.scalar_one_or_none()
    if cart:
        await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await db.commit()
    return {"message": "Cart cleared"}


# ─── Wishlist ────────────────────────────────────────────────────────────────

@router.get("/wishlist")
async def get_wishlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Wishlist)
        .where(Wishlist.user_id == current_user.id)
        .options(selectinload(Wishlist.product))
    )
    items = result.scalars().all()
    return items


@router.post("/wishlist/{product_id}", response_model=dict, status_code=201)
async def add_to_wishlist(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check product
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.status == "approved")
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Product not found")

    # Check duplicate
    result = await db.execute(
        select(Wishlist).where(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already in wishlist")

    item = Wishlist(user_id=current_user.id, product_id=product_id)
    db.add(item)
    await db.commit()
    return {"message": "Added to wishlist"}


@router.delete("/wishlist/{product_id}", response_model=dict)
async def remove_from_wishlist(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Wishlist).where(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not in wishlist")

    await db.delete(item)
    await db.commit()
    return {"message": "Removed from wishlist"}

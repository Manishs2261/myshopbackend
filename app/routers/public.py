from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List
from pathlib import Path

from app.core.database import get_db
from app.models.user import User, Vendor, Product, Category, Shop, ProductVariant

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/test")
async def test_endpoint():
    """Simple test endpoint to verify the router is working"""
    return {"message": "Public router is working", "status": "ok"}


@router.get("/showcase-page", response_class=HTMLResponse)
async def get_showcase_page():
    """Serve the eye-catching showcase HTML page"""
    html_path = Path(__file__).resolve().parent.parent / "showcase.html"
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


@router.get("/vendor/{vendor_id}")
async def get_vendor_public_profile(vendor_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get public vendor profile with shop information and products
    This endpoint is publicly accessible and shows only approved vendors
    """
    try:
        # Get vendor by ID, or by user_id if not found
        result = await db.execute(
            select(Vendor)
            .where(Vendor.id == vendor_id)
            .options(selectinload(Vendor.shop))
        )
        vendor = result.scalar_one_or_none()
        
        if not vendor:
            # Fallback: try by user_id
            result = await db.execute(
                select(Vendor)
                .where(Vendor.user_id == vendor_id)
                .options(selectinload(Vendor.shop))
            )
            vendor = result.scalar_one_or_none()
        
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        # Only show approved vendors publicly
        if vendor.status != "approved":
            raise HTTPException(status_code=404, detail="Vendor not approved")
        
        # Get vendor's user
        result = await db.execute(select(User).where(User.id == vendor.user_id))
        user = result.scalar_one_or_none()
        
        # Get vendor's active products
        products_result = await db.execute(
            select(Product)
            .where(
                Product.vendor_id == vendor.id,
                Product.status == "approved"
            )
            .options(selectinload(Product.category), selectinload(Product.variants))
            .order_by(Product.created_at.desc())
        )
        products = products_result.scalars().all()
        
        # Format products for response
        formatted_products = []
        for product in products:
            # Calculate discounted price
            discounted_price = float(product.price)
            if product.discount_percentage and product.discount_percentage > 0:
                discounted_price = round(
                    float(product.price) * (1 - product.discount_percentage / 100), 2
                )
            
            formatted_products.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": float(product.price),
                "original_price": float(product.original_price) if product.original_price else None,
                "discount_percentage": product.discount_percentage,
                "discounted_price": discounted_price,
                "category_name": product.category.name if product.category else "Uncategorized",
                "images": product.images or [],
                "status": product.status,
                "stock": product.stock,
                "brand": product.brand,
                "unit": product.unit,
                "rating": product.rating,
                "review_count": product.review_count,
                "variants": [
                    {
                        "id": v.id,
                        "size": v.size,
                        "color": v.color,
                        "sku": v.sku,
                        "price": float(v.price) if v.price else None,
                        "stock": v.stock,
                    }
                    for v in product.variants
                ],
                "created_at": product.created_at.isoformat() if product.created_at else None,
            })
        
        # Format shop data
        shop = vendor.shop
        shop_data = {
            "id": shop.id if shop else None,
            "name": shop.name if shop else vendor.business_name,
            "description": shop.description if shop else None,
            "logo_url": shop.logo_url if shop else None,
            "banner_url": shop.banner_url if shop else None,
            "gallery": shop.gallery if shop else [],
            "address": shop.address if shop else None,
            "city": shop.city if shop else None,
            "state": shop.state if shop else None,
            "postal_code": shop.pincode if shop else None,
            "contact_phone": vendor.business_phone or (user.phone if user else None),
            "contact_email": vendor.business_email or (user.email if user else None),
            "opening_time": shop.opening_time if shop else None,
            "closing_time": shop.closing_time if shop else None,
            "working_days": shop.working_days if shop else [],
        }
        
        # Format vendor data
        vendor_data = {
            "id": vendor.id,
            "user_id": vendor.user_id,
            "business_name": vendor.business_name,
            "business_email": vendor.business_email,
            "business_phone": vendor.business_phone,
            "gst_number": vendor.gst_number,
            "pan_number": vendor.pan_number,
            "status": vendor.status,
            "verified": vendor.verified,
        }
        
        return {
            "vendor": vendor_data,
            "shop": shop_data,
            "products": formatted_products,
            "total_products": len(formatted_products),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load vendor profile: {str(e)}")


@router.get("/showcase")
async def get_vendors_showcase(db: AsyncSession = Depends(get_db)):
    """
    Get all approved vendors with their products for the showcase page
    This endpoint returns a marketplace view of all vendors
    """
    try:
        # Get all approved vendors
        vendors_result = await db.execute(
            select(Vendor)
            .where(Vendor.status == "approved")
            .options(selectinload(Vendor.shop))
            .order_by(Vendor.created_at.desc())
        )
        vendors = vendors_result.scalars().all()
        
        showcase_data = []
        
        for vendor in vendors:
            # Get user
            user_result = await db.execute(select(User).where(User.id == vendor.user_id))
            user = user_result.scalar_one_or_none()
            
            # Get vendor's active products
            products_result = await db.execute(
                select(Product)
                .where(
                    Product.vendor_id == vendor.id,
                    Product.status == "approved"
                )
                .options(selectinload(Product.category), selectinload(Product.variants))
                .order_by(Product.created_at.desc())
            )
            products = products_result.scalars().all()
            
            # Format products
            formatted_products = []
            for product in products:
                discounted_price = float(product.price)
                if product.discount_percentage and product.discount_percentage > 0:
                    discounted_price = round(
                        float(product.price) * (1 - product.discount_percentage / 100), 2
                    )
                
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "price": float(product.price),
                    "original_price": float(product.original_price) if product.original_price else None,
                    "discount_percentage": product.discount_percentage,
                    "discounted_price": discounted_price,
                    "category_name": product.category.name if product.category else "Uncategorized",
                    "images": product.images or [],
                    "status": product.status,
                    "stock": product.stock,
                    "brand": product.brand,
                    "rating": product.rating,
                })
            
            shop = vendor.shop
            
            vendor_showcase = {
                "vendor_id": vendor.id,
                "user_id": vendor.user_id,
                "business_name": vendor.business_name,
                "owner_name": user.name if user else vendor.business_name,
                "description": shop.description if shop else f"Shop by {vendor.business_name}",
                "address": shop.address if shop else None,
                "city": shop.city if shop else None,
                "state": shop.state if shop else None,
                "contact_phone": vendor.business_phone or (user.phone if user else None),
                "contact_email": vendor.business_email or (user.email if user else None),
                "status": vendor.status,
                "verified": vendor.verified,
                "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                "banner_url": shop.banner_url if shop else None,
                "logo_url": shop.logo_url if shop else None,
                "total_products": len(formatted_products),
                "products": formatted_products,
            }
            
            showcase_data.append(vendor_showcase)
        
        return {
            "vendors": showcase_data,
            "total_vendors": len(showcase_data),
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to load showcase data",
            "vendors": [],
            "total_vendors": 0
        }


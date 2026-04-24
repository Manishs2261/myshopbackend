from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.db.session import get_db
from app.models.user import User, Vendor, Product, VendorInventory, VendorStatus

router = APIRouter()


# --- Requirement 3: Dashboard Overview Cards ---
@router.get("/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns counts for Dashboard Cards
    """
    # Vendors
    total_vendors = await db.scalar(select(func.count(Vendor.id)))
    active_vendors = await db.scalar(select(func.count(Vendor.id)).where(Vendor.status == VendorStatus.APPROVED))
    pending_vendors = await db.scalar(select(func.count(Vendor.id)).where(Vendor.status == VendorStatus.PENDING))

    # Products (Master Catalog)
    total_products = await db.scalar(select(func.count(Product.id)))

    # Users
    total_users = await db.scalar(select(func.count(User.id)))

    return {
        "total_vendors": total_vendors,
        "active_vendors": active_vendors,
        "pending_vendors": pending_vendors,
        "total_products": total_products,
        "total_users": total_users
    }


# --- Requirement 4: Vendor Management Table ---
@router.get("/vendors")
async def get_all_vendors(
        skip: int = 0,
        limit: int = 10,
        status: str = None,
        db: AsyncSession = Depends(get_db)
):
    query = select(Vendor).offset(skip).limit(limit)
    if status:
        query = query.where(Vendor.status == status)

    result = await db.execute(query)
    vendors = result.scalars().all()
    return vendors


@router.put("/vendors/{vendor_id}/status")
async def update_vendor_status(
        vendor_id: int,
        status: str,  # 'approved' or 'suspended'
        db: AsyncSession = Depends(get_db)
):
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor.status = status
    await db.commit()
    return {"message": f"Vendor status updated to {status}"}


# --- Requirement 5: Product Management ---
@router.get("/products/list")
async def get_products_admin(
        skip: int = 0,
        limit: int = 20,
        db: AsyncSession = Depends(get_db)
):
    # This powers the Product Data Table
    query = select(Product).order_by(desc(Product.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.put("/products/{product_id}/feature")
async def toggle_featured_product(
        product_id: int,
        is_featured: bool,
        db: AsyncSession = Depends(get_db)
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_featured = is_featured
    await db.commit()
    return {"message": "Product feature status updated"}


# --- Requirement 9: Analytics (Top Searched/Growth) ---
@router.get("/analytics/growth")
async def get_platform_growth(db: AsyncSession = Depends(get_db)):
    """
    Returns data formatted for Recharts (React)
    """
    # In a real app, you would group by date.
    # This is a simplified example returning recent vendors
    query = select(Vendor.joined_at).order_by(Vendor.joined_at)
    result = await db.execute(query)
    dates = result.scalars().all()

    # Process dates to format for Chart.js/Recharts
    # Example output: [{"date": "2023-10-01", "vendors": 5}, ...]
    return {"data": dates}
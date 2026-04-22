import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.user import Product, Vendor, User
from sqlalchemy import select

async def check_products():
    async with AsyncSessionLocal() as db:
        # Check all products in database
        result = await db.execute(select(Product))
        products = result.scalars().all()
        print(f"Total products in database: {len(products)}")
        
        for product in products:
            print(f"Product ID: {product.id}, Name: {product.name}, Vendor ID: {product.vendor_id}, Status: {product.status}")
        
        # Check vendors
        result = await db.execute(select(Vendor))
        vendors = result.scalars().all()
        print(f"\nTotal vendors: {len(vendors)}")
        
        for vendor in vendors:
            print(f"Vendor ID: {vendor.id}, User ID: {vendor.user_id}, Status: {vendor.status}")
        
        # Check users with vendor role
        result = await db.execute(select(User).where(User.role == "VENDOR"))
        vendor_users = result.scalars().all()
        print(f"\nTotal vendor users: {len(vendor_users)}")
        
        for user in vendor_users:
            print(f"User ID: {user.id}, Email: {user.email}, Status: {user.status}")

if __name__ == "__main__":
    asyncio.run(check_products())

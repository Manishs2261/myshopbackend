import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.user import Product
from sqlalchemy import select, update

async def simplify_product_status():
    async with AsyncSessionLocal() as db:
        # Find all products with "approved" status
        result = await db.execute(select(Product).where(Product.status == "approved"))
        approved_products = result.scalars().all()
        
        print(f"Found {len(approved_products)} products with 'approved' status")
        
        if approved_products:
            # Update all approved products to "active"
            await db.execute(
                update(Product)
                .where(Product.status == "approved")
                .values(status="active")
            )
            await db.commit()
            print(f"Updated {len(approved_products)} products from 'approved' to 'active'")
        
        # Find all products with "rejected" status
        result = await db.execute(select(Product).where(Product.status == "rejected"))
        rejected_products = result.scalars().all()
        
        print(f"Found {len(rejected_products)} products with 'rejected' status")
        
        if rejected_products:
            # Update all rejected products to "inactive"
            await db.execute(
                update(Product)
                .where(Product.status == "rejected")
                .values(status="inactive")
            )
            await db.commit()
            print(f"Updated {len(rejected_products)} products from 'rejected' to 'inactive'")
        
        # Verify the final status
        active_count = await db.execute(select(Product).where(Product.status == "active"))
        inactive_count = await db.execute(select(Product).where(Product.status == "inactive"))
        
        active_products = active_count.scalars().all()
        inactive_products = inactive_count.scalars().all()
        
        print(f"Final status:")
        print(f"  Active products: {len(active_products)}")
        print(f"  Inactive products: {len(inactive_products)}")
        print(f"  Total products: {len(active_products) + len(inactive_products)}")

if __name__ == "__main__":
    asyncio.run(simplify_product_status())

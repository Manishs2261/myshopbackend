import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.user import Product
from sqlalchemy import select, update

async def update_pending_products():
    async with AsyncSessionLocal() as db:
        # Find all products with "pending" status
        result = await db.execute(select(Product).where(Product.status == "pending"))
        pending_products = result.scalars().all()
        
        print(f"Found {len(pending_products)} products with 'pending' status")
        
        if pending_products:
            # Update all pending products to "approved"
            await db.execute(
                update(Product)
                .where(Product.status == "pending")
                .values(status="approved")
            )
            await db.commit()
            print(f"Updated {len(pending_products)} products from 'pending' to 'approved'")
        else:
            print("No pending products found")
        
        # Verify the update
        result = await db.execute(select(Product).where(Product.status == "approved"))
        approved_products = result.scalars().all()
        print(f"Total approved products: {len(approved_products)}")

if __name__ == "__main__":
    asyncio.run(update_pending_products())

"""
Seed script - run once to create initial admin user and sample categories.
Usage: python seed.py
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.core.database import Base
from app.models.user import User, Category, Vendor
from slugify import slugify

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


CATEGORIES = [
    {"name": "Groceries", "children": ["Fruits & Vegetables", "Dairy & Eggs", "Beverages", "Snacks"]},
    {"name": "Electronics", "children": ["Mobile Phones", "Laptops", "Accessories", "Home Appliances"]},
    {"name": "Clothing", "children": ["Men's", "Women's", "Kids", "Footwear"]},
    {"name": "Home & Kitchen", "children": ["Cookware", "Furniture", "Decor", "Cleaning"]},
    {"name": "Health & Beauty", "children": ["Medicines", "Skincare", "Hair Care", "Fitness"]},
    {"name": "Stationery", "children": ["Books", "Office Supplies", "Art & Craft"]},
    {"name": "Toys & Sports", "children": ["Toys", "Sports Equipment", "Outdoor"]},
    {"name": "Automotive", "children": ["Car Accessories", "Bike Accessories", "Tyres"]},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        # Create admin user
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.role == "ADMIN"))
        if not result.scalar_one_or_none():
            admin = User(
                firebase_uid="admin_seed_uid",
                name="Admin",
                email="admin@localshop.com",
                role="ADMIN",
                status="active",
            )
            db.add(admin)
            print("✅ Admin user created: admin@localshop.com")

        # Create categories
        result = await db.execute(select(Category))
        existing = result.scalars().all()
        if not existing:
            for cat_data in CATEGORIES:
                parent = Category(
                    name=cat_data["name"],
                    slug=slugify(cat_data["name"]),
                    is_active=True,
                )
                db.add(parent)
                await db.flush()
                for child_name in cat_data.get("children", []):
                    child = Category(
                        name=child_name,
                        slug=slugify(child_name),
                        parent_id=parent.id,
                        is_active=True,
                    )
                    db.add(child)
            print(f"✅ {len(CATEGORIES)} parent categories with subcategories created")

        await db.commit()
        print("🌱 Database seeded successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

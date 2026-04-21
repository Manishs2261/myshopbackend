import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.models.user import User

async def check_admin_users():
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.role == "ADMIN"))
        admin_users = result.scalars().all()
        
        print(f"Found {len(admin_users)} admin users:")
        for admin in admin_users:
            print(f"  - ID: {admin.id}, Name: {admin.name}, Email: {admin.email}, Role: {admin.role}, Status: {admin.status}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_admin_users())

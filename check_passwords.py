import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.models.user import User

async def check_admin_passwords():
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.role == "ADMIN"))
        admin_users = result.scalars().all()
        
        print(f"Admin users details:")
        for admin in admin_users:
            print(f"  - ID: {admin.id}")
            print(f"    Name: {admin.name}")
            print(f"    Email: {admin.email}")
            print(f"    Role: {admin.role}")
            print(f"    Status: {admin.status}")
            print(f"    Has password: {'Yes' if hasattr(admin, 'password_hash') and admin.password_hash else 'No'}")
            print(f"    Firebase UID: {admin.firebase_uid}")
            print()
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_admin_passwords())

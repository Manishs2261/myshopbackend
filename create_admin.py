import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_password_admin():
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == "admin@password.local"))
        existing = result.scalar_one_or_none()
        
        if existing:
            print("Admin user already exists")
        else:
            # Create admin with password
            admin = User(
                firebase_uid="admin_password_uid",
                name="Admin User",
                email="admin@password.local",
                role="ADMIN",
                status="active",
                hashed_password=pwd_context.hash("admin123")
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            
            print("Created admin user:")
            print(f"  Email: admin@password.local")
            print(f"  Password: admin123")
            print(f"  ID: {admin.id}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_password_admin())

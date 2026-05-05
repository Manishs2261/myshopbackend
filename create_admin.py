import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from dotenv import load_dotenv
from app.core.config import settings
from app.models.user import User
from passlib.context import CryptContext

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_password_admin():
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env")
        return

    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()

        if existing:
            existing.hashed_password = pwd_context.hash(admin_password)
            existing.role = "ADMIN"
            existing.status = "active"
            await db.commit()
            print(f"Updated admin: {admin_email}")
        else:
            admin = User(
                name="Admin User",
                email=admin_email,
                role="ADMIN",
                status="active",
                hashed_password=pwd_context.hash(admin_password),
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            print(f"Created admin: {admin_email} (ID: {admin.id})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_password_admin())

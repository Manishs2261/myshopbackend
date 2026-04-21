import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update
from app.core.config import settings
from app.models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def fix_rahul_password():
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "rahul@gmail.com"))
        rahul_user = result.scalar_one_or_none()
        
        if rahul_user:
            # Update password to 12345678
            new_password_hash = pwd_context.hash("12345678")
            
            await db.execute(
                update(User)
                .where(User.email == "rahul@gmail.com")
                .values(hashed_password=new_password_hash)
            )
            await db.commit()
            
            print(f"Updated Rahul's password successfully:")
            print(f"  - Email: rahul@gmail.com")
            print(f"  - Password: 12345678")
            print(f"  - User ID: {rahul_user.id}")
            
            # Verify the new password
            result = await db.execute(select(User).where(User.email == "rahul@gmail.com"))
            updated_user = result.scalar_one_or_none()
            is_valid = pwd_context.verify("12345678", updated_user.hashed_password)
            print(f"  - Password verification test: {'PASSED' if is_valid else 'FAILED'}")
        else:
            print("Rahul user not found")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_rahul_password())

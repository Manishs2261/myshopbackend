import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def check_rahul_user():
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "rahul@gmail.com"))
        rahul_user = result.scalar_one_or_none()
        
        if rahul_user:
            print(f"Found Rahul user:")
            print(f"  - ID: {rahul_user.id}")
            print(f"  - Name: {rahul_user.name}")
            print(f"  - Email: {rahul_user.email}")
            print(f"  - Role: {rahul_user.role}")
            print(f"  - Status: {rahul_user.status}")
            print(f"  - Has password: {'Yes' if rahul_user.hashed_password else 'No'}")
            print(f"  - Firebase UID: {rahul_user.firebase_uid}")
            
            # Test password verification
            if rahul_user.hashed_password:
                try:
                    is_valid = pwd_context.verify("12345678", rahul_user.hashed_password)
                    print(f"  - Password '12345678' valid: {is_valid}")
                except Exception as e:
                    print(f"  - Password verification error: {e}")
            else:
                print("  - No password set, using Firebase auth only")
        else:
            print("Rahul user not found")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_rahul_user())

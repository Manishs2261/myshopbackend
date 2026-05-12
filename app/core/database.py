from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that create_all won't add to existing tables
        migrations = [
            "ALTER TABLE marketplace_settings ADD COLUMN IF NOT EXISTS storefront_draft JSON",
            "ALTER TABLE marketplace_settings ADD COLUMN IF NOT EXISTS storefront_published JSON",
            "ALTER TABLE marketplace_settings ADD COLUMN IF NOT EXISTS storefront_status VARCHAR",
            "ALTER TABLE marketplace_settings ADD COLUMN IF NOT EXISTS published_at TIMESTAMP",
        ]
        for sql in migrations:
            try:
                await conn.execute(__import__("sqlalchemy").text(sql))
            except Exception:
                pass

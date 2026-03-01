from fastapi import FastAPI
from app.api.v1.endpoints import admin
from app.db.session import engine
from app.models.all_models import Base

app = FastAPI(title="LocalShop API")

# Setup Routes
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin Panel"])

@app.on_event("startup")
async def on_startup():
    # In Dev: Create tables automatically
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
def read_root():
    return {"message": "LocalShop Backend is Running"}
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import time

from app.core.config import settings
from app.core.database import create_tables
from app.core.firebase import init_firebase

# Import all routers
from app.routers import auth, user, vendor, admin, cart, orders, payments, analytics, reviews, coupons, public


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting LocalShop API...")
    await create_tables()
    init_firebase()
    print("✅ Database tables created")
    yield
    # Shutdown
    print("👋 Shutting down LocalShop API...")


app = FastAPI(
    title="LocalShop API",
    description="""
## 🛍️ LocalShop - Find Products at Local Stores Near You

This API powers a platform that connects customers with local shop owners,
making it easy to discover products available nearby instead of ordering online.

### User Roles
- **USER** - Browse products, manage cart, place orders
- **VENDOR** - Manage shop, add products, fulfill orders  
- **ADMIN** - Platform management, approvals, analytics

### Authentication
All protected endpoints require a **Bearer JWT token**.
Login via `/auth/login` using a Firebase ID token.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middleware ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(round(time.time() - start, 4))
    return response


# ─── Exception Handlers ──────────────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    messages = []
    for error in exc.errors():
        location = " -> ".join(str(part) for part in error.get("loc", []) if part != "body")
        message = error.get("msg", "Invalid request")
        messages.append(f"{location}: {message}" if location else message)
    detail = messages[0] if len(messages) == 1 else messages
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(UnicodeDecodeError)
async def unicode_decode_error_handler(request: Request, exc: UnicodeDecodeError):
    return JSONResponse(
        status_code=400,
        content={
            "detail": (
                "Invalid multipart upload format. Please ensure:\n"
                "1. Product data is sent as JSON string in the 'data' field\n"
                "2. Images are sent as files in the 'images' field\n"
                "3. Content-Type is set to 'multipart/form-data'\n"
                "4. No binary data is mixed with text fields"
            )
        },
    )


# ─── Include Routers ─────────────────────────────────────────────────────────

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(public.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(analytics.router)
app.include_router(reviews.router)
app.include_router(coupons.router)
app.include_router(vendor.router)
app.include_router(admin.router)


# ─── Health Check ────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "localshop-api"}

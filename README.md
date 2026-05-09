# 🛍️ LocalShop API

A FastAPI backend for discovering products at local stores. Customers can search for products and see which nearby shops carry them, at what price, and where.

---

## 🏗️ Project Structure

```
localshop/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── core/
│   │   ├── config.py        # Settings from .env
│   │   ├── database.py      # Async SQLAlchemy setup
│   │   ├── security.py      # JWT auth + role guards
│   │   └── firebase.py      # Firebase token verification
│   ├── models/
│   │   └── user.py          # All DB models (User, Vendor, Shop, Product, etc.)
│   ├── schemas/
│   │   └── schemas.py       # All Pydantic request/response models
│   └── routers/
│       ├── auth.py          # POST /auth/login, /auth/refresh
│       ├── user.py          # GET /users/me, /products, /search, /vendors
│       ├── cart.py          # /cart, /wishlist
│       ├── orders.py        # /orders CRUD
│       ├── payments.py      # /payments (Razorpay)
│       ├── vendor.py        # /vendor/* (shop, products, orders, analytics)
│       ├── admin.py         # /admin/* (users, vendors, products, categories)
│       ├── analytics.py     # /events/batch
│       ├── reviews.py       # /reviews
│       └── coupons.py       # /coupons/validate
├── alembic/                 # DB migrations
├── seed.py                  # Initial data seeder
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## ⚡ Quick Start

### Option 1: Docker (Recommended)

```bash
cp .env.example .env
docker-compose up -d
python seed.py  # seed categories + admin
pip freeze > requirements.txt
```

API available at: http://localhost:8000  
Swagger docs: http://localhost:8000/docs

---

### Option 2: Local Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install uvicorn
pip install fastapi
pip install pydantic-settings
 pip install sqlalchemy   
 pip install asyncpg  
 pip install firebase_admin  
 pip install passlib  
 pip install python-jose
 pip install passlib bcrypt
 pip install email-validator
 pip install slugify
 pip install pillow
 pip install python-multipart
 pip install psycopg2-binary
 pip install asyncpg
 pip uninstall bcrypt passlib -y
 pip install "bcrypt==4.0.1" "passlib[bcrypt]"
 pip install fastapi_mail   
# 3. Setup PostgreSQL
createdb localshop_db

# 4. Configure environment
cp .env.example .env
# Edit .env with your database URL, Firebase credentials, Razorpay keys

# 5. Run migrations
alembic upgrade head

# 6. Seed data
python seed.py

# 7. Start server
uvicorn app.main:app --reload --port 8000
```

---

## 🔐 Authentication Flow

1. User logs in via **Firebase** on Flutter/React app
2. App sends Firebase ID token to `POST /auth/login`
3. Backend verifies token, creates/fetches user, returns **JWT tokens**
4. All subsequent requests use `Authorization: Bearer <access_token>`
5. Refresh using `POST /auth/refresh` when access token expires

```
Firebase Auth → POST /auth/login { firebase_token } → { access_token, refresh_token }
```

---

## 📋 API Endpoints Summary

### 🔐 Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Firebase login → JWT |
| POST | `/auth/refresh` | Refresh access token |

### 👤 User (requires USER role)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users/me` | Get profile |
| PUT | `/users/me` | Update profile |
| GET | `/categories` | Browse categories |
| GET | `/products` | List products (filtered) |
| GET | `/products/{id}` | Product detail |
| GET | `/search?q=...` | Search products |
| GET | `/vendors/{id}` | Vendor profile + shop |

### 🛒 Cart & Wishlist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cart` | Get cart |
| POST | `/cart` | Add to cart |
| PUT | `/cart/{item_id}` | Update quantity |
| DELETE | `/cart/{item_id}` | Remove item |
| DELETE | `/cart` | Clear cart |
| GET | `/wishlist` | Get wishlist |
| POST | `/wishlist/{product_id}` | Add to wishlist |
| DELETE | `/wishlist/{product_id}` | Remove from wishlist |

### 📦 Orders & Payments
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/orders` | Create order from cart |
| GET | `/orders` | My orders |
| GET | `/orders/{id}` | Order detail |
| PUT | `/orders/{id}/cancel` | Cancel order |
| POST | `/payments/create` | Create Razorpay order |
| POST | `/payments/verify` | Verify payment |
| GET | `/payments/status/{order_id}` | Payment status |
| POST | `/coupons/validate` | Validate coupon |

### ⭐ Reviews
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reviews/products/{id}` | Product reviews |
| POST | `/reviews` | Add review |
| DELETE | `/reviews/{id}` | Delete review |

### 🏪 Vendor (requires VENDOR role)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/vendor/me` | Vendor profile |
| PUT | `/vendor/me` | Update vendor profile |
| POST | `/vendor/shop` | Create shop |
| GET | `/vendor/shop` | Get shop |
| PUT | `/vendor/shop` | Update shop |
| POST | `/vendor/products` | Add product |
| GET | `/vendor/products` | List my products |
| GET | `/vendor/products/{id}` | Product detail |
| PUT | `/vendor/products/{id}` | Update product |
| DELETE | `/vendor/products/{id}` | Deactivate product |
| GET | `/vendor/orders` | Vendor orders |
| PUT | `/vendor/orders/{id}` | Update order status |
| GET | `/vendor/analytics/dashboard` | Dashboard stats |
| GET | `/vendor/payouts` | Payout history |
| POST | `/vendor/payout/request` | Request payout |

### 🛠️ Admin (requires ADMIN role)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/users` | All users |
| PUT | `/admin/users/{id}/block` | Block/unblock user |
| GET | `/admin/vendors` | All vendors |
| PUT | `/admin/vendors/{id}/approve` | Approve vendor |
| PUT | `/admin/vendors/{id}/reject` | Reject vendor |
| PUT | `/admin/vendors/{id}/suspend` | Suspend vendor |
| GET | `/admin/products` | Products for review |
| PUT | `/admin/products/{id}/approve` | Approve product |
| PUT | `/admin/products/{id}/reject` | Reject product |
| GET | `/admin/categories` | All categories |
| POST | `/admin/categories` | Create category |
| PUT | `/admin/categories/{id}` | Update category |
| DELETE | `/admin/categories/{id}` | Delete category |
| GET | `/admin/analytics` | System analytics |
| GET | `/admin/coupons` | All coupons |
| POST | `/admin/coupons` | Create coupon |
| PUT | `/admin/coupons/{id}` | Update coupon |
| DELETE | `/admin/coupons/{id}` | Deactivate coupon |
| GET | `/admin/payouts` | All payouts |
| PUT | `/admin/payouts/{id}/process` | Process payout |

### 📊 Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/batch` | Track user events |
| POST | `/events/anonymous` | Track guest events |

---

## 🗄️ Database Models

- **users** - All platform users (customers, vendors, admins)
- **vendors** - Vendor business profiles
- **shops** - Physical store details with location (lat/lng)
- **categories** - Hierarchical product categories
- **products** - Product listings with images, specs, stock
- **product_variants** - Size/color variants per product
- **cart** / **cart_items** - Shopping cart
- **wishlist** - Saved products
- **orders** / **order_items** - Purchase orders
- **payments** - Razorpay payment records
- **reviews** - Product reviews with verified purchase flag
- **coupons** - Discount codes
- **payouts** - Vendor payout requests
- **events** - Analytics event log (JSONB metadata)

---

## 🔧 Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async URL |
| `SECRET_KEY` | JWT signing secret |
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase service account JSON |
| `RAZORPAY_KEY_ID` | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | Razorpay API secret |
| `REDIS_URL` | Redis connection URL |

---

## 🚀 Production Checklist

- [ ] Change `SECRET_KEY` to a strong random value
- [ ] Add real Firebase credentials
- [ ] Configure Razorpay live keys
- [ ] Set `DEBUG=False`
- [ ] Add rate limiting (slowapi)
- [ ] Set up Meilisearch for full-text search
- [ ] Configure S3/Cloudflare R2 for image uploads
- [ ] Add background tasks (Celery/ARQ) for emails
- [ ] Set up monitoring (Sentry, Datadog)

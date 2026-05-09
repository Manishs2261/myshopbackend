"""
Seed script — inserts 40 test products with status='approved' directly into the DB.
Vendor: reetu+3@gmail.com
Run: python seed_products.py
"""
import asyncio
import random
from slugify import slugify as _slugify_lib

def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from dotenv import load_dotenv
from app.core.config import settings
from app.models.user import User, Vendor, Category, Product

load_dotenv()

# ── Free Unsplash placeholder images ────────────────────────────────────────
# Format: https://images.unsplash.com/photo-{id}?w=600&q=80
ELECTRONICS_IMGS = [
    "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&q=80",
    "https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=600&q=80",
    "https://images.unsplash.com/photo-1585386959984-a4155224a1ad?w=600&q=80",
    "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&q=80",
    "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&q=80",
]
FASHION_IMGS = [
    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&q=80",
    "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&q=80",
    "https://images.unsplash.com/photo-1491553895911-0055eca6402d?w=600&q=80",
    "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=600&q=80",
    "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=600&q=80",
]
HOME_IMGS = [
    "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600&q=80",
    "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=600&q=80",
    "https://images.unsplash.com/photo-1581539250439-c96689b516dd?w=600&q=80",
    "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600&q=80",
    "https://images.unsplash.com/photo-1565183997392-2f6f122e5912?w=600&q=80",
]
BEAUTY_IMGS = [
    "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=600&q=80",
    "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=600&q=80",
    "https://images.unsplash.com/photo-1631730486784-74757d38e27f?w=600&q=80",
]
SPORTS_IMGS = [
    "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600&q=80",
    "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600&q=80",
    "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&q=80",
]
BOOKS_IMGS = [
    "https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=600&q=80",
    "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=600&q=80",
]
FOOD_IMGS = [
    "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&q=80",
    "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600&q=80",
]

CATALOG = [
    # ── Electronics ──────────────────────────────────────────────────────────
    {
        "name": "Sony WH-1000XM5 Wireless Headphones",
        "brand": "Sony",
        "price": 24999, "original_price": 34990, "discount_percentage": 29,
        "stock": 45, "rating": 4.8, "review_count": 1243,
        "is_featured": True,
        "description": "Industry-leading noise cancellation with 30-hour battery life and multipoint connection.",
        "tags": ["headphones", "wireless", "noise-cancelling", "sony"],
        "images": ELECTRONICS_IMGS[:2],
        "specifications": {"Driver Size": "30mm", "Frequency Response": "4–40,000 Hz", "Battery": "30 hrs", "Weight": "250g"},
        "category_key": "electronics",
    },
    {
        "name": "Apple AirPods Pro (2nd Gen)",
        "brand": "Apple",
        "price": 19900, "original_price": 24900, "discount_percentage": 20,
        "stock": 60, "rating": 4.7, "review_count": 3821,
        "is_featured": True,
        "description": "Active noise cancellation, Transparency mode, and Adaptive Audio.",
        "tags": ["airpods", "apple", "earbuds", "tws"],
        "images": [ELECTRONICS_IMGS[0], ELECTRONICS_IMGS[2]],
        "specifications": {"Chip": "H2", "Battery": "6 hrs + 30 hrs case", "Water Resistance": "IPX4"},
        "category_key": "electronics",
    },
    {
        "name": "Samsung Galaxy Tab S9 FE",
        "brand": "Samsung",
        "price": 31999, "original_price": 41999, "discount_percentage": 24,
        "stock": 30, "rating": 4.5, "review_count": 876,
        "is_featured": False,
        "description": "10.9-inch display tablet with S Pen included and 8000mAh battery.",
        "tags": ["tablet", "samsung", "android", "s-pen"],
        "images": ELECTRONICS_IMGS[1:4],
        "specifications": {"Display": "10.9 inch TFT", "Processor": "Exynos 1380", "RAM": "6GB", "Storage": "128GB"},
        "category_key": "electronics",
    },
    {
        "name": "boAt Airdopes 141 Bluetooth Earbuds",
        "brand": "boAt",
        "price": 999, "original_price": 2990, "discount_percentage": 67,
        "stock": 200, "rating": 4.1, "review_count": 12400,
        "is_featured": False,
        "description": "42H total playtime, BEAST mode for gaming, and IPX4 water resistance.",
        "tags": ["earbuds", "boat", "tws", "budget"],
        "images": [ELECTRONICS_IMGS[0]],
        "specifications": {"Driver": "8mm", "Battery": "5 hrs + 37 hrs case", "Connectivity": "Bluetooth 5.2"},
        "category_key": "electronics",
    },
    {
        "name": "Logitech MX Master 3S Mouse",
        "brand": "Logitech",
        "price": 8995, "original_price": 12995, "discount_percentage": 31,
        "stock": 85, "rating": 4.8, "review_count": 2109,
        "is_featured": True,
        "description": "8000 DPI precision sensor, ultra-fast MagSpeed scroll, and near-silent clicks.",
        "tags": ["mouse", "logitech", "wireless", "productivity"],
        "images": [ELECTRONICS_IMGS[3]],
        "specifications": {"DPI": "200–8000", "Buttons": "7", "Battery": "70 days USB-C", "Connectivity": "Bluetooth / USB"},
        "category_key": "electronics",
    },
    {
        "name": "Lenovo IdeaPad Slim 3 Laptop",
        "brand": "Lenovo",
        "price": 39990, "original_price": 52990, "discount_percentage": 25,
        "stock": 20, "rating": 4.3, "review_count": 654,
        "is_featured": True,
        "description": "Intel Core i5-12th Gen, 16GB RAM, 512GB SSD, 15.6-inch FHD display.",
        "tags": ["laptop", "lenovo", "intel", "student"],
        "images": [ELECTRONICS_IMGS[4], ELECTRONICS_IMGS[1]],
        "specifications": {"Processor": "Intel Core i5-1235U", "RAM": "16GB DDR4", "Storage": "512GB SSD", "Display": "15.6\" FHD IPS"},
        "category_key": "electronics",
    },
    {
        "name": "Xiaomi Smart Band 8 Pro",
        "brand": "Xiaomi",
        "price": 3999, "original_price": 5999, "discount_percentage": 33,
        "stock": 150, "rating": 4.4, "review_count": 3211,
        "is_featured": False,
        "description": "1.74-inch AMOLED display, 14-day battery, SpO2, heart rate and stress monitoring.",
        "tags": ["smartband", "fitness", "xiaomi", "wearable"],
        "images": [ELECTRONICS_IMGS[2]],
        "specifications": {"Display": "1.74\" AMOLED", "Battery": "14 days", "Water Resistance": "5ATM"},
        "category_key": "electronics",
    },

    # ── Fashion ───────────────────────────────────────────────────────────────
    {
        "name": "Nike Air Max 270 Running Shoes",
        "brand": "Nike",
        "price": 8495, "original_price": 12995, "discount_percentage": 35,
        "stock": 70, "rating": 4.6, "review_count": 1854,
        "is_featured": True,
        "description": "Max Air heel unit for all-day comfort with a bold silhouette.",
        "tags": ["shoes", "nike", "running", "airmax"],
        "images": FASHION_IMGS[:3],
        "specifications": {"Upper": "Mesh + synthetic", "Sole": "Rubber", "Closure": "Lace-up"},
        "category_key": "fashion",
    },
    {
        "name": "Levi's 511 Slim Fit Jeans",
        "brand": "Levi's",
        "price": 2249, "original_price": 4499, "discount_percentage": 50,
        "stock": 120, "rating": 4.4, "review_count": 4520,
        "is_featured": False,
        "description": "Slim fit from hip to ankle, flex stretch fabric for comfort all day.",
        "tags": ["jeans", "levis", "denim", "slim"],
        "images": FASHION_IMGS[1:3],
        "specifications": {"Fit": "Slim", "Fabric": "99% Cotton 1% Elastane", "Rise": "Mid-rise"},
        "category_key": "fashion",
    },
    {
        "name": "Adidas Ultraboost 23 Sneakers",
        "brand": "Adidas",
        "price": 11999, "original_price": 17999, "discount_percentage": 33,
        "stock": 50, "rating": 4.7, "review_count": 2340,
        "is_featured": True,
        "description": "Responsive BOOST midsole and Primeknit+ upper for a sock-like fit.",
        "tags": ["shoes", "adidas", "ultraboost", "running"],
        "images": [FASHION_IMGS[2], FASHION_IMGS[4]],
        "specifications": {"Upper": "Primeknit+", "Midsole": "BOOST", "Drop": "10mm"},
        "category_key": "fashion",
    },
    {
        "name": "H&M Oversized Hoodie",
        "brand": "H&M",
        "price": 1299, "original_price": 2299, "discount_percentage": 43,
        "stock": 200, "rating": 4.0, "review_count": 892,
        "is_featured": False,
        "description": "Relaxed oversized hoodie in soft cotton-blend fabric with kangaroo pocket.",
        "tags": ["hoodie", "hm", "casual", "unisex"],
        "images": [FASHION_IMGS[3]],
        "specifications": {"Fabric": "80% Cotton 20% Polyester", "Fit": "Oversized"},
        "category_key": "fashion",
    },
    {
        "name": "Ray-Ban Aviator Classic Sunglasses",
        "brand": "Ray-Ban",
        "price": 7490, "original_price": 9990, "discount_percentage": 25,
        "stock": 40, "rating": 4.8, "review_count": 1123,
        "is_featured": True,
        "description": "Iconic Aviator style with crystal lenses and metal frame.",
        "tags": ["sunglasses", "rayban", "aviator", "uv400"],
        "images": [FASHION_IMGS[0]],
        "specifications": {"Lens Material": "Crystal", "Frame": "Metal", "UV Protection": "UV400"},
        "category_key": "fashion",
    },
    {
        "name": "Fastrack Analog Watch",
        "brand": "Fastrack",
        "price": 1795, "original_price": 2995, "discount_percentage": 40,
        "stock": 80, "rating": 4.2, "review_count": 2310,
        "is_featured": False,
        "description": "Day and date function with water resistance up to 50m.",
        "tags": ["watch", "fastrack", "analog", "casual"],
        "images": [FASHION_IMGS[1]],
        "specifications": {"Movement": "Quartz", "Water Resistance": "50m", "Case Size": "40mm"},
        "category_key": "fashion",
    },

    # ── Home & Furniture ──────────────────────────────────────────────────────
    {
        "name": "IKEA POÄNG Armchair",
        "brand": "IKEA",
        "price": 12990, "original_price": 16990, "discount_percentage": 24,
        "stock": 15, "rating": 4.5, "review_count": 3410,
        "is_featured": True,
        "description": "Layer-glued bent birch frame with cushion. Exceptionally comfortable and durable.",
        "tags": ["chair", "ikea", "armchair", "furniture"],
        "images": HOME_IMGS[:2],
        "specifications": {"Frame": "Birch", "Seat Width": "60cm", "Max Load": "110kg"},
        "category_key": "home",
    },
    {
        "name": "Philips Air Purifier AC1215",
        "brand": "Philips",
        "price": 9999, "original_price": 14999, "discount_percentage": 33,
        "stock": 35, "rating": 4.3, "review_count": 1540,
        "is_featured": False,
        "description": "HEPA filter removes 99.97% of particles. Coverage up to 333 sqft.",
        "tags": ["air purifier", "philips", "hepa", "home"],
        "images": HOME_IMGS[2:4],
        "specifications": {"Coverage": "333 sqft", "Filter": "True HEPA + Active Carbon", "CADR": "270 m³/h"},
        "category_key": "home",
    },
    {
        "name": "Milton Thermosteel Flask 1L",
        "brand": "Milton",
        "price": 649, "original_price": 1099, "discount_percentage": 41,
        "stock": 300, "rating": 4.5, "review_count": 8760,
        "is_featured": False,
        "description": "Double wall stainless steel insulation. Keeps hot 24 hours, cold 36 hours.",
        "tags": ["flask", "milton", "thermos", "insulated"],
        "images": [HOME_IMGS[4]],
        "specifications": {"Capacity": "1000ml", "Material": "Stainless Steel 304", "Hot": "24 hrs", "Cold": "36 hrs"},
        "category_key": "home",
    },
    {
        "name": "Prestige Induction Cooktop 1600W",
        "brand": "Prestige",
        "price": 1799, "original_price": 3299, "discount_percentage": 45,
        "stock": 60, "rating": 4.4, "review_count": 5230,
        "is_featured": True,
        "description": "Push button control, 7 power levels, auto-off and child lock features.",
        "tags": ["induction", "prestige", "kitchen", "cooktop"],
        "images": HOME_IMGS[1:3],
        "specifications": {"Power": "1600W", "Voltage": "230V AC", "Levels": "7"},
        "category_key": "home",
    },
    {
        "name": "Godrej Interio Study Desk",
        "brand": "Godrej",
        "price": 8499, "original_price": 12999, "discount_percentage": 35,
        "stock": 12, "rating": 4.2, "review_count": 430,
        "is_featured": False,
        "description": "Engineered wood study table with storage drawer and keyboard tray.",
        "tags": ["desk", "godrej", "study", "furniture"],
        "images": [HOME_IMGS[0], HOME_IMGS[3]],
        "specifications": {"Material": "Engineered Wood", "Dimensions": "120×60×75 cm", "Color": "Wenge"},
        "category_key": "home",
    },
    {
        "name": "Amazon Echo Dot 5th Gen",
        "brand": "Amazon",
        "price": 4499, "original_price": 5999, "discount_percentage": 25,
        "stock": 90, "rating": 4.6, "review_count": 6700,
        "is_featured": True,
        "description": "Compact Alexa smart speaker with improved audio and temperature sensor.",
        "tags": ["alexa", "smart speaker", "amazon", "echo"],
        "images": [ELECTRONICS_IMGS[0]],
        "specifications": {"Driver": "1.73\"", "Connectivity": "Wi-Fi + Bluetooth 5.2", "Sensor": "Temperature"},
        "category_key": "home",
    },

    # ── Beauty & Personal Care ────────────────────────────────────────────────
    {
        "name": "Lakme Absolute Skin Natural Mousse Foundation",
        "brand": "Lakme",
        "price": 449, "original_price": 625, "discount_percentage": 28,
        "stock": 180, "rating": 4.1, "review_count": 3400,
        "is_featured": False,
        "description": "Lightweight mousse formula with SPF 8, buildable coverage.",
        "tags": ["foundation", "lakme", "makeup", "mousse"],
        "images": BEAUTY_IMGS[:2],
        "specifications": {"SPF": "8", "Finish": "Natural", "Volume": "25g"},
        "category_key": "beauty",
    },
    {
        "name": "Dove Intensive Repair Shampoo 650ml",
        "brand": "Dove",
        "price": 349, "original_price": 499, "discount_percentage": 30,
        "stock": 250, "rating": 4.3, "review_count": 2890,
        "is_featured": False,
        "description": "Infused with Keratin Actives to repair damaged hair from roots to tips.",
        "tags": ["shampoo", "dove", "haircare", "keratin"],
        "images": [BEAUTY_IMGS[1]],
        "specifications": {"Volume": "650ml", "Hair Type": "Damaged"},
        "category_key": "beauty",
    },
    {
        "name": "Mamaearth Vitamin C Face Serum",
        "brand": "Mamaearth",
        "price": 399, "original_price": 599, "discount_percentage": 33,
        "stock": 140, "rating": 4.4, "review_count": 7810,
        "is_featured": True,
        "description": "1% Vitamin C + 0.5% Niacinamide for brighter, even-toned skin.",
        "tags": ["serum", "vitamin c", "mamaearth", "skincare"],
        "images": BEAUTY_IMGS[:2],
        "specifications": {"Key Ingredients": "Vitamin C, Niacinamide", "Volume": "30ml", "Skin Type": "All"},
        "category_key": "beauty",
    },
    {
        "name": "Gillette Mach3 Razor with 2 Blades",
        "brand": "Gillette",
        "price": 249, "original_price": 375, "discount_percentage": 34,
        "stock": 500, "rating": 4.5, "review_count": 4100,
        "is_featured": False,
        "description": "3 anti-friction blades with lubrastrip for a smooth, comfortable shave.",
        "tags": ["razor", "gillette", "shaving", "grooming"],
        "images": [BEAUTY_IMGS[2]],
        "specifications": {"Blades": "3", "Handle": "Ergonomic"},
        "category_key": "beauty",
    },

    # ── Sports & Fitness ──────────────────────────────────────────────────────
    {
        "name": "Boldfit Gym Gloves with Wrist Support",
        "brand": "Boldfit",
        "price": 299, "original_price": 799, "discount_percentage": 63,
        "stock": 220, "rating": 4.2, "review_count": 5610,
        "is_featured": False,
        "description": "Anti-slip palm, wrist wrap support for heavy lifting.",
        "tags": ["gym gloves", "boldfit", "fitness", "workout"],
        "images": [SPORTS_IMGS[0]],
        "specifications": {"Material": "Leather + Neoprene", "Sizes": "S/M/L/XL"},
        "category_key": "sports",
    },
    {
        "name": "Decathlon Corength 20kg Dumbbell Set",
        "brand": "Decathlon",
        "price": 3999, "original_price": 5999, "discount_percentage": 33,
        "stock": 25, "rating": 4.6, "review_count": 1230,
        "is_featured": True,
        "description": "Hexagonal rubber dumbbell set (2×10kg), non-slip grip and anti-roll design.",
        "tags": ["dumbbell", "decathlon", "weight", "gym"],
        "images": SPORTS_IMGS[1:3],
        "specifications": {"Total Weight": "20kg (2×10kg)", "Material": "Rubber coated cast iron"},
        "category_key": "sports",
    },
    {
        "name": "Nivia Storm Football Size 5",
        "brand": "Nivia",
        "price": 549, "original_price": 999, "discount_percentage": 45,
        "stock": 100, "rating": 4.3, "review_count": 2100,
        "is_featured": False,
        "description": "Machine stitched PU football, ideal for training and recreational play.",
        "tags": ["football", "nivia", "soccer", "sports"],
        "images": [SPORTS_IMGS[0]],
        "specifications": {"Size": "5", "Material": "PU", "Stitching": "Machine"},
        "category_key": "sports",
    },
    {
        "name": "Yonex Nanoray 7 Badminton Racket",
        "brand": "Yonex",
        "price": 1299, "original_price": 2099, "discount_percentage": 38,
        "stock": 45, "rating": 4.5, "review_count": 876,
        "is_featured": False,
        "description": "Isometric head shape for larger sweet spot, graphite composite frame.",
        "tags": ["badminton", "yonex", "racket", "sports"],
        "images": [SPORTS_IMGS[2]],
        "specifications": {"Weight": "85g", "Flex": "Medium", "Max Tension": "24 lbs"},
        "category_key": "sports",
    },
    {
        "name": "Adidas 3-Stripes Yoga Mat 6mm",
        "brand": "Adidas",
        "price": 1799, "original_price": 2999, "discount_percentage": 40,
        "stock": 70, "rating": 4.4, "review_count": 1340,
        "is_featured": False,
        "description": "Non-slip surface with carry strap, ideal for yoga and pilates.",
        "tags": ["yoga mat", "adidas", "yoga", "fitness"],
        "images": [SPORTS_IMGS[1]],
        "specifications": {"Thickness": "6mm", "Material": "NBR", "Size": "173×61cm"},
        "category_key": "sports",
    },

    # ── Books ─────────────────────────────────────────────────────────────────
    {
        "name": "Atomic Habits — James Clear",
        "brand": "Penguin Random House",
        "price": 399, "original_price": 599, "discount_percentage": 33,
        "stock": 500, "rating": 4.9, "review_count": 18200,
        "is_featured": True,
        "description": "Tiny changes, remarkable results. The #1 book on habit formation.",
        "tags": ["books", "self-help", "habits", "bestseller"],
        "images": BOOKS_IMGS[:2],
        "specifications": {"Pages": "320", "Publisher": "Avery", "Language": "English", "Format": "Paperback"},
        "category_key": "books",
    },
    {
        "name": "Rich Dad Poor Dad — Robert Kiyosaki",
        "brand": "Warner Books",
        "price": 249, "original_price": 450, "discount_percentage": 45,
        "stock": 400, "rating": 4.7, "review_count": 22100,
        "is_featured": True,
        "description": "What the rich teach their kids about money that the poor and middle class do not.",
        "tags": ["books", "finance", "investing", "bestseller"],
        "images": [BOOKS_IMGS[1]],
        "specifications": {"Pages": "207", "Publisher": "Warner Books", "Language": "English", "Format": "Paperback"},
        "category_key": "books",
    },
    {
        "name": "The Psychology of Money — Morgan Housel",
        "brand": "Harriman House",
        "price": 349, "original_price": 499, "discount_percentage": 30,
        "stock": 350, "rating": 4.8, "review_count": 9800,
        "is_featured": False,
        "description": "Timeless lessons on wealth, greed, and happiness.",
        "tags": ["books", "finance", "money", "psychology"],
        "images": [BOOKS_IMGS[0]],
        "specifications": {"Pages": "256", "Publisher": "Harriman House", "Language": "English", "Format": "Paperback"},
        "category_key": "books",
    },

    # ── Food & Grocery ────────────────────────────────────────────────────────
    {
        "name": "Tata Sampann Unpolished Masoor Dal 1kg",
        "brand": "Tata",
        "price": 149, "original_price": 185, "discount_percentage": 19,
        "stock": 600, "rating": 4.4, "review_count": 3400,
        "is_featured": False,
        "description": "Rich in protein and fibre, no artificial preservatives.",
        "tags": ["dal", "tata", "grocery", "lentils"],
        "images": FOOD_IMGS[:1],
        "specifications": {"Weight": "1kg", "Type": "Unpolished", "Protein": "25g per 100g"},
        "category_key": "food",
    },
    {
        "name": "Epigamia Greek Yogurt Mango 85g (Pack of 6)",
        "brand": "Epigamia",
        "price": 269, "original_price": 330, "discount_percentage": 18,
        "stock": 200, "rating": 4.6, "review_count": 2200,
        "is_featured": False,
        "description": "High protein, no artificial sweeteners, all-natural mango Greek yogurt.",
        "tags": ["yogurt", "epigamia", "healthy", "snack"],
        "images": FOOD_IMGS[1:2],
        "specifications": {"Protein": "6g per cup", "Sugar": "No added sugar", "Pack": "6×85g"},
        "category_key": "food",
    },
    {
        "name": "Slurrp Farm Organic Millet Cookies 150g",
        "brand": "Slurrp Farm",
        "price": 199, "original_price": 249, "discount_percentage": 20,
        "stock": 300, "rating": 4.5, "review_count": 1870,
        "is_featured": False,
        "description": "Made with bajra and jowar. No maida, no refined sugar.",
        "tags": ["cookies", "millet", "organic", "healthy"],
        "images": [FOOD_IMGS[0]],
        "specifications": {"Weight": "150g", "Grain": "Bajra + Jowar", "Shelf Life": "6 months"},
        "category_key": "food",
    },
    {
        "name": "Sleepy Owl Cold Brew Coffee Original 270ml (Pack of 3)",
        "brand": "Sleepy Owl",
        "price": 359, "original_price": 450, "discount_percentage": 20,
        "stock": 150, "rating": 4.7, "review_count": 4100,
        "is_featured": True,
        "description": "Ready-to-drink cold brew coffee. Smooth, never bitter. No added sugar.",
        "tags": ["coffee", "cold brew", "sleepy owl", "drinks"],
        "images": FOOD_IMGS,
        "specifications": {"Volume": "3×270ml", "Caffeine": "~120mg per bottle", "Sugar": "None"},
        "category_key": "food",
    },
]

# Slugs used for fallback category look-up (will match partial name)
CATEGORY_KEYWORDS = {
    "electronics": ["electronic", "tech", "gadget", "mobile", "computer"],
    "fashion": ["fashion", "cloth", "apparel", "wear", "shoe"],
    "home": ["home", "furniture", "kitchen", "decor", "living"],
    "beauty": ["beauty", "personal", "care", "cosmetic", "grooming"],
    "sports": ["sport", "fitness", "gym", "outdoor", "exercise"],
    "books": ["book", "education", "stationery", "novel"],
    "food": ["food", "grocery", "organic", "health", "nutrition"],
}


def _pick_category(categories: list[Category], key: str) -> Category | None:
    keywords = CATEGORY_KEYWORDS.get(key, [key])
    for cat in categories:
        slug_lower = (cat.slug or "").lower()
        name_lower = (cat.name or "").lower()
        for kw in keywords:
            if kw in slug_lower or kw in name_lower:
                return cat
    return None


async def seed():
    engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"statement_cache_size": 0},
    )
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # ── Get vendor ──────────────────────────────────────────────────────
        result = await db.execute(
            select(User).where(User.email == "reetu+3@gmail.com")
        )
        user = result.scalar_one_or_none()
        if not user:
            print("ERROR: User reetu+3@gmail.com not found in DB")
            return

        result = await db.execute(
            select(Vendor).where(Vendor.user_id == user.id)
        )
        vendor = result.scalar_one_or_none()
        if not vendor:
            print("ERROR: Vendor record not found for this user")
            return

        print(f"Vendor found: {vendor.business_name} (ID={vendor.id})")

        # ── Load all categories ─────────────────────────────────────────────
        result = await db.execute(select(Category).where(Category.is_active == True))
        categories = result.scalars().all()
        print(f"Categories in DB: {[c.name for c in categories]}")

        if not categories:
            print("WARNING: No active categories found. Products will NOT be inserted.")
            return

        # ── Insert products ─────────────────────────────────────────────────
        inserted = 0
        fallback_cat = categories[0]

        for item in CATALOG:
            cat = _pick_category(categories, item["category_key"]) or fallback_cat

            # Generate unique slug
            base_slug = slugify(item["name"])
            slug = base_slug
            counter = 1
            while True:
                exists = await db.execute(
                    select(Product.id).where(Product.slug == slug)
                )
                if not exists.scalar_one_or_none():
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1

            product = Product(
                vendor_id=vendor.id,
                category_id=cat.id,
                name=item["name"],
                slug=slug,
                description=item.get("description", ""),
                brand=item.get("brand"),
                price=item["price"],
                original_price=item.get("original_price"),
                discount_percentage=item.get("discount_percentage"),
                stock=item.get("stock", 50),
                unit="pcs",
                status="approved",
                rating=item.get("rating", 4.0),
                review_count=item.get("review_count", 0),
                images=item.get("images", []),
                tags=item.get("tags", []),
                specifications=item.get("specifications", {}),
                is_featured=item.get("is_featured", False),
                view_count=random.randint(100, 5000),
            )
            db.add(product)
            inserted += 1
            print(f"  + {item['name']} -> category: {cat.name}")

        await db.commit()
        print(f"\nDone! {inserted} products seeded with status='approved'")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

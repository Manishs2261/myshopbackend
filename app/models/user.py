from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date,
    ForeignKey, Enum, JSON, BigInteger, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


# ─── Enums ─────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    USER = "USER"
    VENDOR = "VENDOR"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING = "pending"


class VendorStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class ShopStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ProductStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    INACTIVE = "inactive"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PayoutStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CouponType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class PageTheme(str, enum.Enum):
    DEFAULT = "default"
    MODERN = "modern"
    CLASSIC = "classic"
    MINIMAL = "minimal"
    COLORFUL = "colorful"


class FeedbackType(str, enum.Enum):
    FEEDBACK = "feedback"
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    GENERAL = "general"


class FeedbackStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class FeedbackPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ─── Models ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String(128), unique=True, index=True, nullable=True)  # nullable for direct auth
    name = Column(String(200))
    email = Column(String(200), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    hashed_password = Column(String(256), nullable=True)          # for email/password auth
    unverified_email = Column(String(200), nullable=True)         # temporarily store email during verification
    otp_code = Column(String(10), nullable=True)                  # for phone OTP
    otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(200), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    is_email_verified = Column(Boolean, default=False)
    is_phone_verified = Column(Boolean, default=False)
    role = Column(String(20), default=UserRole.USER)
    status = Column(String(20), default=UserStatus.ACTIVE)
    avatar_url = Column(String(500))
    gender = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    alternate_phone = Column(String(20), nullable=True)
    pincode = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="user", uselist=False)
    orders = relationship("Order", back_populates="user")
    cart = relationship("Cart", back_populates="user", uselist=False)
    wishlist = relationship("Wishlist", back_populates="user")
    events = relationship("Event", back_populates="user")


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    business_name = Column(String(300), nullable=False)
    business_email = Column(String(200))
    business_phone = Column(String(20))
    gst_number = Column(String(50))
    pan_number = Column(String(20))
    status = Column(String(20), default=VendorStatus.PENDING)
    verified = Column(Boolean, default=False)
    bank_account = Column(String(30))
    ifsc_code = Column(String(20))
    total_earnings = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="vendor")
    shop = relationship("Shop", back_populates="vendor", uselist=False)
    products = relationship("Product", back_populates="vendor")
    payouts = relationship("Payout", back_populates="vendor")
    marketplace_settings = relationship("MarketplaceSettings", back_populates="vendor", uselist=False)
    feedbacks = relationship("VendorFeedback", back_populates="vendor")
    sponsorships = relationship("VendorSponsorship", back_populates="vendor")


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), unique=True, nullable=False)
    name = Column(String(300), nullable=False)
    description = Column(Text)
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100), default="India")
    pincode = Column(String(10))
    latitude = Column(Float)
    longitude = Column(Float)
    logo_url = Column(String(500))
    banner_url = Column(String(500))
    gallery = Column(JSON)  # Store array of image URLs
    status = Column(String(20), default=ShopStatus.ACTIVE)
    opening_time = Column(String(10))
    closing_time = Column(String(10))
    working_days = Column(JSON)  # ["Mon","Tue",...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="shop")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True)
    description = Column(Text)
    image_url = Column(String(500))
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(500), nullable=False)
    slug = Column(String(500), unique=True)
    description = Column(Text)
    brand = Column(String(200))
    price = Column(Numeric(10, 2), nullable=False)
    original_price = Column(Numeric(10, 2))
    discount_percentage = Column(Integer)
    stock = Column(Integer, default=0)
    unit = Column(String(50))  # kg, pcs, litre, etc.
    status = Column(String(20), default=ProductStatus.PENDING)
    rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    images = Column(JSON)  # list of URLs
    tags = Column(JSON)  # list of strings
    specifications = Column(JSON)  # {key: value}
    is_featured = Column(Boolean, default=False)
    is_sponsored = Column(Boolean, default=False)
    sponsor_request_status = Column(String(20), default="none")  # none | pending | approved | rejected
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="products")
    category = relationship("Category", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete")
    order_items = relationship("OrderItem", back_populates="product")
    wishlist_items = relationship("Wishlist", back_populates="product")
    reviews = relationship("Review", back_populates="product")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    size = Column(String(50))
    color = Column(String(50))
    sku = Column(String(100), unique=True)
    price = Column(Numeric(10, 2))
    stock = Column(Integer, default=0)
    images = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="variants")


class Cart(Base):
    __tablename__ = "cart"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="cart")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("cart.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")


class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "product_id"),)

    user = relationship("User", back_populates="wishlist")
    product = relationship("Product", back_populates="wishlist_items")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), default=0)
    final_amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(30), default=OrderStatus.PENDING)
    payment_status = Column(String(30), default=PaymentStatus.PENDING)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=True)
    shipping_address = Column(JSON)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete")
    payment = relationship("Payment", back_populates="order", uselist=False)
    coupon = relationship("Coupon")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(String(30), default=OrderStatus.PENDING)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    variant = relationship("ProductVariant")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    razorpay_order_id = Column(String(100), unique=True)
    razorpay_payment_id = Column(String(100))
    razorpay_signature = Column(String(300))
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="INR")
    status = Column(String(30), default=PaymentStatus.PENDING)
    method = Column(String(50))  # upi, card, netbanking, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    order = relationship("Order", back_populates="payment")


class Event(Base):
    __tablename__ = "events"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String(100))
    event_type = Column(String(50), nullable=False)  # search, product_click, add_to_cart, etc.
    event_metadata = Column("metadata", String)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="events")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text)
    images = Column(JSON)
    is_verified_purchase = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("product_id", "user_id"),)

    product = relationship("Product", back_populates="reviews")
    user = relationship("User")


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    type = Column(String(20), default=CouponType.PERCENTAGE)  # percentage, fixed
    value = Column(Numeric(10, 2), nullable=False)
    min_order_amount = Column(Numeric(10, 2), default=0)
    max_discount = Column(Numeric(10, 2))
    usage_limit = Column(Integer)
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    valid_from = Column(DateTime(timezone=True))
    valid_to = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Payout(Base):
    __tablename__ = "payouts"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(30), default=PayoutStatus.PENDING)
    utr_number = Column(String(100))
    notes = Column(Text)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    vendor = relationship("Vendor", back_populates="payouts")


class MarketplaceSettings(Base):
    __tablename__ = "marketplace_settings"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), unique=True)

    # Page Theme and Colors
    theme = Column(String, default=PageTheme.DEFAULT)
    primary_color = Column(String, default="#c8a96e")  # Gold accent
    secondary_color = Column(String, default="#1a1208")  # Dark
    background_color = Column(String, default="#faf8f5")  # Cream

    # Banner Settings
    banner_text = Column(String, default="Welcome to Our Store")
    banner_subtext = Column(String, default="Discover amazing products")
    show_banner = Column(Boolean, default=True)

    # Layout Options
    show_vendor_info = Column(Boolean, default=True)
    show_contact_info = Column(Boolean, default=True)
    show_ratings = Column(Boolean, default=True)
    products_per_page = Column(Integer, default=12)

    # Custom CSS
    custom_css = Column(Text, nullable=True)

    # Social Media Links
    facebook_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    twitter_url = Column(String, nullable=True)
    whatsapp_number = Column(String, nullable=True)

    # Store Settings
    enable_reviews = Column(Boolean, default=True)
    enable_wishlist = Column(Boolean, default=True)
    enable_sharing = Column(Boolean, default=True)

    # SEO Settings
    meta_title = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    meta_keywords = Column(String, nullable=True)

    # Rich storefront editor payloads
    storefront_draft = Column(JSON, nullable=True)
    storefront_published = Column(JSON, nullable=True)
    storefront_status = Column(String, default="draft")
    published_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="marketplace_settings")


class WebsiteSettings(Base):
    __tablename__ = "website_settings"

    id = Column(Integer, primary_key=True, index=True)

    # General
    site_name = Column(String, default="LocalShop")
    tagline = Column(String, default="Your Local Shopping Destination")
    contact_email = Column(String, default="admin@localshop.in")
    contact_phone = Column(String, default="+91 9800000000")
    address = Column(Text, nullable=True)
    timezone = Column(String, default="Asia/Kolkata")
    currency = Column(String, default="INR")

    # Appearance
    logo_url = Column(String, nullable=True)
    favicon_url = Column(String, nullable=True)
    primary_color = Column(String, default="#6c5ce7")
    accent_color = Column(String, default="#00cec9")
    theme_mode = Column(String, default="Dark")
    font_family = Column(String, default="DM Sans")

    # SEO
    seo_meta_title = Column(String, nullable=True)
    seo_meta_description = Column(Text, nullable=True)
    seo_meta_keywords = Column(String, nullable=True)
    seo_og_image_url = Column(String, nullable=True)
    seo_canonical_url = Column(String, nullable=True)

    # Shipping
    shipping_free_above = Column(Float, default=499.0)
    shipping_standard_rate = Column(Float, default=49.0)
    shipping_express_rate = Column(Float, default=99.0)
    shipping_estimated_days = Column(Integer, default=3)
    shipping_policy = Column(Text, nullable=True)

    # Payments
    payment_commission_pct = Column(Float, default=10.0)
    payment_min_payout = Column(Float, default=500.0)
    payment_razorpay_enabled = Column(Boolean, default=True)
    payment_cod_enabled = Column(Boolean, default=True)
    payment_razorpay_key_id = Column(String, nullable=True)
    payment_razorpay_key_secret = Column(String, nullable=True)

    # Email / SMTP
    smtp_host = Column(String, default="smtp.gmail.com")
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_from_name = Column(String, default="LocalShop")
    smtp_from_email = Column(String, default="noreply@localshop.in")
    smtp_encryption = Column(String, default="TLS")

    # Social Links
    social_facebook = Column(String, nullable=True)
    social_instagram = Column(String, nullable=True)
    social_twitter = Column(String, nullable=True)
    social_youtube = Column(String, nullable=True)
    social_linkedin = Column(String, nullable=True)

    # Maintenance
    maintenance_enabled = Column(Boolean, default=False)
    maintenance_message = Column(Text, default="We're improving your experience. We'll be back shortly!")
    maintenance_allowed_ips = Column(String, nullable=True)
    maintenance_estimated_downtime = Column(String, nullable=True)

    # Complex JSON sections
    banner_slides = Column(JSON, nullable=True)
    promo_sections = Column(JSON, nullable=True)
    blog_posts = Column(JSON, nullable=True)
    blog_view_all_url = Column(String, default="/blog")
    blog_section_visible = Column(Boolean, default=True)
    top_navigation = Column(JSON, nullable=True)
    browse_categories = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VendorFeedback(Base):
    __tablename__ = "vendor_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    type = Column(String(30), default=FeedbackType.GENERAL, nullable=False)
    subject = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default=FeedbackStatus.OPEN)
    priority = Column(String(20), default=FeedbackPriority.MEDIUM)
    attachments = Column(JSON, nullable=True)
    admin_response = Column(Text, nullable=True)
    admin_response_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="feedbacks")

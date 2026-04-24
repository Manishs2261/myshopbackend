from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, Enum, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import enum
from datetime import datetime

Base = declarative_base()


# --- Enums ---
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VENDOR = "vendor"
    CUSTOMER = "customer"


class VendorStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"


class PayoutStatus(str, enum.Enum):
    REQUESTED = "requested"
    PROCESSED = "processed"


class PageTheme(str, enum.Enum):
    DEFAULT = "default"
    MODERN = "modern"
    CLASSIC = "classic"
    MINIMAL = "minimal"
    COLORFUL = "colorful"


# --- Models ---

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True)
    phone_number = Column(String, unique=True, nullable=True)
    role = Column(String, default=UserRole.CUSTOMER)  # Store enum as string
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    vendor_profile = relationship("Vendor", back_populates="user", uselist=False)


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    shop_name = Column(String, index=True)
    owner_name = Column(String)
    address = Column(Text)
    # Geospatial data (Simple float for now, PostGIS recommended for production)
    latitude = Column(Float)
    longitude = Column(Float)

    status = Column(String, default=VendorStatus.PENDING)
    razorpay_account_id = Column(String, nullable=True)

    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="vendor_profile")
    inventory = relationship("VendorInventory", back_populates="vendor")
    payouts = relationship("Payout", back_populates="vendor")
    marketplace_settings = relationship("MarketplaceSettings", back_populates="vendor", uselist=False)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"  # Master Catalog

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    image_url = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"))
    barcode = Column(String, index=True, nullable=True)

    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")
    vendor_listings = relationship("VendorInventory", back_populates="product")


class VendorInventory(Base):
    __tablename__ = "vendor_inventory"  # Link between Shop and Product

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    product_id = Column(Integer, ForeignKey("products.id"))

    price = Column(Float)
    is_in_stock = Column(Boolean, default=True)

    vendor = relationship("Vendor", back_populates="inventory")
    product = relationship("Product", back_populates="vendor_listings")


class Payout(Base):
    __tablename__ = "payouts"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    amount = Column(Float)
    status = Column(String, default=PayoutStatus.REQUESTED)
    processed_at = Column(DateTime, nullable=True)

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
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="marketplace_settings")
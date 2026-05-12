from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime
from decimal import Decimal
import re


# ─── Auth ──────────────────────────────────────────────────────────────────

class FirebaseLoginRequest(BaseModel):
    firebase_token: str
    role: Optional[str] = "USER"  # USER or VENDOR


class FirebaseVerifyPhoneRequest(BaseModel):
    firebase_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ─── Customer Registration ──────────────────────────────────────────────────

class CustomerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if not re.match(r"^[6-9]\d{9}$", v.replace("+91", "").replace(" ", "")):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class CustomerLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ─── Vendor Registration ────────────────────────────────────────────────────

class VendorRegisterRequest(BaseModel):
    # Personal info
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=6, max_length=100)

    # Business info
    business_name: Optional[str] = None
    business_email: Optional[EmailStr] = None
    business_phone: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None

    @field_validator("phone", "business_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v
        cleaned = v.replace("+91", "").replace(" ", "")
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return v

    # @field_validator("gst_number")
    # @classmethod
    # def validate_gst(cls, v):
    #     if v and not re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$", v):
    #         raise ValueError("Invalid GST number format (e.g. 27AAPFU0939F1ZV)")
    #     return v
    #
    # @field_validator("pan_number")
    # @classmethod
    # def validate_pan(cls, v):
    #     if v and not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", v):
    #         raise ValueError("Invalid PAN number format (e.g. ABCDE1234F)")
    #     return v


class VendorLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ─── OTP / Phone Auth ───────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        cleaned = v.replace("+91", "").replace(" ", "")
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return cleaned


class SendEmailOTPRequest(BaseModel):
    email: Optional[EmailStr] = None


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str = Field(..., min_length=4, max_length=6)
    role: Optional[str] = "USER"  # USER or VENDOR


# ─── Password Management ────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


# ─── User ──────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None


class UserUpdate(UserBase):
    pass


class UserResponse(BaseModel):
    id: int
    firebase_uid: Optional[str] = None
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    role: str
    status: str
    avatar_url: Optional[str]
    is_email_verified: Optional[bool] = False
    is_phone_verified: Optional[bool] = False
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Vendor ─────────────────────────────────────────────────────────────────

class VendorCreate(BaseModel):
    business_name: str
    business_email: Optional[str] = None
    business_phone: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc_code: Optional[str] = None


class VendorUpdate(VendorCreate):
    business_name: Optional[str] = None


class VendorResponse(BaseModel):
    id: int
    user_id: int
    business_name: str
    business_email: Optional[str]
    business_phone: Optional[str]
    gst_number: Optional[str]
    status: str
    verified: bool
    total_earnings: Optional[Decimal]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Shop ───────────────────────────────────────────────────────────────────

class ShopCreate(BaseModel):
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    working_days: Optional[List[str]] = None


class ShopUpdate(ShopCreate):
    name: Optional[str]


class ShopResponse(BaseModel):
    id: int
    vendor_id: int
    name: str
    description: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    pincode: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    logo_url: Optional[str]
    banner_url: Optional[str]
    gallery: Optional[List[str]]
    status: str
    opening_time: Optional[str]
    closing_time: Optional[str]
    working_days: Optional[List[str]]

    class Config:
        from_attributes = True


class MarketplaceSettingsBase(BaseModel):
    theme: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    background_color: Optional[str] = None
    banner_text: Optional[str] = None
    banner_subtext: Optional[str] = None
    show_banner: Optional[bool] = None
    show_vendor_info: Optional[bool] = None
    show_contact_info: Optional[bool] = None
    show_ratings: Optional[bool] = None
    products_per_page: Optional[int] = Field(default=None, ge=1, le=100)
    custom_css: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    whatsapp_number: Optional[str] = None
    enable_reviews: Optional[bool] = None
    enable_wishlist: Optional[bool] = None
    enable_sharing: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None


class MarketplaceSettingsUpdate(MarketplaceSettingsBase):
    pass


class MarketplaceSettingsResponse(MarketplaceSettingsBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Website Settings ────────────────────────────────────────────────────────

class WebsiteSettingsUpdate(BaseModel):
    # General
    site_name: Optional[str] = None
    tagline: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    # Appearance
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None
    font_family: Optional[str] = None
    # SEO
    seo_meta_title: Optional[str] = None
    seo_meta_description: Optional[str] = None
    seo_meta_keywords: Optional[str] = None
    seo_og_image_url: Optional[str] = None
    seo_canonical_url: Optional[str] = None
    # Shipping
    shipping_free_above: Optional[float] = None
    shipping_standard_rate: Optional[float] = None
    shipping_express_rate: Optional[float] = None
    shipping_estimated_days: Optional[int] = None
    shipping_policy: Optional[str] = None
    # Payments
    payment_commission_pct: Optional[float] = None
    payment_min_payout: Optional[float] = None
    payment_razorpay_enabled: Optional[bool] = None
    payment_cod_enabled: Optional[bool] = None
    payment_razorpay_key_id: Optional[str] = None
    payment_razorpay_key_secret: Optional[str] = None
    # Email / SMTP
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_name: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_encryption: Optional[str] = None
    # Social
    social_facebook: Optional[str] = None
    social_instagram: Optional[str] = None
    social_twitter: Optional[str] = None
    social_youtube: Optional[str] = None
    social_linkedin: Optional[str] = None
    # Maintenance
    maintenance_enabled: Optional[bool] = None
    maintenance_message: Optional[str] = None
    maintenance_allowed_ips: Optional[str] = None
    maintenance_estimated_downtime: Optional[str] = None
    # JSON sections
    banner_slides: Optional[List[Any]] = None
    promo_sections: Optional[List[Any]] = None
    blog_posts: Optional[List[Any]] = None
    blog_view_all_url: Optional[str] = None
    blog_section_visible: Optional[bool] = None
    top_navigation: Optional[List[Any]] = None
    browse_categories: Optional[List[Any]] = None


class WebsiteSettingsResponse(WebsiteSettingsUpdate):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsGeneralResponse(BaseModel):
    id: int
    site_name: Optional[str] = None
    tagline: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsAppearanceResponse(BaseModel):
    id: int
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None
    font_family: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsBannerResponse(BaseModel):
    id: int
    banner_slides: Optional[List[Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsPromoResponse(BaseModel):
    id: int
    promo_sections: Optional[List[Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsBlogResponse(BaseModel):
    id: int
    blog_posts: Optional[List[Any]] = None
    blog_view_all_url: Optional[str] = None
    blog_section_visible: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsNavResponse(BaseModel):
    id: int
    top_navigation: Optional[List[Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsBrowseCategoriesResponse(BaseModel):
    id: int
    browse_categories: Optional[List[Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsShippingResponse(BaseModel):
    id: int
    shipping_free_above: Optional[float] = None
    shipping_standard_rate: Optional[float] = None
    shipping_express_rate: Optional[float] = None
    shipping_estimated_days: Optional[int] = None
    shipping_policy: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsSocialResponse(BaseModel):
    id: int
    social_facebook: Optional[str] = None
    social_instagram: Optional[str] = None
    social_twitter: Optional[str] = None
    social_youtube: Optional[str] = None
    social_linkedin: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsMaintenanceResponse(BaseModel):
    id: int
    maintenance_enabled: Optional[bool] = None
    maintenance_message: Optional[str] = None
    maintenance_estimated_downtime: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WebsiteSettingsHomeResponse(BaseModel):
    id: int
    # General
    site_name: Optional[str] = None
    tagline: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    # Appearance
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_mode: Optional[str] = None
    font_family: Optional[str] = None
    # Banner Slider
    banner_slides: Optional[List[Any]] = None
    # Promo Sections
    promo_sections: Optional[List[Any]] = None
    # Blog Posts
    blog_posts: Optional[List[Any]] = None
    blog_view_all_url: Optional[str] = None
    blog_section_visible: Optional[bool] = None
    # Navigation
    top_navigation: Optional[List[Any]] = None
    browse_categories: Optional[List[Any]] = None
    # Shipping
    shipping_free_above: Optional[float] = None
    shipping_standard_rate: Optional[float] = None
    shipping_express_rate: Optional[float] = None
    shipping_estimated_days: Optional[int] = None
    shipping_policy: Optional[str] = None
    # Social
    social_facebook: Optional[str] = None
    social_instagram: Optional[str] = None
    social_twitter: Optional[str] = None
    social_youtube: Optional[str] = None
    social_linkedin: Optional[str] = None
    # Maintenance
    maintenance_enabled: Optional[bool] = None
    maintenance_message: Optional[str] = None
    maintenance_estimated_downtime: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Category ───────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str]
    image_url: Optional[str]
    parent_id: Optional[int]
    sort_order: Optional[int] = 0


class CategoryUpdate(CategoryCreate):
    name: Optional[str]


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    parent_id: Optional[int]
    is_active: bool
    sort_order: int
    children: Optional[List["CategoryResponse"]] = []

    class Config:
        from_attributes = True


CategoryResponse.model_rebuild()


# ─── Product ────────────────────────────────────────────────────────────────

class ProductVariantCreate(BaseModel):
    size: Optional[str]
    color: Optional[str]
    sku: Optional[str]
    price: Optional[Decimal]
    stock: Optional[int] = 0
    images: Optional[List[str]]


class ProductVariantResponse(BaseModel):
    id: int
    size: Optional[str]
    color: Optional[str]
    sku: Optional[str]
    price: Optional[Decimal]
    stock: int

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    category_id: int
    name: str
    description: Optional[str]
    brand: Optional[str]
    price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    stock: int = 0
    unit: Optional[str]
    images: Optional[List[str]]
    tags: Optional[List[str]]
    specifications: Optional[Dict[str, Any]]
    variants: Optional[List[ProductVariantCreate]]


class ProductUpdate(BaseModel):
    category_id: Optional[int]
    name: Optional[str]
    description: Optional[str]
    brand: Optional[str]
    price: Optional[Decimal]
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    stock: Optional[int]
    unit: Optional[str]
    images: Optional[List[str]]
    tags: Optional[List[str]]
    specifications: Optional[Dict[str, Any]]


class ProductResponse(BaseModel):
    id: int
    vendor_id: int
    category_id: int
    name: str
    slug: Optional[str]
    description: Optional[str]
    brand: Optional[str]
    price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    stock: int
    unit: Optional[str]
    status: str
    rating: float
    review_count: int
    images: Optional[List[str]]
    tags: Optional[List[str]]
    specifications: Optional[Dict[str, Any]]
    is_featured: bool
    is_sponsored: bool = False
    sponsor_request_status: str = "none"
    view_count: int
    variants: List[ProductVariantResponse] = []
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    id: int
    vendor_id: int
    category_id: int
    name: str
    price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    stock: int
    status: str
    rating: float
    images: Optional[List[str]]
    is_featured: bool
    is_sponsored: bool = False
    sponsor_request_status: str = "none"
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Cart ───────────────────────────────────────────────────────────────────

class CartItemCreate(BaseModel):
    product_id: int
    variant_id: Optional[int]
    quantity: int = Field(ge=1, default=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int]
    quantity: int
    product: ProductListResponse

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    id: int
    user_id: int
    items: List[CartItemResponse] = []
    total: Decimal = Decimal("0")

    class Config:
        from_attributes = True


# ─── Wishlist ───────────────────────────────────────────────────────────────

class WishlistResponse(BaseModel):
    id: int
    product_id: int
    product: ProductListResponse
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Order ──────────────────────────────────────────────────────────────────

class ShippingAddress(BaseModel):
    name: str
    phone: str
    address: str
    city: str
    state: str
    pincode: str
    country: str = "India"


class OrderCreate(BaseModel):
    shipping_address: ShippingAddress
    coupon_code: Optional[str]
    notes: Optional[str]


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: Decimal
    status: str
    product: ProductListResponse

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    status: str
    payment_status: str
    shipping_address: Optional[Dict]
    notes: Optional[str]
    items: List[OrderItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: str


# ─── Payment ────────────────────────────────────────────────────────────────

class PaymentCreateRequest(BaseModel):
    order_id: int


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentResponse(BaseModel):
    razorpay_order_id: str
    amount: int
    currency: str
    key_id: str
    order_id: int


# ─── Review ─────────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    product_id: int
    rating: int = Field(ge=1, le=5)
    comment: Optional[str]
    images: Optional[List[str]]


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    rating: int
    comment: Optional[str]
    images: Optional[List[str]]
    is_verified_purchase: bool
    created_at: datetime
    user: Optional[UserResponse]

    class Config:
        from_attributes = True


# ─── Coupon ─────────────────────────────────────────────────────────────────

class CouponCreate(BaseModel):
    code: str
    description: Optional[str]
    type: str = "percentage"
    value: Decimal
    min_order_amount: Optional[Decimal] = 0
    max_discount: Optional[Decimal]
    usage_limit: Optional[int]
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]


class CouponUpdate(CouponCreate):
    code: Optional[str]
    value: Optional[Decimal]
    type: Optional[str]


class CouponResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]
    type: str
    value: Decimal
    min_order_amount: Decimal
    max_discount: Optional[Decimal]
    usage_limit: Optional[int]
    used_count: int
    is_active: bool
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]

    class Config:
        from_attributes = True


class CouponValidate(BaseModel):
    code: str
    order_amount: Decimal


# ─── Help & Feedback ────────────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    type: str = "general"
    subject: str = Field(..., min_length=5, max_length=300)
    description: str = Field(..., min_length=10)
    priority: str = "medium"
    attachments: Optional[List[str]] = None


class FeedbackResponse(BaseModel):
    id: int
    vendor_id: int
    type: str
    subject: str
    description: str
    status: str
    priority: str
    attachments: Optional[List[str]]
    admin_response: Optional[str]
    admin_response_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class AdminFeedbackUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    admin_response: Optional[str] = None


# ─── Events ─────────────────────────────────────────────────────────────────

class EventData(BaseModel):
    type: str
    data: Dict[str, Any]


class EventBatchRequest(BaseModel):
    events: List[EventData]


# ─── Payout ─────────────────────────────────────────────────────────────────

class PayoutRequest(BaseModel):
    amount: Decimal
    notes: Optional[str]


class PayoutResponse(BaseModel):
    id: int
    vendor_id: int
    amount: Decimal
    status: str
    utr_number: Optional[str]
    notes: Optional[str]
    requested_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Pagination ─────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    limit: int
    pages: int


# ─── Analytics ──────────────────────────────────────────────────────────────

class VendorDashboard(BaseModel):
    total_views: int
    total_orders: int
    revenue: Decimal
    conversion_rate: float
    pending_orders: int
    total_products: int


class VendorDashboardRecentProduct(BaseModel):
    id: int
    name: str
    category_name: Optional[str] = None
    price: Decimal
    status: str
    click_count: int = 0
    images: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VendorDashboardOverview(BaseModel):
    total_products: int
    active_products: int
    inactive_products: int
    total_views: int
    total_orders: int
    pending_orders: int
    revenue: Decimal
    completion_score: int
    recent_products: List[VendorDashboardRecentProduct] = []


class VendorAnalyticsSeriesPoint(BaseModel):
    date: str
    value: int


class VendorAnalyticsTopProduct(BaseModel):
    product_id: int
    name: str
    image: Optional[str] = None
    views: int
    clicks: int = 0
    searches: int = 0


class VendorAnalyticsCity(BaseModel):
    city: str
    count: int
    percentage: float


class VendorAnalyticsOverview(BaseModel):
    total_views: int
    total_clicks: int
    total_searches: int
    revenue_estimate: Decimal
    growth_rate: float
    views_by_day: List[VendorAnalyticsSeriesPoint] = []
    clicks_by_day: List[VendorAnalyticsSeriesPoint] = []
    top_products: List[VendorAnalyticsTopProduct] = []
    top_cities: List[VendorAnalyticsCity] = []


class AdminAnalytics(BaseModel):
    total_users: int
    total_vendors: int
    total_products: int
    total_orders: int
    revenue: Decimal
    top_products: List[Dict]
    cart_abandonment_rate: float
    pending_vendor_approvals: int
    pending_product_approvals: int

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.sql import func
from app.core.database import Base


class ProductView(Base):
    __tablename__ = "product_views"

    id = Column(BigInteger, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100))
    ip_address = Column(String(50))
    device = Column(String(50))    # mobile / desktop / tablet
    platform = Column(String(50))  # ios / android / web
    city = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_product_views_vendor_date", "vendor_id", "created_at"),
        Index("ix_product_views_product_date", "product_id", "created_at"),
    )


class ProductImpression(Base):
    __tablename__ = "product_impressions"

    id = Column(BigInteger, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_product_impressions_vendor_date", "vendor_id", "created_at"),
        Index("ix_product_impressions_product_date", "product_id", "created_at"),
    )


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    keyword = Column(String(500), nullable=False)
    result_count = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100))
    city = Column(String(100))
    ip_address = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_search_logs_keyword_date", "keyword", "created_at"),
        Index("ix_search_logs_date", "created_at"),
    )


class VendorAction(Base):
    __tablename__ = "vendor_actions"

    id = Column(BigInteger, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    # call_click | whatsapp_click | direction_click | share | inquiry
    # profile_view | wishlist_add | wishlist_remove | product_click
    action_type = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100))
    device = Column(String(50))
    platform = Column(String(50))
    city = Column(String(100))
    ip_address = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_vendor_actions_vendor_type_date", "vendor_id", "action_type", "created_at"),
        Index("ix_vendor_actions_product_date", "product_id", "created_at"),
    )


class AnalyticsSummary(Base):
    __tablename__ = "analytics_summary"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    total_views = Column(Integer, default=0)
    total_impressions = Column(Integer, default=0)
    total_call_clicks = Column(Integer, default=0)
    total_whatsapp_clicks = Column(Integer, default=0)
    total_direction_clicks = Column(Integer, default=0)
    total_inquiries = Column(Integer, default=0)
    total_wishlist_adds = Column(Integer, default=0)
    total_searches = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("vendor_id", "date", name="uq_analytics_summary_vendor_date"),
    )


class VendorInsight(Base):
    __tablename__ = "vendor_insights"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    # growth | low_ctr | trending | stock_alert | info
    insight_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    extra_data = Column(Text)  # JSON string for additional metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_vendor_insights_vendor_read_date", "vendor_id", "is_read", "created_at"),
    )

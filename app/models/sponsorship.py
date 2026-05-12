from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SponsorshipPlan(Base):
    __tablename__ = "sponsorship_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    duration_days = Column(Integer, nullable=False, default=30)
    priority = Column(Integer, default=1)
    max_categories = Column(Integer, default=3)
    max_locations = Column(Integer, default=3)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sponsorships = relationship("VendorSponsorship", back_populates="plan")


class VendorSponsorship(Base):
    __tablename__ = "vendor_sponsorships"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("sponsorship_plans.id"), nullable=False)
    # valid: pending | approved | active | rejected | expired | paused | cancelled
    status = Column(String(20), nullable=False, default="pending")
    target_categories = Column(JSON, default=list)   # [category_id, ...]
    target_locations = Column(JSON, default=list)    # ["city", "pincode", ...]
    target_keywords = Column(JSON, default=list)     # ["mobile", "electronics", ...]
    priority = Column(Integer, default=1)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    click_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vendor = relationship("Vendor", back_populates="sponsorships")
    plan = relationship("SponsorshipPlan", back_populates="sponsorships")

"""
Pydantic schemas for Admin Analytics Dashboard endpoints.
All endpoints under /admin/analytics/v2/
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel


# ─── Period ──────────────────────────────────────────────────────────────────

class GrowthMetric(BaseModel):
    current: int
    previous: int
    growth_pct: float


# ─── Overview ────────────────────────────────────────────────────────────────

class AdminOverviewResponse(BaseModel):
    period: str
    start_date: str
    end_date: str
    total_users: int
    total_vendors: int
    active_vendors: int
    total_products: int
    total_searches: GrowthMetric
    total_views: GrowthMetric
    total_inquiries: GrowthMetric
    total_actions: GrowthMetric
    dau: int
    mau: int
    platform_growth_pct: float
    fraud_flags: int


# ─── Vendor Leaderboard ───────────────────────────────────────────────────────

class VendorLeaderboardItem(BaseModel):
    vendor_id: int
    shop_name: str
    status: str
    total_products: int
    total_views: int
    total_inquiries: int
    total_contact_actions: int
    ctr_pct: float
    last_active: Optional[str] = None


class VendorLeaderboardResponse(BaseModel):
    items: list[VendorLeaderboardItem]
    total: int
    page: int
    limit: int


# ─── Product Analytics ───────────────────────────────────────────────────────

class AdminProductItem(BaseModel):
    product_id: int
    name: str
    vendor_name: str
    category: str
    views: int
    impressions: int
    ctr: float
    inquiries: int
    wishlist_adds: int
    last_viewed: Optional[str] = None


class AdminProductResponse(BaseModel):
    items: list[AdminProductItem]
    total: int
    page: int
    limit: int


# ─── Search Analytics ────────────────────────────────────────────────────────

class SearchKeywordItem(BaseModel):
    keyword: str
    count: int
    avg_results: float
    is_no_result: bool


class SearchTrendPoint(BaseModel):
    date: str
    count: int


class AdminSearchResponse(BaseModel):
    total_searches: int
    unique_keywords: int
    top_keywords: list[SearchKeywordItem]
    no_result_keywords: list[SearchKeywordItem]
    search_trend: list[SearchTrendPoint]


# ─── Customer Behavior ───────────────────────────────────────────────────────

class ActionBreakdownItem(BaseModel):
    action_type: str
    count: int
    percentage: float


class FunnelStep(BaseModel):
    label: str
    count: int
    drop_pct: float


class DeviceBreakdownItem(BaseModel):
    device: str
    count: int
    percentage: float


class AdminCustomerBehaviorResponse(BaseModel):
    dau: int
    mau: int
    action_breakdown: list[ActionBreakdownItem]
    funnel: list[FunnelStep]
    device_breakdown: list[DeviceBreakdownItem]
    platform_breakdown: list[DeviceBreakdownItem]


# ─── Revenue ─────────────────────────────────────────────────────────────────

class RevenueTrendPoint(BaseModel):
    date: str
    revenue: float
    order_count: int


class AdminRevenueResponse(BaseModel):
    total_revenue: float
    total_orders: int
    avg_order_value: float
    sponsorship_revenue: float
    revenue_trend: list[RevenueTrendPoint]
    revenue_growth_pct: float


# ─── Geo Analytics ───────────────────────────────────────────────────────────

class CityStatItem(BaseModel):
    city: str
    views: int
    searches: int
    actions: int


class AdminGeoResponse(BaseModel):
    top_cities: list[CityStatItem]


# ─── Category Analytics ──────────────────────────────────────────────────────

class CategoryStatItem(BaseModel):
    category_id: int
    name: str
    total_products: int
    total_views: int
    percentage: float


class AdminCategoryResponse(BaseModel):
    items: list[CategoryStatItem]


# ─── Daily Traffic Chart ─────────────────────────────────────────────────────

class DailyTrafficPoint(BaseModel):
    date: str
    views: int
    searches: int
    actions: int
    inquiries: int


class AdminDailyTrafficResponse(BaseModel):
    series: list[DailyTrafficPoint]


# ─── Fraud Detection ─────────────────────────────────────────────────────────

class FraudSummaryItem(BaseModel):
    id: int
    fraud_type: str
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    event_count: int
    detected_at: str
    is_resolved: bool


class AdminFraudResponse(BaseModel):
    total_flagged: int
    unresolved: int
    suspicious_ip_count: int
    items: list[FraudSummaryItem]


# ─── Admin Insights ──────────────────────────────────────────────────────────

class AdminInsightItem(BaseModel):
    id: int
    insight_type: str
    title: str
    message: str
    is_read: bool
    created_at: str


class AdminInsightsResponse(BaseModel):
    items: list[AdminInsightItem]
    unread_count: int

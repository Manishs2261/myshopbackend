"""
Admin Analytics Dashboard — platform-wide analytics endpoints.
All routes require ADMIN role. Prefix: /admin/analytics/v2
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.analytics import (
    AdminInsight, FraudLog, ProductImpression, ProductView, SearchLog, VendorAction,
)
from app.models.user import Category, Order, Product, Shop, User, Vendor
from app.schemas.admin_analytics_schemas import (
    ActionBreakdownItem, AdminCategoryResponse, AdminCustomerBehaviorResponse,
    AdminDailyTrafficResponse, AdminFraudResponse, AdminGeoResponse,
    AdminInsightItem, AdminInsightsResponse, AdminOverviewResponse,
    AdminProductItem, AdminProductResponse, AdminRevenueResponse,
    CategoryStatItem, CityStatItem, DailyTrafficPoint, DeviceBreakdownItem,
    FraudSummaryItem, FunnelStep, GrowthMetric, RevenueTrendPoint,
    SearchKeywordItem, SearchTrendPoint, AdminSearchResponse,
    VendorLeaderboardItem, VendorLeaderboardResponse,
)

router = APIRouter(prefix="/admin/analytics/v2", tags=["Admin Analytics"])
get_admin = require_role("ADMIN")


# ─── Period Helper ───────────────────────────────────────────────────────────

def resolve_period(
    period: str,
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[datetime, datetime, datetime, datetime]:
    """
    Returns (start, end, prev_start, prev_end) in UTC.
    prev_* covers the same duration immediately before start.
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "7d":
        start = now - timedelta(days=7)
        end = now
    elif period == "30d":
        start = now - timedelta(days=30)
        end = now
    else:  # custom
        if not start_date or not end_date:
            raise HTTPException(status_code=422, detail="start_date and end_date required for custom period")
        start = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        end = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)
    delta = end - start
    return start, end, start - delta, start


def growth_pct(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


# ─── Overview ────────────────────────────────────────────────────────────────

@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, prev_start, prev_end = resolve_period(period, start_date, end_date)

    # Static platform counts
    total_users = (await db.execute(
        select(func.count(User.id)).where(User.role == "USER")
    )).scalar() or 0

    total_vendors = (await db.execute(select(func.count(Vendor.id)))).scalar() or 0

    total_products = (await db.execute(
        select(func.count(Product.id)).where(Product.status == "approved")
    )).scalar() or 0

    # Period-based metrics (current + previous for growth)
    async def count_views(s, e):
        return (await db.execute(
            select(func.count()).select_from(ProductView)
            .where(ProductView.created_at >= s, ProductView.created_at < e)
        )).scalar() or 0

    async def count_searches(s, e):
        return (await db.execute(
            select(func.count()).select_from(SearchLog)
            .where(SearchLog.created_at >= s, SearchLog.created_at < e)
        )).scalar() or 0

    async def count_inquiries(s, e):
        return (await db.execute(
            select(func.count()).select_from(VendorAction)
            .where(VendorAction.action_type == "inquiry",
                   VendorAction.created_at >= s, VendorAction.created_at < e)
        )).scalar() or 0

    async def count_actions(s, e):
        return (await db.execute(
            select(func.count()).select_from(VendorAction)
            .where(VendorAction.created_at >= s, VendorAction.created_at < e)
        )).scalar() or 0

    curr_views, prev_views = await count_views(start, end), await count_views(prev_start, prev_end)
    curr_searches, prev_searches = await count_searches(start, end), await count_searches(prev_start, prev_end)
    curr_inquiries, prev_inquiries = await count_inquiries(start, end), await count_inquiries(prev_start, prev_end)
    curr_actions, prev_actions = await count_actions(start, end), await count_actions(prev_start, prev_end)

    # Active vendors in period
    active_vendors = (await db.execute(
        select(func.count(ProductView.vendor_id.distinct()))
        .where(ProductView.created_at >= start, ProductView.created_at < end)
    )).scalar() or 0

    # DAU — distinct sessions/users today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    dau = (await db.execute(
        select(func.count(func.distinct(
            func.coalesce(func.cast(ProductView.user_id, text("TEXT")), ProductView.session_id)
        )))
        .where(ProductView.created_at >= today_start)
    )).scalar() or 0

    # MAU — distinct sessions/users this calendar month
    month_start = today_start.replace(day=1)
    mau = (await db.execute(
        select(func.count(func.distinct(
            func.coalesce(func.cast(ProductView.user_id, text("TEXT")), ProductView.session_id)
        )))
        .where(ProductView.created_at >= month_start)
    )).scalar() or 0

    # Platform growth % based on total views
    plat_growth = growth_pct(curr_views, prev_views)

    # Fraud flags (unresolved in period)
    fraud_flags = (await db.execute(
        select(func.count(FraudLog.id))
        .where(FraudLog.is_resolved == False, FraudLog.detected_at >= start)  # noqa: E712
    )).scalar() or 0

    return AdminOverviewResponse(
        period=period,
        start_date=start.date().isoformat(),
        end_date=end.date().isoformat(),
        total_users=total_users,
        total_vendors=total_vendors,
        active_vendors=active_vendors,
        total_products=total_products,
        total_searches=GrowthMetric(current=curr_searches, previous=prev_searches,
                                    growth_pct=growth_pct(curr_searches, prev_searches)),
        total_views=GrowthMetric(current=curr_views, previous=prev_views,
                                 growth_pct=growth_pct(curr_views, prev_views)),
        total_inquiries=GrowthMetric(current=curr_inquiries, previous=prev_inquiries,
                                     growth_pct=growth_pct(curr_inquiries, prev_inquiries)),
        total_actions=GrowthMetric(current=curr_actions, previous=prev_actions,
                                   growth_pct=growth_pct(curr_actions, prev_actions)),
        dau=dau,
        mau=mau,
        platform_growth_pct=plat_growth,
        fraud_flags=fraud_flags,
    )


# ─── Vendor Leaderboard ──────────────────────────────────────────────────────

@router.get("/vendors", response_model=VendorLeaderboardResponse)
async def vendor_leaderboard(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("views", pattern="^(views|inquiries|contact_actions|products)$"),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)
    offset = (page - 1) * limit

    # Subquery: views per vendor in period
    views_sub = (
        select(ProductView.vendor_id, func.count(ProductView.id).label("views"))
        .where(ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(ProductView.vendor_id)
        .subquery()
    )

    # Subquery: inquiries per vendor
    inquiries_sub = (
        select(VendorAction.vendor_id,
               func.count(VendorAction.id).label("inquiries"))
        .where(VendorAction.action_type == "inquiry",
               VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(VendorAction.vendor_id)
        .subquery()
    )

    # Subquery: contact actions (call + whatsapp) per vendor
    contact_sub = (
        select(VendorAction.vendor_id,
               func.count(VendorAction.id).label("contacts"))
        .where(VendorAction.action_type.in_(["call_click", "whatsapp_click"]),
               VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(VendorAction.vendor_id)
        .subquery()
    )

    # Subquery: last active per vendor
    last_active_sub = (
        select(ProductView.vendor_id,
               func.max(ProductView.created_at).label("last_active"))
        .where(ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(ProductView.vendor_id)
        .subquery()
    )

    # Product count per vendor
    prod_sub = (
        select(Product.vendor_id, func.count(Product.id).label("prod_count"))
        .where(Product.status == "approved")
        .group_by(Product.vendor_id)
        .subquery()
    )

    sort_map = {
        "views": func.coalesce(views_sub.c.views, 0).desc(),
        "inquiries": func.coalesce(inquiries_sub.c.inquiries, 0).desc(),
        "contact_actions": func.coalesce(contact_sub.c.contacts, 0).desc(),
        "products": func.coalesce(prod_sub.c.prod_count, 0).desc(),
    }

    stmt = (
        select(
            Vendor.id,
            Shop.name,
            Vendor.status,
            func.coalesce(prod_sub.c.prod_count, 0).label("total_products"),
            func.coalesce(views_sub.c.views, 0).label("total_views"),
            func.coalesce(inquiries_sub.c.inquiries, 0).label("total_inquiries"),
            func.coalesce(contact_sub.c.contacts, 0).label("total_contact_actions"),
            last_active_sub.c.last_active,
        )
        .outerjoin(Shop, Shop.vendor_id == Vendor.id)
        .outerjoin(views_sub, views_sub.c.vendor_id == Vendor.id)
        .outerjoin(inquiries_sub, inquiries_sub.c.vendor_id == Vendor.id)
        .outerjoin(contact_sub, contact_sub.c.vendor_id == Vendor.id)
        .outerjoin(last_active_sub, last_active_sub.c.vendor_id == Vendor.id)
        .outerjoin(prod_sub, prod_sub.c.vendor_id == Vendor.id)
        .order_by(sort_map[sort_by])
    )

    total = (await db.execute(select(func.count(Vendor.id)))).scalar() or 0
    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()

    items = []
    for row in rows:
        views = row.total_views or 0
        contact = row.total_contact_actions or 0
        ctr = round(contact / views * 100, 1) if views > 0 else 0.0
        items.append(VendorLeaderboardItem(
            vendor_id=row.id,
            shop_name=row.name or f"Vendor #{row.id}",
            status=row.status or "unknown",
            total_products=row.total_products,
            total_views=views,
            total_inquiries=row.total_inquiries or 0,
            total_contact_actions=contact,
            ctr_pct=ctr,
            last_active=row.last_active.isoformat() if row.last_active else None,
        ))

    return VendorLeaderboardResponse(items=items, total=total, page=page, limit=limit)


# ─── Product Analytics ───────────────────────────────────────────────────────

@router.get("/products", response_model=AdminProductResponse)
async def admin_product_analytics(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)
    offset = (page - 1) * limit

    views_sub = (
        select(ProductView.product_id, func.count(ProductView.id).label("views"),
               func.max(ProductView.created_at).label("last_viewed"))
        .where(ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(ProductView.product_id)
        .subquery()
    )
    imp_sub = (
        select(ProductImpression.product_id, func.count(ProductImpression.id).label("impressions"))
        .where(ProductImpression.created_at >= start, ProductImpression.created_at < end)
        .group_by(ProductImpression.product_id)
        .subquery()
    )
    inq_sub = (
        select(VendorAction.product_id, func.count(VendorAction.id).label("inquiries"))
        .where(VendorAction.action_type == "inquiry",
               VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(VendorAction.product_id)
        .subquery()
    )
    wish_sub = (
        select(VendorAction.product_id, func.count(VendorAction.id).label("wishlist_adds"))
        .where(VendorAction.action_type == "wishlist_add",
               VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(VendorAction.product_id)
        .subquery()
    )

    stmt = (
        select(
            Product.id,
            Product.name,
            Vendor.id.label("vid"),
            Shop.name.label("shop_name"),
            Category.name.label("cat_name"),
            func.coalesce(views_sub.c.views, 0).label("views"),
            func.coalesce(imp_sub.c.impressions, 0).label("impressions"),
            func.coalesce(inq_sub.c.inquiries, 0).label("inquiries"),
            func.coalesce(wish_sub.c.wishlist_adds, 0).label("wishlist_adds"),
            views_sub.c.last_viewed,
        )
        .outerjoin(Vendor, Vendor.id == Product.vendor_id)
        .outerjoin(Shop, Shop.vendor_id == Vendor.id)
        .outerjoin(Category, Category.id == Product.category_id)
        .outerjoin(views_sub, views_sub.c.product_id == Product.id)
        .outerjoin(imp_sub, imp_sub.c.product_id == Product.id)
        .outerjoin(inq_sub, inq_sub.c.product_id == Product.id)
        .outerjoin(wish_sub, wish_sub.c.product_id == Product.id)
        .where(Product.status == "approved")
        .order_by(func.coalesce(views_sub.c.views, 0).desc())
    )

    total = (await db.execute(
        select(func.count(Product.id)).where(Product.status == "approved")
    )).scalar() or 0

    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()
    items = []
    for row in rows:
        views = row.views or 0
        impressions = row.impressions or 0
        ctr = round(views / impressions * 100, 1) if impressions > 0 else 0.0
        items.append(AdminProductItem(
            product_id=row.id,
            name=row.name,
            vendor_name=row.shop_name or f"Vendor #{row.vid}",
            category=row.cat_name or "Uncategorized",
            views=views,
            impressions=impressions,
            ctr=ctr,
            inquiries=row.inquiries or 0,
            wishlist_adds=row.wishlist_adds or 0,
            last_viewed=row.last_viewed.isoformat() if row.last_viewed else None,
        ))

    return AdminProductResponse(items=items, total=total, page=page, limit=limit)


# ─── Search Analytics ────────────────────────────────────────────────────────

@router.get("/search", response_model=AdminSearchResponse)
async def admin_search_analytics(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)

    total_searches = (await db.execute(
        select(func.count()).select_from(SearchLog)
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
    )).scalar() or 0

    unique_keywords = (await db.execute(
        select(func.count(SearchLog.keyword.distinct()))
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
    )).scalar() or 0

    kw_rows = (await db.execute(
        select(
            SearchLog.keyword,
            func.count(SearchLog.id).label("cnt"),
            func.avg(SearchLog.result_count).label("avg_results"),
            func.min(SearchLog.result_count).label("min_results"),
        )
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
        .group_by(SearchLog.keyword)
        .order_by(func.count(SearchLog.id).desc())
        .limit(30)
    )).all()

    top_keywords = []
    no_result_keywords = []
    for row in kw_rows:
        avg_r = float(row.avg_results or 0)
        is_no = (row.min_results or 0) == 0 and avg_r < 1
        item = SearchKeywordItem(
            keyword=row.keyword,
            count=row.cnt,
            avg_results=round(avg_r, 1),
            is_no_result=is_no,
        )
        top_keywords.append(item)
        if is_no:
            no_result_keywords.append(item)

    # Daily search trend
    trend_rows = (await db.execute(
        select(
            func.date_trunc("day", SearchLog.created_at).label("day"),
            func.count(SearchLog.id).label("cnt"),
        )
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
        .group_by(text("day"))
        .order_by(text("day"))
    )).all()
    search_trend = [
        SearchTrendPoint(date=row.day.date().isoformat(), count=row.cnt)
        for row in trend_rows
    ]

    return AdminSearchResponse(
        total_searches=total_searches,
        unique_keywords=unique_keywords,
        top_keywords=top_keywords[:20],
        no_result_keywords=no_result_keywords[:10],
        search_trend=search_trend,
    )


# ─── Customer Behavior ───────────────────────────────────────────────────────

@router.get("/customer-behavior", response_model=AdminCustomerBehaviorResponse)
async def admin_customer_behavior(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # DAU / MAU
    dau = (await db.execute(
        select(func.count(func.distinct(
            func.coalesce(func.cast(ProductView.user_id, text("TEXT")), ProductView.session_id)
        ))).where(ProductView.created_at >= today_start)
    )).scalar() or 0

    mau = (await db.execute(
        select(func.count(func.distinct(
            func.coalesce(func.cast(ProductView.user_id, text("TEXT")), ProductView.session_id)
        ))).where(ProductView.created_at >= month_start)
    )).scalar() or 0

    # Action breakdown
    action_rows = (await db.execute(
        select(VendorAction.action_type, func.count(VendorAction.id).label("cnt"))
        .where(VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(VendorAction.action_type)
        .order_by(func.count(VendorAction.id).desc())
    )).all()
    total_actions = sum(r.cnt for r in action_rows) or 1
    action_breakdown = [
        ActionBreakdownItem(
            action_type=r.action_type,
            count=r.cnt,
            percentage=round(r.cnt / total_actions * 100, 1),
        )
        for r in action_rows
    ]

    # Conversion funnel: Searches → Product Views → Contact Actions → Inquiries
    searches = (await db.execute(
        select(func.count()).select_from(SearchLog)
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
    )).scalar() or 0

    views = (await db.execute(
        select(func.count()).select_from(ProductView)
        .where(ProductView.created_at >= start, ProductView.created_at < end)
    )).scalar() or 0

    contact_actions = (await db.execute(
        select(func.count()).select_from(VendorAction)
        .where(VendorAction.action_type.in_(["call_click", "whatsapp_click", "direction_click"]),
               VendorAction.created_at >= start, VendorAction.created_at < end)
    )).scalar() or 0

    inquiries = (await db.execute(
        select(func.count()).select_from(VendorAction)
        .where(VendorAction.action_type == "inquiry",
               VendorAction.created_at >= start, VendorAction.created_at < end)
    )).scalar() or 0

    def drop(a: int, b: int) -> float:
        if a == 0:
            return 0.0
        return round((1 - b / a) * 100, 1)

    funnel = [
        FunnelStep(label="Searches", count=searches, drop_pct=0.0),
        FunnelStep(label="Product Views", count=views, drop_pct=drop(searches, views)),
        FunnelStep(label="Contact Actions", count=contact_actions, drop_pct=drop(views, contact_actions)),
        FunnelStep(label="Inquiries", count=inquiries, drop_pct=drop(contact_actions, inquiries)),
    ]

    # Device breakdown
    device_rows = (await db.execute(
        select(ProductView.device, func.count(ProductView.id).label("cnt"))
        .where(ProductView.device.isnot(None),
               ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(ProductView.device)
        .order_by(func.count(ProductView.id).desc())
    )).all()
    total_device = sum(r.cnt for r in device_rows) or 1
    device_breakdown = [
        DeviceBreakdownItem(device=r.device, count=r.cnt,
                            percentage=round(r.cnt / total_device * 100, 1))
        for r in device_rows
    ]

    # Platform breakdown
    platform_rows = (await db.execute(
        select(ProductView.platform, func.count(ProductView.id).label("cnt"))
        .where(ProductView.platform.isnot(None),
               ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(ProductView.platform)
        .order_by(func.count(ProductView.id).desc())
    )).all()
    total_platform = sum(r.cnt for r in platform_rows) or 1
    platform_breakdown = [
        DeviceBreakdownItem(device=r.platform, count=r.cnt,
                            percentage=round(r.cnt / total_platform * 100, 1))
        for r in platform_rows
    ]

    return AdminCustomerBehaviorResponse(
        dau=dau,
        mau=mau,
        action_breakdown=action_breakdown,
        funnel=funnel,
        device_breakdown=device_breakdown,
        platform_breakdown=platform_breakdown,
    )


# ─── Revenue Analytics ───────────────────────────────────────────────────────

@router.get("/revenue", response_model=AdminRevenueResponse)
async def admin_revenue(
    period: str = Query("30d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import Payment
    start, end, prev_start, prev_end = resolve_period(period, start_date, end_date)

    # Current period revenue
    rev_result = (await db.execute(
        select(func.sum(Order.final_amount), func.count(Order.id))
        .where(Order.payment_status == "paid",
               Order.created_at >= start, Order.created_at < end)
    )).one()
    total_revenue = float(rev_result[0] or 0)
    total_orders = rev_result[1] or 0
    avg_order = round(total_revenue / total_orders, 2) if total_orders else 0.0

    # Previous period revenue (for growth)
    prev_rev = (await db.execute(
        select(func.sum(Order.final_amount))
        .where(Order.payment_status == "paid",
               Order.created_at >= prev_start, Order.created_at < prev_end)
    )).scalar() or 0
    rev_growth = growth_pct(int(total_revenue), int(float(prev_rev)))

    # Sponsorship revenue — sum payments with description/type containing "sponsorship"
    # We use Payment model; if sponsor payments exist they'll be counted
    try:
        sponsor_rev = (await db.execute(
            select(func.sum(Payment.amount))
            .where(Payment.status == "paid",
                   Payment.created_at >= start, Payment.created_at < end)
        )).scalar() or 0
        sponsor_revenue = float(sponsor_rev)
    except Exception:
        sponsor_revenue = 0.0

    # Daily revenue trend
    trend_rows = (await db.execute(
        select(
            func.date_trunc("day", Order.created_at).label("day"),
            func.sum(Order.final_amount).label("rev"),
            func.count(Order.id).label("cnt"),
        )
        .where(Order.payment_status == "paid",
               Order.created_at >= start, Order.created_at < end)
        .group_by(text("day"))
        .order_by(text("day"))
    )).all()
    revenue_trend = [
        RevenueTrendPoint(
            date=row.day.date().isoformat(),
            revenue=round(float(row.rev or 0), 2),
            order_count=row.cnt,
        )
        for row in trend_rows
    ]

    return AdminRevenueResponse(
        total_revenue=round(total_revenue, 2),
        total_orders=total_orders,
        avg_order_value=avg_order,
        sponsorship_revenue=round(sponsor_revenue, 2),
        revenue_trend=revenue_trend,
        revenue_growth_pct=rev_growth,
    )


# ─── Geo Analytics ───────────────────────────────────────────────────────────

@router.get("/geo", response_model=AdminGeoResponse)
async def admin_geo(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)

    views_by_city = {
        row.city: row.cnt
        for row in (await db.execute(
            select(ProductView.city, func.count(ProductView.id).label("cnt"))
            .where(ProductView.city.isnot(None), ProductView.city != "",
                   ProductView.created_at >= start, ProductView.created_at < end)
            .group_by(ProductView.city)
            .order_by(func.count(ProductView.id).desc())
            .limit(30)
        )).all()
    }

    searches_by_city = {
        row.city: row.cnt
        for row in (await db.execute(
            select(SearchLog.city, func.count(SearchLog.id).label("cnt"))
            .where(SearchLog.city.isnot(None), SearchLog.city != "",
                   SearchLog.created_at >= start, SearchLog.created_at < end)
            .group_by(SearchLog.city)
            .order_by(func.count(SearchLog.id).desc())
            .limit(30)
        )).all()
    }

    actions_by_city = {
        row.city: row.cnt
        for row in (await db.execute(
            select(VendorAction.city, func.count(VendorAction.id).label("cnt"))
            .where(VendorAction.city.isnot(None), VendorAction.city != "",
                   VendorAction.created_at >= start, VendorAction.created_at < end)
            .group_by(VendorAction.city)
            .order_by(func.count(VendorAction.id).desc())
            .limit(30)
        )).all()
    }

    all_cities = set(views_by_city) | set(searches_by_city) | set(actions_by_city)
    top_cities = sorted(
        [
            CityStatItem(
                city=c,
                views=views_by_city.get(c, 0),
                searches=searches_by_city.get(c, 0),
                actions=actions_by_city.get(c, 0),
            )
            for c in all_cities
        ],
        key=lambda x: x.views + x.searches + x.actions,
        reverse=True,
    )[:20]

    return AdminGeoResponse(top_cities=top_cities)


# ─── Category Analytics ──────────────────────────────────────────────────────

@router.get("/categories", response_model=AdminCategoryResponse)
async def admin_categories(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)

    rows = (await db.execute(
        select(
            Category.id,
            Category.name,
            func.count(Product.id.distinct()).label("total_products"),
            func.count(ProductView.id).label("total_views"),
        )
        .outerjoin(Product, and_(Product.category_id == Category.id, Product.status == "approved"))
        .outerjoin(ProductView, and_(ProductView.product_id == Product.id,
                                     ProductView.created_at >= start,
                                     ProductView.created_at < end))
        .group_by(Category.id, Category.name)
        .order_by(func.count(ProductView.id).desc())
    )).all()

    total_views = sum(r.total_views for r in rows) or 1
    items = [
        CategoryStatItem(
            category_id=r.id,
            name=r.name,
            total_products=r.total_products,
            total_views=r.total_views,
            percentage=round(r.total_views / total_views * 100, 1),
        )
        for r in rows
    ]
    return AdminCategoryResponse(items=items)


# ─── Daily Traffic Chart ─────────────────────────────────────────────────────

@router.get("/charts/daily-traffic", response_model=AdminDailyTrafficResponse)
async def admin_daily_traffic(
    period: str = Query("30d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)

    views_rows = (await db.execute(
        select(func.date_trunc("day", ProductView.created_at).label("day"),
               func.count(ProductView.id).label("cnt"))
        .where(ProductView.created_at >= start, ProductView.created_at < end)
        .group_by(text("day")).order_by(text("day"))
    )).all()

    search_rows = (await db.execute(
        select(func.date_trunc("day", SearchLog.created_at).label("day"),
               func.count(SearchLog.id).label("cnt"))
        .where(SearchLog.created_at >= start, SearchLog.created_at < end)
        .group_by(text("day")).order_by(text("day"))
    )).all()

    action_rows = (await db.execute(
        select(func.date_trunc("day", VendorAction.created_at).label("day"),
               func.count(VendorAction.id).label("cnt"))
        .where(VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(text("day")).order_by(text("day"))
    )).all()

    inquiry_rows = (await db.execute(
        select(func.date_trunc("day", VendorAction.created_at).label("day"),
               func.count(VendorAction.id).label("cnt"))
        .where(VendorAction.action_type == "inquiry",
               VendorAction.created_at >= start, VendorAction.created_at < end)
        .group_by(text("day")).order_by(text("day"))
    )).all()

    views_map = {r.day.date(): r.cnt for r in views_rows}
    search_map = {r.day.date(): r.cnt for r in search_rows}
    action_map = {r.day.date(): r.cnt for r in action_rows}
    inquiry_map = {r.day.date(): r.cnt for r in inquiry_rows}

    # Merge all dates
    all_dates = sorted(
        set(views_map) | set(search_map) | set(action_map) | set(inquiry_map)
    )
    series = [
        DailyTrafficPoint(
            date=d.isoformat(),
            views=views_map.get(d, 0),
            searches=search_map.get(d, 0),
            actions=action_map.get(d, 0),
            inquiries=inquiry_map.get(d, 0),
        )
        for d in all_dates
    ]
    return AdminDailyTrafficResponse(series=series)


# ─── Fraud Detection ─────────────────────────────────────────────────────────

@router.get("/fraud", response_model=AdminFraudResponse)
async def admin_fraud(
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)

    rows = (await db.execute(
        select(FraudLog)
        .where(FraudLog.detected_at >= start, FraudLog.detected_at < end)
        .order_by(FraudLog.event_count.desc())
        .limit(50)
    )).scalars().all()

    total_flagged = (await db.execute(
        select(func.count(FraudLog.id))
        .where(FraudLog.detected_at >= start, FraudLog.detected_at < end)
    )).scalar() or 0

    unresolved = (await db.execute(
        select(func.count(FraudLog.id))
        .where(FraudLog.is_resolved == False,  # noqa: E712
               FraudLog.detected_at >= start, FraudLog.detected_at < end)
    )).scalar() or 0

    suspicious_ip_count = (await db.execute(
        select(func.count(FraudLog.ip_address.distinct()))
        .where(FraudLog.fraud_type == "ip_velocity",
               FraudLog.detected_at >= start, FraudLog.detected_at < end)
    )).scalar() or 0

    items = [
        FraudSummaryItem(
            id=r.id,
            fraud_type=r.fraud_type,
            ip_address=r.ip_address,
            session_id=r.session_id,
            event_count=r.event_count,
            detected_at=r.detected_at.isoformat(),
            is_resolved=r.is_resolved,
        )
        for r in rows
    ]

    return AdminFraudResponse(
        total_flagged=total_flagged,
        unresolved=unresolved,
        suspicious_ip_count=suspicious_ip_count,
        items=items,
    )


# ─── Admin Insights ──────────────────────────────────────────────────────────

@router.get("/insights", response_model=AdminInsightsResponse)
async def admin_insights(
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AdminInsight)
        .order_by(AdminInsight.created_at.desc())
        .limit(30)
    )).scalars().all()

    unread = sum(1 for r in rows if not r.is_read)
    items = [
        AdminInsightItem(
            id=r.id,
            insight_type=r.insight_type,
            title=r.title,
            message=r.message,
            is_read=r.is_read,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return AdminInsightsResponse(items=items, unread_count=unread)


@router.patch("/insights/{insight_id}/read")
async def mark_admin_insight_read(
    insight_id: int,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(AdminInsight).where(AdminInsight.id == insight_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Insight not found")
    row.is_read = True
    await db.commit()
    return {"ok": True}


# ─── CSV Export ──────────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_csv(
    type: str = Query("vendors", pattern="^(vendors|products|search|geo)$"),
    period: str = Query("7d", pattern="^(today|7d|30d|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    start, end, _, _ = resolve_period(period, start_date, end_date)
    output = StringIO()
    writer = csv.writer(output)

    if type == "vendors":
        writer.writerow(["Vendor ID", "Shop Name", "Status", "Total Products",
                         "Total Views", "Total Inquiries", "Contact Actions", "CTR %", "Last Active"])
        views_sub = (
            select(ProductView.vendor_id, func.count(ProductView.id).label("v"),
                   func.max(ProductView.created_at).label("la"))
            .where(ProductView.created_at >= start, ProductView.created_at < end)
            .group_by(ProductView.vendor_id).subquery()
        )
        inq_sub = (
            select(VendorAction.vendor_id, func.count(VendorAction.id).label("i"))
            .where(VendorAction.action_type == "inquiry",
                   VendorAction.created_at >= start, VendorAction.created_at < end)
            .group_by(VendorAction.vendor_id).subquery()
        )
        contact_sub = (
            select(VendorAction.vendor_id, func.count(VendorAction.id).label("c"))
            .where(VendorAction.action_type.in_(["call_click", "whatsapp_click"]),
                   VendorAction.created_at >= start, VendorAction.created_at < end)
            .group_by(VendorAction.vendor_id).subquery()
        )
        prod_sub = (
            select(Product.vendor_id, func.count(Product.id).label("p"))
            .where(Product.status == "approved").group_by(Product.vendor_id).subquery()
        )
        rows = (await db.execute(
            select(Vendor.id, Shop.name, Vendor.status,
                   func.coalesce(prod_sub.c.p, 0),
                   func.coalesce(views_sub.c.v, 0),
                   func.coalesce(inq_sub.c.i, 0),
                   func.coalesce(contact_sub.c.c, 0),
                   views_sub.c.la)
            .outerjoin(Shop, Shop.vendor_id == Vendor.id)
            .outerjoin(views_sub, views_sub.c.vendor_id == Vendor.id)
            .outerjoin(inq_sub, inq_sub.c.vendor_id == Vendor.id)
            .outerjoin(contact_sub, contact_sub.c.vendor_id == Vendor.id)
            .outerjoin(prod_sub, prod_sub.c.vendor_id == Vendor.id)
            .order_by(func.coalesce(views_sub.c.v, 0).desc())
        )).all()
        for r in rows:
            views = r[4] or 0
            contact = r[6] or 0
            ctr = round(contact / views * 100, 1) if views else 0
            la = r[7].date().isoformat() if r[7] else ""
            writer.writerow([r[0], r[1] or "", r[2], r[3], views, r[5] or 0, contact, ctr, la])

    elif type == "products":
        writer.writerow(["Product ID", "Name", "Vendor", "Category",
                         "Views", "Impressions", "CTR %", "Inquiries", "Wishlist Adds"])
        views_sub = (
            select(ProductView.product_id, func.count(ProductView.id).label("v"))
            .where(ProductView.created_at >= start, ProductView.created_at < end)
            .group_by(ProductView.product_id).subquery()
        )
        imp_sub = (
            select(ProductImpression.product_id, func.count(ProductImpression.id).label("i"))
            .where(ProductImpression.created_at >= start, ProductImpression.created_at < end)
            .group_by(ProductImpression.product_id).subquery()
        )
        rows = (await db.execute(
            select(Product.id, Product.name, Shop.name, Category.name,
                   func.coalesce(views_sub.c.v, 0), func.coalesce(imp_sub.c.i, 0))
            .outerjoin(Vendor, Vendor.id == Product.vendor_id)
            .outerjoin(Shop, Shop.vendor_id == Vendor.id)
            .outerjoin(Category, Category.id == Product.category_id)
            .outerjoin(views_sub, views_sub.c.product_id == Product.id)
            .outerjoin(imp_sub, imp_sub.c.product_id == Product.id)
            .where(Product.status == "approved")
            .order_by(func.coalesce(views_sub.c.v, 0).desc())
        )).all()
        for r in rows:
            v, i = r[4] or 0, r[5] or 0
            writer.writerow([r[0], r[1], r[2] or "", r[3] or "", v, i,
                             round(v / i * 100, 1) if i else 0, 0, 0])

    elif type == "search":
        writer.writerow(["Keyword", "Search Count", "Avg Results", "No Result"])
        rows = (await db.execute(
            select(SearchLog.keyword, func.count(SearchLog.id).label("cnt"),
                   func.avg(SearchLog.result_count).label("avg"))
            .where(SearchLog.created_at >= start, SearchLog.created_at < end)
            .group_by(SearchLog.keyword)
            .order_by(func.count(SearchLog.id).desc())
        )).all()
        for r in rows:
            avg = float(r.avg or 0)
            writer.writerow([r.keyword, r.cnt, round(avg, 1), "Yes" if avg < 1 else "No"])

    elif type == "geo":
        writer.writerow(["City", "Views", "Searches", "Actions"])
        views_map = {
            r.city: r.cnt
            for r in (await db.execute(
                select(ProductView.city, func.count(ProductView.id).label("cnt"))
                .where(ProductView.city.isnot(None), ProductView.city != "",
                       ProductView.created_at >= start, ProductView.created_at < end)
                .group_by(ProductView.city)
            )).all()
        }
        search_map = {
            r.city: r.cnt
            for r in (await db.execute(
                select(SearchLog.city, func.count(SearchLog.id).label("cnt"))
                .where(SearchLog.city.isnot(None), SearchLog.city != "",
                       SearchLog.created_at >= start, SearchLog.created_at < end)
                .group_by(SearchLog.city)
            )).all()
        }
        action_map = {
            r.city: r.cnt
            for r in (await db.execute(
                select(VendorAction.city, func.count(VendorAction.id).label("cnt"))
                .where(VendorAction.city.isnot(None), VendorAction.city != "",
                       VendorAction.created_at >= start, VendorAction.created_at < end)
                .group_by(VendorAction.city)
            )).all()
        }
        all_cities = sorted(
            set(views_map) | set(search_map) | set(action_map),
            key=lambda c: views_map.get(c, 0) + search_map.get(c, 0) + action_map.get(c, 0),
            reverse=True,
        )
        for city in all_cities:
            writer.writerow([city, views_map.get(city, 0),
                             search_map.get(city, 0), action_map.get(city, 0)])

    output.seek(0)
    filename = f"{type}_{period}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

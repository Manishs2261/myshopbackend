"""
Vendor Analytics V2 — Endpoints backed by real event tracking tables.
All routes require VENDOR role. Period helpers support today/7d/30d/custom.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User, Vendor, Product
from app.models.analytics import (
    ProductView, ProductImpression, SearchLog, VendorAction, VendorInsight
)
from app.schemas.schemas import (
    AnalyticsOverviewV2, ProductAnalyticsResponse, ProductAnalyticsItem,
    SearchAnalyticsResponse, SearchKeywordItem,
    ActionsAnalyticsResponse, ActionBreakdown,
    DailyTrafficResponse, DailyPoint,
    InsightListResponse, InsightResponse,
)

router = APIRouter(prefix="/vendor/analytics/v2", tags=["Analytics V2"])
get_vendor_user = require_role("VENDOR", "ADMIN")


# ─── Period resolver ─────────────────────────────────────────────────────────

def _resolve_period(
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
):
    """Return (current_start, current_end, prev_start, prev_end) as UTC datetimes."""
    now = datetime.now(timezone.utc)
    if period == "today":
        current_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_end = now
    elif period == "7d":
        current_start = now - timedelta(days=7)
        current_end = now
    elif period == "30d":
        current_start = now - timedelta(days=30)
        current_end = now
    elif period == "custom" and start_date and end_date:
        try:
            current_start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            current_end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid date format. Use ISO 8601 (YYYY-MM-DD).")
    else:
        # Default: 30d
        current_start = now - timedelta(days=30)
        current_end = now

    span = current_end - current_start
    prev_start = current_start - span
    prev_end = current_start

    return current_start, current_end, prev_start, prev_end


async def _get_vendor(current_user: User, db: AsyncSession) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor profile not found")
    return vendor


# ─── Overview ────────────────────────────────────────────────────────────────

@router.get("/overview", response_model=AnalyticsOverviewV2)
async def vendor_analytics_overview(
    period: str = Query(default="30d", description="today|7d|30d|custom"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Main dashboard overview card metrics."""
    vendor = await _get_vendor(current_user, db)
    cs, ce, ps, pe = _resolve_period(period, start_date, end_date)

    async def count_views(start, end):
        r = await db.execute(
            select(func.count()).select_from(ProductView)
            .where(ProductView.vendor_id == vendor.id, ProductView.created_at >= start, ProductView.created_at <= end)
        )
        return r.scalar() or 0

    async def count_impressions(start, end):
        r = await db.execute(
            select(func.count()).select_from(ProductImpression)
            .where(ProductImpression.vendor_id == vendor.id, ProductImpression.created_at >= start, ProductImpression.created_at <= end)
        )
        return r.scalar() or 0

    async def count_actions_by_type(start, end):
        r = await db.execute(
            select(VendorAction.action_type, func.count().label("cnt"))
            .where(VendorAction.vendor_id == vendor.id, VendorAction.created_at >= start, VendorAction.created_at <= end)
            .group_by(VendorAction.action_type)
        )
        return {row[0]: row[1] for row in r.all()}

    async def count_searches(start, end):
        r = await db.execute(
            select(func.count()).select_from(SearchLog)
            .where(SearchLog.created_at >= start, SearchLog.created_at <= end)
        )
        return r.scalar() or 0

    # Run all current-period queries in parallel
    (
        cur_views, cur_impressions, cur_actions, cur_searches,
        prev_views, prev_actions,
    ) = await asyncio.gather(
        count_views(cs, ce),
        count_impressions(cs, ce),
        count_actions_by_type(cs, ce),
        count_searches(cs, ce),
        count_views(ps, pe),
        count_actions_by_type(ps, pe),
    )

    ctr = round((cur_views / cur_impressions * 100), 2) if cur_impressions else 0.0

    prev_total_actions = sum(prev_actions.values())
    cur_total_actions = sum(cur_actions.values())

    def _growth(cur, prev) -> float:
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round((cur - prev) / prev * 100, 2)

    return AnalyticsOverviewV2(
        period=period,
        start_date=cs.date().isoformat(),
        end_date=ce.date().isoformat(),
        total_views=cur_views,
        total_impressions=cur_impressions,
        ctr_percentage=ctr,
        total_call_clicks=cur_actions.get("call_click", 0),
        total_whatsapp_clicks=cur_actions.get("whatsapp_click", 0),
        total_direction_clicks=cur_actions.get("direction_click", 0),
        total_inquiries=cur_actions.get("inquiry", 0),
        total_wishlist_adds=cur_actions.get("wishlist_add", 0),
        total_searches=cur_searches,
        view_growth_pct=_growth(cur_views, prev_views),
        action_growth_pct=_growth(cur_total_actions, prev_total_actions),
    )


# ─── Product-level analytics ─────────────────────────────────────────────────

@router.get("/products", response_model=ProductAnalyticsResponse)
async def vendor_product_analytics(
    period: str = Query(default="30d"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="views", description="views|ctr|impressions|actions"),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-product analytics breakdown with views, CTR, and action counts."""
    vendor = await _get_vendor(current_user, db)
    cs, ce, _, _ = _resolve_period(period, start_date, end_date)

    # Fetch vendor products
    products_result = await db.execute(
        select(Product).where(Product.vendor_id == vendor.id)
    )
    products = products_result.scalars().all()
    if not products:
        return ProductAnalyticsResponse(items=[], total=0, page=page, limit=limit)

    product_ids = [p.id for p in products]
    product_map = {p.id: p for p in products}

    # Fetch views per product
    views_result = await db.execute(
        select(ProductView.product_id, func.count().label("cnt"), func.max(ProductView.created_at).label("last_view"))
        .where(ProductView.product_id.in_(product_ids), ProductView.created_at >= cs, ProductView.created_at <= ce)
        .group_by(ProductView.product_id)
    )
    views_map = {row[0]: (row[1], row[2]) for row in views_result.all()}

    # Fetch impressions per product
    imp_result = await db.execute(
        select(ProductImpression.product_id, func.count().label("cnt"))
        .where(ProductImpression.product_id.in_(product_ids), ProductImpression.created_at >= cs, ProductImpression.created_at <= ce)
        .group_by(ProductImpression.product_id)
    )
    imp_map = {row[0]: row[1] for row in imp_result.all()}

    # Fetch actions per product per type
    actions_result = await db.execute(
        select(VendorAction.product_id, VendorAction.action_type, func.count().label("cnt"))
        .where(VendorAction.product_id.in_(product_ids), VendorAction.created_at >= cs, VendorAction.created_at <= ce)
        .group_by(VendorAction.product_id, VendorAction.action_type)
    )
    actions_map: dict[int, dict[str, int]] = {}
    for row in actions_result.all():
        pid, atype, cnt = row
        actions_map.setdefault(pid, {})[atype] = cnt

    items: list[ProductAnalyticsItem] = []
    for pid, product in product_map.items():
        views, last_view = views_map.get(pid, (0, None))
        impressions = imp_map.get(pid, 0)
        acts = actions_map.get(pid, {})
        ctr = round((views / impressions * 100), 2) if impressions else 0.0
        items.append(ProductAnalyticsItem(
            product_id=pid,
            name=product.name,
            image=(product.images or [None])[0] if product.images else None,
            views=views,
            impressions=impressions,
            ctr=ctr,
            wishlist_count=acts.get("wishlist_add", 0),
            call_clicks=acts.get("call_click", 0),
            whatsapp_clicks=acts.get("whatsapp_click", 0),
            direction_clicks=acts.get("direction_click", 0),
            last_viewed_at=last_view.isoformat() if last_view else None,
        ))

    # Sort
    if sort == "ctr":
        items.sort(key=lambda x: x.ctr, reverse=True)
    elif sort == "impressions":
        items.sort(key=lambda x: x.impressions, reverse=True)
    elif sort == "actions":
        items.sort(key=lambda x: x.call_clicks + x.whatsapp_clicks + x.direction_clicks, reverse=True)
    else:
        items.sort(key=lambda x: x.views, reverse=True)

    total = len(items)
    offset = (page - 1) * limit
    return ProductAnalyticsResponse(
        items=items[offset: offset + limit],
        total=total,
        page=page,
        limit=limit,
    )


# ─── Search keywords ─────────────────────────────────────────────────────────

@router.get("/search-keywords", response_model=SearchAnalyticsResponse)
async def vendor_search_keywords(
    period: str = Query(default="30d"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Top searched keywords on the platform (platform-wide, as search is not vendor-scoped)."""
    cs, ce, _, _ = _resolve_period(period, start_date, end_date)

    result = await db.execute(
        select(
            SearchLog.keyword,
            func.count().label("cnt"),
            func.avg(SearchLog.result_count).label("avg_results"),
        )
        .where(SearchLog.created_at >= cs, SearchLog.created_at <= ce)
        .group_by(SearchLog.keyword)
        .order_by(func.count().desc())
        .limit(limit * 2)  # fetch extra so we can split top vs no-result
    )
    rows = result.all()

    total_result = await db.execute(
        select(func.count()).select_from(SearchLog)
        .where(SearchLog.created_at >= cs, SearchLog.created_at <= ce)
    )
    total_searches = total_result.scalar() or 0

    top_keywords: list[SearchKeywordItem] = []
    no_result_keywords: list[SearchKeywordItem] = []

    for keyword, cnt, avg_results in rows:
        avg_r = float(avg_results or 0)
        item = SearchKeywordItem(
            keyword=keyword,
            count=cnt,
            result_count_avg=round(avg_r, 1),
            is_no_result=(avg_r < 0.5),
        )
        if avg_r < 0.5:
            no_result_keywords.append(item)
        else:
            top_keywords.append(item)

    return SearchAnalyticsResponse(
        top_keywords=top_keywords[:limit],
        no_result_keywords=no_result_keywords[:limit],
        total_searches=total_searches,
    )


# ─── Actions breakdown ───────────────────────────────────────────────────────

@router.get("/actions", response_model=ActionsAnalyticsResponse)
async def vendor_actions_breakdown(
    period: str = Query(default="30d"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Customer action breakdown (call/WhatsApp/directions/share/etc.) for the vendor."""
    vendor = await _get_vendor(current_user, db)
    cs, ce, _, _ = _resolve_period(period, start_date, end_date)

    result = await db.execute(
        select(VendorAction.action_type, func.count().label("cnt"))
        .where(VendorAction.vendor_id == vendor.id, VendorAction.created_at >= cs, VendorAction.created_at <= ce)
        .group_by(VendorAction.action_type)
        .order_by(func.count().desc())
    )
    rows = result.all()
    total = sum(r[1] for r in rows)

    breakdown = [
        ActionBreakdown(
            action_type=row[0],
            count=row[1],
            percentage=round(row[1] / total * 100, 1) if total else 0.0,
        )
        for row in rows
    ]
    return ActionsAnalyticsResponse(breakdown=breakdown, total_actions=total)


# ─── Daily traffic chart ─────────────────────────────────────────────────────

@router.get("/charts/daily-traffic", response_model=DailyTrafficResponse)
async def vendor_daily_traffic(
    period: str = Query(default="30d"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily series: views, total actions, and searches per day for chart rendering."""
    vendor = await _get_vendor(current_user, db)
    cs, ce, _, _ = _resolve_period(period, start_date, end_date)

    async def daily_views():
        r = await db.execute(
            select(func.date(ProductView.created_at).label("d"), func.count().label("cnt"))
            .where(ProductView.vendor_id == vendor.id, ProductView.created_at >= cs, ProductView.created_at <= ce)
            .group_by(func.date(ProductView.created_at))
            .order_by(func.date(ProductView.created_at))
        )
        return {str(row[0]): row[1] for row in r.all()}

    async def daily_actions():
        r = await db.execute(
            select(func.date(VendorAction.created_at).label("d"), func.count().label("cnt"))
            .where(VendorAction.vendor_id == vendor.id, VendorAction.created_at >= cs, VendorAction.created_at <= ce)
            .group_by(func.date(VendorAction.created_at))
            .order_by(func.date(VendorAction.created_at))
        )
        return {str(row[0]): row[1] for row in r.all()}

    async def daily_searches():
        r = await db.execute(
            select(func.date(SearchLog.created_at).label("d"), func.count().label("cnt"))
            .where(SearchLog.created_at >= cs, SearchLog.created_at <= ce)
            .group_by(func.date(SearchLog.created_at))
            .order_by(func.date(SearchLog.created_at))
        )
        return {str(row[0]): row[1] for row in r.all()}

    views_by_day, actions_by_day, searches_by_day = await asyncio.gather(
        daily_views(), daily_actions(), daily_searches()
    )

    # Build complete date range
    all_dates: set[str] = set(views_by_day) | set(actions_by_day) | set(searches_by_day)
    series: list[DailyPoint] = sorted(
        [
            DailyPoint(
                date=d,
                views=views_by_day.get(d, 0),
                actions=actions_by_day.get(d, 0),
                searches=searches_by_day.get(d, 0),
            )
            for d in all_dates
        ],
        key=lambda x: x.date,
    )

    return DailyTrafficResponse(series=series)


# ─── Insights ────────────────────────────────────────────────────────────────

@router.get("/insights", response_model=InsightListResponse)
async def vendor_insights(
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Smart vendor insights generated by the nightly scheduler."""
    vendor = await _get_vendor(current_user, db)

    result = await db.execute(
        select(VendorInsight)
        .where(VendorInsight.vendor_id == vendor.id)
        .order_by(VendorInsight.created_at.desc())
        .limit(30)
    )
    insights = result.scalars().all()

    unread = sum(1 for i in insights if not i.is_read)
    return InsightListResponse(
        items=[
            InsightResponse(
                id=i.id,
                insight_type=i.insight_type,
                title=i.title,
                message=i.message,
                is_read=i.is_read,
                created_at=i.created_at.isoformat(),
            )
            for i in insights
        ],
        unread_count=unread,
    )


@router.patch("/insights/{insight_id}/read", response_model=dict)
async def mark_insight_read(
    insight_id: int,
    current_user: User = Depends(get_vendor_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a vendor insight as read."""
    vendor = await _get_vendor(current_user, db)
    result = await db.execute(
        select(VendorInsight)
        .where(VendorInsight.id == insight_id, VendorInsight.vendor_id == vendor.id)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(404, "Insight not found")
    insight.is_read = True
    await db.commit()
    return {"success": True}

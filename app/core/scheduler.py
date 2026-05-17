"""
APScheduler configuration for nightly analytics aggregation and insight generation.
Jobs run inside the FastAPI process on a cron schedule.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, func, text

log = logging.getLogger("localshop.scheduler")
scheduler = AsyncIOScheduler(timezone="UTC")


async def _get_session():
    """Get a fresh DB session for background jobs."""
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal()


async def aggregate_daily_summaries() -> None:
    """
    Runs at 01:00 UTC daily.
    Computes yesterday's analytics per vendor and upserts into analytics_summary.
    """
    from app.models.analytics import (
        ProductView, ProductImpression, VendorAction, AnalyticsSummary
    )
    from app.models.user import Vendor
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    yesterday = date.today() - timedelta(days=1)
    day_start = datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    log.info(f"[scheduler] Aggregating daily summaries for {yesterday}")

    async with await _get_session() as db:
        try:
            # Get all vendors that had any activity yesterday
            active_vendors_result = await db.execute(
                select(ProductView.vendor_id.distinct())
                .where(ProductView.created_at >= day_start, ProductView.created_at < day_end)
                .union(
                    select(VendorAction.vendor_id.distinct())
                    .where(VendorAction.created_at >= day_start, VendorAction.created_at < day_end)
                )
            )
            vendor_ids = [row[0] for row in active_vendors_result.all()]

            if not vendor_ids:
                log.info("[scheduler] No vendor activity yesterday, skipping aggregation.")
                return

            for vendor_id in vendor_ids:
                views_r = await db.execute(
                    select(func.count()).select_from(ProductView)
                    .where(ProductView.vendor_id == vendor_id, ProductView.created_at >= day_start, ProductView.created_at < day_end)
                )
                total_views = views_r.scalar() or 0

                imp_r = await db.execute(
                    select(func.count()).select_from(ProductImpression)
                    .where(ProductImpression.vendor_id == vendor_id, ProductImpression.created_at >= day_start, ProductImpression.created_at < day_end)
                )
                total_impressions = imp_r.scalar() or 0

                actions_r = await db.execute(
                    select(VendorAction.action_type, func.count().label("cnt"))
                    .where(VendorAction.vendor_id == vendor_id, VendorAction.created_at >= day_start, VendorAction.created_at < day_end)
                    .group_by(VendorAction.action_type)
                )
                actions = {row[0]: row[1] for row in actions_r.all()}

                stmt = pg_insert(AnalyticsSummary).values(
                    vendor_id=vendor_id,
                    date=yesterday,
                    total_views=total_views,
                    total_impressions=total_impressions,
                    total_call_clicks=actions.get("call_click", 0),
                    total_whatsapp_clicks=actions.get("whatsapp_click", 0),
                    total_direction_clicks=actions.get("direction_click", 0),
                    total_inquiries=actions.get("inquiry", 0),
                    total_wishlist_adds=actions.get("wishlist_add", 0),
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_analytics_summary_vendor_date",
                    set_=dict(
                        total_views=stmt.excluded.total_views,
                        total_impressions=stmt.excluded.total_impressions,
                        total_call_clicks=stmt.excluded.total_call_clicks,
                        total_whatsapp_clicks=stmt.excluded.total_whatsapp_clicks,
                        total_direction_clicks=stmt.excluded.total_direction_clicks,
                        total_inquiries=stmt.excluded.total_inquiries,
                        total_wishlist_adds=stmt.excluded.total_wishlist_adds,
                    ),
                )
                await db.execute(stmt)

            await db.commit()
            log.info(f"[scheduler] Aggregated summaries for {len(vendor_ids)} vendors.")
        except Exception as e:
            log.error(f"[scheduler] aggregate_daily_summaries failed: {e}", exc_info=True)
            await db.rollback()


async def generate_vendor_insights() -> None:
    """
    Runs at 02:00 UTC daily.
    Generates smart insight notifications for vendors based on recent trends.
    """
    from app.models.analytics import ProductView, VendorAction, VendorInsight
    from app.models.user import Vendor, Product

    now = datetime.now(timezone.utc)
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)

    log.info("[scheduler] Generating vendor insights...")

    async with await _get_session() as db:
        try:
            vendors_result = await db.execute(select(Vendor.id))
            vendor_ids = [row[0] for row in vendors_result.all()]

            new_insights: list[VendorInsight] = []

            for vendor_id in vendor_ids:
                # --- Insight 1: View growth ---
                this_week_views_r = await db.execute(
                    select(func.count()).select_from(ProductView)
                    .where(ProductView.vendor_id == vendor_id, ProductView.created_at >= this_week_start)
                )
                this_week_views = this_week_views_r.scalar() or 0

                last_week_views_r = await db.execute(
                    select(func.count()).select_from(ProductView)
                    .where(
                        ProductView.vendor_id == vendor_id,
                        ProductView.created_at >= last_week_start,
                        ProductView.created_at < this_week_start,
                    )
                )
                last_week_views = last_week_views_r.scalar() or 0

                if last_week_views > 0 and this_week_views > last_week_views:
                    growth_pct = round((this_week_views - last_week_views) / last_week_views * 100, 1)
                    if growth_pct >= 20:
                        new_insights.append(VendorInsight(
                            vendor_id=vendor_id,
                            insight_type="growth",
                            title="Your shop is getting more attention!",
                            message=f"Your product views increased by {growth_pct}% this week compared to last week. Keep it up!",
                            extra_data=json.dumps({"growth_pct": growth_pct, "this_week": this_week_views, "last_week": last_week_views}),
                        ))

                # --- Insight 2: Low CTR warning ---
                impressions_r = await db.execute(
                    select(func.count()).select_from(ProductView)
                    .where(ProductView.vendor_id == vendor_id, ProductView.created_at >= this_week_start)
                )
                views_count = impressions_r.scalar() or 0

                # We approximate CTR via views vs actions; if views > 50 but actions < 2% of views
                actions_r = await db.execute(
                    select(func.count()).select_from(VendorAction)
                    .where(
                        VendorAction.vendor_id == vendor_id,
                        VendorAction.action_type.in_(["call_click", "whatsapp_click", "direction_click"]),
                        VendorAction.created_at >= this_week_start,
                    )
                )
                contact_actions = actions_r.scalar() or 0

                if views_count >= 50 and contact_actions < views_count * 0.02:
                    new_insights.append(VendorInsight(
                        vendor_id=vendor_id,
                        insight_type="low_ctr",
                        title="Improve your contact conversion rate",
                        message="Customers are viewing your products but not reaching out. Try adding clearer contact info, better product photos, or a competitive price.",
                        extra_data=json.dumps({"views": views_count, "contact_actions": contact_actions}),
                    ))

                # --- Insight 3: Out-of-stock products with recent views ---
                oos_result = await db.execute(
                    select(Product.name)
                    .join(ProductView, ProductView.product_id == Product.id)
                    .where(
                        Product.vendor_id == vendor_id,
                        Product.stock == 0,
                        ProductView.created_at >= this_week_start,
                    )
                    .distinct()
                    .limit(3)
                )
                oos_products = [row[0] for row in oos_result.all()]
                if oos_products:
                    names = ", ".join(oos_products)
                    new_insights.append(VendorInsight(
                        vendor_id=vendor_id,
                        insight_type="stock_alert",
                        title="Out-of-stock products are getting views",
                        message=f"The following products are out of stock but still receiving views: {names}. Consider restocking.",
                        extra_data=json.dumps({"products": oos_products}),
                    ))

            if new_insights:
                db.add_all(new_insights)
                await db.commit()
                log.info(f"[scheduler] Created {len(new_insights)} vendor insights.")
            else:
                log.info("[scheduler] No new insights generated.")

        except Exception as e:
            log.error(f"[scheduler] generate_vendor_insights failed: {e}", exc_info=True)
            await db.rollback()


async def generate_admin_insights() -> None:
    """
    Runs at 03:00 UTC daily.
    Generates platform-wide smart insights for the admin dashboard.
    """
    from app.models.analytics import ProductView, SearchLog, VendorAction, AdminInsight
    from app.models.user import Vendor, Product, Category

    now = datetime.now(timezone.utc)
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    log.info("[scheduler] Generating admin platform insights...")

    async with await _get_session() as db:
        try:
            new_insights: list[AdminInsight] = []

            # --- Insight 1: Platform view growth ---
            this_week_views = (await db.execute(
                select(func.count()).select_from(ProductView)
                .where(ProductView.created_at >= this_week_start)
            )).scalar() or 0

            last_week_views = (await db.execute(
                select(func.count()).select_from(ProductView)
                .where(ProductView.created_at >= last_week_start,
                       ProductView.created_at < this_week_start)
            )).scalar() or 0

            if last_week_views > 0:
                growth = round((this_week_views - last_week_views) / last_week_views * 100, 1)
                if abs(growth) >= 10:
                    direction = "increased" if growth > 0 else "decreased"
                    new_insights.append(AdminInsight(
                        insight_type="growth" if growth > 0 else "alert",
                        title=f"Platform views {direction} by {abs(growth)}%",
                        message=(
                            f"Total product views this week: {this_week_views:,} "
                            f"vs {last_week_views:,} last week ({growth:+.1f}%)."
                        ),
                        metadata_json=json.dumps(
                            {"this_week": this_week_views, "last_week": last_week_views,
                             "growth_pct": growth}
                        ),
                    ))

            # --- Insight 2: Trending keyword ---
            top_this = (await db.execute(
                select(SearchLog.keyword, func.count(SearchLog.id).label("cnt"))
                .where(SearchLog.created_at >= this_week_start)
                .group_by(SearchLog.keyword)
                .order_by(func.count(SearchLog.id).desc())
                .limit(1)
            )).first()

            top_last = (await db.execute(
                select(SearchLog.keyword, func.count(SearchLog.id).label("cnt"))
                .where(SearchLog.created_at >= last_week_start,
                       SearchLog.created_at < this_week_start)
                .group_by(SearchLog.keyword)
                .order_by(func.count(SearchLog.id).desc())
                .limit(1)
            )).first()

            if top_this and top_this.cnt >= 5:
                prev_cnt = top_last.cnt if top_last and top_last.keyword == top_this.keyword else 0
                if prev_cnt == 0 or top_this.cnt > prev_cnt * 1.5:
                    new_insights.append(AdminInsight(
                        insight_type="trending",
                        title=f'"{top_this.keyword}" is trending',
                        message=(
                            f'"{top_this.keyword}" was searched {top_this.cnt} times this week'
                            + (f" vs {prev_cnt} last week." if prev_cnt else ".")
                        ),
                        metadata_json=json.dumps(
                            {"keyword": top_this.keyword, "this_week": top_this.cnt,
                             "last_week": prev_cnt}
                        ),
                    ))

            # --- Insight 3: Peak usage hour ---
            hour_row = (await db.execute(
                select(
                    func.extract("hour", VendorAction.created_at).label("hr"),
                    func.count(VendorAction.id).label("cnt"),
                )
                .where(VendorAction.created_at >= this_week_start)
                .group_by(text("hr"))
                .order_by(func.count(VendorAction.id).desc())
                .limit(1)
            )).first()

            if hour_row:
                hr = int(hour_row.hr)
                suffix = "AM" if hr < 12 else "PM"
                hr12 = hr if 1 <= hr <= 12 else (hr - 12 if hr > 12 else 12)
                new_insights.append(AdminInsight(
                    insight_type="info",
                    title=f"Users most active at {hr12}:00 {suffix}",
                    message=(
                        f"Platform activity peaks at {hr12}:00 {suffix} this week "
                        f"with {hour_row.cnt:,} user actions."
                    ),
                    metadata_json=json.dumps({"peak_hour": hr, "action_count": hour_row.cnt}),
                ))

            # --- Insight 4: Top category by views ---
            cat_row = (await db.execute(
                select(Category.name, func.count(ProductView.id).label("cnt"))
                .join(Product, Product.category_id == Category.id)
                .join(ProductView, ProductView.product_id == Product.id)
                .where(ProductView.created_at >= this_week_start)
                .group_by(Category.name)
                .order_by(func.count(ProductView.id).desc())
                .limit(1)
            )).first()

            if cat_row and cat_row.cnt >= 10:
                new_insights.append(AdminInsight(
                    insight_type="info",
                    title=f'"{cat_row.name}" is the top category this week',
                    message=(
                        f'Products in "{cat_row.name}" received {cat_row.cnt:,} views this week, '
                        f"making it the most engaged category."
                    ),
                    metadata_json=json.dumps({"category": cat_row.name, "views": cat_row.cnt}),
                ))

            # --- Insight 5: Inactive vendor count ---
            active_vendor_ids = set(
                row[0]
                for row in (await db.execute(
                    select(ProductView.vendor_id.distinct())
                    .where(ProductView.created_at >= this_week_start)
                )).all()
            )
            total_vendor_count = (await db.execute(
                select(func.count(Vendor.id)).where(Vendor.status == "approved")
            )).scalar() or 0
            inactive_count = max(0, total_vendor_count - len(active_vendor_ids))

            if inactive_count > 0:
                new_insights.append(AdminInsight(
                    insight_type="warning",
                    title=f"{inactive_count} vendor(s) had no activity this week",
                    message=(
                        f"{inactive_count} approved vendor(s) received zero product views "
                        f"this week. Consider sending re-engagement notifications."
                    ),
                    metadata_json=json.dumps(
                        {"inactive_count": inactive_count, "total_vendors": total_vendor_count}
                    ),
                ))

            if new_insights:
                db.add_all(new_insights)
                await db.commit()
                log.info(f"[scheduler] Created {len(new_insights)} admin insights.")
            else:
                log.info("[scheduler] No new admin insights generated.")

        except Exception as e:
            log.error(f"[scheduler] generate_admin_insights failed: {e}", exc_info=True)
            await db.rollback()


async def detect_fraud_patterns() -> None:
    """
    Runs at 04:00 UTC daily.
    Detects suspicious activity from yesterday and logs to fraud_logs table.
    """
    from app.models.analytics import ProductView, SearchLog, VendorAction, FraudLog

    yesterday = date.today() - timedelta(days=1)
    day_start = datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    log.info(f"[scheduler] Detecting fraud patterns for {yesterday}")

    async with await _get_session() as db:
        try:
            new_logs: list[FraudLog] = []

            # --- Rule 1: IP velocity — IPs with >200 product views in 24h ---
            ip_view_rows = (await db.execute(
                select(ProductView.ip_address, func.count(ProductView.id).label("cnt"))
                .where(ProductView.ip_address.isnot(None),
                       ProductView.created_at >= day_start,
                       ProductView.created_at < day_end)
                .group_by(ProductView.ip_address)
                .having(func.count(ProductView.id) > 200)
            )).all()

            for row in ip_view_rows:
                # Deduplication: check if this IP was already flagged today
                existing = (await db.execute(
                    select(func.count(FraudLog.id))
                    .where(FraudLog.fraud_type == "ip_velocity",
                           FraudLog.ip_address == row.ip_address,
                           func.date(FraudLog.detected_at) == yesterday)
                )).scalar() or 0
                if existing == 0:
                    new_logs.append(FraudLog(
                        fraud_type="ip_velocity",
                        ip_address=row.ip_address,
                        event_count=row.cnt,
                        details=json.dumps(
                            {"date": str(yesterday), "views": row.cnt, "threshold": 200}
                        ),
                    ))

            # --- Rule 2: Search spam — same IP + same keyword > 30 times in 24h ---
            search_spam_rows = (await db.execute(
                select(SearchLog.ip_address, SearchLog.keyword,
                       func.count(SearchLog.id).label("cnt"))
                .where(SearchLog.ip_address.isnot(None),
                       SearchLog.created_at >= day_start,
                       SearchLog.created_at < day_end)
                .group_by(SearchLog.ip_address, SearchLog.keyword)
                .having(func.count(SearchLog.id) > 30)
            )).all()

            for row in search_spam_rows:
                existing = (await db.execute(
                    select(func.count(FraudLog.id))
                    .where(FraudLog.fraud_type == "search_spam",
                           FraudLog.ip_address == row.ip_address,
                           func.date(FraudLog.detected_at) == yesterday)
                )).scalar() or 0
                if existing == 0:
                    new_logs.append(FraudLog(
                        fraud_type="search_spam",
                        ip_address=row.ip_address,
                        event_count=row.cnt,
                        details=json.dumps(
                            {"date": str(yesterday), "keyword": row.keyword,
                             "count": row.cnt, "threshold": 30}
                        ),
                    ))

            # --- Rule 3: Bot sessions — >100 views AND 0 actions in 24h ---
            view_sessions = set(
                row[0]
                for row in (await db.execute(
                    select(ProductView.session_id)
                    .where(ProductView.session_id.isnot(None),
                           ProductView.created_at >= day_start,
                           ProductView.created_at < day_end)
                    .group_by(ProductView.session_id)
                    .having(func.count(ProductView.id) > 100)
                )).all()
            )
            action_sessions = set(
                row[0]
                for row in (await db.execute(
                    select(VendorAction.session_id.distinct())
                    .where(VendorAction.session_id.isnot(None),
                           VendorAction.created_at >= day_start,
                           VendorAction.created_at < day_end)
                )).all()
            )
            bot_sessions = view_sessions - action_sessions

            for session_id in list(bot_sessions)[:20]:  # cap at 20 per run
                view_count = (await db.execute(
                    select(func.count(ProductView.id))
                    .where(ProductView.session_id == session_id,
                           ProductView.created_at >= day_start,
                           ProductView.created_at < day_end)
                )).scalar() or 0

                existing = (await db.execute(
                    select(func.count(FraudLog.id))
                    .where(FraudLog.fraud_type == "session_spam",
                           FraudLog.session_id == session_id,
                           func.date(FraudLog.detected_at) == yesterday)
                )).scalar() or 0
                if existing == 0:
                    new_logs.append(FraudLog(
                        fraud_type="session_spam",
                        session_id=session_id,
                        event_count=view_count,
                        details=json.dumps(
                            {"date": str(yesterday), "views": view_count,
                             "actions": 0, "threshold": 100}
                        ),
                    ))

            if new_logs:
                db.add_all(new_logs)
                await db.commit()
                log.info(f"[scheduler] Logged {len(new_logs)} fraud patterns.")
            else:
                log.info("[scheduler] No fraud patterns detected.")

        except Exception as e:
            log.error(f"[scheduler] detect_fraud_patterns failed: {e}", exc_info=True)
            await db.rollback()


def start_scheduler() -> None:
    scheduler.add_job(
        aggregate_daily_summaries,
        CronTrigger(hour=1, minute=0),
        id="aggregate_daily_summaries",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        generate_vendor_insights,
        CronTrigger(hour=2, minute=0),
        id="generate_vendor_insights",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        generate_admin_insights,
        CronTrigger(hour=3, minute=0),
        id="generate_admin_insights",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        detect_fraud_patterns,
        CronTrigger(hour=4, minute=0),
        id="detect_fraud_patterns",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("[scheduler] APScheduler started — daily jobs at 01:00, 02:00, 03:00, 04:00 UTC.")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("[scheduler] APScheduler stopped.")

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
    scheduler.start()
    log.info("[scheduler] APScheduler started — daily jobs scheduled at 01:00 and 02:00 UTC.")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("[scheduler] APScheduler stopped.")

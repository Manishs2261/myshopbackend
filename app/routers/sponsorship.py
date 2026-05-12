from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_vendor
from app.models.user import User, Vendor
from app.models.sponsorship import SponsorshipPlan, VendorSponsorship
from app.schemas.schemas import (
    SponsorshipPlanCreate, SponsorshipPlanUpdate, SponsorshipPlanResponse,
    VendorSponsorshipCreate, SponsorshipApproveRequest,
    VendorSponsorshipResponse, SponsorshipAnalyticsResponse,
)

router = APIRouter(prefix="/sponsorships", tags=["Sponsorships"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _plan_to_dict(plan: SponsorshipPlan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "price": float(plan.price) if plan.price else 0,
        "duration_days": plan.duration_days,
        "priority": plan.priority,
        "max_categories": plan.max_categories,
        "max_locations": plan.max_locations,
        "is_active": plan.is_active,
    }


def _sponsorship_to_dict(s: VendorSponsorship, include_plan: bool = False) -> dict:
    data = {
        "id": s.id,
        "vendor_id": s.vendor_id,
        "plan_id": s.plan_id,
        "status": s.status,
        "target_categories": s.target_categories or [],
        "target_locations": s.target_locations or [],
        "target_keywords": s.target_keywords or [],
        "priority": s.priority,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "click_count": s.click_count or 0,
        "view_count": s.view_count or 0,
        "admin_notes": s.admin_notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if include_plan and s.plan:
        data["plan"] = _plan_to_dict(s.plan)
    return data


# ─── A: Admin — Plan CRUD ────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SponsorshipPlan).order_by(SponsorshipPlan.priority.desc())
    )
    plans = result.scalars().all()
    return [_plan_to_dict(p) for p in plans]


@router.post("/plans")
async def create_plan(
    body: SponsorshipPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    plan = SponsorshipPlan(**body.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _plan_to_dict(plan)


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: int,
    body: SponsorshipPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(select(SponsorshipPlan).where(SponsorshipPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return _plan_to_dict(plan)


# ─── B: Admin — Request Management ──────────────────────────────────────────

@router.get("")
async def list_sponsorships(
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    query = (
        select(VendorSponsorship)
        .options(
            selectinload(VendorSponsorship.vendor).selectinload(Vendor.shop),
            selectinload(VendorSponsorship.plan),
        )
        .order_by(VendorSponsorship.created_at.desc())
    )
    if status:
        query = query.where(VendorSponsorship.status == status)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    rows = []
    for s in items:
        row = _sponsorship_to_dict(s, include_plan=True)
        if s.vendor:
            row["business_name"] = s.vendor.business_name
            row["vendor_status"] = s.vendor.status
            if s.vendor.shop:
                row["shop_name"] = s.vendor.shop.name
                row["shop_city"] = s.vendor.shop.city
        rows.append(row)

    return {"items": rows, "total": total, "page": page, "pages": max(1, -(-total // limit))}


@router.put("/{sponsorship_id}/approve")
async def approve_sponsorship(
    sponsorship_id: int,
    body: SponsorshipApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(VendorSponsorship)
        .options(selectinload(VendorSponsorship.plan))
        .where(VendorSponsorship.id == sponsorship_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sponsorship not found")
    if s.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail=f"Cannot approve a sponsorship with status '{s.status}'")

    s.status = "active"
    s.start_date = body.start_date
    s.end_date = body.end_date
    if s.plan:
        s.priority = s.plan.priority
    await db.commit()
    await db.refresh(s)
    return _sponsorship_to_dict(s)


@router.put("/{sponsorship_id}/reject")
async def reject_sponsorship(
    sponsorship_id: int,
    admin_notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(select(VendorSponsorship).where(VendorSponsorship.id == sponsorship_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sponsorship not found")
    s.status = "rejected"
    if admin_notes:
        s.admin_notes = admin_notes
    await db.commit()
    return {"ok": True, "status": "rejected"}


@router.put("/{sponsorship_id}/toggle")
async def toggle_sponsorship(
    sponsorship_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(select(VendorSponsorship).where(VendorSponsorship.id == sponsorship_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sponsorship not found")
    if s.status == "active":
        s.status = "paused"
    elif s.status == "paused":
        s.status = "active"
    else:
        raise HTTPException(status_code=400, detail=f"Cannot toggle a sponsorship with status '{s.status}'")
    await db.commit()
    return {"ok": True, "status": s.status}


@router.put("/{sponsorship_id}/priority")
async def update_priority(
    sponsorship_id: int,
    priority: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(select(VendorSponsorship).where(VendorSponsorship.id == sponsorship_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sponsorship not found")
    s.priority = priority
    await db.commit()
    return {"ok": True, "priority": priority}


@router.get("/analytics")
async def sponsorship_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    status_counts = await db.execute(
        select(VendorSponsorship.status, func.count().label("cnt"))
        .group_by(VendorSponsorship.status)
    )
    counts = {row.status: row.cnt for row in status_counts}

    agg = await db.execute(
        select(
            func.coalesce(func.sum(VendorSponsorship.click_count), 0).label("clicks"),
            func.coalesce(func.sum(VendorSponsorship.view_count), 0).label("views"),
        ).where(VendorSponsorship.status == "active")
    )
    agg_row = agg.one()

    return {
        "total_active": counts.get("active", 0),
        "total_pending": counts.get("pending", 0),
        "total_rejected": counts.get("rejected", 0),
        "total_expired": counts.get("expired", 0),
        "total_paused": counts.get("paused", 0),
        "aggregate_clicks": int(agg_row.clicks),
        "aggregate_views": int(agg_row.views),
    }


# ─── C: Vendor — Self-Service ────────────────────────────────────────────────

@router.get("/vendor/plans")
async def vendor_list_plans(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_vendor),
):
    result = await db.execute(
        select(SponsorshipPlan)
        .where(SponsorshipPlan.is_active == True)
        .order_by(SponsorshipPlan.priority.desc())
    )
    plans = result.scalars().all()
    return [_plan_to_dict(p) for p in plans]


@router.post("/vendor/apply")
async def vendor_apply(
    body: VendorSponsorshipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_vendor),
):
    vendor_result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = vendor_result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    # Guard: no existing pending or active sponsorship
    existing = await db.execute(
        select(VendorSponsorship).where(
            VendorSponsorship.vendor_id == vendor.id,
            VendorSponsorship.status.in_(["pending", "active"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already have a pending or active sponsorship")

    # Validate plan
    plan_result = await db.execute(
        select(SponsorshipPlan).where(SponsorshipPlan.id == body.plan_id, SponsorshipPlan.is_active == True)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Sponsorship plan not found or inactive")

    cats = body.target_categories or []
    locs = body.target_locations or []
    if len(cats) > plan.max_categories:
        raise HTTPException(status_code=400, detail=f"Plan allows at most {plan.max_categories} target categories")
    if len(locs) > plan.max_locations:
        raise HTTPException(status_code=400, detail=f"Plan allows at most {plan.max_locations} target locations")

    s = VendorSponsorship(
        vendor_id=vendor.id,
        plan_id=plan.id,
        status="pending",
        target_categories=cats,
        target_locations=locs,
        target_keywords=body.target_keywords or [],
        priority=plan.priority,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _sponsorship_to_dict(s)


@router.get("/vendor/status")
async def vendor_sponsorship_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_vendor),
):
    vendor_result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = vendor_result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    result = await db.execute(
        select(VendorSponsorship)
        .options(selectinload(VendorSponsorship.plan))
        .where(VendorSponsorship.vendor_id == vendor.id)
        .order_by(VendorSponsorship.created_at.desc())
    )
    items = result.scalars().all()
    return [_sponsorship_to_dict(s, include_plan=True) for s in items]


@router.delete("/vendor/{sponsorship_id}/cancel")
async def vendor_cancel(
    sponsorship_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_vendor),
):
    vendor_result = await db.execute(select(Vendor).where(Vendor.user_id == current_user.id))
    vendor = vendor_result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    result = await db.execute(
        select(VendorSponsorship).where(
            VendorSponsorship.id == sponsorship_id,
            VendorSponsorship.vendor_id == vendor.id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sponsorship not found")
    if s.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending sponsorships can be cancelled")
    s.status = "cancelled"
    await db.commit()
    return {"ok": True, "status": "cancelled"}

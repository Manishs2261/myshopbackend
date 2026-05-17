from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Event
from app.models.analytics import ProductView, ProductImpression, SearchLog, VendorAction
from app.schemas.schemas import EventBatchRequest, TrackEventRequest

router = APIRouter(tags=["Analytics"])

ACTION_TYPES = {
    "call_click", "whatsapp_click", "direction_click", "share",
    "inquiry", "profile_view", "wishlist_add", "wishlist_remove", "product_click",
}


@router.post("/events/batch", response_model=dict)
async def track_events_batch(
    payload: EventBatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Batch event tracking for analytics.
    Event types: search, product_click, add_to_cart, checkout_start,
                 page_view, wishlist_add, category_browse, etc.
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    events = []
    for event_data in payload.events:
        event = Event(
            user_id=current_user.id,
            event_type=event_data.type,
            metadata=event_data.data,
            ip_address=ip,
            user_agent=user_agent,
        )
        events.append(event)

    db.add_all(events)
    await db.commit()

    return {"message": f"Tracked {len(events)} events"}


@router.post("/events/anonymous", response_model=dict)
async def track_anonymous_events(
    payload: EventBatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Track events for non-authenticated users (guest browsing)."""
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    session_id = request.headers.get("x-session-id")

    events = [
        Event(
            user_id=None,
            session_id=session_id,
            event_type=e.type,
            metadata=e.data,
            ip_address=ip,
            user_agent=user_agent,
        )
        for e in payload.events
    ]

    db.add_all(events)
    await db.commit()
    return {"message": f"Tracked {len(events)} anonymous events"}


@router.post("/analytics/track", response_model=dict)
async def track_events_unified(
    payload: TrackEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Unified event tracking endpoint. Accepts both authenticated and anonymous events.
    Writes typed rows to dedicated analytics tables + the generic events table.
    Failures on individual events are silently skipped — tracking must never break UX.

    Supported event types:
    - product_view: data={product_id, vendor_id, device?, platform?, city?}
    - product_impression: data={product_id, vendor_id}
    - search: data={keyword, result_count?, city?}
    - call_click | whatsapp_click | direction_click | share | inquiry |
      profile_view | wishlist_add | wishlist_remove | product_click:
        data={vendor_id, product_id?}
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")
    session_id = request.headers.get("x-session-id")

    # Try to resolve authenticated user from Authorization header (optional)
    user_id: Optional[int] = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.security import decode_token
            from sqlalchemy import select
            token = auth_header[7:]
            payload_data = decode_token(token)
            uid = payload_data.get("sub")
            if uid:
                result = await db.execute(
                    select(User).where(
                        (User.firebase_uid == uid) | (User.id == _safe_int(uid))
                    )
                )
                user = result.scalar_one_or_none()
                if user:
                    user_id = user.id
        except Exception:
            pass  # token errors don't block tracking

    tracked = 0
    for event in payload.events:
        try:
            d = event.data
            event_type = event.type

            if event_type == "product_view":
                db.add(ProductView(
                    product_id=int(d["product_id"]),
                    vendor_id=int(d["vendor_id"]),
                    user_id=user_id,
                    session_id=session_id,
                    ip_address=ip,
                    device=d.get("device"),
                    platform=d.get("platform"),
                    city=d.get("city"),
                ))

            elif event_type == "product_impression":
                db.add(ProductImpression(
                    product_id=int(d["product_id"]),
                    vendor_id=int(d["vendor_id"]),
                    session_id=session_id,
                ))

            elif event_type == "search":
                db.add(SearchLog(
                    keyword=str(d.get("keyword", ""))[:500],
                    result_count=int(d.get("result_count", 0)),
                    user_id=user_id,
                    session_id=session_id,
                    city=d.get("city"),
                    ip_address=ip,
                ))

            elif event_type in ACTION_TYPES:
                db.add(VendorAction(
                    vendor_id=int(d["vendor_id"]),
                    product_id=int(d["product_id"]) if d.get("product_id") else None,
                    action_type=event_type,
                    user_id=user_id,
                    session_id=session_id,
                    device=d.get("device"),
                    platform=d.get("platform"),
                    city=d.get("city"),
                    ip_address=ip,
                ))

            # Also write to generic Event table for backward compatibility
            db.add(Event(
                user_id=user_id,
                session_id=session_id,
                event_type=event_type,
                metadata=str(d),
                ip_address=ip,
                user_agent=user_agent,
            ))
            tracked += 1

        except Exception:
            continue  # silently skip malformed events

    await db.commit()
    return {"tracked": tracked}


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

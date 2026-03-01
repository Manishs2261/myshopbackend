from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Event
from app.schemas.schemas import EventBatchRequest

router = APIRouter(tags=["Analytics"])


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

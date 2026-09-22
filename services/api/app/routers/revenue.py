from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.audited_earnings import (
    audited_earnings_chart,
    audited_earnings_records,
    audited_earnings_summary,
)
from app.utils.response import success

router = APIRouter(prefix="/api/revenue", tags=["revenue"])


@router.get("")
def revenue_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success(audited_earnings_summary(user.id, db))


@router.get("/chart")
def revenue_chart(
    range_days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(audited_earnings_chart(user.id, range_days, db))


@router.get("/records")
def revenue_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success(audited_earnings_records(user.id, db))

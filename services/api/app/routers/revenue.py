from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.asset import Asset
from app.models.revenue import Revenue
from app.models.user import User
from app.schemas.revenue import RevenueRecord
from app.utils.response import success

router = APIRouter(prefix="/api/revenue", tags=["revenue"])


@router.get("")
def revenue_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    today_amt = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user.id, Revenue.date == today
    ).scalar()
    total_amt = db.query(func.coalesce(func.sum(Revenue.amount), 0)).filter(
        Revenue.user_id == user.id
    ).scalar()
    assets = db.query(Asset).filter(Asset.user_id == user.id, Asset.status == "active").all()
    asset_value = sum(float(a.value) * a.quantity for a in assets)
    rate = round(float(today_amt) / asset_value * 100, 2) if asset_value > 0 else 0
    return success({
        "today": round(float(today_amt), 2) if settings.REVENUE_SETTLEMENT_ENABLED else 0,
        "total": round(float(total_amt), 2) if settings.REVENUE_SETTLEMENT_ENABLED else 0,
        "rate": rate if settings.REVENUE_SETTLEMENT_ENABLED else 0,
        "historical_test_total": round(float(total_amt), 2),
        "revenue_settlement_enabled": settings.REVENUE_SETTLEMENT_ENABLED,
    })


@router.get("/chart")
def revenue_chart(range_days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start = date.today() - timedelta(days=range_days - 1)
    rows = db.query(Revenue.date, func.sum(Revenue.amount)).filter(
        Revenue.user_id == user.id, Revenue.date >= start
    ).group_by(Revenue.date).order_by(Revenue.date).all()
    m = {r[0]: float(r[1]) for r in rows}
    points = []
    cum = 0
    for i in range(range_days):
        d = start + timedelta(days=i)
        cum += m.get(d, 0) if settings.REVENUE_SETTLEMENT_ENABLED else 0
        points.append({"date": d.strftime("%m-%d"), "amount": round(cum, 2)})
    return success(points)


@router.get("/records")
def revenue_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.REVENUE_SETTLEMENT_ENABLED:
        return success([])
    items = db.query(Revenue).filter(Revenue.user_id == user.id).order_by(
        Revenue.created_at.desc()
    ).limit(50).all()
    out = []
    for r in items:
        out.append({
            "id": r.id, "amount": float(r.amount),
            "date": r.date.strftime("%Y-%m-%d") if r.date else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return success(out)

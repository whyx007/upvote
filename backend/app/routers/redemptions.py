"""Admin-confirmed redemptions: balance/stock checks, cancel with refund."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Redemption, Reward, Student
from ..security import get_db, require_admin
from ..services.points import balances_for_students
from .semesters import current_semester

router = APIRouter(prefix="/api/redemptions", tags=["redemptions"])


class RedemptionIn(BaseModel):
    student_id: int
    reward_id: int


def _balance(db, request, student_id, semester_id):
    return balances_for_students(db, [student_id], semester_id, request.app.state.settings.coins_per_like)[student_id][
        "semester_balance"
    ]


@router.post("")
def create_redemption(body: RedemptionIn, request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    student = db.get(Student, body.student_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=404, detail="学生不存在")
    reward = db.get(Reward, body.reward_id)
    if reward is None or not reward.is_active:
        raise HTTPException(status_code=404, detail="奖励不存在")
    semester = current_semester(db)
    if semester is None:
        raise HTTPException(status_code=400, detail="当前没有激活的学期")
    if _balance(db, request, student.id, semester.id) < reward.cost_coins:
        raise HTTPException(status_code=400, detail="星灿币不足")
    if reward.stock is not None:
        if reward.stock <= 0:
            raise HTTPException(status_code=400, detail="奖励库存不足")
        reward.stock -= 1
    redemption = Redemption(
        student_id=student.id,
        reward_id=reward.id,
        cost_coins=reward.cost_coins,
        semester_id=semester.id,
        operator_id=admin.id,
    )
    db.add(redemption)
    db.commit()
    return {"id": redemption.id, "new_balance": _balance(db, request, student.id, semester.id)}


@router.get("")
def list_redemptions(
    student_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(Redemption)
    if student_id is not None:
        stmt = stmt.where(Redemption.student_id == student_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    redemptions = db.scalars(stmt.order_by(Redemption.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for r in redemptions:
        student = db.get(Student, r.student_id)
        reward = db.get(Reward, r.reward_id)
        items.append(
            {
                "id": r.id,
                "student_id": r.student_id,
                "student_name": student.name if student else None,
                "reward_id": r.reward_id,
                "reward_name": reward.name if reward else None,
                "cost_coins": r.cost_coins,
                "created_at": r.created_at.isoformat(),
                "cancelled": r.cancelled_at is not None,
            }
        )
    return {"total": total, "items": items}


@router.post("/{redemption_id}/cancel")
def cancel_redemption(redemption_id: int, request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    redemption = db.get(Redemption, redemption_id)
    if redemption is None:
        raise HTTPException(status_code=404, detail="兑换记录不存在")
    if redemption.cancelled_at is not None:
        raise HTTPException(status_code=400, detail="该兑换已取消")
    redemption.cancelled_at = datetime.now()
    reward = db.get(Reward, redemption.reward_id)
    if reward is not None and reward.stock is not None:
        reward.stock += 1
    db.commit()
    return {"ok": True, "new_balance": _balance(db, request, redemption.student_id, redemption.semester_id)}
"""管理员学年升级：预览与执行。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SchoolClass
from ..security import get_db, require_admin, verify_password
from ..services.promotion import apply_plan, build_plan, default_target_year
from ..services.grades import grade_of_class, normalize_grade

router = APIRouter(prefix="/api/admin/promotion", tags=["promotion"])

PROMOTE_CONFIRM = "学年升级"


class PromoteIn(BaseModel):
    password: str
    confirm: str
    target_year: int
    new_grade7_count: int


def _default_grade7_count(db: Session) -> int:
    classes = db.scalars(select(SchoolClass)).all()
    return sum(
        1
        for klass in classes
        if (normalize_grade(klass.grade) or grade_of_class(klass.name)) == "七年级"
        and klass.is_active
    )


@router.get("/preview")
def preview(
    target_year: int | None = Query(None),
    new_grade7_count: int | None = Query(None),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    year = target_year or default_target_year()
    count = _default_grade7_count(db) if new_grade7_count is None else new_grade7_count
    try:
        plan = build_plan(db, year, count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return plan


@router.post("/run")
def run_promotion(body: PromoteIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    if not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=400, detail="管理员密码错误")
    if body.confirm.strip() != PROMOTE_CONFIRM:
        raise HTTPException(status_code=400, detail=f"请输入“{PROMOTE_CONFIRM}”确认")
    try:
        plan = build_plan(db, body.target_year, body.new_grade7_count)
        apply_plan(db, plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "plan": plan}
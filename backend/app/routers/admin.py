"""Destructive roster reset used by the admin import page.

Only 校长/主任 can call it; requires the current account password plus an
explicit confirmation phrase. Keeps admin accounts, semesters and rewards.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import (
    Group,
    GroupMember,
    ImportBatch,
    Like,
    Redemption,
    SchoolClass,
    Student,
    Teacher,
    TeacherClass,
)
from ..security import get_db, require_admin, verify_password

router = APIRouter(prefix="/api/admin", tags=["admin"])

CONFIRM_TEXT = "清除名单"


class ClearRosterIn(BaseModel):
    password: str
    confirm: str


@router.post("/clear-roster")
def clear_roster(
    body: ClearRosterIn,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=400, detail="管理员密码错误")
    if body.confirm.strip() != CONFIRM_TEXT:
        raise HTTPException(status_code=400, detail=f"请输入“{CONFIRM_TEXT}”确认")

    counts = {}
    counts["likes"] = db.execute(delete(Like)).rowcount or 0
    counts["redemptions"] = db.execute(delete(Redemption)).rowcount or 0
    counts["group_members"] = db.execute(delete(GroupMember)).rowcount or 0
    counts["groups"] = db.execute(delete(Group)).rowcount or 0
    counts["teacher_classes"] = db.execute(delete(TeacherClass)).rowcount or 0
    counts["students"] = db.execute(delete(Student)).rowcount or 0
    counts["classes"] = db.execute(delete(SchoolClass)).rowcount or 0
    counts["teachers"] = (
        db.execute(delete(Teacher).where(Teacher.role != "admin")).rowcount or 0
    )
    counts["import_batches"] = db.execute(delete(ImportBatch)).rowcount or 0
    db.commit()
    return {"ok": True, "counts": counts}
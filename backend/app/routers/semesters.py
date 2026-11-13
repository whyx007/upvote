from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Semester
from ..security import get_current_teacher, get_db, require_admin

router = APIRouter(prefix="/api/semesters", tags=["semesters"])


class SemesterIn(BaseModel):
    name: str
    start_date: date
    end_date: date


def serialize_semester(s: Semester) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "start_date": s.start_date.isoformat(),
        "end_date": s.end_date.isoformat(),
        "is_current": s.is_current,
    }


def current_semester(db: Session) -> Semester | None:
    return db.scalar(select(Semester).where(Semester.is_current.is_(True)))


@router.get("")
def list_semesters(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    semesters = db.scalars(select(Semester).order_by(Semester.start_date)).all()
    return {"items": [serialize_semester(s) for s in semesters]}


@router.post("")
def create_semester(body: SemesterIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    if body.end_date <= body.start_date:
        raise HTTPException(status_code=400, detail="结束日期必须晚于开始日期")
    if db.scalar(select(Semester).where(Semester.name == body.name)):
        raise HTTPException(status_code=400, detail="学期名称已存在")
    semester = Semester(name=body.name, start_date=body.start_date, end_date=body.end_date)
    db.add(semester)
    db.commit()
    return serialize_semester(semester)


@router.get("/current")
def get_current(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    semester = current_semester(db)
    return serialize_semester(semester) if semester else None


@router.post("/{semester_id}/activate")
def activate_semester(semester_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    semester = db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(status_code=404, detail="学期不存在")
    for s in db.scalars(select(Semester).where(Semester.is_current.is_(True))).all():
        s.is_current = False
    semester.is_current = True
    db.commit()
    return serialize_semester(semester)
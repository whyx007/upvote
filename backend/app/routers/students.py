from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Student
from ..security import get_current_teacher, get_db, require_admin

router = APIRouter(prefix="/api/students", tags=["students"])


class StudentIn(BaseModel):
    student_no: str
    name: str
    grade: str | None = None
    class_name: str
    enrollment_year: int | None = None


class StudentPatch(BaseModel):
    name: str | None = None
    grade: str | None = None
    class_name: str | None = None
    enrollment_year: int | None = None


def serialize_student(s: Student) -> dict:
    return {
        "id": s.id,
        "student_no": s.student_no,
        "name": s.name,
        "grade": s.grade,
        "class_name": s.class_name,
        "enrollment_year": s.enrollment_year,
    }


@router.get("")
def list_students(
    q: str = "",
    class_name: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    stmt = select(Student).where(Student.is_active.is_(True))
    if q:
        stmt = stmt.where(or_(Student.name.contains(q), Student.student_no.contains(q)))
    if class_name:
        stmt = stmt.where(Student.class_name == class_name)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    students = db.scalars(
        stmt.order_by(Student.class_name, Student.student_no).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"total": total, "items": [serialize_student(s) for s in students]}


@router.post("")
def create_student(body: StudentIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Student).where(Student.student_no == body.student_no)):
        raise HTTPException(status_code=400, detail="学号已存在")
    student = Student(**body.model_dump())
    db.add(student)
    db.commit()
    return serialize_student(student)


@router.patch("/{student_id}")
def update_student(student_id: int, body: StudentPatch, admin=Depends(require_admin), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(student, field, value)
    db.commit()
    return serialize_student(student)


@router.delete("/{student_id}")
def deactivate_student(student_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    student.is_active = False
    db.commit()
    return {"ok": True}
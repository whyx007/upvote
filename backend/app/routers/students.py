from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Student
from ..security import get_current_teacher, get_db
from ..services.class_roles import assert_class_manager

router = APIRouter(prefix="/api/students", tags=["students"])


class StudentIn(BaseModel):
    student_no: str
    name: str
    gender: str | None = None
    grade: str | None = None
    class_name: str
    enrollment_year: int | None = None


class StudentPatch(BaseModel):
    name: str | None = None
    gender: str | None = None
    grade: str | None = None
    class_name: str | None = None
    enrollment_year: int | None = None


def _validate_gender(gender: str | None) -> str | None:
    if gender in (None, ""):
        return None
    if gender not in ("男", "女"):
        raise HTTPException(status_code=400, detail="性别只能为 男 或 女")
    return gender


def serialize_student(s: Student) -> dict:
    return {
        "id": s.id,
        "student_no": s.student_no,
        "name": s.name,
        "gender": s.gender,
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
def create_student(body: StudentIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    assert_class_manager(db, teacher, body.class_name)
    if db.scalar(select(Student).where(Student.student_no == body.student_no)):
        raise HTTPException(status_code=400, detail="学号已存在")
    data = body.model_dump()
    data["gender"] = _validate_gender(data.get("gender"))
    student = Student(**data)
    db.add(student)
    db.commit()
    return serialize_student(student)


@router.patch("/{student_id}")
def update_student(student_id: int, body: StudentPatch, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    assert_class_manager(db, teacher, student.class_name)
    data = body.model_dump(exclude_unset=True)
    if teacher.role != "admin" and data.get("class_name") not in (None, student.class_name):
        raise HTTPException(status_code=403, detail="班级管理角色不能将学生转到其他班级")
    if "gender" in data:
        data["gender"] = _validate_gender(data["gender"])
    for field, value in data.items():
        setattr(student, field, value)
    db.commit()
    return serialize_student(student)


@router.delete("/{student_id}")
def deactivate_student(student_id: int, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    assert_class_manager(db, teacher, student.class_name)
    student.is_active = False
    db.commit()
    return {"ok": True}
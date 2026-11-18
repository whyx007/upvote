from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Student
from ..security import get_current_teacher, get_db, require_admin
from ..services.class_roles import assert_class_manager
from ..services.class_service import class_names_for_grade, ensure_school_class
from ..services.grades import class_sort_key, grade_of_class, grade_values, normalize_grade

router = APIRouter(prefix="/api/students", tags=["students"])


class StudentIn(BaseModel):
    student_no: str | None = None
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


def _next_student_no(db: Session) -> str:
    max_id = db.scalar(select(func.max(Student.id))) or 0
    while True:
        max_id += 1
        candidate = f"S{max_id:06d}"
        if db.scalar(select(Student.id).where(Student.student_no == candidate)) is None:
            return candidate


def serialize_student(s: Student) -> dict:
    return {
        "id": s.id,
        "student_no": s.student_no,
        "name": s.name,
        "gender": s.gender,
        "grade": normalize_grade(s.grade) or grade_of_class(s.class_name),
        "class_name": s.class_name,
        "enrollment_year": s.enrollment_year,
    }


@router.get("")
def list_students(
    q: str = "",
    class_name: str = "",
    grade: str = "",
    enrollment_year: int | None = None,
    gender: str = "",
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(Student)
    if not include_inactive:
        stmt = stmt.where(Student.is_active.is_(True))
    if q:
        stmt = stmt.where(or_(Student.name.contains(q), Student.student_no.contains(q)))
    if class_name:
        stmt = stmt.where(Student.class_name == class_name)
    if gender:
        stmt = stmt.where(Student.gender == gender)
    if enrollment_year is not None:
        stmt = stmt.where(Student.enrollment_year == enrollment_year)
    if grade:
        values = grade_values(grade)
        names = class_names_for_grade(db, grade)
        stmt = stmt.where(or_(Student.grade.in_(values), Student.class_name.in_(names)))
    students = db.scalars(stmt).all()
    students = sorted(students, key=lambda s: (class_sort_key(s.class_name), s.student_no))
    total = len(students)
    page_items = students[(page - 1) * page_size : (page - 1) * page_size + page_size]
    return {"total": total, "items": [serialize_student(s) for s in page_items]}


@router.post("")
def create_student(body: StudentIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    assert_class_manager(db, teacher, body.class_name)
    student_no = (body.student_no or "").strip() or _next_student_no(db)
    if db.scalar(select(Student).where(Student.student_no == student_no)):
        raise HTTPException(status_code=400, detail="学号已存在")
    data = body.model_dump()
    data["student_no"] = student_no
    data["gender"] = _validate_gender(data.get("gender"))
    data["grade"] = normalize_grade(data.get("grade")) or grade_of_class(data["class_name"])
    ensure_school_class(db, data["class_name"], grade=data["grade"], enrollment_year=data.get("enrollment_year"))
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
    if "grade" in data and data["grade"]:
        data["grade"] = normalize_grade(data["grade"])
    elif "class_name" in data:
        data["grade"] = grade_of_class(data["class_name"])
    for field, value in data.items():
        setattr(student, field, value)
    ensure_school_class(db, student.class_name, grade=student.grade, enrollment_year=student.enrollment_year)
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
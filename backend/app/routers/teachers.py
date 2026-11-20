from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Teacher, TeacherClass
from ..security import get_current_teacher, get_db, hash_password, require_admin
from ..services.access import (
    ROLE_ADMIN,
    ROLE_SUBJECT_LEAD,
    ROLE_TEACHER,
    all_class_names,
    assigned_class_names,
    normalize_role,
)
from ..services.class_service import ensure_school_class
from ..services.class_roles import CLASS_MANAGER_DUTIES, assert_any_class_manager
from ..services.grades import class_sort_key, grade_of_class, normalize_grade
from ..services.subjects import normalize_subject
from .auth import serialize_teacher

router = APIRouter(prefix="/api", tags=["teachers"])

DEFAULT_PASSWORD = "123456"


class TeacherIn(BaseModel):
    employee_no: str | None = None
    name: str
    phone: str | None = None
    password: str | None = Field(None, min_length=6)
    role: str = ROLE_TEACHER
    subject: str | None = None


class TeacherPatch(BaseModel):
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    subject: str | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=6)


class TeacherClassesIn(BaseModel):
    class_names: list[str]


def _next_employee_no(db: Session) -> str:
    number = 1
    while True:
        candidate = f"T{number:03d}"
        if db.scalar(select(Teacher.id).where(Teacher.employee_no == candidate)) is None:
            return candidate
        number += 1


def _validate_role_subject(role: str | None, subject: str | None) -> tuple[str, str | None]:
    try:
        normalized_role = normalize_role(role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    normalized_subject = normalize_subject(subject)
    if normalized_role == ROLE_SUBJECT_LEAD and not normalized_subject:
        raise HTTPException(status_code=400, detail="学科组长必须选择学科")
    return normalized_role, normalized_subject


def _classes_by_teacher(db: Session, teacher_ids: list[int]) -> dict[int, list[str]]:
    if not teacher_ids:
        return {}
    rows = db.execute(
        select(TeacherClass.teacher_id, TeacherClass.class_name).where(TeacherClass.teacher_id.in_(teacher_ids))
    ).all()
    result: dict[int, list[str]] = {}
    for teacher_id, class_name in rows:
        result.setdefault(teacher_id, []).append(class_name)
    return {tid: sorted(names, key=class_sort_key) for tid, names in result.items()}


def _serialize_full(db: Session, t: Teacher) -> dict:
    classes = _classes_by_teacher(db, [t.id]).get(t.id, [])
    return {**serialize_teacher(t), "is_active": t.is_active, "classes": classes}


@router.get("/my/classes")
def my_classes(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    if teacher.role == ROLE_ADMIN:
        return all_class_names(db)
    return assigned_class_names(db, teacher)


@router.get("/my/class-roles")
def my_class_roles(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    if teacher.role == ROLE_ADMIN:
        return {"items": []}
    rows = db.execute(
        select(TeacherClass.class_name, TeacherClass.duty)
        .where(TeacherClass.teacher_id == teacher.id, TeacherClass.duty.in_(CLASS_MANAGER_DUTIES))
        .order_by(TeacherClass.class_name)
    ).all()
    return {"items": [{"class_name": class_name, "duty": duty} for class_name, duty in rows]}


@router.get("/teachers/options")
def teacher_options(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Limited teacher options for class managers; no phone/account role exposure."""
    assert_any_class_manager(db, teacher)
    teachers = db.scalars(select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.employee_no)).all()
    classes_map = _classes_by_teacher(db, [t.id for t in teachers])
    return {
        "items": [
            {
                "id": t.id,
                "employee_no": t.employee_no,
                "name": t.name,
                "subject": t.subject,
                "is_active": t.is_active,
                "classes": classes_map.get(t.id, []),
            }
            for t in teachers
        ]
    }


@router.get("/teachers")
def list_teachers(
    q: str = "",
    role: str = "",
    subject: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(Teacher)
    if q:
        stmt = stmt.where(or_(Teacher.name.contains(q), Teacher.employee_no.contains(q)))
    if role:
        try:
            stmt = stmt.where(Teacher.role == normalize_role(role))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    teachers = db.scalars(stmt.order_by(Teacher.employee_no)).all()
    if subject:
        wanted = normalize_subject(subject)
        teachers = [t for t in teachers if normalize_subject(t.subject) == wanted]
    total = len(teachers)
    page_items = teachers[(page - 1) * page_size : (page - 1) * page_size + page_size]
    classes_map = _classes_by_teacher(db, [t.id for t in page_items])
    return {
        "total": total,
        "items": [
            {**serialize_teacher(t), "is_active": t.is_active, "classes": classes_map.get(t.id, [])}
            for t in page_items
        ],
    }


@router.post("/teachers")
def create_teacher(body: TeacherIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    role, subject = _validate_role_subject(body.role, body.subject)
    employee_no = (body.employee_no or "").strip() or _next_employee_no(db)
    if db.scalar(select(Teacher).where(Teacher.employee_no == employee_no)):
        raise HTTPException(status_code=400, detail="工号已存在")
    teacher = Teacher(
        employee_no=employee_no,
        name=body.name,
        phone=body.phone,
        password_hash=hash_password(body.password or DEFAULT_PASSWORD),
        role=role,
        subject=subject,
    )
    db.add(teacher)
    db.commit()
    return _serialize_full(db, teacher)


@router.patch("/teachers/{teacher_id}")
def update_teacher(teacher_id: int, body: TeacherPatch, admin=Depends(require_admin), db: Session = Depends(get_db)):
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    data = body.model_dump(exclude_unset=True)
    role = data.get("role", teacher.role)
    subject = data.get("subject", teacher.subject)
    role, subject = _validate_role_subject(role, subject)
    if "role" in data:
        data["role"] = role
    if "subject" in data:
        data["subject"] = subject
    if "password" in data:
        teacher.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(teacher, field, value)
    db.commit()
    return _serialize_full(db, teacher)


@router.delete("/teachers/{teacher_id}")
def deactivate_teacher(teacher_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    teacher.is_active = False
    db.commit()
    return {"ok": True}


@router.put("/teachers/{teacher_id}/classes")
def set_teacher_classes(teacher_id: int, body: TeacherClassesIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    """原子化替换教师的任教班级；保留未变班级上的班主任/副班主任角色。"""
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    desired = {name.strip() for name in body.class_names if name and name.strip()}
    for class_name in desired:
        ensure_school_class(db, class_name, grade=grade_of_class(class_name))
    existing = {
        tc.class_name: tc
        for tc in db.scalars(select(TeacherClass).where(TeacherClass.teacher_id == teacher_id)).all()
    }
    for class_name, tc in existing.items():
        if class_name not in desired:
            db.delete(tc)
    db.flush()
    for class_name in sorted(desired - set(existing)):
        db.add(TeacherClass(teacher_id=teacher_id, class_name=class_name, duty="teacher"))
    db.commit()
    return _serialize_full(db, teacher)


@router.get("/teaching")
def list_teaching(
    q: str = "",
    subject: str = "",
    grade: str = "",
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """全局任教关系视图：教师 × 班级，支持按学科/年级筛选。"""
    stmt = select(Teacher).where(Teacher.is_active.is_(True))
    if q:
        stmt = stmt.where(or_(Teacher.name.contains(q), Teacher.employee_no.contains(q)))
    teachers = db.scalars(stmt.order_by(Teacher.employee_no)).all()
    if subject:
        wanted = normalize_subject(subject)
        teachers = [t for t in teachers if normalize_subject(t.subject) == wanted]
    classes_map = _classes_by_teacher(db, [t.id for t in teachers])
    wanted_grade = normalize_grade(grade) if grade else None
    items = []
    for t in teachers:
        classes = classes_map.get(t.id, [])
        if wanted_grade:
            classes = [c for c in classes if grade_of_class(c) == wanted_grade]
            if not classes:
                continue
        items.append(
            {
                **serialize_teacher(t),
                "is_active": t.is_active,
                "classes": classes,
            }
        )
    return {"total": len(items), "items": items}
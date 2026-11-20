"""Class roster with balances and group memberships; class registry & teacher assignments."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, SchoolClass, Semester, Student, Teacher, TeacherClass
from ..security import get_current_teacher, get_db, require_admin
from ..services.access import all_class_names, assert_class_access, is_admin, is_subject_lead
from ..services.class_roles import (
    CLASS_MANAGER_DUTIES,
    assert_class_manager,
    get_assignment,
    normalize_duty,
    set_class_teacher,
)
from ..services.class_service import (
    class_has_students,
    class_summaries,
    create_class,
    ensure_school_class,
    rename_class,
    sync_classes_from_students,
)
from ..services.grades import grade_of_class, normalize_grade
from ..services.points import balances_for_students, like_counts_for_students, like_counts_for_teacher
from .auth import serialize_teacher
from .semesters import current_semester
from .students import serialize_student

router = APIRouter(prefix="/api/classes", tags=["classes"])


def _viewer_scope(db: Session, teacher: Teacher, class_name: str) -> str:
    """决定班级名单返回哪一级数据。

    - self：普通任课教师/学科组长，只看本人点赞；
    - class_manager：本班班主任/副班主任，额外看班级和学生总点赞；
    - admin：校长/主任，额外看学生官方星灿币余额。
    """
    if is_admin(teacher):
        return "admin"
    assignment = get_assignment(db, teacher.id, class_name)
    if assignment is not None and assignment.duty in CLASS_MANAGER_DUTIES:
        return "class_manager"
    return "self"


class AssignTeacherIn(BaseModel):
    teacher_id: int
    duty: str = "teacher"


class ClassIn(BaseModel):
    grade: str
    class_no: int = Field(ge=1, le=200)
    enrollment_year: int | None = None
    name: str | None = None


class ClassPatch(BaseModel):
    name: str | None = None
    grade: str | None = None
    class_no: int | None = Field(None, ge=1, le=200)
    enrollment_year: int | None = None
    is_active: bool | None = None


class BulkClassItem(BaseModel):
    grade: str
    count: int = Field(ge=1, le=200)
    start: int = Field(1, ge=1, le=200)
    enrollment_year: int | None = None


class BulkClassesIn(BaseModel):
    items: list[BulkClassItem]


@router.get("")
def list_classes(admin=Depends(require_admin), db: Session = Depends(get_db)):
    return all_class_names(db)


@router.get("/registry")
def class_registry(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    # 学科组长需要按班级筛选本科目统计，因此允许只读班级列表
    if not (is_admin(teacher) or is_subject_lead(teacher)):
        raise HTTPException(status_code=403, detail="需要管理员或学科组长权限")
    return {"items": class_summaries(db)}


@router.post("/registry")
def create_class_route(body: ClassIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    try:
        klass = create_class(
            db,
            grade=body.grade,
            class_no=body.class_no,
            enrollment_year=body.enrollment_year,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return {"id": klass.id, "name": klass.name, "grade": klass.grade}


@router.post("/registry/bulk")
def bulk_create_classes(body: BulkClassesIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    created, skipped = [], []
    for item in body.items:
        for number in range(item.start, item.start + item.count):
            try:
                klass = create_class(
                    db,
                    grade=item.grade,
                    class_no=number,
                    enrollment_year=item.enrollment_year,
                )
            except ValueError:
                skipped.append(f"{normalize_grade(item.grade) or item.grade}{number}班")
                continue
            created.append({"id": klass.id, "name": klass.name, "grade": klass.grade})
    db.commit()
    return {"created": len(created), "skipped": len(skipped), "items": created, "skipped_names": skipped}


@router.post("/registry/sync")
def sync_classes(admin=Depends(require_admin), db: Session = Depends(get_db)):
    summary = sync_classes_from_students(db)
    db.commit()
    return summary


@router.patch("/registry/{class_id}")
def update_class(class_id: int, body: ClassPatch, admin=Depends(require_admin), db: Session = Depends(get_db)):
    klass = db.get(SchoolClass, class_id)
    if klass is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        if body.name is not None and body.name.strip() != klass.name:
            rename_class(db, klass, body.name)
        if body.grade is not None:
            klass.grade = normalize_grade(body.grade) or klass.grade
        if body.class_no is not None:
            klass.class_no = body.class_no
        if body.enrollment_year is not None:
            klass.enrollment_year = body.enrollment_year
        if body.is_active is not None:
            klass.is_active = body.is_active
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return {"id": klass.id, "name": klass.name, "grade": klass.grade, "is_active": klass.is_active}


@router.delete("/registry/{class_id}")
def deactivate_class(class_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    klass = db.get(SchoolClass, class_id)
    if klass is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    if class_has_students(db, klass.name):
        raise HTTPException(status_code=400, detail="该班级还有学生，请先转班或停用学生")
    klass.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/{class_name}/teachers")
def class_teachers(class_name: str, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    assert_class_access(db, teacher, class_name)
    rows = db.execute(
        select(Teacher, TeacherClass.duty)
        .join(TeacherClass, TeacherClass.teacher_id == Teacher.id)
        .where(TeacherClass.class_name == class_name, Teacher.is_active.is_(True))
        .order_by(Teacher.employee_no)
    ).all()
    return {"items": [{**serialize_teacher(t), "duty": duty} for t, duty in rows]}


@router.post("/{class_name}/teachers")
def assign_class_teacher(
    class_name: str,
    body: AssignTeacherIn,
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    assert_class_manager(db, teacher, class_name, teacher_management=True)
    target = db.get(Teacher, body.teacher_id)
    if target is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    try:
        duty = normalize_duty(body.duty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ensure_school_class(db, class_name, grade=grade_of_class(class_name))
    assignment = set_class_teacher(db, target.id, class_name, duty)
    db.commit()
    return {"ok": True, "teacher_id": target.id, "duty": assignment.duty}


@router.delete("/{class_name}/teachers/{teacher_id}")
def remove_class_teacher(
    class_name: str,
    teacher_id: int,
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    assert_class_manager(db, teacher, class_name, teacher_management=True)
    tc = db.scalar(
        select(TeacherClass).where(TeacherClass.teacher_id == teacher_id, TeacherClass.class_name == class_name)
    )
    if tc is not None:
        db.delete(tc)
        db.commit()
    return {"ok": True}


@router.get("/{class_name}/roster")
def class_roster(
    class_name: str,
    request: Request,
    semester_id: int | None = Query(None),
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    assert_class_access(db, teacher, class_name)
    scope = _viewer_scope(db, teacher, class_name)
    semester = db.get(Semester, semester_id) if semester_id else current_semester(db)
    students = db.scalars(
        select(Student)
        .where(Student.class_name == class_name, Student.is_active.is_(True))
        .order_by(Student.student_no)
    ).all()
    ids = [s.id for s in students]
    semester_key = semester.id if semester else None
    my_counts = like_counts_for_teacher(db, teacher.id, ids, semester_key, class_name)
    totals = (
        like_counts_for_students(db, ids, semester_key, class_name)
        if scope in ("class_manager", "admin")
        else {}
    )
    balances = (
        balances_for_students(db, ids, semester_key, request.app.state.settings.coins_per_like)
        if scope == "admin"
        else {}
    )
    memberships = db.execute(
        select(GroupMember.student_id, Group.name)
        .join(Group, GroupMember.group_id == Group.id)
        .where(GroupMember.student_id.in_(ids))
    ).all()
    groups_by_student: dict[int, list[str]] = {}
    for student_id, group_name in memberships:
        groups_by_student.setdefault(student_id, []).append(group_name)
    items = []
    for s in students:
        item = {**serialize_student(s), **my_counts[s.id], "groups": groups_by_student.get(s.id, [])}
        if scope in ("class_manager", "admin"):
            item.update(totals[s.id])
        if scope == "admin":
            item.update(balances[s.id])
        items.append(item)
    payload = {
        "class_name": class_name,
        "semester_id": semester_key,
        "viewer_scope": scope,
        "items": items,
    }
    if scope in ("class_manager", "admin"):
        payload["class_semester_likes"] = sum(x["student_semester_likes"] for x in totals.values())
        payload["class_total_likes"] = sum(x["student_total_likes"] for x in totals.values())
    return payload
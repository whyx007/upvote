"""Class-scoped duties and permission checks.

角色挂在“教师 × 班级”关系上：同一教师可在不同班级担任不同角色。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Teacher, TeacherClass

DUTY_TEACHER = "teacher"
DUTY_HEAD = "head"
DUTY_DEPUTY = "deputy"
CLASS_MANAGER_DUTIES = (DUTY_HEAD, DUTY_DEPUTY)
DUTY_LABELS = {DUTY_TEACHER: "任课教师", DUTY_HEAD: "班主任", DUTY_DEPUTY: "副班主任"}
_DUTY_ALIASES = {
    "": None,
    "任课": DUTY_TEACHER,
    "任课教师": DUTY_TEACHER,
    "teacher": DUTY_TEACHER,
    "班主任": DUTY_HEAD,
    "head": DUTY_HEAD,
    "副班主任": DUTY_DEPUTY,
    "deputy": DUTY_DEPUTY,
}


def normalize_duty(value: str | None, *, preserve_when_empty: bool = False):
    """Normalize Chinese/English duty input; empty can mean preserve existing."""
    raw = (value or "").strip()
    if raw not in _DUTY_ALIASES:
        raise ValueError("班级角色只能为：任课教师、班主任、副班主任")
    duty = _DUTY_ALIASES[raw]
    if duty is None and not preserve_when_empty:
        return DUTY_TEACHER
    return duty


def get_assignment(db: Session, teacher_id: int, class_name: str) -> TeacherClass | None:
    return db.scalar(
        select(TeacherClass).where(TeacherClass.teacher_id == teacher_id, TeacherClass.class_name == class_name)
    )


def set_class_teacher(db: Session, teacher_id: int, class_name: str, duty: str = DUTY_TEACHER) -> TeacherClass:
    """Upsert an assignment and keep at most one head/deputy per class.

    Caller controls the transaction; this function flushes but does not commit.
    """
    assignment = get_assignment(db, teacher_id, class_name)
    if assignment is None:
        assignment = TeacherClass(teacher_id=teacher_id, class_name=class_name, duty=duty)
        db.add(assignment)
    else:
        assignment.duty = duty
    if duty in CLASS_MANAGER_DUTIES:
        others = db.scalars(
            select(TeacherClass).where(
                TeacherClass.class_name == class_name,
                TeacherClass.duty == duty,
                TeacherClass.teacher_id != teacher_id,
            )
        ).all()
        for other in others:
            other.duty = DUTY_TEACHER
    db.flush()
    return assignment


def assert_class_manager(
    db: Session,
    teacher: Teacher,
    class_name: str,
    *,
    teacher_management: bool = False,
) -> TeacherClass | None:
    """Allow admins and class managers; teacher assignments require head specifically."""
    if teacher.role == "admin":
        return None
    assignment = get_assignment(db, teacher.id, class_name)
    if assignment is None or assignment.duty not in CLASS_MANAGER_DUTIES:
        raise HTTPException(status_code=403, detail="只有班主任或副班主任可以管理本班")
    if teacher_management and assignment.duty != DUTY_HEAD:
        raise HTTPException(status_code=403, detail="只有班主任可以调整本班任课教师")
    return assignment


def assert_any_class_manager(db: Session, teacher: Teacher) -> None:
    if teacher.role == "admin":
        return
    exists = db.scalar(
        select(TeacherClass.id).where(
            TeacherClass.teacher_id == teacher.id, TeacherClass.duty.in_(CLASS_MANAGER_DUTIES)
        )
    )
    if exists is None:
        raise HTTPException(status_code=403, detail="仅班主任或副班主任可查看教师选项")


def assert_class_group_manager(db: Session, teacher: Teacher, class_name: str) -> None:
    """小组管理：校长/主任全权；学科组长限本人任教班；班主任/副班主任限本班。"""
    from .access import assigned_class_names, is_admin, is_subject_lead

    if is_admin(teacher):
        return
    if is_subject_lead(teacher):
        if class_name in assigned_class_names(db, teacher):
            return
        raise HTTPException(status_code=403, detail="学科组长只能管理本人任教班级的小组")
    assert_class_manager(db, teacher, class_name)
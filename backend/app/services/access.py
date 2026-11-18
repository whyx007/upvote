"""集中鉴权：班级可见范围、点赞范围、统计范围。

三层数据权限：
- teacher（任课教师）：只看/操作本人任教班，只统计本人；
- subject_lead（学科组长）：任教班同教师；额外可看同学科教师的使用统计与明细；
- admin（校长/主任）：全校。
班主任/副班主任是“班级职责”，在 class_roles 中单独判断，与三层数据权限叠加。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SchoolClass, Student, Teacher, TeacherClass
from .subjects import normalize_subject

ROLE_TEACHER = "teacher"
ROLE_SUBJECT_LEAD = "subject_lead"
ROLE_ADMIN = "admin"
ROLES = (ROLE_TEACHER, ROLE_SUBJECT_LEAD, ROLE_ADMIN)
ROLE_LABELS = {ROLE_TEACHER: "任课教师", ROLE_SUBJECT_LEAD: "学科组长", ROLE_ADMIN: "校长/主任"}


def is_admin(teacher: Teacher) -> bool:
    return teacher.role == ROLE_ADMIN


def is_subject_lead(teacher: Teacher) -> bool:
    return teacher.role == ROLE_SUBJECT_LEAD


def normalize_role(value: str | None, default: str = ROLE_TEACHER) -> str:
    raw = (value or "").strip()
    aliases = {
        "": default,
        "teacher": ROLE_TEACHER,
        "任课教师": ROLE_TEACHER,
        "教师": ROLE_TEACHER,
        "subject_lead": ROLE_SUBJECT_LEAD,
        "学科组长": ROLE_SUBJECT_LEAD,
        "组长": ROLE_SUBJECT_LEAD,
        "admin": ROLE_ADMIN,
        "管理员": ROLE_ADMIN,
        "校长": ROLE_ADMIN,
        "主任": ROLE_ADMIN,
        "校长/主任": ROLE_ADMIN,
    }
    if raw not in aliases:
        raise ValueError("角色只能为：任课教师、学科组长、校长/主任")
    return aliases[raw]


def all_class_names(db: Session) -> list[str]:
    names: set[str] = set()
    names.update(db.scalars(select(SchoolClass.name).where(SchoolClass.is_active.is_(True))).all())
    names.update(db.scalars(select(Student.class_name).where(Student.is_active.is_(True)).distinct()).all())
    names.update(db.scalars(select(TeacherClass.class_name).distinct()).all())
    return sorted((n for n in names if n), key=_class_sort)


def assigned_class_names(db: Session, teacher: Teacher) -> list[str]:
    names = db.scalars(select(TeacherClass.class_name).where(TeacherClass.teacher_id == teacher.id)).all()
    return sorted({n for n in names if n}, key=_class_sort)


def visible_class_names(db: Session, teacher: Teacher) -> list[str]:
    if is_admin(teacher):
        return all_class_names(db)
    return assigned_class_names(db, teacher)


def assert_class_access(db: Session, teacher: Teacher, class_name: str) -> None:
    if is_admin(teacher):
        return
    if class_name not in assigned_class_names(db, teacher):
        raise HTTPException(status_code=403, detail="无权访问该班级")


def assert_like_access(db: Session, teacher: Teacher, class_name: str) -> None:
    if is_admin(teacher):
        return
    if class_name not in assigned_class_names(db, teacher):
        raise HTTPException(status_code=403, detail="只能给本人任教班级的学生点赞")


def stats_scope_label(teacher: Teacher) -> str:
    if is_admin(teacher):
        return "全校"
    if is_subject_lead(teacher):
        return f"{normalize_subject(teacher.subject) or '未设学科'}学科"
    return "本人"


def stats_teachers(db: Session, teacher: Teacher) -> list[Teacher]:
    """返回当前账号可见统计的教师列表。"""
    if is_admin(teacher):
        return db.scalars(select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.employee_no)).all()
    if is_subject_lead(teacher):
        subject = normalize_subject(teacher.subject)
        if not subject:
            raise HTTPException(status_code=403, detail="学科组长尚未设置学科，请联系管理员")
        teachers = db.scalars(select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.employee_no)).all()
        return [t for t in teachers if normalize_subject(t.subject) == subject]
    return [teacher]


def assert_stats_teacher(teacher: Teacher, target: Teacher) -> None:
    if is_admin(teacher):
        return
    if is_subject_lead(teacher):
        if normalize_subject(target.subject) != normalize_subject(teacher.subject):
            raise HTTPException(status_code=403, detail="只能查看本科目教师的统计")
        return
    if target.id != teacher.id:
        raise HTTPException(status_code=403, detail="只能查看本人统计")


def _class_sort(name: str):
    from .grades import class_sort_key

    return class_sort_key(name)
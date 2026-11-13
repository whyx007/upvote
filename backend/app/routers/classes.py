"""Class roster with balances and group memberships; class teacher assignments."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, Semester, Student, Teacher, TeacherClass
from ..security import get_current_teacher, get_db, require_admin
from ..services.points import balances_for_students
from .auth import serialize_teacher
from .semesters import current_semester
from .students import serialize_student

router = APIRouter(prefix="/api/classes", tags=["classes"])


class AssignTeacherIn(BaseModel):
    teacher_id: int


@router.get("")
def list_classes(teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    classes = db.scalars(select(Student.class_name).where(Student.is_active.is_(True)).distinct()).all()
    return sorted(set(classes))


@router.get("/{class_name}/teachers")
def class_teachers(class_name: str, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    teachers = db.scalars(
        select(Teacher)
        .join(TeacherClass, TeacherClass.teacher_id == Teacher.id)
        .where(TeacherClass.class_name == class_name, Teacher.is_active.is_(True))
        .order_by(Teacher.employee_no)
    ).all()
    return {"items": [serialize_teacher(t) for t in teachers]}


@router.post("/{class_name}/teachers")
def assign_class_teacher(class_name: str, body: AssignTeacherIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Teacher, body.teacher_id)
    if t is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    exists = db.scalar(
        select(TeacherClass).where(TeacherClass.teacher_id == t.id, TeacherClass.class_name == class_name)
    )
    if exists is None:
        db.add(TeacherClass(teacher_id=t.id, class_name=class_name))
        db.commit()
    return {"ok": True}


@router.delete("/{class_name}/teachers/{teacher_id}")
def remove_class_teacher(class_name: str, teacher_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
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
    semester = db.get(Semester, semester_id) if semester_id else current_semester(db)
    students = db.scalars(
        select(Student)
        .where(Student.class_name == class_name, Student.is_active.is_(True))
        .order_by(Student.student_no)
    ).all()
    ids = [s.id for s in students]
    balances = balances_for_students(
        db, ids, semester.id if semester else None, request.app.state.settings.coins_per_like
    )
    memberships = db.execute(
        select(GroupMember.student_id, Group.name)
        .join(Group, GroupMember.group_id == Group.id)
        .where(GroupMember.student_id.in_(ids))
    ).all()
    groups_by_student: dict[int, list[str]] = {}
    for student_id, group_name in memberships:
        groups_by_student.setdefault(student_id, []).append(group_name)
    items = [
        {**serialize_student(s), **balances[s.id], "groups": groups_by_student.get(s.id, [])}
        for s in students
    ]
    return {"class_name": class_name, "semester_id": semester.id if semester else None, "items": items}
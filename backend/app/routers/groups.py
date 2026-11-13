from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, Student
from ..security import get_current_teacher, get_db, require_admin

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    name: str
    class_name: str
    member_student_nos: list[str] = []


class GroupPatch(BaseModel):
    name: str | None = None
    class_name: str | None = None
    member_student_nos: list[str] | None = None


def _resolve_members(db: Session, student_nos: list[str]) -> list[Student]:
    students = []
    missing = []
    for no in student_nos:
        student = db.scalar(select(Student).where(Student.student_no == no))
        if student is None:
            missing.append(no)
        else:
            students.append(student)
    if missing:
        raise HTTPException(status_code=400, detail=f"成员学号不存在：{','.join(missing)}")
    return students


def _serialize(db: Session, g: Group) -> dict:
    count = db.scalar(select(func.count(GroupMember.id)).where(GroupMember.group_id == g.id))
    return {"id": g.id, "name": g.name, "class_name": g.class_name, "member_count": count}


@router.get("")
def list_groups(
    class_name: str = "",
    include_members: bool = False,
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    stmt = select(Group)
    if class_name:
        stmt = stmt.where(Group.class_name == class_name)
    groups = db.scalars(stmt.order_by(Group.class_name, Group.name)).all()
    items = []
    for g in groups:
        item = _serialize(db, g)
        if include_members:
            members = db.scalars(
                select(Student)
                .join(GroupMember, GroupMember.student_id == Student.id)
                .where(GroupMember.group_id == g.id)
                .order_by(Student.student_no)
            ).all()
            item["members"] = [{"id": s.id, "student_no": s.student_no, "name": s.name} for s in members]
        items.append(item)
    return {"items": items}


@router.post("")
def create_group(body: GroupIn, admin=Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Group).where(Group.name == body.name, Group.class_name == body.class_name)):
        raise HTTPException(status_code=400, detail="同班级下小组名称已存在")
    students = _resolve_members(db, body.member_student_nos)
    group = Group(name=body.name, class_name=body.class_name)
    db.add(group)
    db.flush()
    for student in students:
        db.add(GroupMember(group_id=group.id, student_id=student.id))
    db.commit()
    return _serialize(db, group)


@router.patch("/{group_id}")
def update_group(group_id: int, body: GroupPatch, admin=Depends(require_admin), db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="小组不存在")
    data = body.model_dump(exclude_unset=True)
    member_nos = data.pop("member_student_nos", None)
    for field, value in data.items():
        setattr(group, field, value)
    if member_nos is not None:
        students = _resolve_members(db, member_nos)
        for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all():
            db.delete(m)
        db.flush()
        for student in students:
            db.add(GroupMember(group_id=group.id, student_id=student.id))
    db.commit()
    return _serialize(db, group)


@router.delete("/{group_id}")
def delete_group(group_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="小组不存在")
    for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all():
        db.delete(m)
    db.delete(group)
    db.commit()
    return {"ok": True}
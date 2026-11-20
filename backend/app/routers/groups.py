import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, Student
from ..security import get_current_teacher, get_db
from ..services.access import assert_class_access, visible_class_names
from ..services.class_roles import assert_class_group_manager
from ..services.class_service import ensure_school_class
from ..services.grades import class_sort_key
from ..services.group_names import group_sort_key, next_group_names

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    name: str
    class_name: str
    member_student_nos: list[str] = []


class GroupPatch(BaseModel):
    name: str | None = None
    class_name: str | None = None
    member_student_nos: list[str] | None = None


class GroupBatchIn(BaseModel):
    class_name: str
    names: list[str] | None = Field(default=None, max_length=100)
    count: int | None = Field(default=None, ge=1, le=100)


class GroupRandomizeIn(BaseModel):
    class_name: str


def _resolve_members(db: Session, student_nos: list[str], class_name: str) -> list[Student]:
    students = []
    missing = []
    wrong_class = []
    for no in student_nos:
        student = db.scalar(select(Student).where(Student.student_no == no))
        if student is None:
            missing.append(no)
        elif student.class_name != class_name:
            wrong_class.append(no)
        else:
            students.append(student)
    if missing:
        raise HTTPException(status_code=400, detail=f"成员学号不存在：{','.join(missing)}")
    if wrong_class:
        raise HTTPException(status_code=400, detail=f"成员不属于本班：{','.join(wrong_class)}")
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
        assert_class_access(db, teacher, class_name)
        stmt = stmt.where(Group.class_name == class_name)
    else:
        stmt = stmt.where(Group.class_name.in_(visible_class_names(db, teacher) or ["__none__"]))
    groups = list(db.scalars(stmt).all())
    groups.sort(key=lambda group: (class_sort_key(group.class_name), group_sort_key(group.name)))
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
def create_group(body: GroupIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    assert_class_group_manager(db, teacher, body.class_name)
    if db.scalar(select(Group).where(Group.name == body.name, Group.class_name == body.class_name)):
        raise HTTPException(status_code=400, detail="同班级下小组名称已存在")
    students = _resolve_members(db, body.member_student_nos, body.class_name)
    ensure_school_class(db, body.class_name)
    group = Group(name=body.name, class_name=body.class_name)
    db.add(group)
    db.flush()
    for student in students:
        db.add(GroupMember(group_id=group.id, student_id=student.id))
    db.commit()
    return _serialize(db, group)


@router.post("/batch")
def create_groups_batch(body: GroupBatchIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    """批量新增小组。

    - 传 count：按已有“第N组/第一组”的序号自动续号；
    - 传 names：按给定名称创建，已存在的名称跳过。
    """
    assert_class_group_manager(db, teacher, body.class_name)
    if body.count is not None and body.names:
        raise HTTPException(status_code=400, detail="count 和 names 只能提供一个")

    ensure_school_class(db, body.class_name)
    existing = set(
        db.scalars(select(Group.name).where(Group.class_name == body.class_name)).all()
    )

    if body.count is not None:
        names = next_group_names(existing, body.count)
        skipped: list[str] = []
    else:
        names = []
        for raw in body.names or []:
            name = (raw or "").strip()
            if not name or name in names:
                continue
            if len(name) > 64:
                raise HTTPException(status_code=400, detail=f"小组名称过长：{name[:20]}…")
            names.append(name)
        if not names:
            raise HTTPException(status_code=400, detail="请至少提供一个小组名称")
        skipped = [name for name in names if name in existing]
        names = [name for name in names if name not in existing]

    created: list[str] = []
    for name in names:
        if name in existing:
            continue
        db.add(Group(name=name, class_name=body.class_name))
        existing.add(name)
        created.append(name)
    db.commit()
    return {"created": len(created), "skipped": skipped, "items": created}


@router.post("/randomize")
def randomize_groups(body: GroupRandomizeIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    """只把尚未分组的学生随机补进空小组；已有成员不动。"""
    assert_class_group_manager(db, teacher, body.class_name)
    groups = db.scalars(
        select(Group).where(Group.class_name == body.class_name).order_by(Group.id)
    ).all()
    if not groups:
        raise HTTPException(status_code=400, detail="请先创建小组，再随机分组")
    students = db.scalars(
        select(Student)
        .where(Student.class_name == body.class_name, Student.is_active.is_(True))
        .order_by(Student.student_no)
    ).all()
    if not students:
        raise HTTPException(status_code=400, detail="该班级还没有学生")

    group_ids = [g.id for g in groups]
    memberships = db.execute(
        select(GroupMember.group_id, GroupMember.student_id).where(
            GroupMember.group_id.in_(group_ids)
        )
    ).all()
    occupied_group_ids = {group_id for group_id, _ in memberships}
    grouped_student_ids = {student_id for _, student_id in memberships}
    empty_groups = [group for group in groups if group.id not in occupied_group_ids]
    if not empty_groups:
        raise HTTPException(status_code=400, detail="没有空小组可补")
    ungrouped = [student for student in students if student.id not in grouped_student_ids]
    if not ungrouped:
        raise HTTPException(status_code=400, detail="没有未分组学生")

    shuffled = list(ungrouped)
    random.shuffle(shuffled)
    base, extra = divmod(len(shuffled), len(empty_groups))
    cursor = 0
    items = []
    for index, group in enumerate(empty_groups):
        size = base + (1 if index < extra else 0)
        for student in shuffled[cursor : cursor + size]:
            db.add(GroupMember(group_id=group.id, student_id=student.id))
        cursor += size
        items.append({"id": group.id, "name": group.name, "member_count": size})
    db.commit()
    return {"groups": len(empty_groups), "students": len(shuffled), "items": items}


@router.patch("/{group_id}")
def update_group(group_id: int, body: GroupPatch, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="小组不存在")
    assert_class_group_manager(db, teacher, group.class_name)
    data = body.model_dump(exclude_unset=True)
    if teacher.role != "admin" and data.get("class_name") not in (None, group.class_name):
        raise HTTPException(status_code=403, detail="班级管理角色不能将小组转到其他班级")
    member_nos = data.pop("member_student_nos", None)
    target_class = data.get("class_name", group.class_name)
    ensure_school_class(db, target_class)
    for field, value in data.items():
        setattr(group, field, value)
    if member_nos is not None:
        students = _resolve_members(db, member_nos, target_class)
        for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all():
            db.delete(m)
        db.flush()
        for student in students:
            db.add(GroupMember(group_id=group.id, student_id=student.id))
    db.commit()
    return _serialize(db, group)


@router.delete("/{group_id}")
def delete_group(group_id: int, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="小组不存在")
    assert_class_group_manager(db, teacher, group.class_name)
    for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all():
        db.delete(m)
    db.delete(group)
    db.commit()
    return {"ok": True}
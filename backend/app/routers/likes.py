"""One-tap likes (student / group fan-out), same-day batch revoke, recent feed."""
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, Like, Student, Teacher
from ..security import get_current_teacher, get_db
from ..services.access import assert_like_access
from ..services.points import like_counts_for_teacher
from .semesters import current_semester

router = APIRouter(prefix="/api/likes", tags=["likes"])


class LikeIn(BaseModel):
    target_type: Literal["student", "group"]
    target_id: int


class RevokeIn(BaseModel):
    batch_id: str


class DecrementIn(BaseModel):
    student_id: int


@router.post("")
def create_like(body: LikeIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    semester = current_semester(db)
    if semester is None:
        raise HTTPException(status_code=400, detail="当前没有激活的学期，请先在管理端创建并激活学期")
    group = None
    if body.target_type == "student":
        student = db.get(Student, body.target_id)
        if student is None or not student.is_active:
            raise HTTPException(status_code=404, detail="学生不存在")
        assert_like_access(db, teacher, student.class_name)
        targets = [student]
    else:
        group = db.get(Group, body.target_id)
        if group is None:
            raise HTTPException(status_code=404, detail="小组不存在")
        assert_like_access(db, teacher, group.class_name)
        targets = db.scalars(
            select(Student)
            .join(GroupMember, GroupMember.student_id == Student.id)
            .where(GroupMember.group_id == group.id, Student.is_active.is_(True))
        ).all()
        if not targets:
            raise HTTPException(status_code=400, detail="小组没有成员")
    batch_id = uuid4().hex
    for student in targets:
        db.add(
            Like(
                batch_id=batch_id,
                teacher_id=teacher.id,
                student_id=student.id,
                group_id=group.id if group else None,
                semester_id=semester.id,
                class_name=student.class_name,
            )
        )
    db.commit()
    class_name = targets[0].class_name if targets else None
    my_counts = like_counts_for_teacher(
        db, teacher.id, [s.id for s in targets], semester.id, class_name
    )
    return {
        "batch_id": batch_id,
        "count": len(targets),
        "likes": [
            {"student_id": s.id, "student_name": s.name, **my_counts[s.id]}
            for s in targets
        ],
    }


@router.post("/decrement")
def decrement_like(body: DecrementIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    """课堂纠错：减少当前学期本人最近一次给该学生的点赞（-1）。"""
    student = db.get(Student, body.student_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=404, detail="学生不存在")
    assert_like_access(db, teacher, student.class_name)
    semester = current_semester(db)
    if semester is None:
        raise HTTPException(status_code=400, detail="当前没有激活的学期")
    like = db.scalar(
        select(Like)
        .where(
            Like.student_id == student.id,
            Like.semester_id == semester.id,
            Like.teacher_id == teacher.id,
            Like.revoked_at.is_(None),
        )
        .order_by(Like.id.desc())
        .limit(1)
    )
    if like is None:
        raise HTTPException(status_code=400, detail="没有可减少的点赞（只能减少本人本学期有效点赞）")
    if like.created_at.date() != date.today():
        raise HTTPException(status_code=400, detail="只能减少当日点赞，更早的请在管理端处理")
    like.revoked_at = datetime.now()
    db.commit()
    my_counts = like_counts_for_teacher(
        db, teacher.id, [student.id], semester.id, student.class_name
    )[student.id]
    return {"student_id": student.id, **my_counts, "count": 1}


@router.post("/revoke")
def revoke_like(body: RevokeIn, teacher=Depends(get_current_teacher), db: Session = Depends(get_db)):
    likes = db.scalars(select(Like).where(Like.batch_id == body.batch_id)).all()
    if not likes:
        raise HTTPException(status_code=404, detail="点赞记录不存在")
    if any(like.teacher_id != teacher.id for like in likes):
        raise HTTPException(status_code=403, detail="只能撤销本人的点赞")
    if any(like.revoked_at is not None for like in likes):
        raise HTTPException(status_code=400, detail="该点赞已撤销")
    if any(like.created_at.date() != date.today() for like in likes):
        raise HTTPException(status_code=400, detail="只能撤销当日点赞")
    now = datetime.now()
    for like in likes:
        like.revoked_at = now
    db.commit()
    return {"revoked_count": len(likes)}


@router.get("/recent")
def recent_likes(
    limit: int = Query(20, ge=1, le=100),
    class_name: str = "",
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    stmt = select(Like).order_by(Like.id.desc())
    if teacher.role != "admin":
        stmt = stmt.where(Like.teacher_id == teacher.id)
    if class_name:
        stmt = stmt.where(Like.class_name == class_name)
    likes = db.scalars(stmt.limit(300)).all()
    batches: dict[str, list[Like]] = {}
    for like in likes:
        batches.setdefault(like.batch_id, []).append(like)
    today = date.today()
    items = []
    for batch_id, batch_likes in list(batches.items())[:limit]:
        first = batch_likes[0]
        student_names = []
        for like in batch_likes:
            student = db.get(Student, like.student_id)
            if student and student.name not in student_names:
                student_names.append(student.name)
        group = db.get(Group, first.group_id) if first.group_id else None
        first_student = db.get(Student, first.student_id)
        items.append(
            {
                "batch_id": batch_id,
                "count": len(batch_likes),
                "student_names": student_names[:3],
                "group_name": group.name if group else None,
                "class_name": first.class_name
                or (first_student.class_name if first_student else None),
                "teacher_name": db.get(Teacher, first.teacher_id).name,
                "created_at": first.created_at.isoformat(),
                "revoked": first.revoked_at is not None,
                "can_revoke": first.teacher_id == teacher.id
                and first.revoked_at is None
                and first.created_at.date() == today,
            }
        )
    return {"items": items}
"""教师维度使用统计：按周/月/自定义区间汇总点赞数、使用天数、明细。"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Group, Like, Student, Teacher, TeacherClass
from .class_service import class_names_for_grade
from .grades import class_sort_key
from .subjects import normalize_subject

PERIODS = ("week", "month", "custom")


def resolve_period(
    period: str | None,
    start: date | None,
    end: date | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime, date, date]:
    """返回 [start_dt, end_dt) 与用于展示的起止日期（含）。"""
    now = now or datetime.now()
    period = (period or "month").strip().lower()
    if period not in PERIODS:
        raise HTTPException(status_code=400, detail="统计周期只能为 week/month/custom")
    today = now.date()
    if period == "custom":
        if start is None:
            raise HTTPException(status_code=400, detail="自定义统计需要开始日期")
        end = end or today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = today
    else:  # month
        start = today.replace(day=1)
        end = today
    if end < start:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    if period != "custom":
        # 本周/本月统计到当前时刻即可，不把未来时间算进去
        end_dt = min(end_dt, now + timedelta(seconds=1))
    return start_dt, end_dt, start, end


def usage_report(
    db: Session,
    teachers: list[Teacher],
    start_dt: datetime,
    end_dt: datetime,
    *,
    grade: str | None = None,
    class_name: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    teacher_ids = [t.id for t in teachers]
    if not teacher_ids:
        return {
            "items": [],
            "summary": {
                "teacher_count": 0,
                "active_teachers": 0,
                "total_likes": 0,
                "start_date": (start_date or start_dt.date()).isoformat(),
                "end_date": (end_date or (end_dt - timedelta(days=1)).date()).isoformat(),
            },
        }

    conditions = [Like.revoked_at.is_(None), Like.created_at >= start_dt, Like.created_at < end_dt]
    conditions.append(Like.teacher_id.in_(teacher_ids))
    if class_name:
        conditions.append(Student.class_name == class_name)
    elif grade:
        names = class_names_for_grade(db, grade)
        conditions.append(Student.class_name.in_(names or ["__none__"]))

    rows = db.execute(
        select(
            Like.teacher_id,
            func.count(Like.id),
            func.count(func.distinct(Like.student_id)),
            func.count(func.distinct(func.date(Like.created_at))),
            func.min(Like.created_at),
            func.max(Like.created_at),
            func.group_concat(func.distinct(Student.class_name)),
        )
        .join(Student, Like.student_id == Student.id)
        .where(*conditions)
        .group_by(Like.teacher_id)
    ).all()
    stats = {
        teacher_id: {
            "like_count": like_count,
            "student_count": student_count,
            "active_days": active_days,
            "first_like_at": first,
            "last_like_at": last,
            "liked_classes": sorted({c for c in (classes or "").split(",") if c}, key=class_sort_key),
        }
        for teacher_id, like_count, student_count, active_days, first, last, classes in rows
    }

    assignments: dict[int, list[str]] = {}
    for teacher_id, cls in db.execute(
        select(TeacherClass.teacher_id, TeacherClass.class_name)
        .where(TeacherClass.teacher_id.in_(teacher_ids))
        .order_by(TeacherClass.class_name)
    ).all():
        assignments.setdefault(teacher_id, []).append(cls)
    for names in assignments.values():
        names.sort(key=class_sort_key)

    items = []
    for teacher in teachers:
        row = stats.get(teacher.id, {})
        items.append(
            {
                "teacher_id": teacher.id,
                "employee_no": teacher.employee_no,
                "name": teacher.name,
                "subject": normalize_subject(teacher.subject),
                "role": teacher.role,
                "classes": assignments.get(teacher.id, []),
                "liked_classes": row.get("liked_classes", []),
                "like_count": row.get("like_count", 0),
                "student_count": row.get("student_count", 0),
                "active_days": row.get("active_days", 0),
                "first_like_at": row["first_like_at"].isoformat() if row.get("first_like_at") else None,
                "last_like_at": row["last_like_at"].isoformat() if row.get("last_like_at") else None,
            }
        )
    items.sort(key=lambda x: (-x["like_count"], x["name"]))
    return {
        "items": items,
        "summary": {
            "teacher_count": len(teachers),
            "active_teachers": sum(1 for x in items if x["like_count"] > 0),
            "total_likes": sum(x["like_count"] for x in items),
            "start_date": (start_date or start_dt.date()).isoformat(),
            "end_date": (end_date or (end_dt - timedelta(days=1)).date()).isoformat(),
        },
    }


def usage_detail(
    db: Session,
    teacher_id: int,
    start_dt: datetime,
    end_dt: datetime,
    *,
    grade: str | None = None,
    class_name: str | None = None,
    limit: int = 500,
) -> list[dict]:
    conditions = [
        Like.teacher_id == teacher_id,
        Like.revoked_at.is_(None),
        Like.created_at >= start_dt,
        Like.created_at < end_dt,
    ]
    if class_name:
        conditions.append(Student.class_name == class_name)
    elif grade:
        names = class_names_for_grade(db, grade)
        conditions.append(Student.class_name.in_(names or ["__none__"]))
    rows = db.execute(
        select(Like, Student)
        .join(Student, Like.student_id == Student.id)
        .where(*conditions)
        .order_by(Like.created_at.desc(), Like.id.desc())
        .limit(limit)
    ).all()
    items = []
    for like, student in rows:
        group = db.get(Group, like.group_id) if like.group_id else None
        items.append(
            {
                "id": like.id,
                "student_id": student.id,
                "student_name": student.name,
                "student_no": student.student_no,
                "class_name": student.class_name,
                "group_name": group.name if group else None,
                "created_at": like.created_at.isoformat(),
            }
        )
    return items
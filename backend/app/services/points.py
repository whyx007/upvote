"""Point balances / like counts: valid likes minus confirmed redemptions.

- balances_for_students：学生官方余额（所有老师汇总），仅管理员/兑换使用。
- like_counts_for_students：学生收到的点赞数（所有老师汇总），供班主任/副班主任查看。
- like_counts_for_teacher：当前查看者自己给出的点赞数，供所有教师查看自己的数据。
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Like, Redemption


def _like_counts(db: Session, student_ids, *extra) -> dict[int, int]:
    stmt = (
        select(Like.student_id, func.count(Like.id))
        .where(Like.student_id.in_(student_ids), Like.revoked_at.is_(None), *extra)
        .group_by(Like.student_id)
    )
    return dict(db.execute(stmt).all())


def like_counts_for_students(db: Session, student_ids, semester_id) -> dict:
    """Return {student_id: {student_semester_likes, student_total_likes}}.

    这是“该学生收到的全部有效点赞”，不区分老师，只给班主任/副班主任和管理员。
    """
    ids = list(student_ids)
    if not ids:
        return {}
    total = _like_counts(db, ids)
    semester = _like_counts(db, ids, Like.semester_id == semester_id) if semester_id is not None else {}
    return {
        sid: {
            "student_semester_likes": semester.get(sid, 0),
            "student_total_likes": total.get(sid, 0),
        }
        for sid in ids
    }


def like_counts_for_teacher(db: Session, teacher_id: int, student_ids, semester_id) -> dict:
    """Return {student_id: {my_semester_likes, my_total_likes}} for one teacher."""
    ids = list(student_ids)
    if not ids:
        return {}
    total = _like_counts(db, ids, Like.teacher_id == teacher_id)
    semester = (
        _like_counts(db, ids, Like.teacher_id == teacher_id, Like.semester_id == semester_id)
        if semester_id is not None
        else {}
    )
    return {
        sid: {
            "my_semester_likes": semester.get(sid, 0),
            "my_total_likes": total.get(sid, 0),
        }
        for sid in ids
    }


def balances_for_students(db: Session, student_ids, semester_id, coins_per_like: int) -> dict:
    """Return {student_id: {semester_balance, total_balance}}."""
    ids = list(student_ids)
    if not ids:
        return {}

    def like_counts(*extra):
        stmt = (
            select(Like.student_id, func.count(Like.id))
            .where(Like.student_id.in_(ids), Like.revoked_at.is_(None), *extra)
            .group_by(Like.student_id)
        )
        return dict(db.execute(stmt).all())

    def redemption_sums(*extra):
        stmt = (
            select(Redemption.student_id, func.sum(Redemption.cost_coins))
            .where(Redemption.student_id.in_(ids), Redemption.cancelled_at.is_(None), *extra)
            .group_by(Redemption.student_id)
        )
        return dict(db.execute(stmt).all())

    total_likes = like_counts()
    total_red = redemption_sums()
    if semester_id is not None:
        sem_likes = like_counts(Like.semester_id == semester_id)
        sem_red = redemption_sums(Redemption.semester_id == semester_id)
    else:
        sem_likes, sem_red = {}, {}
    return {
        sid: {
            "semester_balance": sem_likes.get(sid, 0) * coins_per_like - sem_red.get(sid, 0),
            "total_balance": total_likes.get(sid, 0) * coins_per_like - total_red.get(sid, 0),
        }
        for sid in ids
    }
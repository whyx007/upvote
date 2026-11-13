"""Point balances: valid likes minus confirmed redemptions, per semester and total."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Like, Redemption


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
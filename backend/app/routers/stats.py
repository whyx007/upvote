"""Overview stats and Excel export of student balances."""
import io

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Like, Redemption, Student, Teacher
from ..security import get_current_teacher, get_db
from ..services.points import balances_for_students
from .semesters import current_semester

router = APIRouter(prefix="/api/stats", tags=["stats"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _semester(db, semester_id):
    from ..models import Semester

    return db.get(Semester, semester_id) if semester_id else current_semester(db)


@router.get("/overview")
def overview(
    request: Request,
    semester_id: int | None = Query(None),
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    semester = _semester(db, semester_id)
    coins = request.app.state.settings.coins_per_like
    students = db.scalars(select(Student).where(Student.is_active.is_(True))).all()
    total_teachers = db.scalar(select(func.count(Teacher.id)).where(Teacher.is_active.is_(True)))

    like_filters = [Like.revoked_at.is_(None)]
    red_filters = [Redemption.cancelled_at.is_(None)]
    if semester is not None:
        like_filters.append(Like.semester_id == semester.id)
        red_filters.append(Redemption.semester_id == semester.id)
    total_likes = db.scalar(select(func.count(Like.id)).where(*like_filters))
    total_redemptions = db.scalar(select(func.count(Redemption.id)).where(*red_filters))
    total_coins_redeemed = db.scalar(select(func.coalesce(func.sum(Redemption.cost_coins), 0)).where(*red_filters))

    balances = balances_for_students(db, [s.id for s in students], semester.id if semester else None, coins)
    ranked = sorted(students, key=lambda s: balances[s.id]["semester_balance"], reverse=True)
    top_students = [
        {
            "student_no": s.student_no,
            "name": s.name,
            "class_name": s.class_name,
            **balances[s.id],
        }
        for s in ranked[:10]
    ]

    per_class = []
    class_names = sorted({s.class_name for s in students})
    for class_name in class_names:
        class_students = [s for s in students if s.class_name == class_name]
        class_likes = db.scalar(
            select(func.count(Like.id))
            .join(Student, Like.student_id == Student.id)
            .where(Student.class_name == class_name, *like_filters)
        )
        per_class.append({"class_name": class_name, "student_count": len(class_students), "likes": class_likes})

    return {
        "semester": {"id": semester.id, "name": semester.name} if semester else None,
        "total_students": len(students),
        "total_teachers": total_teachers,
        "total_likes": total_likes,
        "total_coins_issued": total_likes * coins,
        "total_redemptions": total_redemptions,
        "total_coins_redeemed": total_coins_redeemed,
        "top_students": top_students,
        "per_class": per_class,
    }


@router.get("/export")
def export_balances(
    request: Request,
    semester_id: int | None = Query(None),
    admin=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    semester = _semester(db, semester_id)
    students = db.scalars(
        select(Student).where(Student.is_active.is_(True)).order_by(Student.class_name, Student.student_no)
    ).all()
    balances = balances_for_students(
        db, [s.id for s in students], semester.id if semester else None, request.app.state.settings.coins_per_like
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "星灿币统计"
    ws.append(["学号", "姓名", "年级", "班级", "学期星灿币", "累计星灿币"])
    for s in students:
        b = balances[s.id]
        ws.append([s.student_no, s.name, s.grade, s.class_name, b["semester_balance"], b["total_balance"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=upvote_stats.xlsx"},
    )
"""Overview stats, teacher usage reports and Excel exports."""
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Like, Redemption, Student, Teacher
from ..security import get_current_teacher, get_db, require_admin
from ..services.access import assert_stats_teacher, is_subject_lead, stats_teachers
from ..services.grades import class_sort_key, normalize_grade
from ..services.points import balances_for_students
from ..services.subjects import normalize_subject
from ..services.usage import resolve_period, usage_detail, usage_report
from .semesters import current_semester

router = APIRouter(prefix="/api/stats", tags=["stats"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _semester(db, semester_id):
    from ..models import Semester

    return db.get(Semester, semester_id) if semester_id else current_semester(db)


def _usage_teachers(teacher, subject: str, db: Session) -> list[Teacher]:
    teachers = stats_teachers(db, teacher)
    if subject:
        wanted = normalize_subject(subject)
        if is_subject_lead(teacher) and wanted != normalize_subject(teacher.subject):
            raise HTTPException(status_code=403, detail="学科组长只能查看本科目统计")
        teachers = [t for t in teachers if normalize_subject(t.subject) == wanted]
    return teachers


def _usage_report(
    db: Session,
    teacher,
    *,
    period: str | None,
    start: date | None,
    end: date | None,
    subject: str,
    grade: str,
    class_name: str,
) -> dict:
    start_dt, end_dt, start_date, end_date = resolve_period(period, start, end)
    teachers = _usage_teachers(teacher, subject, db)
    report = usage_report(
        db,
        teachers,
        start_dt,
        end_dt,
        grade=grade,
        class_name=class_name,
        start_date=start_date,
        end_date=end_date,
    )
    report["period"] = {
        "key": period or "month",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    report["scope"] = {
        "role": teacher.role,
        "subject": normalize_subject(teacher.subject),
        "class_name": class_name or None,
        "grade": grade or None,
    }
    return report


@router.get("/overview")
def overview(
    request: Request,
    semester_id: int | None = Query(None),
    admin=Depends(require_admin),
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
    historical_classes = set(
        db.scalars(select(Like.class_name).where(Like.class_name.is_not(None)).distinct()).all()
    )
    class_names = sorted({s.class_name for s in students} | historical_classes, key=class_sort_key)
    for class_name in class_names:
        class_students = [s for s in students if s.class_name == class_name]
        class_likes = db.scalar(
            select(func.count(Like.id)).where(Like.class_name == class_name, *like_filters)
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


@router.get("/usage")
def usage(
    period: str = Query("month"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    subject: str = "",
    grade: str = "",
    class_name: str = "",
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    return _usage_report(
        db,
        teacher,
        period=period,
        start=start,
        end=end,
        subject=subject,
        grade=grade,
        class_name=class_name,
    )


@router.get("/usage/export")
def export_usage(
    period: str = Query("month"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    subject: str = "",
    grade: str = "",
    class_name: str = "",
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    report = _usage_report(
        db,
        teacher,
        period=period,
        start=start,
        end=end,
        subject=subject,
        grade=grade,
        class_name=class_name,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "教师使用统计"
    ws.append(["工号", "姓名", "学科", "角色", "任教班级", "统计期内点赞班级", "点赞数", "使用天数", "覆盖学生数", "首次点赞", "最近点赞"])
    for item in report["items"]:
        ws.append(
            [
                item["employee_no"],
                item["name"],
                item["subject"] or "",
                item["role"],
                "、".join(item["classes"]),
                "、".join(item["liked_classes"]),
                item["like_count"],
                item["active_days"],
                item["student_count"],
                item["first_like_at"] or "",
                item["last_like_at"] or "",
            ]
        )
    ws.append([])
    summary = report["summary"]
    ws.append(["统计区间", f"{summary['start_date']} 至 {summary['end_date']}"])
    ws.append(["教师数", summary["teacher_count"]])
    ws.append(["活跃教师", summary["active_teachers"]])
    ws.append(["点赞总数", summary["total_likes"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=upvote_usage.xlsx"},
    )


@router.get("/usage/{teacher_id}")
def usage_detail_route(
    teacher_id: int,
    period: str = Query("month"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    grade: str = "",
    class_name: str = "",
    teacher=Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    target = db.get(Teacher, teacher_id)
    if target is None:
        raise HTTPException(status_code=404, detail="教师不存在")
    assert_stats_teacher(teacher, target)
    start_dt, end_dt, start_date, end_date = resolve_period(period, start, end)
    items = usage_detail(db, target.id, start_dt, end_dt, grade=grade, class_name=class_name)
    return {
        "teacher": {"id": target.id, "name": target.name, "subject": normalize_subject(target.subject)},
        "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "items": items,
    }


@router.get("/export")
def export_balances(
    request: Request,
    semester_id: int | None = Query(None),
    admin=Depends(require_admin),
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
        ws.append([s.student_no, s.name, normalize_grade(s.grade) or s.grade, s.class_name, b["semester_balance"], b["total_balance"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=upvote_stats.xlsx"},
    )
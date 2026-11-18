"""Admin roster exports: students / teachers / teaching assignments."""
import io

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Semester, Student, Teacher, TeacherClass
from ..security import get_db, require_admin
from ..services.access import ROLE_LABELS
from ..services.grades import grade_of_class, normalize_grade
from ..services.points import balances_for_students
from ..services.subjects import normalize_subject
from .semesters import current_semester

router = APIRouter(prefix="/api/exports", tags=["exports"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(wb: Workbook, filename: str) -> Response:
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/students.xlsx")
def export_students(
    request: Request,
    semester_id: int | None = Query(None),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    semester = db.get(Semester, semester_id) if semester_id else current_semester(db)
    students = db.scalars(select(Student).where(Student.is_active.is_(True)).order_by(Student.class_name, Student.student_no)).all()
    balances = balances_for_students(
        db,
        [s.id for s in students],
        semester.id if semester else None,
        request.app.state.settings.coins_per_like,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "学生名册"
    ws.append(["学号", "姓名", "年级", "班级", "级（入学年份）", "性别", "学期星灿币", "累计星灿币"])
    for s in students:
        b = balances[s.id]
        ws.append(
            [
                s.student_no,
                s.name,
                normalize_grade(s.grade) or grade_of_class(s.class_name) or "",
                s.class_name,
                s.enrollment_year or "",
                s.gender or "",
                b["semester_balance"],
                b["total_balance"],
            ]
        )
    return _xlsx(wb, "upvote_students.xlsx")


@router.get("/teachers.xlsx")
def export_teachers(admin=Depends(require_admin), db: Session = Depends(get_db)):
    teachers = db.scalars(select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.employee_no)).all()
    classes = {}
    for teacher_id, class_name in db.execute(select(TeacherClass.teacher_id, TeacherClass.class_name)).all():
        classes.setdefault(teacher_id, []).append(class_name)
    wb = Workbook()
    ws = wb.active
    ws.title = "教师名册"
    ws.append(["工号", "姓名", "学科", "角色", "手机号", "任教班级"])
    for t in teachers:
        ws.append(
            [
                t.employee_no,
                t.name,
                normalize_subject(t.subject) or "",
                ROLE_LABELS.get(t.role, t.role),
                t.phone or "",
                "、".join(sorted(classes.get(t.id, []))),
            ]
        )
    return _xlsx(wb, "upvote_teachers.xlsx")


@router.get("/teaching.xlsx")
def export_teaching(admin=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Teacher, TeacherClass.class_name, TeacherClass.duty)
        .join(TeacherClass, TeacherClass.teacher_id == Teacher.id)
        .where(Teacher.is_active.is_(True))
        .order_by(Teacher.employee_no, TeacherClass.class_name)
    ).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "任教关系"
    ws.append(["工号", "姓名", "学科", "班级", "班级角色"])
    duty_labels = {"teacher": "任课教师", "head": "班主任", "deputy": "副班主任"}
    for teacher, class_name, duty in rows:
        ws.append([teacher.employee_no, teacher.name, normalize_subject(teacher.subject) or "", class_name, duty_labels.get(duty, duty)])
    return _xlsx(wb, "upvote_teaching.xlsx")
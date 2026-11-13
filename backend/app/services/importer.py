"""Excel import: tolerant parsing, idempotent upsert, per-row error reporting.

支持零散增量导入：按 学号/工号/(小组名+班级)/(工号+班级) 幂等去重。
"""
import io
import json
import re

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, ImportBatch, Student, Teacher, TeacherClass
from ..security import hash_password

SHEET_STUDENTS = "学生"
SHEET_TEACHERS = "教师"
SHEET_GROUPS = "小组"
SHEET_TEACHING = "任教"

HEADERS = {
    SHEET_STUDENTS: ["学号", "姓名", "年级", "班级", "入学年份"],
    SHEET_TEACHERS: ["工号", "姓名", "手机号", "初始密码", "角色", "学科"],
    SHEET_GROUPS: ["小组名称", "班级", "成员学号"],
    SHEET_TEACHING: ["工号", "班级"],
}
EXAMPLES = {
    SHEET_STUDENTS: ["2026001", "张小明", "初一", "初一1班", 2026],
    SHEET_TEACHERS: ["T001", "王老师", "13800000001", "123456", "teacher", "语文"],
    SHEET_GROUPS: ["星辰组", "初一1班", "2026001,2026002"],
    SHEET_TEACHING: ["T001", "初一1班"],
}
DEFAULT_TEACHER_PASSWORD = "123456"


def build_template() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, header in HEADERS.items():
        ws = wb.create_sheet(name)
        ws.append(header)
        ws.append(EXAMPLES[name])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _data_rows(ws):
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None or _s(v) == "" for v in row):
            continue
        yield idx, list(row) + [None] * 8


def _new_stat():
    return {"created": 0, "updated": 0, "errors": []}


def _import_students(db: Session, ws) -> dict:
    stat = _new_stat()
    for row_no, row in _data_rows(ws):
        student_no, name, grade, class_name, year = _s(row[0]), _s(row[1]), _s(row[2]), _s(row[3]), row[4]
        if not student_no:
            stat["errors"].append({"row": row_no, "message": "学号为必填项"})
            continue
        if not name or not class_name:
            stat["errors"].append({"row": row_no, "message": "姓名、班级为必填项"})
            continue
        enrollment_year = None
        if year is not None and _s(year):
            try:
                enrollment_year = int(float(_s(year)))
            except ValueError:
                stat["errors"].append({"row": row_no, "message": f"入学年份无效：{year}"})
                continue
        student = db.scalar(select(Student).where(Student.student_no == student_no))
        if student is None:
            student = Student(student_no=student_no)
            db.add(student)
            stat["created"] += 1
        else:
            stat["updated"] += 1
        student.name, student.grade, student.class_name = name, grade or None, class_name
        student.enrollment_year = enrollment_year
        student.is_active = True
    return stat


def _import_teachers(db: Session, ws) -> dict:
    stat = _new_stat()
    for row_no, row in _data_rows(ws):
        employee_no, name, phone = _s(row[0]), _s(row[1]), _s(row[2])
        password, role, subject = _s(row[3]), _s(row[4]), _s(row[5])
        if not employee_no or not name:
            stat["errors"].append({"row": row_no, "message": "工号、姓名为必填项"})
            continue
        if role not in ("teacher", "admin"):
            role = "teacher"
        teacher = db.scalar(select(Teacher).where(Teacher.employee_no == employee_no))
        if teacher is None:
            teacher = Teacher(employee_no=employee_no, password_hash=hash_password(password or DEFAULT_TEACHER_PASSWORD))
            db.add(teacher)
            stat["created"] += 1
        else:
            stat["updated"] += 1
            if password:
                teacher.password_hash = hash_password(password)
        teacher.name, teacher.phone, teacher.role = name, phone or None, role
        if subject:
            teacher.subject = subject
        teacher.is_active = True
    return stat


def _import_groups(db: Session, ws) -> dict:
    stat = _new_stat()
    for row_no, row in _data_rows(ws):
        name, class_name, members_raw = _s(row[0]), _s(row[1]), _s(row[2])
        if not name or not class_name:
            stat["errors"].append({"row": row_no, "message": "小组名称、班级为必填项"})
            continue
        member_nos = [x for x in re.split(r"[,，、;；\s]+", members_raw) if x]
        students = []
        missing = []
        for no in member_nos:
            student = db.scalar(select(Student).where(Student.student_no == no))
            if student is None:
                missing.append(no)
            else:
                students.append(student)
        if missing:
            stat["errors"].append({"row": row_no, "message": f"成员学号不存在：{','.join(missing)}"})
            continue
        group = db.scalar(select(Group).where(Group.name == name, Group.class_name == class_name))
        if group is None:
            group = Group(name=name, class_name=class_name)
            db.add(group)
            db.flush()
            stat["created"] += 1
        else:
            stat["updated"] += 1
            for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all():
                db.delete(m)
            db.flush()
        for student in students:
            db.add(GroupMember(group_id=group.id, student_id=student.id))
    return stat


def _import_teaching(db: Session, ws) -> dict:
    stat = _new_stat()
    for row_no, row in _data_rows(ws):
        employee_no, class_name = _s(row[0]), _s(row[1])
        if not employee_no or not class_name:
            stat["errors"].append({"row": row_no, "message": "工号、班级为必填项"})
            continue
        teacher = db.scalar(select(Teacher).where(Teacher.employee_no == employee_no))
        if teacher is None:
            stat["errors"].append({"row": row_no, "message": f"工号不存在：{employee_no}"})
            continue
        exists = db.scalar(
            select(TeacherClass).where(TeacherClass.teacher_id == teacher.id, TeacherClass.class_name == class_name)
        )
        if exists is None:
            db.add(TeacherClass(teacher_id=teacher.id, class_name=class_name))
            stat["created"] += 1
        else:
            stat["updated"] += 1
    return stat


def import_workbook(db: Session, content: bytes, filename: str, operator_id: int) -> dict:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    summary = {}
    handlers = {
        SHEET_STUDENTS: ("students", _import_students),
        SHEET_TEACHERS: ("teachers", _import_teachers),
        SHEET_GROUPS: ("groups", _import_groups),
        SHEET_TEACHING: ("teaching", _import_teaching),
    }
    for sheet_name, (key, handler) in handlers.items():
        if sheet_name in wb.sheetnames:
            summary[key] = handler(db, wb[sheet_name])
            # 会话 autoflush=False：先落盘本表新增，后续 sheet 的跨表查询才能看到
            db.flush()
    wb.close()
    if not summary:
        raise ValueError("未找到有效工作表（学生/教师/小组/任教）")
    db.add(ImportBatch(filename=filename, created_by=operator_id, summary_json=json.dumps(summary, ensure_ascii=False)))
    db.commit()
    return summary
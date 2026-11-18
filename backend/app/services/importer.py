"""Excel import: tolerant header mapping, idempotent upsert, per-row error reporting.

支持零散增量导入：按 学号/工号/(小组名+班级)/(工号+班级) 幂等去重。
学生缺学号时按“姓名+班级+级”匹配，教师缺工号时按“手机号”或“姓名+学科”匹配。
"""
import io
import json
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Group, GroupMember, ImportBatch, Student, Teacher, TeacherClass
from ..security import hash_password
from .access import normalize_role
from .class_roles import get_assignment, normalize_duty, set_class_teacher
from .class_service import ensure_school_class
from .grades import class_no_of, grade_of_class, normalize_grade
from .subjects import SUBJECTS, normalize_subject

SHEET_STUDENTS = "学生"
SHEET_TEACHERS = "教师"
SHEET_GROUPS = "小组"
SHEET_TEACHING = "任教"

HEADERS = {
    SHEET_STUDENTS: ["学号", "姓名", "班级", "级", "性别"],
    SHEET_TEACHERS: ["工号", "姓名", "学科", "手机号", "初始密码", "角色"],
    SHEET_GROUPS: ["小组名称", "班级", "成员学号"],
    SHEET_TEACHING: ["工号", "班级", "角色"],
}
EXAMPLES = {
    SHEET_STUDENTS: ["2026001", "张小明", "七年级一班", 2026, "男"],
    SHEET_TEACHERS: ["T001", "王老师", "语文", "13800000001", "123456", "任课教师"],
    SHEET_GROUPS: ["星辰组", "七年级一班", "2026001,2026002"],
    SHEET_TEACHING: ["T001", "七年级一班", "任课教师"],
}
TEMPLATE_SHEETS = (SHEET_STUDENTS, SHEET_TEACHERS)
DEFAULT_TEACHER_PASSWORD = "123456"

TEMPLATE_NOTES = [
    ("学生", "学号", "否", "2026001", "留空自动生成；按学号或“姓名+班级+级”幂等更新"),
    ("学生", "姓名", "是", "张小明", "学生姓名"),
    ("学生", "班级", "是", "七年级一班", "年级和班级合并为班级；系统自动建班并归班"),
    ("学生", "级", "否", "2026", "入学年份，显示为 2026级；兼容“届/入学年份”表头"),
    ("学生", "性别", "否", "男", "只能填 男 或 女"),
    ("教师", "工号", "否", "T001", "留空自动生成 T001、T002…；也是登录账号"),
    ("教师", "姓名", "是", "王老师", "教师姓名"),
    ("教师", "学科", "条件必填", "语文", "学科组长必填；按语数英物化生政史地体音美微维护"),
    ("教师", "手机号", "否", "13800000001", "也可作为登录账号"),
    ("教师", "初始密码", "否", "123456", "留空默认 123456"),
    ("教师", "角色", "否", "任课教师", "任课教师/学科组长/校长主任；留空默认任课教师"),
]

HEADER_ALIASES = {
    "学号": "学号",
    "姓名": "姓名",
    "年级": "年级",
    "班级": "班级",
    "班": "班级",
    "级": "级",
    "届": "级",
    "入学年份": "级",
    "级(入学年份)": "级",
    "入学级": "级",
    "性别": "性别",
    "工号": "工号",
    "教师工号": "工号",
    "学科": "学科",
    "手机号": "手机号",
    "手机": "手机号",
    "初始密码": "初始密码",
    "密码": "初始密码",
    "角色": "角色",
    "小组名称": "小组名称",
    "小组": "小组名称",
    "成员学号": "成员学号",
    "成员": "成员学号",
}


def build_template() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    header_font = Font(bold=True, color="7A4B00")
    header_fill = PatternFill("solid", fgColor="FFE7BA")
    for name in TEMPLATE_SHEETS:
        header = HEADERS[name]
        ws = wb.create_sheet(name)
        ws.append(header)
        ws.append(EXAMPLES[name])
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for index, title in enumerate(header, start=1):
            width = max(len(title) + 6, 14)
            ws.column_dimensions[get_column_letter(index)].width = width
        ws.freeze_panes = "A2"

    notes = wb.create_sheet("说明")
    notes.append(["星灿点赞系统 · 名单导入说明"])
    notes["A1"].font = Font(bold=True, size=14, color="7A4B00")
    notes.merge_cells("A1:E1")
    notes.append([])
    notes.append(["工作表", "列名", "是否必填", "示例", "说明"])
    for cell in notes[3]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for row in TEMPLATE_NOTES:
        notes.append(list(row))
    notes.append([])
    notes.append(["通用规则", "", "", "", "一个 Excel 可只包含学生或教师；学生可以一张“学生”表导入，也可以每个班一个 sheet（sheet 名=班级，如“七年级一班”）；教师可以一张“教师”表导入，也可以每个学科一个 sheet（sheet 名=学科，如“语文”）。"])
    notes.append(["通用规则", "", "", "", "按学号/工号幂等去重；学生缺学号按“姓名+班级+级”匹配；错误逐行报告，不影响其他行。"])
    notes.append(["不在 Excel 输入", "", "", "", "小组、任教关系请在网页设置：班主任/副班主任可管本班小组；学科组长及以上可在本人任教班建组。"])
    notes.append(["兼任", "", "", "", "学科组长可以同时担任班主任/副班主任；教师角色与班级职责分开设置。"])
    for index, width in enumerate([10, 14, 12, 26, 60], start=1):
        notes.column_dimensions[get_column_letter(index)].width = width
    notes.freeze_panes = "A4"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _header_key(value) -> str | None:
    raw = _s(value).replace("（", "(").replace("）", ")").replace(" ", "")
    return HEADER_ALIASES.get(raw)


def _rows(ws):
    """按表头名取列，返回 (Excel 行号, dict)；不依赖列顺序。"""
    iterator = ws.iter_rows(values_only=True)
    try:
        header = next(iterator)
    except StopIteration:
        return
    columns: dict[int, str] = {}
    for index, cell in enumerate(header):
        key = _header_key(cell)
        if key and key not in columns.values():
            columns[index] = key
    if not columns:
        return
    for row_no, row in enumerate(iterator, start=2):
        if all(v is None or _s(v) == "" for v in row):
            continue
        data = {}
        for index, key in columns.items():
            data[key] = row[index] if index < len(row) else None
        yield row_no, data


def _new_stat():
    return {"created": 0, "updated": 0, "errors": []}


def _error(stat, row, message, sheet=None):
    item = {"row": row, "message": message}
    if sheet:
        item["sheet"] = sheet
    stat["errors"].append(item)


def _next_student_no(db: Session) -> str:
    max_id = db.scalar(select(func.max(Student.id))) or 0
    while True:
        max_id += 1
        candidate = f"S{max_id:06d}"
        if db.scalar(select(Student.id).where(Student.student_no == candidate)) is None:
            return candidate


def _next_employee_no(db: Session) -> str:
    number = 1
    while True:
        candidate = f"T{number:03d}"
        if db.scalar(select(Teacher.id).where(Teacher.employee_no == candidate)) is None:
            return candidate
        number += 1


def _import_students(
    db: Session,
    ws,
    default_class: str | None = None,
    sheet_name: str | None = None,
    strict_class: bool = False,
) -> dict:
    stat = _new_stat()
    for row_no, row in _rows(ws):
        student_no, name = _s(row.get("学号")), _s(row.get("姓名"))
        grade_raw = _s(row.get("年级"))
        row_class = _s(row.get("班级"))
        class_name = row_class or (default_class or "")
        year_raw, gender = _s(row.get("级")), _s(row.get("性别"))
        if strict_class and row_class and default_class and row_class != default_class:
            _error(stat, row_no, f"班级与文件名不一致：{row_class} ≠ {default_class}", sheet_name)
            continue
        if not name or not class_name:
            _error(stat, row_no, "姓名、班级为必填项", sheet_name)
            continue
        if gender and gender not in ("男", "女"):
            _error(stat, row_no, f"性别只能为 男 或 女：{gender}", sheet_name)
            continue
        enrollment_year = None
        if year_raw:
            try:
                enrollment_year = int(float(year_raw))
            except ValueError:
                _error(stat, row_no, f"级（入学年份）无效：{year_raw}", sheet_name)
                continue
        grade = normalize_grade(grade_raw) or grade_of_class(class_name)
        ensure_school_class(db, class_name, grade=grade, enrollment_year=enrollment_year)
        student = None
        if student_no:
            student = db.scalar(select(Student).where(Student.student_no == student_no))
        else:
            conditions = [Student.name == name, Student.class_name == class_name]
            if enrollment_year is not None:
                conditions.append(Student.enrollment_year == enrollment_year)
            student = db.scalar(select(Student).where(*conditions).order_by(Student.id).limit(1))
            if student is not None:
                student_no = student.student_no
        if student is None:
            student = Student(student_no=student_no or _next_student_no(db))
            db.add(student)
            created = True
            stat["created"] += 1
        else:
            created = False
            stat["updated"] += 1
        student.name = name
        student.grade = grade
        student.class_name = class_name
        if enrollment_year is not None:
            student.enrollment_year = enrollment_year
        if gender:
            student.gender = gender
        student.is_active = True
        if created:
            # 先落盘，后续行生成学号时才能看到本条；同时保持两行同名的学号不冲突
            db.flush()
    return stat


def _import_teachers(
    db: Session,
    ws,
    default_subject: str | None = None,
    sheet_name: str | None = None,
    strict_subject: bool = False,
) -> dict:
    stat = _new_stat()
    for row_no, row in _rows(ws):
        employee_no, name = _s(row.get("工号")), _s(row.get("姓名"))
        phone, password = _s(row.get("手机号")), _s(row.get("初始密码"))
        row_subject = _s(row.get("学科"))
        role_raw, subject_raw = _s(row.get("角色")), row_subject or (default_subject or "")
        if not name:
            _error(stat, row_no, "姓名为必填项", sheet_name)
            continue
        if strict_subject and row_subject and default_subject:
            if normalize_subject(row_subject) != normalize_subject(default_subject):
                _error(stat, row_no, f"学科与文件名不一致：{row_subject} ≠ {default_subject}", sheet_name)
                continue
        try:
            role = normalize_role(role_raw or "teacher")
        except ValueError as exc:
            _error(stat, row_no, str(exc), sheet_name)
            continue
        subject = normalize_subject(subject_raw)
        if role == "subject_lead" and not subject:
            _error(stat, row_no, "学科组长必须填写学科", sheet_name)
            continue
        teacher = None
        if employee_no:
            teacher = db.scalar(select(Teacher).where(Teacher.employee_no == employee_no))
        elif phone:
            teacher = db.scalar(select(Teacher).where(Teacher.phone == phone).order_by(Teacher.id).limit(1))
            if teacher is not None:
                employee_no = teacher.employee_no
            else:
                employee_no = phone
        else:
            conditions = [Teacher.name == name]
            if subject:
                conditions.append(Teacher.subject == subject)
            teacher = db.scalar(select(Teacher).where(*conditions).order_by(Teacher.id).limit(1))
            if teacher is not None:
                employee_no = teacher.employee_no
        if teacher is None:
            teacher = Teacher(
                employee_no=employee_no or _next_employee_no(db),
                password_hash=hash_password(password or DEFAULT_TEACHER_PASSWORD),
            )
            db.add(teacher)
            created = True
            stat["created"] += 1
        else:
            created = False
            stat["updated"] += 1
            if password:
                teacher.password_hash = hash_password(password)
        teacher.name = name
        teacher.phone = phone or None
        teacher.role = role
        if subject:
            teacher.subject = subject
        teacher.is_active = True
        if created:
            db.flush()
    return stat


def _import_groups(db: Session, ws) -> dict:
    stat = _new_stat()
    for row_no, row in _rows(ws):
        name, class_name = _s(row.get("小组名称")), _s(row.get("班级"))
        members_raw = _s(row.get("成员学号"))
        if not name or not class_name:
            stat["errors"].append({"row": row_no, "message": "小组名称、班级为必填项"})
            continue
        ensure_school_class(db, class_name)
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
    for row_no, row in _rows(ws):
        employee_no, class_name = _s(row.get("工号")), _s(row.get("班级"))
        duty_raw = _s(row.get("角色"))
        if not employee_no or not class_name:
            stat["errors"].append({"row": row_no, "message": "工号、班级为必填项"})
            continue
        teacher = db.scalar(select(Teacher).where(Teacher.employee_no == employee_no))
        if teacher is None:
            stat["errors"].append({"row": row_no, "message": f"工号不存在：{employee_no}"})
            continue
        try:
            duty = normalize_duty(duty_raw, preserve_when_empty=True)
        except ValueError as e:
            stat["errors"].append({"row": row_no, "message": str(e)})
            continue
        ensure_school_class(db, class_name, grade=grade_of_class(class_name))
        existing = get_assignment(db, teacher.id, class_name)
        effective_duty = duty or (existing.duty if existing else "teacher")
        set_class_teacher(db, teacher.id, class_name, effective_duty)
        if existing is None:
            stat["created"] += 1
        else:
            stat["updated"] += 1
    return stat


def _merge_stat(summary: dict, key: str, stat: dict) -> None:
    if key not in summary:
        summary[key] = stat
        return
    target = summary[key]
    target["created"] += stat["created"]
    target["updated"] += stat["updated"]
    target["errors"].extend(stat["errors"])


def _looks_like_class(sheet_name: str) -> bool:
    return grade_of_class(sheet_name) is not None and class_no_of(sheet_name) is not None


def _looks_like_subject(sheet_name: str) -> bool:
    return normalize_subject(sheet_name) in SUBJECTS


def _sheet_kind(ws) -> str:
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    keys = {_header_key(cell) for cell in header if _header_key(cell)}
    if "工号" in keys and "学号" not in keys:
        return "teacher"
    if "姓名" in keys:
        return "student"
    return "unknown"


def import_workbook(db: Session, content: bytes, filename: str, operator_id: int) -> dict:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    summary = {}
    stem = Path(filename or "").stem.strip()
    file_class = stem if _looks_like_class(stem) else None
    file_subject = None if file_class else (stem if _looks_like_subject(stem) else None)
    legacy = {
        SHEET_GROUPS: ("groups", _import_groups),
        SHEET_TEACHING: ("teaching", _import_teaching),
    }
    for ws in wb.worksheets:
        sheet_name = (ws.title or "").strip()
        kind = _sheet_kind(ws)
        if file_class:
            # 一个班一个文件：文件名就是班级，只处理学生 sheet
            if kind != "student":
                continue
            key, stat = "students", _import_students(
                db, ws, default_class=file_class, sheet_name=sheet_name, strict_class=True
            )
        elif file_subject:
            # 一个学科一个文件：文件名就是学科，只处理教师 sheet
            if kind != "teacher":
                continue
            key, stat = "teachers", _import_teachers(
                db, ws, default_subject=file_subject, sheet_name=sheet_name, strict_subject=True
            )
        elif sheet_name == SHEET_STUDENTS:
            key, stat = "students", _import_students(db, ws, sheet_name=sheet_name)
        elif sheet_name == SHEET_TEACHERS:
            key, stat = "teachers", _import_teachers(db, ws, sheet_name=sheet_name)
        elif sheet_name in legacy:
            key, handler = legacy[sheet_name]
            stat = handler(db, ws)
        elif _looks_like_class(sheet_name):
            # 一班一表：sheet 名就是班级，如“七年级一班”
            key, stat = "students", _import_students(db, ws, default_class=sheet_name, sheet_name=sheet_name)
        elif _looks_like_subject(sheet_name):
            # 一学科一表：sheet 名就是学科，如“语文”
            key, stat = "teachers", _import_teachers(db, ws, default_subject=sheet_name, sheet_name=sheet_name)
        else:
            continue
        _merge_stat(summary, key, stat)
        # 会话 autoflush=False：先落盘本 sheet 新增，后续 sheet 才能看到
        db.flush()
    wb.close()
    if not summary:
        if file_class:
            raise ValueError(f"文件名“{stem}”是班级，但文件里没有找到学生名单")
        if file_subject:
            raise ValueError(f"文件名“{stem}”是学科，但文件里没有找到教师名单")
        raise ValueError("未找到有效工作表（学生/教师，或按班级/学科命名的 sheet）")
    db.add(ImportBatch(filename=filename, created_by=operator_id, summary_json=json.dumps(summary, ensure_ascii=False)))
    db.commit()
    return summary
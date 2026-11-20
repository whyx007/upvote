"""管理端数据管理：完整备份、恢复出厂、上传恢复、Excel 导出。"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..db import Base, ensure_schema, make_engine, make_session_factory
from ..models import (
    Group,
    GroupMember,
    ImportBatch,
    Like,
    Redemption,
    Reward,
    SchoolClass,
    Semester,
    Student,
    Teacher,
    TeacherClass,
)
from ..security import get_db, require_admin, verify_password
from ..services.class_roles import DUTY_LABELS
from ..services.data_backup import (
    AUTO_KEEP,
    AUTO_PREFIX,
    TZ,
    auto_backup_dir,
    create_safety_backup,
    create_sqlite_backup,
    list_auto_backups,
    next_backup_at,
    sqlite_path,
    validate_database_file,
)
from ..services.grades import class_sort_key, normalize_grade
from ..services.subjects import normalize_subject

router = APIRouter(prefix="/api/admin/data", tags=["data-admin"])

RESET_CONFIRM = "恢复出厂设置"
RESTORE_CONFIRM = "恢复数据"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ResetBody(BaseModel):
    password: str
    confirm: str


def _db_path(request: Request) -> Path:
    path = sqlite_path(request.app.state.settings.database_url)
    if path is None:
        raise HTTPException(status_code=400, detail="当前数据库不是 SQLite 文件，无法使用该功能")
    return path


def _apk_path(request: Request) -> Path:
    return _db_path(request).parent / "app" / "upvote.apk"


def _count(db: Session, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


@router.get("/summary")
def data_summary(request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    path = _db_path(request)
    apk = _apk_path(request)
    backups = list_auto_backups(request.app.state.settings.database_url)
    return {
        "database": {
            "path": str(path),
            "size": path.stat().st_size if path.exists() else 0,
        },
        "counts": {
            "teachers": _count(db, Teacher),
            "active_teachers": _count(db, Teacher, Teacher.is_active.is_(True)),
            "students": _count(db, Student),
            "classes": _count(db, SchoolClass),
            "groups": _count(db, Group),
            "likes": _count(db, Like, Like.revoked_at.is_(None)),
            "redemptions": _count(db, Redemption, Redemption.cancelled_at.is_(None)),
        },
        "backup": {
            "enabled": request.app.state.settings.backup_scheduler_enabled,
            "keep": AUTO_KEEP,
            "next_at": next_backup_at().isoformat(),
            "last": backups[0] if backups else None,
            "items": backups,
        },
        "apk": {
            "available": apk.is_file(),
            "size": apk.stat().st_size if apk.is_file() else 0,
            "updated_at": datetime.fromtimestamp(apk.stat().st_mtime, TZ).isoformat()
            if apk.is_file()
            else None,
        },
    }


@router.get("/apk")
def download_apk(request: Request, admin=Depends(require_admin)):
    """下载当前部署的安卓 APK。"""
    path = _apk_path(request)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚未上传安卓 APK")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename="upvote.apk",
    )


@router.get("/backup")
def download_manual_backup(request: Request, admin=Depends(require_admin)):
    source = _db_path(request)
    if not source.exists():
        raise HTTPException(status_code=404, detail="数据库文件不存在")
    directory = source.parent / "backups" / "manual"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"upvote-manual-{datetime.now(TZ):%Y%m%d-%H%M%S}.db"
    create_sqlite_backup(source, target)
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=target.name,
        background=BackgroundTask(os.unlink, target),
    )


@router.get("/backups")
def data_backups(request: Request, admin=Depends(require_admin)):
    path = _db_path(request)
    return {
        "directory": str(auto_backup_dir(path)),
        "keep": AUTO_KEEP,
        "items": list_auto_backups(request.app.state.settings.database_url),
    }


@router.get("/backups/{name}")
def download_auto_backup(name: str, request: Request, admin=Depends(require_admin)):
    path = _db_path(request)
    if not name.startswith(AUTO_PREFIX) or not name.endswith(".db") or Path(name).name != name:
        raise HTTPException(status_code=400, detail="备份文件名非法")
    target = auto_backup_dir(path) / name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="备份不存在")
    return FileResponse(target, media_type="application/octet-stream", filename=target.name)


@router.get("/export.xlsx")
def export_personnel_and_likes(request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    teachers = db.scalars(select(Teacher).order_by(Teacher.employee_no)).all()
    students = db.scalars(select(Student).order_by(Student.class_name, Student.student_no)).all()
    classes = db.scalars(select(SchoolClass).order_by(SchoolClass.name)).all()
    groups = db.scalars(select(Group).order_by(Group.class_name, Group.name)).all()
    semester = db.scalar(select(Semester).where(Semester.is_current.is_(True)))

    classes_by_teacher: dict[int, list[str]] = {}
    for teacher_id, class_name in db.execute(select(TeacherClass.teacher_id, TeacherClass.class_name)).all():
        classes_by_teacher.setdefault(teacher_id, []).append(class_name)
    for names in classes_by_teacher.values():
        names.sort(key=class_sort_key)

    group_counts = dict(
        db.execute(
            select(GroupMember.group_id, func.count(GroupMember.id)).group_by(GroupMember.group_id)
        ).all()
    )
    group_members = db.execute(
        select(Group.name, Group.class_name, Student.student_no, Student.name)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .join(Student, Student.id == GroupMember.student_id)
        .order_by(Group.class_name, Group.name, Student.student_no)
    ).all()

    like_counts: dict[int, int] = {}
    if semester is not None:
        like_counts = dict(
            db.execute(
                select(Like.student_id, func.count(Like.id))
                .where(Like.revoked_at.is_(None), Like.semester_id == semester.id)
                .group_by(Like.student_id)
            ).all()
        )

    def add_sheet(title: str, header: list[str], rows):
        sheet = wb.create_sheet(title)
        sheet.append(header)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"

    wb = Workbook()
    wb.remove(wb.active)

    add_sheet(
        "教师",
        ["工号", "姓名", "手机号", "角色", "学科", "状态", "任教班级"],
        [
            [
                teacher.employee_no,
                teacher.name,
                teacher.phone or "",
                {"teacher": "任课教师", "subject_lead": "学科组长", "admin": "校长/主任"}.get(
                    teacher.role, teacher.role
                ),
                normalize_subject(teacher.subject) or "",
                "正常" if teacher.is_active else "已停用",
                "、".join(classes_by_teacher.get(teacher.id, [])),
            ]
            for teacher in teachers
        ],
    )
    add_sheet(
        "学生",
        ["学号", "姓名", "性别", "年级", "班级", "级（入学年份）", "状态"],
        [
            [
                student.student_no,
                student.name,
                student.gender or "",
                normalize_grade(student.grade) or student.grade or "",
                student.class_name,
                student.enrollment_year or "",
                "在读" if student.is_active else "已离校",
            ]
            for student in students
        ],
    )
    add_sheet(
        "班级",
        ["班级", "年级", "班号", "级（入学年份）", "状态"],
        [
            [
                klass.name,
                normalize_grade(klass.grade) or klass.grade,
                klass.class_no or "",
                klass.enrollment_year or "",
                "启用" if klass.is_active else "停用",
            ]
            for klass in classes
        ],
    )
    add_sheet(
        "任教关系",
        ["工号", "姓名", "学科", "班级", "班级角色"],
        [
            [
                teacher.employee_no,
                teacher.name,
                normalize_subject(teacher.subject) or "",
                tp.class_name,
                DUTY_LABELS.get(tp.duty, tp.duty),
            ]
            for tp in db.scalars(select(TeacherClass).order_by(TeacherClass.class_name, TeacherClass.teacher_id)).all()
            for teacher in [db.get(Teacher, tp.teacher_id)]
            if teacher is not None
        ],
    )
    add_sheet(
        "小组",
        ["小组", "班级", "成员数"],
        [[group.name, group.class_name, group_counts.get(group.id, 0)] for group in groups],
    )
    add_sheet(
        "小组成员",
        ["小组", "班级", "学号", "姓名"],
        [[group_name, class_name, student_no, student_name] for group_name, class_name, student_no, student_name in group_members],
    )
    add_sheet(
        "学生点赞总数",
        ["学号", "姓名", "班级", "本学期有效点赞总数", "统计学期"],
        [
            [
                student.student_no,
                student.name,
                student.class_name,
                like_counts.get(student.id, 0),
                semester.name if semester else "未激活学期",
            ]
            for student in students
        ],
    )

    buffer = BytesIO()
    wb.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=upvote-personnel-likes.xlsx"},
    )


@router.post("/reset")
def reset_factory(request: Request, body: ResetBody, admin=Depends(require_admin), db: Session = Depends(get_db)):
    if not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=400, detail="管理员密码错误")
    if body.confirm.strip() != RESET_CONFIRM:
        raise HTTPException(status_code=400, detail=f"请输入“{RESET_CONFIRM}”确认")

    safety = create_safety_backup(request.app.state.settings.database_url, "before-reset")
    counts = {}
    counts["redemptions"] = db.execute(delete(Redemption)).rowcount or 0
    counts["likes"] = db.execute(delete(Like)).rowcount or 0
    counts["group_members"] = db.execute(delete(GroupMember)).rowcount or 0
    counts["groups"] = db.execute(delete(Group)).rowcount or 0
    counts["teacher_classes"] = db.execute(delete(TeacherClass)).rowcount or 0
    counts["students"] = db.execute(delete(Student)).rowcount or 0
    counts["classes"] = db.execute(delete(SchoolClass)).rowcount or 0
    counts["semesters"] = db.execute(delete(Semester)).rowcount or 0
    counts["rewards"] = db.execute(delete(Reward)).rowcount or 0
    counts["import_batches"] = db.execute(delete(ImportBatch)).rowcount or 0
    counts["teachers"] = (
        db.execute(delete(Teacher).where(Teacher.id != admin.id)).rowcount or 0
    )
    db.commit()
    return {
        "ok": True,
        "counts": counts,
        "safety_backup": safety.name if safety else None,
    }


def _copy_sqlite(source: Path, target: Path) -> None:
    source_db = sqlite3.connect(str(source))
    target_db = sqlite3.connect(str(target))
    try:
        with target_db:
            source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()


@router.post("/restore")
async def restore_database(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    confirm: str = Form(...),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not verify_password(password, admin.password_hash):
        raise HTTPException(status_code=400, detail="管理员密码错误")
    if confirm.strip() != RESTORE_CONFIRM:
        raise HTTPException(status_code=400, detail=f"请输入“{RESTORE_CONFIRM}”确认")
    if not (file.filename or "").lower().endswith(".db"):
        raise HTTPException(status_code=400, detail="只能上传 .db 备份文件")

    live_path = _db_path(request)
    fd, temp_name = tempfile.mkstemp(prefix="upvote-upload-", suffix=".db", dir=str(live_path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    total = 0
    try:
        with temp_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="备份文件过大")
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            validate_database_file(temp_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        safety = create_safety_backup(request.app.state.settings.database_url, "before-restore")
        lock = getattr(request.app.state, "data_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            request.app.state.data_lock = lock
        async with lock:
            request.app.state.maintenance = True
            try:
                db.close()
                request.app.state.engine.dispose()
                _copy_sqlite(temp_path, live_path)
                new_engine = make_engine(request.app.state.settings.database_url)
                Base.metadata.create_all(new_engine)
                ensure_schema(new_engine)
                request.app.state.engine = new_engine
                request.app.state.session_factory = make_session_factory(new_engine)
            finally:
                request.app.state.maintenance = False
        return {
            "ok": True,
            "relogin": True,
            "safety_backup": safety.name if safety else None,
        }
    finally:
        temp_path.unlink(missing_ok=True)
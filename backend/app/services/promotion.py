"""学年升级：七→八、八→九、九按届归档，并创建新七年级空班。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Group, Like, SchoolClass, Student, TeacherClass
from .grades import GRADES, build_class_name, class_no_of, class_sort_key, grade_of_class, normalize_grade


def default_target_year(today: date | None = None) -> int:
    today = today or date.today()
    if 1 <= today.month <= 7:
        return today.year
    return today.year + 1


def _grade_of(klass: SchoolClass) -> str | None:
    return normalize_grade(klass.grade) or grade_of_class(klass.name)


def _target_name(klass: SchoolClass, new_grade: str) -> str:
    number = class_no_of(klass.name)
    if number is None:
        raise ValueError(f"无法识别班级编号：{klass.name}")
    return build_class_name(new_grade, number)


def build_plan(db: Session, target_year: int, new_grade7_count: int) -> dict:
    if not 2000 <= target_year <= 2100:
        raise ValueError("目标学年不合法")
    if not 0 <= new_grade7_count <= 100:
        raise ValueError("新七年级班级数只能为 0-100")

    classes = db.scalars(select(SchoolClass).order_by(SchoolClass.id)).all()
    by_grade: dict[str, list[SchoolClass]] = defaultdict(list)
    for klass in classes:
        grade = _grade_of(klass)
        if grade in GRADES:
            by_grade[grade].append(klass)

    active_counts = dict(
        db.execute(
            select(Student.class_name, func.count(Student.id))
            .where(Student.is_active.is_(True))
            .group_by(Student.class_name)
        ).all()
    )
    teacher_counts = dict(
        db.execute(
            select(TeacherClass.class_name, func.count(TeacherClass.id)).group_by(TeacherClass.class_name)
        ).all()
    )
    group_counts = dict(
        db.execute(select(Group.class_name, func.count(Group.id)).group_by(Group.class_name)).all()
    )

    available = {klass.name for klass in classes}
    errors: list[str] = []
    warnings: list[str] = []
    graduate = []
    promote8 = []
    promote7 = []
    new_grade7 = []

    if not by_grade["九年级"]:
        warnings.append("当前没有九年级班级，毕业归档将跳过。")
    if not by_grade["八年级"]:
        warnings.append("当前没有八年级班级，八→九将跳过。")
    if not by_grade["七年级"]:
        warnings.append("当前没有七年级班级，七→八将跳过。")

    for klass in sorted(by_grade["九年级"], key=lambda item: class_sort_key(item.name)):
        cohort = klass.enrollment_year or (target_year - 3)
        base = f"{cohort}届{klass.name}"
        archive_name = base
        suffix = 2
        while archive_name in available:
            archive_name = f"{base}-{suffix}"
            suffix += 1
        available.discard(klass.name)
        available.add(archive_name)
        graduate.append(
            {
                "old": klass.name,
                "new": archive_name,
                "students": active_counts.get(klass.name, 0),
                "teachers": teacher_counts.get(klass.name, 0),
                "groups": group_counts.get(klass.name, 0),
            }
        )

    for klass in sorted(by_grade["八年级"], key=lambda item: class_sort_key(item.name)):
        try:
            target = _target_name(klass, "九年级")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target in available:
            errors.append(f"九年级目标班级已存在：{target}")
            continue
        available.discard(klass.name)
        available.add(target)
        promote8.append(
            {
                "old": klass.name,
                "new": target,
                "students": active_counts.get(klass.name, 0),
                "teachers": teacher_counts.get(klass.name, 0),
                "groups": group_counts.get(klass.name, 0),
            }
        )

    for klass in sorted(by_grade["七年级"], key=lambda item: class_sort_key(item.name)):
        try:
            target = _target_name(klass, "八年级")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target in available:
            errors.append(f"八年级目标班级已存在：{target}")
            continue
        available.discard(klass.name)
        available.add(target)
        promote7.append(
            {
                "old": klass.name,
                "new": target,
                "students": active_counts.get(klass.name, 0),
                "teachers": teacher_counts.get(klass.name, 0),
                "groups": group_counts.get(klass.name, 0),
            }
        )

    for number in range(1, new_grade7_count + 1):
        name = build_class_name("七年级", number)
        if name in available:
            errors.append(f"新七年级班级名已存在：{name}")
            continue
        available.add(name)
        new_grade7.append(name)

    return {
        "target_year": target_year,
        "target_label": f"{target_year}-{target_year + 1}学年",
        "new_grade7_count": new_grade7_count,
        "graduate": graduate,
        "promote8": promote8,
        "promote7": promote7,
        "new_grade7": new_grade7,
        "warnings": warnings,
        "errors": errors,
    }


def apply_plan(db: Session, plan: dict) -> dict:
    if plan["errors"]:
        raise ValueError("；".join(plan["errors"]))

    try:
        for entry in plan["graduate"]:
            db.execute(
                update(SchoolClass)
                .where(SchoolClass.name == entry["old"])
                .values(name=entry["new"], is_active=False)
            )
            db.execute(
                update(Student)
                .where(Student.class_name == entry["old"])
                .values(class_name=entry["new"], is_active=False)
            )
            db.execute(
                update(TeacherClass)
                .where(TeacherClass.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.execute(
                update(Group)
                .where(Group.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            # 九年级班级名会被新九年级复用；历史点赞改挂到归档班名，避免和新一届混在一起。
            db.execute(
                update(Like)
                .where(Like.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.flush()

        for entry in plan["promote8"]:
            db.execute(
                update(SchoolClass)
                .where(SchoolClass.name == entry["old"])
                .values(name=entry["new"], grade="九年级")
            )
            db.execute(
                update(Student)
                .where(Student.class_name == entry["old"])
                .values(class_name=entry["new"], grade="九年级")
            )
            db.execute(
                update(TeacherClass)
                .where(TeacherClass.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.execute(
                update(Group)
                .where(Group.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.flush()

        for entry in plan["promote7"]:
            db.execute(
                update(SchoolClass)
                .where(SchoolClass.name == entry["old"])
                .values(name=entry["new"], grade="八年级")
            )
            db.execute(
                update(Student)
                .where(Student.class_name == entry["old"])
                .values(class_name=entry["new"], grade="八年级")
            )
            db.execute(
                update(TeacherClass)
                .where(TeacherClass.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.execute(
                update(Group)
                .where(Group.class_name == entry["old"])
                .values(class_name=entry["new"])
            )
            db.flush()

        for name in plan["new_grade7"]:
            db.add(
                SchoolClass(
                    name=name,
                    grade="七年级",
                    class_no=class_no_of(name),
                    enrollment_year=plan["target_year"],
                    is_active=True,
                )
            )
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("升级时遇到班级/教师/小组唯一约束冲突，请先检查数据") from exc
    except Exception:
        db.rollback()
        raise
    return plan
"""班级主数据维护：建班、同步、改名（级联班级名字段）。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Group, SchoolClass, Student, TeacherClass
from .grades import build_class_name, class_no_of, grade_of_class, normalize_grade


def ensure_school_class(
    db: Session,
    class_name: str,
    *,
    grade: str | None = None,
    enrollment_year: int | None = None,
) -> SchoolClass | None:
    name = (class_name or "").strip()
    if not name:
        return None
    existing = db.scalar(select(SchoolClass).where(SchoolClass.name == name))
    if existing is not None:
        if grade and not existing.grade:
            existing.grade = normalize_grade(grade) or existing.grade
        if enrollment_year and not existing.enrollment_year:
            existing.enrollment_year = enrollment_year
        return existing
    if enrollment_year is None:
        # 同名班级历史上通常属于同一级；取学生表里最新的一条作为推断
        enrollment_year = db.scalar(
            select(Student.enrollment_year)
            .where(Student.class_name == name, Student.enrollment_year.is_not(None))
            .order_by(Student.id.desc())
            .limit(1)
        )
    klass = SchoolClass(
        name=name,
        grade=normalize_grade(grade) or grade_of_class(name) or "",
        class_no=class_no_of(name),
        enrollment_year=enrollment_year,
    )
    db.add(klass)
    db.flush()
    return klass


def sync_classes_from_students(db: Session) -> dict:
    rows = db.execute(
        select(Student.class_name, Student.grade, Student.enrollment_year)
        .where(Student.is_active.is_(True))
        .order_by(Student.id.desc())
    ).all()
    seen: dict[str, tuple[str | None, int | None]] = {}
    for class_name, grade, year in rows:
        if class_name and class_name not in seen:
            seen[class_name] = (grade, year)
    created = 0
    for class_name, (grade, year) in seen.items():
        if db.scalar(select(SchoolClass.id).where(SchoolClass.name == class_name)) is not None:
            continue
        ensure_school_class(db, class_name, grade=grade, enrollment_year=year)
        created += 1
    db.flush()
    return {"created": created, "total": len(seen)}


def class_summaries(db: Session) -> list[dict]:
    from .access import all_class_names

    counts = dict(
        db.execute(
            select(Student.class_name, func.count(Student.id))
            .where(Student.is_active.is_(True))
            .group_by(Student.class_name)
        ).all()
    )
    years = dict(
        db.execute(
            select(Student.class_name, func.max(Student.enrollment_year))
            .where(Student.is_active.is_(True), Student.enrollment_year.is_not(None))
            .group_by(Student.class_name)
        ).all()
    )
    registry = {
        c.name: c
        for c in db.scalars(select(SchoolClass).where(SchoolClass.is_active.is_(True))).all()
    }
    items = []
    for name in all_class_names(db):
        klass = registry.get(name)
        items.append(
            {
                "id": klass.id if klass else None,
                "name": name,
                "grade": (klass.grade if klass else None) or grade_of_class(name),
                "class_no": (klass.class_no if klass else None) or class_no_of(name),
                "enrollment_year": (klass.enrollment_year if klass else None) or years.get(name),
                "student_count": counts.get(name, 0),
                "registered": klass is not None,
                "is_active": klass.is_active if klass else True,
            }
        )
    return items


def create_class(
    db: Session,
    *,
    grade: str,
    class_no: int,
    enrollment_year: int | None = None,
    name: str | None = None,
) -> SchoolClass:
    normalized = normalize_grade(grade)
    if not normalized:
        raise ValueError("年级不能为空")
    class_name = (name or build_class_name(normalized, class_no)).strip()
    if db.scalar(select(SchoolClass.id).where(SchoolClass.name == class_name)) is not None:
        raise ValueError(f"班级已存在：{class_name}")
    klass = SchoolClass(
        name=class_name,
        grade=normalized,
        class_no=class_no,
        enrollment_year=enrollment_year,
    )
    db.add(klass)
    db.flush()
    return klass


def rename_class(db: Session, klass: SchoolClass, new_name: str) -> SchoolClass:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("班级名称不能为空")
    if new_name == klass.name:
        return klass
    if db.scalar(select(SchoolClass.id).where(SchoolClass.name == new_name)) is not None:
        raise ValueError(f"班级已存在：{new_name}")
    old_name = klass.name
    klass.name = new_name
    klass.grade = normalize_grade(klass.grade) or grade_of_class(new_name) or klass.grade
    klass.class_no = class_no_of(new_name)
    for row in db.scalars(select(Student).where(Student.class_name == old_name)).all():
        row.class_name = new_name
    for row in db.scalars(select(Group).where(Group.class_name == old_name)).all():
        row.class_name = new_name
    for row in db.scalars(select(TeacherClass).where(TeacherClass.class_name == old_name)).all():
        row.class_name = new_name
    db.flush()
    return klass


def class_has_students(db: Session, class_name: str) -> bool:
    return db.scalar(
        select(func.count(Student.id)).where(Student.class_name == class_name, Student.is_active.is_(True))
    ) > 0


def class_names_for_grade(db: Session, grade: str | None) -> list[str]:
    if not grade:
        return []
    from .access import all_class_names

    return [name for name in all_class_names(db) if grade_of_class(name) == normalize_grade(grade)]
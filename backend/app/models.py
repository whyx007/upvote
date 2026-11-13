from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="teacher")  # teacher | admin
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 男 | 女 | None
    grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    class_name: Mapped[str] = mapped_column(String(64), index=True)
    enrollment_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("name", "class_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    class_name: Mapped[str] = mapped_column(String(64), index=True)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "student_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)


class TeacherClass(Base):
    __tablename__ = "teacher_classes"
    __table_args__ = (UniqueConstraint("teacher_id", "class_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    class_name: Mapped[str] = mapped_column(String(64))
    duty: Mapped[str] = mapped_column(String(16), default="teacher")  # teacher | head | deputy


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    summary_json: Mapped[str] = mapped_column(Text, default="{}")


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(32), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    cost_coins: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = 不限量
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Redemption(Base):
    __tablename__ = "redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    reward_id: Mapped[int] = mapped_column(ForeignKey("rewards.id"))
    cost_coins: Mapped[int] = mapped_column(Integer)  # 币价快照
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"), index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
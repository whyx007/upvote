from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_schema(engine):
    """轻量迁移：为已存在的旧库补齐新增列（SQLite ALTER TABLE ADD COLUMN，幂等）。"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "teachers" in tables:
        cols = {c["name"] for c in inspector.get_columns("teachers")}
        if "subject" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE teachers ADD COLUMN subject VARCHAR(32)"))
    if "students" in tables:
        cols = {c["name"] for c in inspector.get_columns("students")}
        if "gender" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students ADD COLUMN gender VARCHAR(8)"))
    if "teacher_classes" in tables:
        cols = {c["name"] for c in inspector.get_columns("teacher_classes")}
        if "duty" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE teacher_classes ADD COLUMN duty VARCHAR(16) DEFAULT 'teacher'"))
    if "likes" in tables:
        indexes = {i["name"] for i in inspector.get_indexes("likes")}
        with engine.begin() as conn:
            if "ix_likes_created_at" not in indexes:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_likes_created_at ON likes (created_at)"))
            if "ix_likes_student_semester" not in indexes:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_likes_student_semester "
                        "ON likes (student_id, semester_id, revoked_at)"
                    )
                )
            if "ix_likes_teacher_semester" not in indexes:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_likes_teacher_semester "
                        "ON likes (teacher_id, semester_id, revoked_at)"
                    )
                )
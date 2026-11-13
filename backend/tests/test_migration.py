"""Lightweight schema migration: add missing columns to existing SQLite DBs."""
from sqlalchemy import create_engine, inspect, text

from app.db import ensure_schema


def test_migration_adds_subject_to_old_teachers_table(tmp_path):
    db_file = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE teachers (id INTEGER PRIMARY KEY, employee_no VARCHAR(64), "
                "name VARCHAR(64), phone VARCHAR(32), password_hash VARCHAR(128), "
                "role VARCHAR(16), is_active BOOLEAN, created_at DATETIME)"
            )
        )
    ensure_schema(engine)
    cols = [c["name"] for c in inspect(engine).get_columns("teachers")]
    assert "subject" in cols
    ensure_schema(engine)  # 幂等
    cols = [c["name"] for c in inspect(engine).get_columns("teachers")]
    assert cols.count("subject") == 1
    engine.dispose()


def test_migration_adds_gender_to_old_students_table(tmp_path):
    db_file = tmp_path / "old2.db"
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE students (id INTEGER PRIMARY KEY, student_no VARCHAR(64), "
                "name VARCHAR(64), grade VARCHAR(32), class_name VARCHAR(64), "
                "enrollment_year INTEGER, is_active BOOLEAN, created_at DATETIME)"
            )
        )
    ensure_schema(engine)
    cols = [c["name"] for c in inspect(engine).get_columns("students")]
    assert "gender" in cols
    engine.dispose()
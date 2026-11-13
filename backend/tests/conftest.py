"""Shared fixtures: fresh SQLite per test, TestClient, admin auth helpers."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        secret_key="test-secret-key-0123456789abcdef",
        coins_per_like=1,
    )
    application = create_app(settings)
    with TestClient(application) as c:
        yield c


@pytest.fixture()
def admin_token(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def semester_id(client, admin_headers):
    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "2026-2027学年第一学期", "start_date": "2026-09-01", "end_date": "2027-01-15"},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.post(f"/api/semesters/{sid}/activate", headers=admin_headers).status_code == 200
    return sid


@pytest.fixture()
def school(client, admin_headers, semester_id):
    """Semester + 2 students + group + teacher T001 assigned to 初一1班."""
    from tests.helpers import (
        GROUP_HEADER,
        TEACHER_HEADER,
        TEACHING_HEADER,
        import_students,
        login_headers,
        make_xlsx,
        upload,
    )

    import_students(
        client,
        admin_headers,
        [
            ["2026001", "张小明", "初一", "初一1班", 2026],
            ["2026002", "李小红", "初一", "初一1班", 2026],
        ],
    )
    upload(
        client,
        admin_headers,
        make_xlsx(
            {
                "教师": [TEACHER_HEADER, ["T001", "王老师", None, None, None]],
                "任教": [TEACHING_HEADER, ["T001", "初一1班"]],
                "小组": [GROUP_HEADER, ["星辰组", "初一1班", "2026001,2026002"]],
            }
        ),
    )
    students = client.get("/api/students", headers=admin_headers).json()["items"]
    groups = client.get("/api/groups", headers=admin_headers).json()["items"]
    return {
        "semester_id": semester_id,
        "student_ids": {s["student_no"]: s["id"] for s in students},
        "group_id": groups[0]["id"],
        "teacher_headers": login_headers(client, "T001", "123456"),
    }
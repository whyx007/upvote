"""Admin-only destructive roster reset with password + confirmation."""
from tests.helpers import login_headers


def test_clear_roster_requires_password_and_confirm(client, admin_headers, school):
    wrong_password = client.post(
        "/api/admin/clear-roster",
        headers=admin_headers,
        json={"password": "wrong", "confirm": "清除名单"},
    )
    assert wrong_password.status_code == 400
    wrong_confirm = client.post(
        "/api/admin/clear-roster",
        headers=admin_headers,
        json={"password": "admin123", "confirm": "清空"},
    )
    assert wrong_confirm.status_code == 400

    r = client.post(
        "/api/admin/clear-roster",
        headers=admin_headers,
        json={"password": "admin123", "confirm": "清除名单"},
    )
    assert r.status_code == 200, r.text
    counts = r.json()["counts"]
    assert counts["students"] == 2
    assert counts["teachers"] == 1
    assert counts["classes"] >= 1

    assert client.get("/api/students", headers=admin_headers).json()["total"] == 0
    assert client.get("/api/classes", headers=admin_headers).json() == []
    teachers = client.get("/api/teachers", headers=admin_headers).json()["items"]
    assert [t["employee_no"] for t in teachers] == ["admin"]
    assert client.get("/api/stats/overview", headers=admin_headers).json()["total_students"] == 0
    assert login_headers(client, "admin", "admin123")


def test_clear_roster_requires_admin(client, school):
    r = client.post(
        "/api/admin/clear-roster",
        headers=school["teacher_headers"],
        json={"password": "123456", "confirm": "清除名单"},
    )
    assert r.status_code == 403
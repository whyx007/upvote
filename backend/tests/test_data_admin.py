"""Data management: summary, backup, Excel export, factory reset and restore."""
import io
import sqlite3
from datetime import datetime

from openpyxl import load_workbook

from app.services.data_backup import TZ, next_backup_at, sqlite_path


def _like(client, headers, student_id):
    r = client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": student_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_data_summary_and_manual_backup(client, admin_headers, school):
    r = client.get("/api/admin/data/summary", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"]["students"] == 2
    assert body["counts"]["likes"] == 0
    assert body["backup"]["enabled"] is False
    assert body["backup"]["keep"] == 5
    assert body["backup"]["next_at"]

    r = client.get("/api/admin/data/backup", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"SQLite format 3\x00")
    assert ".db" in r.headers.get("content-disposition", "")


def test_data_export_has_rosters_and_semester_like_totals(client, admin_headers, school):
    _like(client, school["teacher_headers"], school["student_ids"]["2026001"])
    r = client.get("/api/admin/data/export.xlsx", headers=admin_headers)
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    assert set(wb.sheetnames) >= {"教师", "学生", "班级", "任教关系", "小组", "小组成员", "学生点赞总数"}
    sheet = wb["学生点赞总数"]
    header = [cell.value for cell in sheet[1]]
    rows = {row[0]: row for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert rows["2026001"][header.index("本学期有效点赞总数")] == 1
    assert rows["2026002"][header.index("本学期有效点赞总数")] == 0


def test_factory_reset_keeps_current_admin_and_clears_everything(client, admin_headers, school):
    _like(client, school["teacher_headers"], school["student_ids"]["2026001"])
    client.post("/api/rewards", headers=admin_headers, json={"name": "笔记本", "cost_coins": 1})

    assert client.post(
        "/api/admin/data/reset",
        headers=admin_headers,
        json={"password": "wrong", "confirm": "恢复出厂设置"},
    ).status_code == 400
    assert client.post(
        "/api/admin/data/reset",
        headers=admin_headers,
        json={"password": "admin123", "confirm": "错误确认"},
    ).status_code == 400

    r = client.post(
        "/api/admin/data/reset",
        headers=admin_headers,
        json={"password": "admin123", "confirm": "恢复出厂设置"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["safety_backup"].endswith(".db")

    # 管理员仍可登录，业务数据全部清空
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/api/students", headers=headers).json()["total"] == 0
    assert client.get("/api/teachers", headers=headers, params={"page_size": 500}).json()["total"] == 1
    assert client.get("/api/semesters/current", headers=headers).json() is None
    assert client.get("/api/rewards", headers=headers).json()["items"] == []
    summary = client.get("/api/admin/data/summary", headers=headers).json()
    assert summary["counts"]["students"] == 0
    assert summary["counts"]["likes"] == 0


def test_restore_uploaded_db(client, admin_headers, school, tmp_path):
    db_path = sqlite_path(client.app.state.settings.database_url)
    assert db_path is not None
    backup_path = tmp_path / "backup.db"
    source = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(backup_path))
    with target:
        source.backup(target)
    target.close()
    source.close()

    # 备份后新增的学生，恢复后应消失
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2099001", "name": "恢复前新增", "class_name": "初一1班"},
    )
    assert r.status_code == 200, r.text

    content = backup_path.read_bytes()
    r = client.post(
        "/api/admin/data/restore",
        headers=admin_headers,
        data={"password": "admin123", "confirm": "恢复数据"},
        files={"file": ("backup.db", content, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["relogin"] is True

    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    students = client.get("/api/students", headers=headers).json()["items"]
    assert all(s["student_no"] != "2099001" for s in students)


def test_next_backup_time_skips_weekends():
    friday = datetime(2026, 11, 20, 10, 0, tzinfo=TZ)
    assert next_backup_at(friday).isoformat() == "2026-11-20T23:30:00+08:00"
    saturday = datetime(2026, 11, 21, 10, 0, tzinfo=TZ)
    assert next_backup_at(saturday).isoformat() == "2026-11-23T23:30:00+08:00"
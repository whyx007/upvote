"""Semester management: create, activate (single current), validation."""
from datetime import date

from app.routers.semesters import suggest_semesters


def test_suggest_semesters_uses_current_date():
    autumn = suggest_semesters(date(2026, 11, 20))
    assert autumn[0] == {
        "name": "2026-2027学年第一学期",
        "start_date": "2026-09-01",
        "end_date": "2027-01-15",
    }
    assert autumn[1]["name"] == "2026-2027学年第二学期"
    assert autumn[1]["start_date"] == "2027-02-01"
    assert autumn[2]["name"] == "2027-2028学年第一学期"

    spring = suggest_semesters(date(2027, 3, 1))
    assert spring[0]["name"] == "2026-2027学年第二学期"
    assert spring[0]["start_date"] == "2027-02-01"
    assert spring[1]["name"] == "2027-2028学年第一学期"

    january = suggest_semesters(date(2027, 1, 10))
    assert january[0]["name"] == "2026-2027学年第一学期"


def test_suggest_endpoint(client, admin_headers):
    r = client.get("/api/semesters/suggest", headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 4
    assert {"name", "start_date", "end_date"} <= set(items[0])


def test_create_and_activate_semester(client, admin_headers):
    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "2026-2027学年第一学期", "start_date": "2026-09-01", "end_date": "2027-01-15"},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.post(f"/api/semesters/{sid}/activate", headers=admin_headers).status_code == 200
    current = client.get("/api/semesters/current", headers=admin_headers).json()
    assert current["id"] == sid
    assert current["is_current"] is True


def test_only_one_current_semester(client, admin_headers):
    ids = []
    for name in ("第一学期", "第二学期"):
        r = client.post(
            "/api/semesters",
            headers=admin_headers,
            json={"name": name, "start_date": "2026-09-01", "end_date": "2027-01-15"},
        )
        ids.append(r.json()["id"])
        client.post(f"/api/semesters/{ids[-1]}/activate", headers=admin_headers)
    current = client.get("/api/semesters/current", headers=admin_headers).json()
    assert current["id"] == ids[1]
    listing = client.get("/api/semesters", headers=admin_headers).json()["items"]
    assert [s["is_current"] for s in listing] == [False, True]


def test_semester_end_before_start_rejected(client, admin_headers):
    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "坏学期", "start_date": "2027-01-15", "end_date": "2026-09-01"},
    )
    assert r.status_code == 400


def test_activate_requires_admin(client, admin_headers, school):
    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "第二学期", "start_date": "2027-02-01", "end_date": "2027-07-01"},
    )
    sid = r.json()["id"]
    assert client.post(f"/api/semesters/{sid}/activate", headers=school["teacher_headers"]).status_code == 403


def test_current_semester_null_when_none(client, admin_headers):
    r = client.get("/api/semesters/current", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() is None
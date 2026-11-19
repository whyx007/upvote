"""Single-step decrement: teacher removes one own like from the current semester."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import Like
from tests.helpers import login_headers


def like(client, headers, student_id):
    r = client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": student_id})
    assert r.status_code == 200, r.text
    return r.json()


def decrement(client, headers, student_id):
    return client.post("/api/likes/decrement", headers=headers, json={"student_id": student_id})


def balance(client, headers, student_no="2026001"):
    items = client.get("/api/classes/初一1班/roster", headers=headers).json()["items"]
    return next(s for s in items if s["student_no"] == student_no)["semester_balance"]


def test_decrement_reduces_balance(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    like(client, school["teacher_headers"], sid)
    like(client, school["teacher_headers"], sid)
    assert balance(client, admin_headers) == 2
    r = decrement(client, school["teacher_headers"], sid)
    assert r.status_code == 200, r.text
    assert r.json()["my_semester_likes"] == 1
    assert "semester_balance" not in r.json()
    assert balance(client, admin_headers) == 1


def test_decrement_without_any_like_rejected(client, school):
    r = decrement(client, school["teacher_headers"], school["student_ids"]["2026001"])
    assert r.status_code == 400


def test_decrement_stops_at_zero(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    like(client, school["teacher_headers"], sid)
    assert decrement(client, school["teacher_headers"], sid).status_code == 200
    assert decrement(client, school["teacher_headers"], sid).status_code == 400
    assert balance(client, admin_headers) == 0


def test_decrement_does_not_touch_other_teachers_like(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    like(client, school["teacher_headers"], sid)
    other = login_headers(client, "admin", "admin123")
    r = decrement(client, other, sid)
    assert r.status_code == 400
    assert balance(client, admin_headers) == 1


def test_decrement_previous_day_rejected(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    like(client, school["teacher_headers"], sid)
    with client.app.state.session_factory() as db:
        rec = db.scalar(select(Like).where(Like.student_id == sid))
        rec.created_at = datetime.now() - timedelta(days=1)
        db.commit()
    assert decrement(client, school["teacher_headers"], sid).status_code == 400
    assert balance(client, admin_headers) == 1


def test_decrement_unknown_student_rejected(client, school):
    assert decrement(client, school["teacher_headers"], 999999).status_code == 404


def test_decrement_requires_current_semester(client, admin_headers):
    from tests.helpers import import_students

    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    sid = client.get("/api/students", headers=admin_headers).json()["items"][0]["id"]
    assert decrement(client, admin_headers, sid).status_code == 400
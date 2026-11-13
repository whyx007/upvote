"""Likes: one-tap student/group likes, batch revoke, semester-scoped balances."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import Like
from tests.helpers import GROUP_HEADER, import_students, make_xlsx, upload


def like_student(client, headers, student_id):
    return client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": student_id})


def roster(client, headers, class_name="初一1班"):
    r = client.get(f"/api/classes/{class_name}/roster", headers=headers)
    assert r.status_code == 200, r.text
    return {item["student_no"]: item for item in r.json()["items"]}


def test_like_student_increments_balance(client, admin_headers, school):
    r = like_student(client, school["teacher_headers"], school["student_ids"]["2026001"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["batch_id"]
    row = roster(client, admin_headers)["2026001"]
    assert row["semester_balance"] == 1
    assert row["total_balance"] == 1


def test_like_group_fans_out_to_members(client, admin_headers, school):
    r = client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "group", "target_id": school["group_id"]},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 2
    rows = roster(client, admin_headers)
    assert rows["2026001"]["semester_balance"] == 1
    assert rows["2026002"]["semester_balance"] == 1


def test_revoke_own_batch_restores_balance(client, admin_headers, school):
    batch_id = like_student(client, school["teacher_headers"], school["student_ids"]["2026001"]).json()["batch_id"]
    r = client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": batch_id})
    assert r.status_code == 200
    assert r.json()["revoked_count"] == 1
    assert roster(client, admin_headers)["2026001"]["semester_balance"] == 0


def test_revoke_group_batch_restores_all(client, admin_headers, school):
    r = client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "group", "target_id": school["group_id"]},
    )
    batch_id = r.json()["batch_id"]
    r2 = client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": batch_id})
    assert r2.json()["revoked_count"] == 2
    rows = roster(client, admin_headers)
    assert rows["2026001"]["semester_balance"] == 0
    assert rows["2026002"]["semester_balance"] == 0


def test_cannot_revoke_other_teacher_batch(client, admin_headers, school):
    batch_id = like_student(client, school["teacher_headers"], school["student_ids"]["2026001"]).json()["batch_id"]
    r = client.post("/api/likes/revoke", headers=admin_headers, json={"batch_id": batch_id})
    assert r.status_code == 403


def test_cannot_revoke_previous_day(client, school):
    batch_id = like_student(client, school["teacher_headers"], school["student_ids"]["2026001"]).json()["batch_id"]
    with client.app.state.session_factory() as db:
        like = db.scalar(select(Like).where(Like.batch_id == batch_id))
        like.created_at = datetime.now() - timedelta(days=1)
        db.commit()
    r = client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": batch_id})
    assert r.status_code == 400


def test_cannot_revoke_twice(client, school):
    batch_id = like_student(client, school["teacher_headers"], school["student_ids"]["2026001"]).json()["batch_id"]
    client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": batch_id})
    r = client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": batch_id})
    assert r.status_code == 400


def test_like_without_current_semester_rejected(client, admin_headers):
    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    student_id = client.get("/api/students", headers=admin_headers).json()["items"][0]["id"]
    r = like_student(client, admin_headers, student_id)
    assert r.status_code == 400


def test_like_unknown_target_rejected(client, school):
    r = like_student(client, school["teacher_headers"], 999999)
    assert r.status_code == 404


def test_like_empty_group_rejected(client, admin_headers, school):
    upload(client, admin_headers, make_xlsx({"小组": [GROUP_HEADER, ["空组", "初一1班", ""]]}))
    groups = client.get("/api/groups", headers=admin_headers).json()["items"]
    empty = next(g for g in groups if g["name"] == "空组")
    r = client.post("/api/likes", headers=school["teacher_headers"], json={"target_type": "group", "target_id": empty["id"]})
    assert r.status_code == 400


def test_roster_accumulates_multiple_likes(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    like_student(client, school["teacher_headers"], sid)
    like_student(client, school["teacher_headers"], sid)
    like_student(client, school["teacher_headers"], school["student_ids"]["2026002"])
    rows = roster(client, admin_headers)
    assert rows["2026001"]["semester_balance"] == 2
    assert rows["2026002"]["semester_balance"] == 1
    assert rows["2026001"]["groups"] == ["星辰组"]


def test_balance_scoped_by_semester(client, admin_headers, school):
    like_student(client, school["teacher_headers"], school["student_ids"]["2026001"])
    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "第二学期", "start_date": "2027-02-01", "end_date": "2027-07-01"},
    )
    client.post(f"/api/semesters/{r.json()['id']}/activate", headers=admin_headers)
    row = roster(client, admin_headers)["2026001"]
    assert row["semester_balance"] == 0
    assert row["total_balance"] == 1


def test_recent_feed_shows_batch_with_undo(client, school):
    client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "group", "target_id": school["group_id"]},
    )
    r = client.get("/api/likes/recent", headers=school["teacher_headers"])
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["count"] == 2
    assert item["group_name"] == "星辰组"
    assert item["can_revoke"] is True


def test_admin_sees_all_recent(client, admin_headers, school):
    like_student(client, school["teacher_headers"], school["student_ids"]["2026001"])
    r = client.get("/api/likes/recent", headers=admin_headers)
    assert len(r.json()["items"]) == 1
"""Teacher usage statistics: period filters, subject scope, detail and export."""
from datetime import date, timedelta

from tests.helpers import login_headers


def _patch_subject(client, admin_headers, employee_no, subject):
    items = client.get("/api/teachers", headers=admin_headers, params={"page_size": 500}).json()["items"]
    teacher = next(t for t in items if t["employee_no"] == employee_no)
    client.patch(f"/api/teachers/{teacher['id']}", headers=admin_headers, json={"subject": subject})
    return teacher


def test_usage_month_and_custom_period(client, admin_headers, school):
    _patch_subject(client, admin_headers, "T001", "语文")
    assert client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026001"]},
    ).status_code == 200
    assert client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026002"]},
    ).status_code == 200

    today = date.today()
    r = client.get(
        "/api/stats/usage",
        headers=admin_headers,
        params={"period": "custom", "start": (today - timedelta(days=1)).isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["total_likes"] == 2
    t1 = next(x for x in body["items"] if x["employee_no"] == "T001")
    assert t1["like_count"] == 2
    assert t1["active_days"] == 1
    assert t1["student_count"] == 2
    assert len(t1["liked_classes"]) == 1


def test_usage_grade_and_class_filters(client, admin_headers, school):
    _patch_subject(client, admin_headers, "T001", "语文")
    client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026001"]},
    )
    r = client.get("/api/stats/usage", headers=admin_headers, params={"grade": "七年级"})
    assert r.status_code == 200
    assert r.json()["summary"]["total_likes"] == 1
    r = client.get("/api/stats/usage", headers=admin_headers, params={"grade": "八年级"})
    assert r.status_code == 200
    assert r.json()["summary"]["total_likes"] == 0
    r = client.get("/api/stats/usage", headers=admin_headers, params={"class_name": "初一1班"})
    assert r.status_code == 200
    assert r.json()["summary"]["total_likes"] == 1
    r = client.get("/api/stats/usage", headers=admin_headers, params={"class_name": "初一2班"})
    assert r.status_code == 200
    assert r.json()["summary"]["total_likes"] == 0


def test_teacher_only_sees_own_usage(client, admin_headers, school):
    _patch_subject(client, admin_headers, "T001", "语文")
    client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026001"]},
    )
    r = client.get("/api/stats/usage", headers=school["teacher_headers"], params={"period": "month"})
    assert r.status_code == 200
    assert {x["employee_no"] for x in r.json()["items"]} == {"T001"}
    detail = client.get(
        f"/api/stats/usage/{r.json()['items'][0]['teacher_id']}",
        headers=school["teacher_headers"],
        params={"period": "month"},
    )
    assert detail.status_code == 200
    assert detail.json()["items"][0]["student_name"] == "张小明"


def test_usage_export(client, admin_headers, school):
    r = client.get("/api/stats/usage/export", headers=admin_headers, params={"period": "month"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
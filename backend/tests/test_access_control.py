"""Three-tier data access: teacher / subject lead / admin."""
from tests.helpers import login_headers


def _teacher(client, admin_headers, employee_no):
    items = client.get("/api/teachers", headers=admin_headers, params={"page_size": 500}).json()["items"]
    return next(t for t in items if t["employee_no"] == employee_no)


def _make(client, admin_headers, employee_no, name, subject, role="teacher"):
    r = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": employee_no, "name": name, "subject": subject, "role": role},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _assign(client, admin_headers, teacher_id, classes):
    r = client.put(f"/api/teachers/{teacher_id}/classes", headers=admin_headers, json={"class_names": classes})
    assert r.status_code == 200, r.text


def _student(client, admin_headers, class_name, no, name):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": no, "name": name, "class_name": class_name, "gender": "男"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_teacher_cannot_access_or_like_other_class(client, admin_headers, school):
    t1 = _teacher(client, admin_headers, "T001")
    t2 = _make(client, admin_headers, "T002", "数学老师", "数学")
    _assign(client, admin_headers, t2["id"], ["初一2班"])
    outsider = _student(client, admin_headers, "初一2班", "2027001", "外班学生")
    headers = school["teacher_headers"]

    assert client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": outsider["id"]}).status_code == 403
    assert client.get("/api/classes/初一2班/roster", headers=headers).status_code == 403
    assert client.get("/api/classes/初一2班/teachers", headers=headers).status_code == 403
    assert client.get("/api/groups", headers=headers, params={"class_name": "初一2班"}).status_code == 403
    assert client.get("/api/students", headers=headers).status_code == 403
    assert client.get("/api/classes", headers=headers).status_code == 403
    assert client.get("/api/stats/overview", headers=headers).status_code == 403

    # 本人任教班可以正常点赞、看花名册
    sid = school["student_ids"]["2026001"]
    assert client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": sid}).status_code == 200
    assert client.get("/api/classes/初一1班/roster", headers=headers).status_code == 200


def test_subject_lead_sees_same_subject_summary_and_detail_only(client, admin_headers, school):
    t1 = _teacher(client, admin_headers, "T001")
    client.patch(f"/api/teachers/{t1['id']}", headers=admin_headers, json={"subject": "语文"})
    lead = _make(client, admin_headers, "T003", "语文组长", "语文", role="subject_lead")
    other = _make(client, admin_headers, "T004", "数学老师", "数学")
    _assign(client, admin_headers, lead["id"], ["初一1班"])
    _assign(client, admin_headers, other["id"], ["初一1班"])

    # 语文老师和数学老师各点一次
    assert client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026001"]},
    ).status_code == 200
    other_headers = login_headers(client, "T004", "123456")
    assert client.post(
        "/api/likes",
        headers=other_headers,
        json={"target_type": "student", "target_id": school["student_ids"]["2026002"]},
    ).status_code == 200

    lead_headers = login_headers(client, "T003", "123456")
    assert client.get("/api/classes/registry", headers=lead_headers).status_code == 200
    assert client.get("/api/classes/registry", headers=school["teacher_headers"]).status_code == 403
    r = client.get("/api/stats/usage", headers=lead_headers, params={"period": "month"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert {x["employee_no"] for x in items} == {"T001", "T003"}
    assert next(x for x in items if x["employee_no"] == "T001")["like_count"] == 1

    detail = client.get(f"/api/stats/usage/{t1['id']}", headers=lead_headers, params={"period": "month"})
    assert detail.status_code == 200, detail.text
    assert detail.json()["items"][0]["student_name"] == "张小明"

    # 不能看其他学科老师，也不能看全校概览
    assert client.get(f"/api/stats/usage/{other['id']}", headers=lead_headers, params={"period": "month"}).status_code == 403
    assert client.get("/api/stats/overview", headers=lead_headers).status_code == 403

    # 本人的点赞记录仍只看自己，不串其他老师
    recent = client.get("/api/likes/recent", headers=lead_headers).json()["items"]
    assert all(item["teacher_name"] == "语文组长" for item in recent)


def test_admin_sees_all_usage_and_rosters(client, admin_headers, school):
    t1 = _teacher(client, admin_headers, "T001")
    client.patch(f"/api/teachers/{t1['id']}", headers=admin_headers, json={"subject": "语文"})
    r = client.get("/api/stats/usage", headers=admin_headers, params={"period": "month"})
    assert r.status_code == 200
    assert r.json()["scope"]["role"] == "admin"
    assert client.get("/api/exports/students.xlsx", headers=admin_headers).status_code == 200
    assert client.get("/api/exports/teachers.xlsx", headers=admin_headers).status_code == 200
    assert client.get("/api/exports/teaching.xlsx", headers=admin_headers).status_code == 200


def test_subject_lead_requires_subject(client, admin_headers):
    r = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T900", "name": "无学科组长", "role": "subject_lead"},
    )
    assert r.status_code == 400
    assert "学科" in r.json()["detail"]


def test_teacher_auto_ids_start_at_t001(client, admin_headers):
    r1 = client.post("/api/teachers", headers=admin_headers, json={"name": "甲老师", "subject": "语文"})
    r2 = client.post("/api/teachers", headers=admin_headers, json={"name": "乙老师", "subject": "数学"})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["employee_no"] == "T001"
    assert r2.json()["employee_no"] == "T002"


def test_subject_lead_can_manage_groups_in_assigned_class_only(client, admin_headers, school):
    lead = _make(client, admin_headers, "T003", "语文组长", "语文", role="subject_lead")
    _assign(client, admin_headers, lead["id"], ["初一1班"])
    regular = _make(client, admin_headers, "T004", "普通老师", "数学")
    _assign(client, admin_headers, regular["id"], ["初一1班"])
    lead_headers = login_headers(client, "T003", "123456")
    regular_headers = login_headers(client, "T004", "123456")

    r = client.post(
        "/api/groups",
        headers=lead_headers,
        json={"name": "组长建的组", "class_name": "初一1班", "member_student_nos": ["2026001"]},
    )
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    assert client.patch(f"/api/groups/{gid}", headers=lead_headers, json={"name": "组长改名"}).status_code == 200
    assert client.delete(f"/api/groups/{gid}", headers=lead_headers).status_code == 200

    # 不是本人任教班不能建组
    assert client.post(
        "/api/groups",
        headers=lead_headers,
        json={"name": "跨班组", "class_name": "初一2班", "member_student_nos": []},
    ).status_code == 403
    # 普通任课教师仍不能建组
    assert client.post(
        "/api/groups",
        headers=regular_headers,
        json={"name": "普通老师的组", "class_name": "初一1班", "member_student_nos": []},
    ).status_code == 403
    # 校长/主任任意班
    assert client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "校级组", "class_name": "初一2班", "member_student_nos": []},
    ).status_code == 200
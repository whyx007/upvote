"""Like visibility: own counts, class-manager totals, subject lead and admin scopes."""
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


def _set_duty(client, admin_headers, class_name, teacher_id, duty):
    r = client.post(
        f"/api/classes/{class_name}/teachers",
        headers=admin_headers,
        json={"teacher_id": teacher_id, "duty": duty},
    )
    assert r.status_code == 200, r.text


def _like(client, headers, student_id):
    r = client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": student_id})
    assert r.status_code == 200, r.text
    return r.json()


def _roster(client, headers, class_name="初一1班"):
    r = client.get(f"/api/classes/{class_name}/roster", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _row(payload, student_no):
    return next(x for x in payload["items"] if x["student_no"] == student_no)


def test_regular_teacher_only_sees_own_likes(client, admin_headers, school):
    t2 = _make(client, admin_headers, "T002", "数学老师", "数学")
    _assign(client, admin_headers, t2["id"], ["初一1班"])
    t2_headers = login_headers(client, "T002", "123456")
    sid = school["student_ids"]["2026001"]

    mine = _like(client, school["teacher_headers"], sid)
    assert mine["likes"][0]["my_semester_likes"] == 1
    assert "semester_balance" not in mine["likes"][0]
    for _ in range(2):
        other = _like(client, t2_headers, sid)
    assert other["likes"][0]["my_semester_likes"] == 2

    payload = _roster(client, school["teacher_headers"])
    assert payload["viewer_scope"] == "self"
    assert "class_semester_likes" not in payload
    assert "class_total_likes" not in payload
    row = _row(payload, "2026001")
    assert row["my_semester_likes"] == 1
    assert row["my_total_likes"] == 1
    for hidden in ("student_semester_likes", "student_total_likes", "semester_balance", "total_balance"):
        assert hidden not in row

    # 管理员能看到完整口径：全班 3 赞，学生 3 赞，官方余额 3 星灿币
    admin_payload = _roster(client, admin_headers)
    assert admin_payload["viewer_scope"] == "admin"
    assert admin_payload["class_semester_likes"] == 3
    assert admin_payload["class_total_likes"] == 3
    admin_row = _row(admin_payload, "2026001")
    assert admin_row["student_semester_likes"] == 3
    assert admin_row["student_total_likes"] == 3
    assert admin_row["semester_balance"] == 3
    assert admin_row["total_balance"] == 3
    assert admin_row["my_semester_likes"] == 0


def test_head_and_deputy_see_totals_but_not_other_teacher_usage(client, admin_headers, school):
    t1 = _teacher(client, admin_headers, "T001")
    head = _make(client, admin_headers, "T002", "班主任", "语文")
    deputy = _make(client, admin_headers, "T003", "副班主任", "数学")
    _assign(client, admin_headers, head["id"], ["初一1班"])
    _assign(client, admin_headers, deputy["id"], ["初一1班"])
    _set_duty(client, admin_headers, "初一1班", head["id"], "head")
    _set_duty(client, admin_headers, "初一1班", deputy["id"], "deputy")
    head_headers = login_headers(client, "T002", "123456")
    deputy_headers = login_headers(client, "T003", "123456")

    sid1 = school["student_ids"]["2026001"]
    sid2 = school["student_ids"]["2026002"]
    _like(client, school["teacher_headers"], sid1)
    _like(client, head_headers, sid1)
    _like(client, head_headers, sid1)
    _like(client, deputy_headers, sid2)

    head_payload = _roster(client, head_headers)
    assert head_payload["viewer_scope"] == "class_manager"
    assert head_payload["class_semester_likes"] == 4
    assert head_payload["class_total_likes"] == 4
    row1 = _row(head_payload, "2026001")
    row2 = _row(head_payload, "2026002")
    assert row1["student_semester_likes"] == 3
    assert row1["student_total_likes"] == 3
    assert row1["my_semester_likes"] == 2
    assert row2["student_semester_likes"] == 1
    assert row2["my_semester_likes"] == 0
    # 班主任/副班主任仍然看不到官方星币余额，也没有按老师拆分的字段
    for row in (row1, row2):
        assert "semester_balance" not in row
        assert "total_balance" not in row
        assert "teacher_likes" not in row
        assert "teachers" not in row

    deputy_payload = _roster(client, deputy_headers)
    assert deputy_payload["viewer_scope"] == "class_manager"
    assert deputy_payload["class_semester_likes"] == 4
    assert _row(deputy_payload, "2026001")["my_semester_likes"] == 0
    assert _row(deputy_payload, "2026002")["my_semester_likes"] == 1

    # 班主任/副班主任的使用统计仍只返回本人，不能看其他老师
    for headers, employee_no, like_count in (
        (head_headers, "T002", 2),
        (deputy_headers, "T003", 1),
    ):
        usage = client.get("/api/stats/usage", headers=headers, params={"period": "month"}).json()
        assert {x["employee_no"] for x in usage["items"]} == {employee_no}
        assert usage["items"][0]["like_count"] == like_count
        assert client.get(
            f"/api/stats/usage/{t1['id']}", headers=headers, params={"period": "month"}
        ).status_code == 403
        recent = client.get("/api/likes/recent", headers=headers).json()["items"]
        assert all(item["teacher_name"] == usage["items"][0]["name"] for item in recent)


def test_subject_lead_same_subject_stats_but_class_roster_is_private(client, admin_headers, school):
    t1 = _teacher(client, admin_headers, "T001")
    client.patch(f"/api/teachers/{t1['id']}", headers=admin_headers, json={"subject": "语文"})
    lead = _make(client, admin_headers, "T003", "语文组长", "语文", role="subject_lead")
    other = _make(client, admin_headers, "T004", "数学老师", "数学")
    principal = _make(client, admin_headers, "T900", "校长", "语文", role="admin")
    _assign(client, admin_headers, lead["id"], ["初一1班"])
    _assign(client, admin_headers, other["id"], ["初一1班"])
    lead_headers = login_headers(client, "T003", "123456")
    other_headers = login_headers(client, "T004", "123456")

    sid1 = school["student_ids"]["2026001"]
    sid2 = school["student_ids"]["2026002"]
    _like(client, school["teacher_headers"], sid1)
    _like(client, other_headers, sid1)
    _like(client, other_headers, sid1)
    _like(client, lead_headers, sid2)

    payload = _roster(client, lead_headers)
    assert payload["viewer_scope"] == "self"
    assert "class_semester_likes" not in payload
    row1 = _row(payload, "2026001")
    assert row1["my_semester_likes"] == 0
    assert "student_semester_likes" not in row1

    usage = client.get("/api/stats/usage", headers=lead_headers, params={"period": "month"}).json()
    assert {x["employee_no"] for x in usage["items"]} == {"T001", "T003"}
    assert next(x for x in usage["items"] if x["employee_no"] == "T001")["like_count"] == 1
    assert client.get(
        f"/api/stats/usage/{t1['id']}", headers=lead_headers, params={"period": "month"}
    ).status_code == 200
    assert client.get(
        f"/api/stats/usage/{other['id']}", headers=lead_headers, params={"period": "month"}
    ).status_code == 403
    # 校长/主任即使带同学科，也不进入学科组长的统计范围
    assert "T900" not in {x["employee_no"] for x in usage["items"]}
    assert client.get(
        f"/api/stats/usage/{principal['id']}", headers=lead_headers, params={"period": "month"}
    ).status_code == 403


def test_class_totals_follow_current_class_and_ignore_revoked(client, admin_headers, school):
    head = _make(client, admin_headers, "T002", "班主任", "语文")
    _assign(client, admin_headers, head["id"], ["初一1班"])
    _set_duty(client, admin_headers, "初一1班", head["id"], "head")
    head_headers = login_headers(client, "T002", "123456")

    sid1 = school["student_ids"]["2026001"]
    sid2 = school["student_ids"]["2026002"]
    first = _like(client, school["teacher_headers"], sid1)
    revoked = _like(client, school["teacher_headers"], sid1)
    _like(client, school["teacher_headers"], sid2)
    _like(client, head_headers, sid1)
    r = client.post("/api/likes/revoke", headers=school["teacher_headers"], json={"batch_id": revoked["batch_id"]})
    assert r.status_code == 200, r.text

    payload = _roster(client, head_headers)
    assert payload["class_semester_likes"] == 3
    assert payload["class_total_likes"] == 3
    assert _row(payload, "2026001")["student_semester_likes"] == 2
    assert _row(payload, "2026002")["student_semester_likes"] == 1
    assert _row(payload, "2026001")["my_semester_likes"] == 1

    # 学生转班后，历史点赞保留在点赞发生时的班级快照中
    r = client.patch(f"/api/students/{sid2}", headers=admin_headers, json={"class_name": "初一2班"})
    assert r.status_code == 200, r.text
    payload = _roster(client, head_headers)
    assert payload["class_semester_likes"] == 2
    assert all(x["student_no"] != "2026002" for x in payload["items"])
    other_payload = _roster(client, admin_headers, "初一2班")
    assert other_payload["class_semester_likes"] == 0
    assert _row(other_payload, "2026002")["student_semester_likes"] == 0

    old_class_usage = client.get(
        "/api/stats/usage", headers=admin_headers, params={"class_name": "初一1班"}
    ).json()
    assert old_class_usage["summary"]["total_likes"] == 3


def test_cumulative_likes_survive_semester_switch(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    _like(client, school["teacher_headers"], sid)

    r = client.post(
        "/api/semesters",
        headers=admin_headers,
        json={"name": "第二学期", "start_date": "2027-02-01", "end_date": "2027-07-01"},
    )
    assert r.status_code == 200, r.text
    assert client.post(f"/api/semesters/{r.json()['id']}/activate", headers=admin_headers).status_code == 200

    row = _row(_roster(client, school["teacher_headers"]), "2026001")
    assert row["my_semester_likes"] == 0
    assert row["my_total_likes"] == 1

    _like(client, school["teacher_headers"], sid)
    row = _row(_roster(client, school["teacher_headers"]), "2026001")
    assert row["my_semester_likes"] == 1
    assert row["my_total_likes"] == 2

    admin_row = _row(_roster(client, admin_headers), "2026001")
    assert admin_row["student_semester_likes"] == 1
    assert admin_row["student_total_likes"] == 2


def test_group_like_response_only_returns_my_counts(client, admin_headers, school):
    r = client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "group", "target_id": school["group_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert all(x["my_semester_likes"] == 1 for x in body["likes"])
    assert all("semester_balance" not in x for x in body["likes"])

    r = client.post(
        "/api/likes/decrement",
        headers=school["teacher_headers"],
        json={"student_id": school["student_ids"]["2026001"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["my_semester_likes"] == 0
    assert "semester_balance" not in r.json()
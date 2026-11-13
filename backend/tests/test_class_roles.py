"""Class duties: head/deputy teacher roles and scoped management permissions."""
import pytest

from tests.helpers import login_headers


def teacher_id(client, admin_headers, employee_no):
    items = client.get("/api/teachers", headers=admin_headers, params={"page_size": 200}).json()["items"]
    return next(t for t in items if t["employee_no"] == employee_no)["id"]


def assign(client, headers, class_name, tid, duty):
    return client.post(
        f"/api/classes/{class_name}/teachers", headers=headers, json={"teacher_id": tid, "duty": duty}
    )


def make_teacher(client, admin_headers, employee_no, name):
    r = client.post("/api/teachers", headers=admin_headers, json={"employee_no": employee_no, "name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_assign_head_and_deputy_with_single_holder(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    t2 = make_teacher(client, admin_headers, "T002", "赵老师")
    t3 = make_teacher(client, admin_headers, "T003", "钱老师")
    assert assign(client, admin_headers, "初一1班", t1, "head").status_code == 200
    assert assign(client, admin_headers, "初一1班", t2, "deputy").status_code == 200
    # 新班主任接任后，原班主任自动成为普通任课教师
    assert assign(client, admin_headers, "初一1班", t3, "head").status_code == 200
    items = client.get("/api/classes/初一1班/teachers", headers=admin_headers).json()["items"]
    duties = {t["employee_no"]: t["duty"] for t in items}
    assert duties["T001"] == "teacher"
    assert duties["T002"] == "deputy"
    assert duties["T003"] == "head"


def test_invalid_duty_rejected(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    assert assign(client, admin_headers, "初一1班", t1, "principal").status_code == 400


def test_my_class_roles(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    t2 = make_teacher(client, admin_headers, "T002", "赵老师")
    assign(client, admin_headers, "初一1班", t1, "head")
    assign(client, admin_headers, "初一1班", t2, "deputy")
    r = client.get("/api/my/class-roles", headers=school["teacher_headers"])
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [{"class_name": "初一1班", "duty": "head"}]
    deputy_headers = login_headers(client, "T002", "123456")
    assert client.get("/api/my/class-roles", headers=deputy_headers).json()["items"] == [
        {"class_name": "初一1班", "duty": "deputy"}
    ]


@pytest.mark.parametrize("duty", ["head", "deputy"])
def test_class_managers_can_manage_own_students(client, admin_headers, school, duty):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, duty)
    headers = school["teacher_headers"]
    r = client.post(
        "/api/students",
        headers=headers,
        json={"student_no": "2026999", "name": "本班新生", "class_name": "初一1班"},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.patch(f"/api/students/{sid}", headers=headers, json={"name": "本班新生改"}).status_code == 200
    assert client.delete(f"/api/students/{sid}", headers=headers).status_code == 200


def test_class_manager_cannot_manage_other_class_students(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, "head")
    r = client.post(
        "/api/students",
        headers=school["teacher_headers"],
        json={"student_no": "2026999", "name": "跨班新生", "class_name": "初一2班"},
    )
    assert r.status_code == 403


def test_regular_teacher_cannot_manage_students(client, school):
    r = client.post(
        "/api/students",
        headers=school["teacher_headers"],
        json={"student_no": "2026999", "name": "越权新生", "class_name": "初一1班"},
    )
    assert r.status_code == 403


def test_head_can_manage_class_teachers_but_deputy_cannot(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    t2 = make_teacher(client, admin_headers, "T002", "赵老师")
    t3 = make_teacher(client, admin_headers, "T003", "钱老师")
    assign(client, admin_headers, "初一1班", t2, "deputy")
    deputy_headers = login_headers(client, "T002", "123456")
    assert assign(client, deputy_headers, "初一1班", t3, "teacher").status_code == 403

    head_headers = school["teacher_headers"]
    assign(client, admin_headers, "初一1班", t1, "head")
    assert assign(client, head_headers, "初一1班", t3, "teacher").status_code == 200
    assert client.delete(f"/api/classes/初一1班/teachers/{t3}", headers=head_headers).status_code == 200


@pytest.mark.parametrize("duty", ["head", "deputy"])
def test_class_managers_can_manage_own_groups(client, admin_headers, school, duty):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, duty)
    headers = school["teacher_headers"]
    r = client.post(
        "/api/groups",
        headers=headers,
        json={"name": "新管理组", "class_name": "初一1班", "member_student_nos": ["2026001"]},
    )
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    assert client.patch(f"/api/groups/{gid}", headers=headers, json={"name": "新管理组改"}).status_code == 200
    assert client.delete(f"/api/groups/{gid}", headers=headers).status_code == 200


def test_class_manager_cannot_manage_other_class_groups(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, "head")
    r = client.post(
        "/api/groups",
        headers=school["teacher_headers"],
        json={"name": "跨班组", "class_name": "初一2班", "member_student_nos": []},
    )
    assert r.status_code == 403


def test_head_can_list_teacher_options(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, "head")
    r = client.get("/api/teachers/options", headers=school["teacher_headers"])
    assert r.status_code == 200, r.text
    assert any(t["employee_no"] == "T001" for t in r.json()["items"])
    assert "phone" not in r.json()["items"][0]


def test_regular_teacher_cannot_list_teacher_options(client, school):
    assert client.get("/api/teachers/options", headers=school["teacher_headers"]).status_code == 403


def test_class_manager_cannot_add_out_of_class_group_member(client, admin_headers, school):
    t1 = teacher_id(client, admin_headers, "T001")
    assign(client, admin_headers, "初一1班", t1, "head")
    client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2026999", "name": "外班学生", "class_name": "初一2班"},
    )
    r = client.post(
        "/api/groups",
        headers=school["teacher_headers"],
        json={"name": "越界组", "class_name": "初一1班", "member_student_nos": ["2026999"]},
    )
    assert r.status_code == 400
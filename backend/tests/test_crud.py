"""Admin CRUD for teachers/students/groups; permission boundaries."""
from tests.helpers import login_headers


def test_admin_create_teacher_and_login(client, admin_headers):
    r = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T002", "name": "赵老师", "password": "abc12345"},
    )
    assert r.status_code == 200, r.text
    assert login_headers(client, "T002", "abc12345")


def test_admin_update_teacher_role(client, admin_headers):
    tid = client.post("/api/teachers", headers=admin_headers, json={"employee_no": "T002", "name": "赵老师"}).json()["id"]
    r = client.patch(f"/api/teachers/{tid}", headers=admin_headers, json={"role": "admin"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": "T002", "password": "123456"}).json()["teacher"]["role"] == "admin"


def test_admin_deactivate_teacher_blocks_login(client, admin_headers):
    tid = client.post("/api/teachers", headers=admin_headers, json={"employee_no": "T002", "name": "赵老师"}).json()["id"]
    assert client.delete(f"/api/teachers/{tid}", headers=admin_headers).status_code == 200
    assert client.post("/api/auth/login", json={"username": "T002", "password": "123456"}).status_code == 401


def test_teacher_cannot_manage_teachers(client, school):
    r = client.post("/api/teachers", headers=school["teacher_headers"], json={"employee_no": "T999", "name": "黑客"})
    assert r.status_code == 403


def test_teacher_list_pagination(client, admin_headers):
    for i in range(3):
        client.post("/api/teachers", headers=admin_headers, json={"employee_no": f"T10{i}", "name": f"老师{i}"})
    r = client.get("/api/teachers", headers=admin_headers, params={"page_size": 2})
    assert r.json()["total"] == 4  # + seeded admin
    assert len(r.json()["items"]) == 2


def test_teacher_list_accepts_large_page(client, admin_headers):
    r = client.get("/api/teachers", headers=admin_headers, params={"page_size": 500})
    assert r.status_code == 200


def test_admin_create_student(client, admin_headers):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2026099", "name": "新同学", "class_name": "初一1班"},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/students", headers=admin_headers, params={"q": "新同学"}).json()["total"] == 1


def test_admin_update_student(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    r = client.patch(f"/api/students/{sid}", headers=admin_headers, json={"name": "张小明改"})
    assert r.status_code == 200
    assert client.get("/api/students", headers=admin_headers, params={"q": "张小明改"}).json()["total"] == 1


def test_admin_delete_student_soft(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    assert client.delete(f"/api/students/{sid}", headers=admin_headers).status_code == 200
    assert client.get("/api/students", headers=admin_headers).json()["total"] == 1
    roster = client.get("/api/classes/初一1班/roster", headers=admin_headers).json()["items"]
    assert all(s["student_no"] != "2026001" for s in roster)


def test_admin_create_group_with_members(client, admin_headers, school):
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "新星组", "class_name": "初一1班", "member_student_nos": ["2026001"]},
    )
    assert r.status_code == 200, r.text
    groups = client.get("/api/groups", headers=admin_headers).json()["items"]
    new = next(g for g in groups if g["name"] == "新星组")
    assert new["member_count"] == 1


def test_admin_update_group_members(client, admin_headers, school):
    gid = school["group_id"]
    r = client.patch(f"/api/groups/{gid}", headers=admin_headers, json={"member_student_nos": ["2026002"]})
    assert r.status_code == 200
    groups = client.get("/api/groups", headers=admin_headers).json()["items"]
    assert next(g for g in groups if g["id"] == gid)["member_count"] == 1


def test_admin_delete_group(client, admin_headers, school):
    assert client.delete(f"/api/groups/{school['group_id']}", headers=admin_headers).status_code == 200
    assert client.get("/api/groups", headers=admin_headers).json()["items"] == []


def test_classes_list(client, admin_headers, school):
    r = client.get("/api/classes", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == ["初一1班"]


def test_teacher_subject_and_classes_in_list(client, admin_headers, school):
    teachers = client.get("/api/teachers", headers=admin_headers, params={"page_size": 200}).json()["items"]
    t = next(x for x in teachers if x["employee_no"] == "T001")
    assert t["classes"] == ["初一1班"]
    r = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T002", "name": "赵老师", "subject": "数学"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["subject"] == "数学"
    tid = r.json()["id"]
    assert client.patch(f"/api/teachers/{tid}", headers=admin_headers, json={"subject": "物理"}).json()["subject"] == "物理"


def test_student_gender_crud_and_roster(client, admin_headers, school):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2026099", "name": "新同学", "class_name": "初一1班", "gender": "女"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["gender"] == "女"
    sid = r.json()["id"]
    assert client.patch(f"/api/students/{sid}", headers=admin_headers, json={"gender": "男"}).json()["gender"] == "男"
    bad = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2026098", "name": "坏性别", "class_name": "初一1班", "gender": "X"},
    )
    assert bad.status_code == 400
    roster = client.get("/api/classes/初一1班/roster", headers=admin_headers).json()["items"]
    assert next(x for x in roster if x["student_no"] == "2026099")["gender"] == "男"
"""Class teachers: list with subject, assign/remove teaching assignments."""


def test_class_teachers_list(client, admin_headers, school):
    r = client.get("/api/classes/初一1班/teachers", headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(t["employee_no"] == "T001" for t in items)


def test_assign_and_remove_class_teacher(client, admin_headers, school):
    tid = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T002", "name": "赵老师", "subject": "数学"},
    ).json()["id"]
    r = client.post("/api/classes/初一1班/teachers", headers=admin_headers, json={"teacher_id": tid})
    assert r.status_code == 200, r.text
    items = client.get("/api/classes/初一1班/teachers", headers=admin_headers).json()["items"]
    t = next(x for x in items if x["employee_no"] == "T002")
    assert t["subject"] == "数学"
    # 重复指派幂等
    assert client.post("/api/classes/初一1班/teachers", headers=admin_headers, json={"teacher_id": tid}).status_code == 200
    items = client.get("/api/classes/初一1班/teachers", headers=admin_headers).json()["items"]
    assert sum(1 for x in items if x["employee_no"] == "T002") == 1
    r = client.delete(f"/api/classes/初一1班/teachers/{tid}", headers=admin_headers)
    assert r.status_code == 200
    items = client.get("/api/classes/初一1班/teachers", headers=admin_headers).json()["items"]
    assert all(x["employee_no"] != "T002" for x in items)


def test_assign_unknown_teacher_404(client, admin_headers, school):
    r = client.post("/api/classes/初一1班/teachers", headers=admin_headers, json={"teacher_id": 99999})
    assert r.status_code == 404


def test_assign_requires_admin(client, school):
    r = client.post("/api/classes/初一1班/teachers", headers=school["teacher_headers"], json={"teacher_id": 1})
    assert r.status_code == 403
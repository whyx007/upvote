"""Class registry (28/20/12), 级 (enrollment year) roster and imports."""
import io

from openpyxl import load_workbook

from tests.helpers import import_students, login_headers, make_xlsx, upload


def test_bulk_create_60_classes_and_empty_class_roster(client, admin_headers):
    r = client.post(
        "/api/classes/registry/bulk",
        headers=admin_headers,
        json={
            "items": [
                {"grade": "七年级", "count": 28, "enrollment_year": 2026},
                {"grade": "八年级", "count": 20, "enrollment_year": 2025},
                {"grade": "九年级", "count": 12, "enrollment_year": 2024},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 60
    assert len(client.get("/api/classes", headers=admin_headers).json()) == 60
    registry = client.get("/api/classes/registry", headers=admin_headers).json()["items"]
    assert len(registry) == 60
    assert next(x for x in registry if x["name"] == "七年级二十八班")["student_count"] == 0

    # 空班也能指派教师并查看空花名册
    teacher = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T100", "name": "空班老师", "subject": "语文"},
    ).json()
    assert client.put(
        f"/api/teachers/{teacher['id']}/classes", headers=admin_headers, json={"class_names": ["七年级二十八班"]}
    ).status_code == 200
    headers = login_headers(client, "T100", "123456")
    roster = client.get("/api/classes/七年级二十八班/roster", headers=headers)
    assert roster.status_code == 200
    assert roster.json()["items"] == []
    assert "七年级二十八班" in client.get("/api/my/classes", headers=headers).json()


def test_student_import_with_grade_alias_and_cohort(client, admin_headers):
    r = import_students(
        client,
        admin_headers,
        [
            ["", "张小明", "初一", "初一1班", 2026, "男"],
            ["", "李小红", "初一", "初一1班", 2026, "女"],
        ],
    )
    assert r.status_code == 200, r.text
    assert r.json()["students"]["created"] == 2
    listing = client.get("/api/students", headers=admin_headers, params={"grade": "七年级"}).json()
    assert listing["total"] == 2
    assert {x["grade"] for x in listing["items"]} == {"七年级"}
    assert {x["enrollment_year"] for x in listing["items"]} == {2026}
    # 同一份名单再导入按“姓名+班级+级”更新，不重复
    again = import_students(client, admin_headers, [["", "张小明", "初一", "初一1班", 2026, "男"]])
    assert again.json()["students"]["updated"] == 1
    assert client.get("/api/students", headers=admin_headers).json()["total"] == 2


def test_student_create_without_number_and_filters(client, admin_headers):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"name": "无学号", "class_name": "初二3班", "gender": "女", "enrollment_year": 2025},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_no"].startswith("S")
    assert r.json()["grade"] == "八年级"
    # 班级主数据自动出现
    assert "初二3班" in client.get("/api/classes", headers=admin_headers).json()


def test_rename_class_moves_students(client, admin_headers):
    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    registry = client.get("/api/classes/registry", headers=admin_headers).json()["items"]
    klass = next(x for x in registry if x["name"] == "初一1班")
    assert klass["id"] is not None
    r = client.patch(
        f"/api/classes/registry/{klass['id']}",
        headers=admin_headers,
        json={"name": "七年级一班"},
    )
    assert r.status_code == 200, r.text
    student = client.get("/api/students", headers=admin_headers).json()["items"][0]
    assert student["class_name"] == "七年级一班"


def test_deactivate_class_with_students_rejected(client, admin_headers):
    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    registry = client.get("/api/classes/registry", headers=admin_headers).json()["items"]
    kid = next(x for x in registry if x["name"] == "初一1班")["id"]
    assert client.delete(f"/api/classes/registry/{kid}", headers=admin_headers).status_code == 400


def test_import_teacher_subject_and_role(client, admin_headers):
    content = make_xlsx(
        {
            "教师": [
                ["工号", "姓名", "学科", "手机号", "初始密码", "角色"],
                ["T201", "语文组长", "语文", None, None, "学科组长"],
                ["T202", "数学老师", "数学", None, None, "任课教师"],
            ]
        }
    )
    r = upload(client, admin_headers, content)
    assert r.status_code == 200, r.text
    assert r.json()["teachers"]["created"] == 2
    items = client.get("/api/teachers", headers=admin_headers, params={"subject": "语文"}).json()["items"]
    assert len(items) == 1
    assert items[0]["role"] == "subject_lead"
    assert client.post("/api/auth/login", json={"username": "T201", "password": "123456"}).status_code == 200


def test_import_template_contains_cohort_column(client, admin_headers):
    r = client.get("/api/imports/template", headers=admin_headers)
    wb = load_workbook(io.BytesIO(r.content))
    headers = [c.value for c in wb["学生"][1]]
    assert "级" in headers
    assert "学科" in [c.value for c in wb["教师"][1]]
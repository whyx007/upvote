"""Excel import: template, upsert, row errors, scattered incremental data."""
import io

from openpyxl import load_workbook

from tests.helpers import (
    GROUP_HEADER,
    STUDENT_HEADER,
    TEACHER_HEADER,
    TEACHING_HEADER,
    import_students,
    make_xlsx,
    upload,
)


def test_template_download_has_four_sheets(client, admin_headers):
    r = client.get("/api/imports/template", headers=admin_headers)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert set(wb.sheetnames) == {"学生", "教师", "小组", "任教"}


def test_import_students_creates(client, admin_headers):
    r = import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    assert r.status_code == 200, r.text
    assert r.json()["students"]["created"] == 1
    listing = client.get("/api/students", headers=admin_headers, params={"q": "张小明"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["student_no"] == "2026001"


def test_import_students_upsert_no_duplicates(client, admin_headers):
    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    r = import_students(client, admin_headers, [["2026001", "张小明改", "初一", "初一2班", 2026]])
    assert r.json()["students"]["created"] == 0
    assert r.json()["students"]["updated"] == 1
    listing = client.get("/api/students", headers=admin_headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["name"] == "张小明改"
    assert listing["items"][0]["class_name"] == "初一2班"


def test_import_student_missing_required_reports_row_error(client, admin_headers):
    r = import_students(client, admin_headers, [["", "无学号", "初一", "初一1班", None]])
    assert r.status_code == 200
    errors = r.json()["students"]["errors"]
    assert len(errors) == 1
    assert errors[0]["row"] == 2
    assert "学号" in errors[0]["message"]
    assert client.get("/api/students", headers=admin_headers).json()["total"] == 0


def test_import_teachers_default_password_and_login(client, admin_headers):
    content = make_xlsx({"教师": [TEACHER_HEADER, ["T001", "王老师", "13800000001", None, None]]})
    r = upload(client, admin_headers, content)
    assert r.json()["teachers"]["created"] == 1
    login = client.post("/api/auth/login", json={"username": "T001", "password": "123456"})
    assert login.status_code == 200
    assert login.json()["teacher"]["role"] == "teacher"


def test_import_groups_with_members(client, admin_headers):
    import_students(
        client,
        admin_headers,
        [["2026001", "张小明", "初一", "初一1班", 2026], ["2026002", "李小红", "初一", "初一1班", 2026]],
    )
    content = make_xlsx({"小组": [GROUP_HEADER, ["星辰组", "初一1班", "2026001,2026002"]]})
    r = upload(client, admin_headers, content)
    assert r.json()["groups"]["created"] == 1
    groups = client.get("/api/groups", headers=admin_headers, params={"class_name": "初一1班"}).json()
    assert groups["items"][0]["name"] == "星辰组"
    assert groups["items"][0]["member_count"] == 2


def test_import_group_unknown_member_reports_error(client, admin_headers):
    content = make_xlsx({"小组": [GROUP_HEADER, ["幽灵组", "初一1班", "9999999"]]})
    r = upload(client, admin_headers, content)
    errors = r.json()["groups"]["errors"]
    assert len(errors) == 1
    assert "9999999" in errors[0]["message"]
    assert client.get("/api/groups", headers=admin_headers).json()["items"] == []


def test_import_teaching_assignments(client, admin_headers):
    upload(client, admin_headers, make_xlsx({"教师": [TEACHER_HEADER, ["T001", "王老师", None, None, None]]}))
    r = upload(client, admin_headers, make_xlsx({"任教": [TEACHING_HEADER, ["T001", "初一1班"]]}))
    assert r.json()["teaching"]["created"] == 1
    token = client.post("/api/auth/login", json={"username": "T001", "password": "123456"}).json()["token"]
    classes = client.get("/api/my/classes", headers={"Authorization": f"Bearer {token}"}).json()
    assert classes == ["初一1班"]


def test_incremental_scattered_import_keeps_existing(client, admin_headers):
    import_students(client, admin_headers, [["2026001", "张小明", "初一", "初一1班", 2026]])
    import_students(client, admin_headers, [["2026002", "李小红", "初一", "初一1班", 2026]])
    listing = client.get("/api/students", headers=admin_headers).json()
    assert listing["total"] == 2


def test_import_requires_admin(client, admin_headers):
    upload(client, admin_headers, make_xlsx({"教师": [TEACHER_HEADER, ["T001", "王老师", None, None, None]]}))
    token = client.post("/api/auth/login", json={"username": "T001", "password": "123456"}).json()["token"]
    r = import_students(client, {"Authorization": f"Bearer {token}"}, [["2026001", "张小明", "初一", "初一1班", 2026]])
    assert r.status_code == 403


def test_import_batch_history(client, admin_headers):
    upload(client, admin_headers, make_xlsx({"学生": [STUDENT_HEADER]}), filename="第一批.xlsx")
    history = client.get("/api/imports", headers=admin_headers).json()
    assert history["total"] == 1
    assert history["items"][0]["filename"] == "第一批.xlsx"


def test_single_workbook_cross_sheet_references(client, admin_headers):
    """同一工作簿内：小组引用本簿学生、任教引用本簿教师，必须成功。"""
    content = make_xlsx(
        {
            "学生": [
                STUDENT_HEADER,
                ["2026001", "张小明", "初一", "初一1班", 2026],
                ["2026002", "李小红", "初一", "初一1班", 2026],
            ],
            "教师": [TEACHER_HEADER, ["T001", "王老师", None, None, None]],
            "小组": [GROUP_HEADER, ["星辰组", "初一1班", "2026001,2026002"]],
            "任教": [TEACHING_HEADER, ["T001", "初一1班"]],
        }
    )
    r = upload(client, admin_headers, content)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["students"]["created"] == 2
    assert body["groups"]["created"] == 1
    assert body["groups"]["errors"] == []
    assert body["teaching"]["created"] == 1
    assert body["teaching"]["errors"] == []


def test_template_teacher_sheet_has_subject(client, admin_headers):
    r = client.get("/api/imports/template", headers=admin_headers)
    wb = load_workbook(io.BytesIO(r.content))
    header = [c.value for c in wb["教师"][1]]
    assert "学科" in header


def test_import_teachers_with_subject(client, admin_headers):
    content = make_xlsx({"教师": [TEACHER_HEADER + ["学科"], ["T001", "王老师", None, None, None, "语文"]]})
    r = upload(client, admin_headers, content)
    assert r.json()["teachers"]["created"] == 1
    teachers = client.get("/api/teachers", headers=admin_headers).json()["items"]
    t = next(x for x in teachers if x["employee_no"] == "T001")
    assert t["subject"] == "语文"
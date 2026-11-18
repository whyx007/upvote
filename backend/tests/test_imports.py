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


def test_template_download_has_two_roster_sheets(client, admin_headers):
    r = client.get("/api/imports/template", headers=admin_headers)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert set(wb.sheetnames) == {"学生", "教师", "说明"}
    assert "级" in [c.value for c in wb["学生"][1]]
    assert "班级" in [c.value for c in wb["学生"][1]]
    assert "年级" not in [c.value for c in wb["学生"][1]]


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


def test_import_student_without_student_no_gets_generated(client, admin_headers):
    r = import_students(client, admin_headers, [["", "无学号", "初一", "初一1班", None]])
    assert r.status_code == 200
    errors = r.json()["students"]["errors"]
    assert errors == []
    listing = client.get("/api/students", headers=admin_headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["student_no"].startswith("S")


def test_import_students_from_one_sheet_per_class(client, admin_headers):
    content = make_xlsx(
        {
            "七年级一班": [
                ["学号", "姓名", "性别", "级"],
                ["2026001", "张小明", "男", 2026],
                ["2026002", "李小红", "女", 2026],
            ],
            "七年级二班": [
                ["学号", "姓名", "性别", "级"],
                ["2026003", "王大力", "男", 2026],
            ],
        }
    )
    r = upload(client, admin_headers, content)
    assert r.status_code == 200, r.text
    assert r.json()["students"]["created"] == 3
    listing = client.get("/api/students", headers=admin_headers).json()
    assert listing["total"] == 3
    assert {x["class_name"] for x in listing["items"]} == {"七年级一班", "七年级二班"}


def test_import_teachers_from_one_sheet_per_subject(client, admin_headers):
    content = make_xlsx(
        {
            "语文": [
                ["工号", "姓名", "手机号", "初始密码", "角色"],
                ["T001", "语文组长", None, None, "学科组长"],
            ],
            "数学": [
                ["工号", "姓名", "手机号", "初始密码", "角色"],
                ["T002", "数学老师", None, None, "任课教师"],
            ],
        }
    )
    r = upload(client, admin_headers, content)
    assert r.status_code == 200, r.text
    assert r.json()["teachers"]["created"] == 2
    chinese = client.get("/api/teachers", headers=admin_headers, params={"subject": "语文"}).json()["items"]
    assert chinese[0]["role"] == "subject_lead"
    math = client.get("/api/teachers", headers=admin_headers, params={"subject": "数学"}).json()["items"]
    assert math[0]["employee_no"] == "T002"


def test_import_teachers_default_password_and_login(client, admin_headers):
    content = make_xlsx({"教师": [TEACHER_HEADER, ["T001", "王老师", "13800000001", None, None]]})
    r = upload(client, admin_headers, content)
    assert r.json()["teachers"]["created"] == 1
    login = client.post("/api/auth/login", json={"username": "T001", "password": "123456"})
    assert login.status_code == 200
    assert login.json()["teacher"]["role"] == "teacher"


def test_import_one_class_per_file_with_multi_select(client, admin_headers):
    def class_file(name, student_no):
        return make_xlsx({"学生": [["学号", "姓名", "性别"], [student_no, name, "男"]]})

    r = client.post(
        "/api/imports",
        headers=admin_headers,
        files=[
            ("files", ("七年级一班.xlsx", class_file("张小明", "2026001"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("七年级二班.xlsx", class_file("李小红", "2026002"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert len(body["items"]) == 2
    assert all(item["ok"] for item in body["items"])
    listing = client.get("/api/students", headers=admin_headers).json()
    assert listing["total"] == 2
    assert {x["class_name"] for x in listing["items"]} == {"七年级一班", "七年级二班"}


def test_class_file_name_mismatch_reports_row_error(client, admin_headers):
    content = make_xlsx({"学生": [["学号", "姓名", "班级"], ["2026001", "张小明", "七年级二班"]]})
    r = upload(client, admin_headers, content, filename="七年级一班.xlsx")
    assert r.status_code == 200, r.text
    errors = r.json()["students"]["errors"]
    assert errors and "不一致" in errors[0]["message"]
    assert client.get("/api/students", headers=admin_headers).json()["total"] == 0


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


def test_template_student_sheet_has_gender(client, admin_headers):
    r = client.get("/api/imports/template", headers=admin_headers)
    wb = load_workbook(io.BytesIO(r.content))
    header = [c.value for c in wb["学生"][1]]
    assert "性别" in header


def test_import_students_with_gender(client, admin_headers):
    content = make_xlsx({"学生": [STUDENT_HEADER + ["性别"], ["2026001", "张小明", "初一", "初一1班", 2026, "男"]]})
    r = upload(client, admin_headers, content)
    assert r.json()["students"]["created"] == 1
    s = client.get("/api/students", headers=admin_headers).json()["items"][0]
    assert s["gender"] == "男"


def test_import_student_invalid_gender_reports_error(client, admin_headers):
    content = make_xlsx({"学生": [STUDENT_HEADER + ["性别"], ["2026001", "张小明", "初一", "初一1班", 2026, "未知"]]})
    r = upload(client, admin_headers, content)
    errors = r.json()["students"]["errors"]
    assert len(errors) == 1
    assert "性别" in errors[0]["message"]


def test_import_teaching_with_class_duty(client, admin_headers):
    upload(client, admin_headers, make_xlsx({"教师": [TEACHER_HEADER, ["T001", "王老师", None, None, None]]}))
    r = upload(client, admin_headers, make_xlsx({"任教": [TEACHING_HEADER + ["角色"], ["T001", "初一1班", "班主任"]]}))
    assert r.status_code == 200, r.text
    assert r.json()["teaching"]["created"] == 1
    items = client.get("/api/classes/初一1班/teachers", headers=admin_headers).json()["items"]
    assert items[0]["duty"] == "head"
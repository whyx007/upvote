"""Test helpers: Excel builders and API shortcuts."""
import io

from openpyxl import Workbook

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STUDENT_HEADER = ["学号", "姓名", "年级", "班级", "入学年份"]
TEACHER_HEADER = ["工号", "姓名", "手机号", "初始密码", "角色"]
GROUP_HEADER = ["小组名称", "班级", "成员学号"]
TEACHING_HEADER = ["工号", "班级"]


def make_xlsx(sheets: dict) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, headers, content, filename="import.xlsx"):
    return client.post(
        "/api/imports", headers=headers, files={"file": (filename, content, XLSX_MIME)}
    )


def import_students(client, headers, rows):
    return upload(client, headers, make_xlsx({"学生": [STUDENT_HEADER, *rows]}))


def login_headers(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
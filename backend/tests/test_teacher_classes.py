"""Teacher-centric teaching assignment management (atomic replace)."""
from tests.helpers import login_headers


def _teacher_id(client, headers, employee_no):
    items = client.get("/api/teachers", headers=headers, params={"page_size": 200}).json()["items"]
    return next(t for t in items if t["employee_no"] == employee_no)["id"]


def test_set_teacher_classes_replace_and_clear(client, admin_headers, school):
    tid = _teacher_id(client, admin_headers, "T001")
    r = client.put(f"/api/teachers/{tid}/classes", headers=admin_headers, json={"class_names": ["初一1班", "初一2班"]})
    assert r.status_code == 200, r.text
    assert r.json()["classes"] == ["初一1班", "初一2班"]
    # 替换：移除旧班级
    r2 = client.put(f"/api/teachers/{tid}/classes", headers=admin_headers, json={"class_names": ["初一2班"]})
    assert r2.json()["classes"] == ["初一2班"]
    # 教师视角同步
    headers = login_headers(client, "T001", "123456")
    assert client.get("/api/my/classes", headers=headers).json() == ["初一2班"]
    # 清空
    r3 = client.put(f"/api/teachers/{tid}/classes", headers=admin_headers, json={"class_names": []})
    assert r3.json()["classes"] == []


def test_set_teacher_classes_deduplicates(client, admin_headers, school):
    tid = _teacher_id(client, admin_headers, "T001")
    r = client.put(
        f"/api/teachers/{tid}/classes",
        headers=admin_headers,
        json={"class_names": ["初一1班", "初一1班", "初一2班"]},
    )
    assert r.json()["classes"] == ["初一1班", "初一2班"]


def test_set_teacher_classes_requires_admin(client, admin_headers, school):
    tid = _teacher_id(client, admin_headers, "T001")
    r = client.put(f"/api/teachers/{tid}/classes", headers=school["teacher_headers"], json={"class_names": []})
    assert r.status_code == 403


def test_set_teacher_classes_unknown_teacher_404(client, admin_headers):
    r = client.put("/api/teachers/99999/classes", headers=admin_headers, json={"class_names": []})
    assert r.status_code == 404
"""学年升级：预览、九→归档、八→九、七→八、新建七年级。"""
from sqlalchemy import select

from app.models import Group, Like, SchoolClass, Student, TeacherClass


def _class(client, admin_headers, grade, number, year):
    r = client.post(
        "/api/classes/registry",
        headers=admin_headers,
        json={"grade": grade, "class_no": number, "enrollment_year": year},
    )
    assert r.status_code == 200, r.text
    return r.json()["name"]


def _student(client, admin_headers, no, name, class_name, grade, year):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={
            "student_no": no,
            "name": name,
            "class_name": class_name,
            "grade": grade,
            "enrollment_year": year,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_promotion_preview_and_run(client, admin_headers, school):
    seven = _class(client, admin_headers, "七年级", 10, 2026)
    eight = _class(client, admin_headers, "八年级", 10, 2025)
    nine = _class(client, admin_headers, "九年级", 10, 2024)
    _student(client, admin_headers, "202601001", "七年级学生", seven, "七年级", 2026)
    _student(client, admin_headers, "202501001", "八年级学生", eight, "八年级", 2025)
    _student(client, admin_headers, "202401001", "九年级学生", nine, "九年级", 2024)

    teacher = client.post(
        "/api/teachers",
        headers=admin_headers,
        json={"employee_no": "T900", "name": "跟班老师", "subject": "语文"},
    ).json()
    r = client.put(
        f"/api/teachers/{teacher['id']}/classes",
        headers=admin_headers,
        json={"class_names": [seven, eight, nine]},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "毕业组", "class_name": nine, "member_student_nos": ["202401001"]},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "升级组", "class_name": eight, "member_student_nos": ["202501001"]},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/likes",
        headers=admin_headers,
        json={"target_type": "student", "target_id": client.get("/api/students", headers=admin_headers, params={"q": "202401001"}).json()["items"][0]["id"]},
    )
    assert r.status_code == 200, r.text

    preview = client.get(
        "/api/admin/promotion/preview",
        headers=admin_headers,
        params={"target_year": 2027, "new_grade7_count": 2},
    )
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan["graduate"][0]["old"] == nine
    assert plan["graduate"][0]["new"] == "2024届九年级十班"
    assert plan["promote8"][0]["new"] == "九年级十班"
    promote7 = {item["old"]: item["new"] for item in plan["promote7"]}
    assert promote7[seven] == "八年级十班"
    assert plan["new_grade7"] == ["七年级一班", "七年级二班"]
    assert not plan["errors"]

    r = client.post(
        "/api/admin/promotion/run",
        headers=admin_headers,
        json={
            "password": "admin123",
            "confirm": "学年升级",
            "target_year": 2027,
            "new_grade7_count": 2,
        },
    )
    assert r.status_code == 200, r.text

    with client.app.state.session_factory() as db:
        classes = {klass.name: klass for klass in db.scalars(select(SchoolClass)).all()}
        assert classes["2024届九年级十班"].is_active is False
        assert classes["九年级十班"].is_active is True
        assert classes["九年级十班"].grade == "九年级"
        assert classes["八年级十班"].grade == "八年级"
        assert classes["七年级一班"].is_active is True
        assert classes["七年级一班"].enrollment_year == 2027

        graduated = db.scalar(select(Student).where(Student.student_no == "202401001"))
        assert graduated.is_active is False
        assert graduated.class_name == "2024届九年级十班"
        assert graduated.grade == "九年级"

        promoted8 = db.scalar(select(Student).where(Student.student_no == "202501001"))
        assert promoted8.is_active is True
        assert promoted8.class_name == "九年级十班"
        assert promoted8.grade == "九年级"

        promoted7 = db.scalar(select(Student).where(Student.student_no == "202601001"))
        assert promoted7.class_name == "八年级十班"
        assert promoted7.grade == "八年级"

        like = db.scalar(select(Like))
        assert like.class_name == "2024届九年级十班"

        assignments = {
            row.class_name
            for row in db.scalars(
                select(TeacherClass).where(TeacherClass.teacher_id == teacher["id"])
            ).all()
        }
        assert assignments == {"2024届九年级十班", "九年级十班", "八年级十班"}

        groups = {group.name: group.class_name for group in db.scalars(select(Group)).all()}
        assert groups["毕业组"] == "2024届九年级十班"
        assert groups["升级组"] == "九年级十班"

    class_names = client.get("/api/classes", headers=admin_headers).json()
    assert "2024届九年级十班" not in class_names
    my_classes = client.get("/api/my/classes", headers=admin_headers).json()
    assert "2024届九年级十班" not in my_classes
    visible_groups = client.get("/api/groups", headers=admin_headers).json()["items"]
    assert all(group["name"] != "毕业组" for group in visible_groups)
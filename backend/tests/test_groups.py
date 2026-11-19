"""Group member details and multi-group membership."""


def test_groups_include_members(client, admin_headers, school):
    r = client.get(
        "/api/groups",
        headers=admin_headers,
        params={"class_name": "初一1班", "include_members": 1},
    )
    assert r.status_code == 200, r.text
    g = r.json()["items"][0]
    assert g["member_count"] == 2
    names = {m["name"] for m in g["members"]}
    assert names == {"张小明", "李小红"}
    assert {m["student_no"] for m in g["members"]} == {"2026001", "2026002"}
    assert all("id" in m for m in g["members"])


def test_groups_without_flag_have_no_members(client, admin_headers, school):
    r = client.get("/api/groups", headers=admin_headers)
    assert "members" not in r.json()["items"][0]


def test_student_can_be_in_multiple_groups(client, admin_headers, school):
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "第二组", "class_name": "初一1班", "member_student_nos": ["2026001"]},
    )
    assert r.status_code == 200, r.text
    roster = client.get("/api/classes/初一1班/roster", headers=admin_headers).json()["items"]
    s = next(x for x in roster if x["student_no"] == "2026001")
    assert set(s["groups"]) == {"星辰组", "第二组"}
    other = next(x for x in roster if x["student_no"] == "2026002")
    assert other["groups"] == ["星辰组"]


def test_batch_create_groups_skips_existing(client, admin_headers, school):
    r = client.post(
        "/api/groups/batch",
        headers=admin_headers,
        json={
            "class_name": "初一1班",
            "names": ["星辰组", "追光组", "追光组", "  ", "启航组"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert body["items"] == ["追光组", "启航组"]
    assert body["skipped"] == ["星辰组"]

    groups = client.get("/api/groups", headers=admin_headers, params={"class_name": "初一1班"}).json()["items"]
    assert {g["name"] for g in groups} == {"星辰组", "追光组", "启航组"}


def test_batch_create_groups_by_count_continues_numbering(client, admin_headers, school):
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "第一组", "class_name": "初一1班", "member_student_nos": []},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/groups/batch",
        headers=admin_headers,
        json={"class_name": "初一1班", "count": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == ["第二组", "第三组"]

    r = client.post(
        "/api/groups/batch",
        headers=admin_headers,
        json={"class_name": "初一1班", "count": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == ["第四组", "第五组"]

    # 已有阿拉伯数字组名时，沿用阿拉伯数字风格
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "第10组", "class_name": "初一1班", "member_student_nos": []},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/api/groups/batch",
        headers=admin_headers,
        json={"class_name": "初一1班", "count": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == ["第11组"]


def test_randomize_groups_clears_and_balances_members(client, admin_headers, school):
    r = client.post(
        "/api/groups",
        headers=admin_headers,
        json={"name": "追光组", "class_name": "初一1班", "member_student_nos": []},
    )
    assert r.status_code == 200, r.text

    r = client.post("/api/groups/randomize", headers=admin_headers, json={"class_name": "初一1班"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["groups"] == 2
    assert body["students"] == 2
    assert sorted(x["member_count"] for x in body["items"]) == [1, 1]

    groups = client.get(
        "/api/groups", headers=admin_headers, params={"class_name": "初一1班", "include_members": 1}
    ).json()["items"]
    memberships = {m["student_no"]: 0 for g in groups for m in g["members"]}
    for group in groups:
        for member in group["members"]:
            memberships[member["student_no"]] += 1
    assert memberships == {"2026001": 1, "2026002": 1}


def test_batch_and_randomize_require_group_manager(client, admin_headers, school):
    for path, payload in (
        ("/api/groups/batch", {"class_name": "初一1班", "names": ["新组"]}),
        ("/api/groups/randomize", {"class_name": "初一1班"}),
    ):
        assert client.post(path, headers=school["teacher_headers"], json=payload).status_code == 403


def test_randomize_requires_groups(client, admin_headers):
    r = client.post(
        "/api/students",
        headers=admin_headers,
        json={"student_no": "2027001", "name": "无组学生", "class_name": "初一2班"},
    )
    assert r.status_code == 200, r.text
    r = client.post("/api/groups/randomize", headers=admin_headers, json={"class_name": "初一2班"})
    assert r.status_code == 400
    assert "小组" in r.json()["detail"]
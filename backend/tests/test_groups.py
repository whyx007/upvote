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
"""Rewards catalog and redemptions: deduct, stock, cancel/refund, permissions."""
from tests.helpers import import_students


def give_likes(client, headers, student_id, n):
    for _ in range(n):
        r = client.post("/api/likes", headers=headers, json={"target_type": "student", "target_id": student_id})
        assert r.status_code == 200, r.text


def make_reward(client, headers, name="笔记本", cost=10, stock=None):
    body = {"name": name, "cost_coins": cost}
    if stock is not None:
        body["stock"] = stock
    r = client.post("/api/rewards", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_create_reward_and_list(client, admin_headers):
    make_reward(client, admin_headers, stock=5)
    items = client.get("/api/rewards", headers=admin_headers).json()["items"]
    assert items[0]["name"] == "笔记本"
    assert items[0]["cost_coins"] == 10
    assert items[0]["stock"] == 5


def test_redeem_deducts_balance(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    give_likes(client, school["teacher_headers"], sid, 12)
    reward_id = make_reward(client, admin_headers, cost=10)
    r = client.post("/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id})
    assert r.status_code == 200, r.text
    assert r.json()["new_balance"] == 2


def test_redeem_insufficient_balance_rejected(client, admin_headers, school):
    reward_id = make_reward(client, admin_headers, cost=10)
    r = client.post(
        "/api/redemptions",
        headers=admin_headers,
        json={"student_id": school["student_ids"]["2026001"], "reward_id": reward_id},
    )
    assert r.status_code == 400


def test_redeem_stock_decrements_and_out_of_stock(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    give_likes(client, school["teacher_headers"], sid, 2)
    reward_id = make_reward(client, admin_headers, cost=1, stock=1)
    assert client.post("/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id}).status_code == 200
    r = client.post("/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id})
    assert r.status_code == 400
    assert client.get("/api/rewards", headers=admin_headers).json()["items"][0]["stock"] == 0


def test_redeem_unlimited_stock(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    give_likes(client, school["teacher_headers"], sid, 3)
    reward_id = make_reward(client, admin_headers, cost=1)
    for _ in range(3):
        assert client.post("/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id}).status_code == 200


def test_cancel_redemption_refunds_and_restocks(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    give_likes(client, school["teacher_headers"], sid, 10)
    reward_id = make_reward(client, admin_headers, cost=10, stock=1)
    redemption_id = client.post(
        "/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id}
    ).json()["id"]
    r = client.post(f"/api/redemptions/{redemption_id}/cancel", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["new_balance"] == 10
    assert client.get("/api/rewards", headers=admin_headers).json()["items"][0]["stock"] == 1


def test_redeem_requires_admin(client, school):
    r = client.post(
        "/api/redemptions",
        headers=school["teacher_headers"],
        json={"student_id": school["student_ids"]["2026001"], "reward_id": 1},
    )
    assert r.status_code == 403


def test_redemption_history(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    give_likes(client, school["teacher_headers"], sid, 10)
    reward_id = make_reward(client, admin_headers, cost=10)
    client.post("/api/redemptions", headers=admin_headers, json={"student_id": sid, "reward_id": reward_id})
    r = client.get("/api/redemptions", headers=admin_headers, params={"student_id": sid})
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["reward_name"] == "笔记本"
    assert item["cost_coins"] == 10
    assert item["student_name"] == "张小明"


def test_teacher_can_view_rewards(client, school):
    r = client.get("/api/rewards", headers=school["teacher_headers"])
    assert r.status_code == 200
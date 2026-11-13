"""Auth: seeded admin, login, me, change password, lockout."""


def test_seeded_admin_can_login(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["teacher"]["role"] == "admin"
    assert body["teacher"]["employee_no"] == "admin"
    assert body["token"]


def test_login_wrong_password_rejected(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_rejected(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_me_returns_current_teacher(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["employee_no"] == "admin"
    assert r.json()["role"] == "admin"


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_change_password(client, admin_headers):
    r = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"old_password": "admin123", "new_password": "newpass456"},
    )
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "newpass456"}).status_code == 200


def test_change_password_wrong_old_rejected(client, admin_headers):
    r = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"old_password": "bad", "new_password": "newpass456"},
    )
    assert r.status_code == 400


def test_repeated_failed_logins_locked_out(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 429
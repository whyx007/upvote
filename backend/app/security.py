"""Password hashing, JWT, auth dependencies, login rate limiting."""
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .models import Teacher

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(teacher: Teacher, settings) -> str:
    payload = {
        "sub": str(teacher.id),
        "role": teacher.role,
        "name": teacher.name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_ttl_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def get_current_teacher(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Teacher:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(
            credentials.credentials, request.app.state.settings.secret_key, algorithms=["HS256"]
        )
        teacher_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    teacher = db.get(Teacher, teacher_id)
    if teacher is None or not teacher.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return teacher


def require_admin(teacher: Teacher = Depends(get_current_teacher)) -> Teacher:
    if teacher.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return teacher


def check_login_rate_limit(request: Request, username: str) -> None:
    settings = request.app.state.settings
    failures: dict = request.app.state.login_failures
    now = time.monotonic()
    attempts = [t for t in failures.get(username, []) if now - t < settings.login_lockout_seconds]
    if len(attempts) >= settings.login_max_attempts:
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")
    failures[username] = attempts


def record_login_failure(request: Request, username: str) -> None:
    failures: dict = request.app.state.login_failures
    failures.setdefault(username, []).append(time.monotonic())


def clear_login_failures(request: Request, username: str) -> None:
    request.app.state.login_failures.pop(username, None)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Teacher
from ..security import (
    check_login_rate_limit,
    clear_login_failures,
    create_token,
    get_current_teacher,
    get_db,
    hash_password,
    record_login_failure,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


def serialize_teacher(t: Teacher) -> dict:
    return {"id": t.id, "employee_no": t.employee_no, "name": t.name, "phone": t.phone, "role": t.role}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    check_login_rate_limit(request, body.username)
    teacher = db.scalar(
        select(Teacher).where(or_(Teacher.employee_no == body.username, Teacher.phone == body.username))
    )
    if teacher is None or not verify_password(body.password, teacher.password_hash):
        record_login_failure(request, body.username)
        raise HTTPException(status_code=401, detail="工号或密码错误")
    if not teacher.is_active:
        raise HTTPException(status_code=401, detail="账号已停用")
    clear_login_failures(request, body.username)
    return {"token": create_token(teacher, request.app.state.settings), "teacher": serialize_teacher(teacher)}


@router.get("/me")
def me(teacher: Teacher = Depends(get_current_teacher)):
    return serialize_teacher(teacher)


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    request: Request,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, teacher.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    teacher.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
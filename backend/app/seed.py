"""First-run seeding: default admin account."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Teacher
from .security import hash_password


def seed_admin(db: Session, settings) -> None:
    if db.scalar(select(func.count(Teacher.id))) == 0:
        db.add(
            Teacher(
                employee_no=settings.admin_employee_no,
                name="管理员",
                password_hash=hash_password(settings.admin_default_password),
                role="admin",
            )
        )
        db.commit()
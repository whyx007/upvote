"""Application settings (env-overridable)."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str = "sqlite:///data/upvote.db"
    secret_key: str = "dev-insecure-secret-change-me-0123456789"
    coins_per_like: int = 1
    token_ttl_hours: int = 168  # 7 天，Pad 免频繁登录
    admin_employee_no: str = "admin"
    admin_default_password: str = "admin123"
    login_max_attempts: int = 10
    login_lockout_seconds: int = 300
    backup_scheduler_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("UPVOTE_DATABASE_URL", cls.database_url),
            secret_key=os.environ.get("UPVOTE_SECRET_KEY", cls.secret_key),
            coins_per_like=int(os.environ.get("UPVOTE_COINS_PER_LIKE", "1")),
            token_ttl_hours=int(os.environ.get("UPVOTE_TOKEN_TTL_HOURS", "168")),
            backup_scheduler_enabled=os.environ.get("UPVOTE_BACKUP_SCHEDULER", "1").lower()
            not in ("0", "false", "no", "off"),
        )
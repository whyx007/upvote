"""SQLite 在线备份、自动轮替和恢复校验。"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy.engine.url import make_url

# 中国标准时间无夏令时，固定 UTC+8，避免 Windows 缺少 tzdata 时无法启动。
TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)
AUTO_PREFIX = "upvote-auto-"
SAFETY_PREFIX = "upvote-safety-"
AUTO_KEEP = 5
SAFETY_KEEP = 5
BACKUP_HOUR = 23
BACKUP_MINUTE = 30
REQUIRED_TABLES = {
    "teachers",
    "students",
    "classes",
    "teacher_classes",
    "groups",
    "group_members",
    "semesters",
    "likes",
    "rewards",
    "redemptions",
    "import_batches",
}


def sqlite_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve()


def auto_backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backups" / "auto"


def safety_backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backups" / "safety"


def create_sqlite_backup(source_path: Path, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(target_path))
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()
    return target_path


def _prune(directory: Path, prefix: str, keep: int) -> None:
    files = sorted(directory.glob(f"{prefix}*.db"), key=lambda item: item.name)
    for old in files[:-keep]:
        old.unlink(missing_ok=True)


def create_auto_backup(database_url: str) -> Path | None:
    db_path = sqlite_path(database_url)
    if db_path is None or not db_path.exists():
        return None
    directory = auto_backup_dir(db_path)
    target = directory / f"{AUTO_PREFIX}{datetime.now(TZ):%Y%m%d-%H%M%S}.db"
    create_sqlite_backup(db_path, target)
    _prune(directory, AUTO_PREFIX, AUTO_KEEP)
    return target


def create_safety_backup(database_url: str, reason: str) -> Path | None:
    db_path = sqlite_path(database_url)
    if db_path is None or not db_path.exists():
        return None
    directory = safety_backup_dir(db_path)
    target = directory / f"{SAFETY_PREFIX}{reason}-{datetime.now(TZ):%Y%m%d-%H%M%S}.db"
    create_sqlite_backup(db_path, target)
    _prune(directory, SAFETY_PREFIX, SAFETY_KEEP)
    return target


def next_backup_at(now: datetime | None = None) -> datetime:
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    for offset in range(0, 8):
        day = (now + timedelta(days=offset)).date()
        if day.weekday() >= 5:
            continue
        candidate = datetime.combine(day, time(BACKUP_HOUR, BACKUP_MINUTE), tzinfo=TZ)
        if candidate > now:
            return candidate
    return now + timedelta(days=1)


async def auto_backup_loop(database_url: str) -> None:
    while True:
        target = next_backup_at()
        delay = max(1.0, (target - datetime.now(TZ)).total_seconds())
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(create_auto_backup, database_url)
        except Exception:
            logger.exception("自动备份失败")


def list_auto_backups(database_url: str) -> list[dict]:
    db_path = sqlite_path(database_url)
    if db_path is None:
        return []
    directory = auto_backup_dir(db_path)
    if not directory.is_dir():
        return []
    files = sorted(directory.glob(f"{AUTO_PREFIX}*.db"), key=lambda item: item.name, reverse=True)
    items = []
    for path in files:
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, TZ).isoformat(),
            }
        )
    return items


def validate_database_file(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(16)
    if header != b"SQLite format 3\x00":
        raise ValueError("不是有效的 SQLite 数据库文件")

    connection = sqlite3.connect(str(path))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("数据库完整性校验失败")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(f"备份缺少必要的数据表：{', '.join(sorted(missing))}")
        admin_count = connection.execute(
            "SELECT COUNT(*) FROM teachers WHERE role='admin' AND is_active=1"
        ).fetchone()[0]
        if not admin_count:
            raise ValueError("备份中没有可用的管理员账号")
    finally:
        connection.close()
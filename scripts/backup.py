"""SQLite 在线安全备份（sqlite3.backup API），保留最近 30 份。

用法：python scripts/backup.py [数据库路径]
默认路径：data/upvote.db（相对当前目录）或环境变量 UPVOTE_DB。
建议每日计划任务执行一次。
"""
import os
import sqlite3
import sys
from datetime import datetime


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("UPVOTE_DB", os.path.join("data", "upvote.db"))
    if not os.path.exists(src):
        print(f"数据库不存在：{src}")
        sys.exit(1)
    dst_dir = os.path.join(os.path.dirname(os.path.abspath(src)), "backups")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"upvote-{datetime.now():%Y%m%d-%H%M%S}.db")
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    with target:
        source.backup(target)
    target.close()
    source.close()
    backups = sorted(f for f in os.listdir(dst_dir) if f.startswith("upvote-") and f.endswith(".db"))
    for old in backups[:-30]:
        os.remove(os.path.join(dst_dir, old))
    print(f"备份完成：{dst}（保留最近 {min(len(backups), 30)} 份）")


if __name__ == "__main__":
    main()
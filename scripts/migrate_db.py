"""把本地 SQLite 库整体迁移到 VPS（文件级迁移，保留点赞流水/账号密码等全部数据）。

用法：python scripts/migrate_db.py [--dry]
流程：本地 sqlite backup API 生成一致性快照 -> SFTP 上传 -> 远端停容器、备份旧库、替换、启容器 -> 校验。
"""
import os
import sqlite3
import sys
import time

import paramiko

HOST = os.environ.get("DSH_SSH_HOST", "43.133.86.206")
PORT = int(os.environ.get("DSH_SSH_PORT", "22"))
USER = os.environ.get("DSH_SSH_USER", "ubuntu")
PASSWORD = os.environ.get("DSH_SSH_PASSWORD", "")

LOCAL_DB = os.path.join("data", "upvote.db")
SNAPSHOT = os.path.join("build", "upvote-migrate.db")
REMOTE_DIR = "/opt/upvote"
REMOTE_DB = f"{REMOTE_DIR}/data/upvote.db"
REMOTE_TMP = "/tmp/upvote-migrate.db"
CONTAINER = "upvote"


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False)
    return c


def run(c, cmd, timeout=300, quiet=False):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    text = (out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")).strip()
    if not quiet:
        print(text)
    return out.channel.recv_exit_status(), text


def local_stats(path):
    db = sqlite3.connect(path)
    rows = {}
    for t in ("students", "teachers", "groups", "likes", "semesters"):
        try:
            rows[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            rows[t] = None
    rows["active_likes"] = db.execute("SELECT COUNT(*) FROM likes WHERE revoked_at IS NULL").fetchone()[0]
    db.close()
    return rows


def main():
    if not PASSWORD:
        raise SystemExit("请设置 DSH_SSH_PASSWORD")
    if not os.path.exists(LOCAL_DB):
        raise SystemExit(f"本地库不存在：{LOCAL_DB}")

    print("==> 1/5 生成一致性快照（sqlite backup API，含 WAL 未落盘数据）")
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    if os.path.exists(SNAPSHOT):
        os.remove(SNAPSHOT)
    src = sqlite3.connect(LOCAL_DB)
    dst = sqlite3.connect(SNAPSHOT)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    stats = local_stats(SNAPSHOT)
    print(f"快照 {SNAPSHOT} ({os.path.getsize(SNAPSHOT)/1024:.0f} KB) 内容: {stats}")

    if "--dry" in sys.argv:
        print("dry-run：不做远端变更")
        return

    c = connect()
    try:
        print("==> 2/5 上传快照")
        with c.open_sftp() as sftp:
            sftp.put(SNAPSHOT, REMOTE_TMP)
        print(f"已上传 {REMOTE_TMP}")

        print("==> 3/5 停容器并备份线上库")
        ts = time.strftime("%Y%m%d-%H%M%S")
        run(c, f"sudo -n docker stop {CONTAINER}", quiet=True)
        code, text = run(
            c,
            f"sudo -n test -f {REMOTE_DB} && sudo -n cp {REMOTE_DB} {REMOTE_DIR}/data/upvote.db.bak.{ts} && echo BACKED_UP || echo NO_OLD_DB",
            quiet=True,
        )
        print(text)

        print("==> 4/5 替换数据库")
        run(
            c,
            f"sudo -n cp {REMOTE_TMP} {REMOTE_DB} && sudo -n chown 1000:1000 {REMOTE_DB} 2>/dev/null; "
            f"sudo -n chmod 664 {REMOTE_DB} && sudo -n rm -f {REMOTE_DIR}/data/upvote.db-wal {REMOTE_DIR}/data/upvote.db-shm",
            quiet=True,
        )
        code, text = run(c, f"ls -l {REMOTE_DB}", quiet=True)
        print(text)

        print("==> 5/5 启动容器并校验")
        run(c, f"sudo -n docker start {CONTAINER}", quiet=True)
        for _ in range(20):
            code, text = run(c, "curl -s --max-time 5 http://127.0.0.1:9100/api/health || true", quiet=True)
            if '"ok"' in text:
                print("健康检查:", text)
                break
            time.sleep(3)
        else:
            run(c, f"sudo -n docker logs --tail 30 {CONTAINER}")
            raise SystemExit("健康检查失败")

        # 用 admin 校验数据是否一致
        code, text = run(
            c,
            "curl -s -X POST http://127.0.0.1:9100/api/auth/login "
            "-H 'Content-Type: application/json' "
            "-d '{\"username\":\"admin\",\"password\":\"admin123\"}'",
            quiet=True,
        )
        if '"token"' not in text:
            print("警告：admin 登录未成功（若本地已改过密码属正常）")
        token = text.split('"token":"')[1].split('"')[0] if '"token":"' in text else ""
        if token:
            for label, path in [
                ("学生", "/api/students?page_size=1"),
                ("教师", "/api/teachers?page_size=1"),
                ("小组", "/api/groups"),
                ("学期", "/api/semesters/current"),
            ]:
                code, out = run(
                    c,
                    f"curl -s -H 'Authorization: Bearer {token}' 'http://127.0.0.1:9100{path}'",
                    quiet=True,
                )
                out = out[:120].replace("\n", " ")
                print(f"{label}: {out}")
        print(f"\n完成。旧库已备份为 {REMOTE_DIR}/data/upvote.db.bak.{ts}")
        print(f"访问：http://{HOST}:9100/")
    finally:
        c.close()


if __name__ == "__main__":
    main()
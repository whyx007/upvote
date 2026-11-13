"""把 upvote 项目部署到 VPS（SSH + git bundle + Docker）。

用法：
    python scripts/deploy_vps.py --dry     # 只探测远端环境
    python scripts/deploy_vps.py           # 完整部署（首次可自动初始化）

SSH 信息：环境变量 DSH_SSH_HOST/PORT/USER/PASSWORD 或下方默认值。
"""
import os
import posixpath
import secrets
import sys
import time

import paramiko

HOST = os.environ.get("DSH_SSH_HOST", "43.133.86.206")
PORT = int(os.environ.get("DSH_SSH_PORT", "22"))
USER = os.environ.get("DSH_SSH_USER", "ubuntu")
PASSWORD = os.environ.get("DSH_SSH_PASSWORD", "")

REMOTE_DIR = "/opt/upvote"
BUNDLE_REMOTE = "/tmp/upvote.bundle"
BUNDLE_LOCAL = os.path.join("build", "upvote.bundle")
PORT_HOST = 9100
BRANCH = "master"

LOCAL_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=PASSWORD,
        timeout=20,
        banner_timeout=30,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run(client, cmd, timeout=1800, sudo=False, quiet=False, check=False):
    real = f"sudo -n bash -lc {shell_quote(cmd)}" if sudo else f"bash -lc {shell_quote(cmd)}"
    _, stdout, stderr = client.exec_command(real, timeout=timeout, get_pty=False)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if not quiet:
        text = (out + err).strip()
        if text:
            print(text)
    if check and code != 0:
        raise RuntimeError(f"远端命令失败({code}): {cmd[:100]}\n{err.strip()[:500]}")
    return code, out, err


def shell_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


def probe(client):
    print("==> 远端环境探测")
    checks = {
        "系统": "cat /etc/os-release | head -2",
        "Docker": "docker --version 2>&1 | head -1",
        "Compose": "docker compose version 2>&1 | head -1",
        "磁盘": "df -h / | tail -1",
        "内存": "free -h | head -2",
        f"端口{PORT_HOST}": f"(ss -ltn 2>/dev/null || netstat -ltn) | grep -E ':{PORT_HOST}\\b' || echo 'free'",
        "端口9000": "(ss -ltn 2>/dev/null || netstat -ltn) | grep -E ':9000\\b' | head -2 || echo 'free'",
        "ufw": "sudo -n ufw status 2>/dev/null | head -6 || echo 'no ufw/noperm'",
        "iptables": "sudo -n iptables -S 2>/dev/null | grep -cE 'ACCEPT|DROP' || echo 0",
        "docker组": "id -nG | tr ' ' '\\n' | grep -c docker || echo 0",
        "远程目录": f"ls -la {REMOTE_DIR} 2>/dev/null | head -5 || echo 'missing'",
        "公网IP": "curl -s --max-time 8 https://api.ipify.org || echo unknown",
    }
    for label, cmd in checks.items():
        code, out, err = run(client, cmd, timeout=60, quiet=True)
        print(f"--- {label} ---")
        print((out + err).strip() or "(空)")


def ensure_swap(client):
    """小内存机器构建镜像前确保有 swap，避免 node/pip 构建 OOM。"""
    code, out, _ = run(client, "swapon --show | wc -l", quiet=True)
    if out.strip().isdigit() and int(out.strip()) > 0:
        print("已有 swap，跳过")
        return
    print("未启用 swap，创建 2G swap 文件（构建后可保留）")
    run(
        client,
        "sudo -n fallocate -l 2G /swapfile 2>/dev/null || sudo -n dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none && "
        "sudo -n chmod 600 /swapfile && sudo -n mkswap /swapfile >/dev/null && sudo -n swapon /swapfile && "
        "grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo -n tee -a /etc/fstab >/dev/null",
        check=True,
    )
    run(client, "free -h | tail -1", quiet=False)


def deploy(client, skip_probe=False):
    if not skip_probe:
        probe(client)

    print("\n==> 1/6 本地生成 git bundle")
    os.makedirs(os.path.dirname(BUNDLE_LOCAL), exist_ok=True)
    rc = os.system(f'git -C "{LOCAL_REPO}" bundle create "{os.path.join(LOCAL_REPO, BUNDLE_LOCAL)}" {BRANCH} 2>&1')
    if rc != 0:
        raise SystemExit("git bundle 生成失败")
    size = os.path.getsize(os.path.join(LOCAL_REPO, BUNDLE_LOCAL))
    print(f"bundle 大小 {size / 1024:.0f} KB")

    print("==> 2/6 上传 bundle")
    transport = client.open_sftp()
    transport.put(os.path.join(LOCAL_REPO, BUNDLE_LOCAL), BUNDLE_REMOTE)
    transport.close()
    print(f"已上传到 {BUNDLE_REMOTE}")

    print("==> 3/6 远端代码目录")
    run(client, f"sudo -n mkdir -p {REMOTE_DIR} && sudo -n chown {USER}:{USER} {REMOTE_DIR}", check=True)
    has_repo = run(client, f"test -d {REMOTE_DIR}/.git && echo yes || echo no", quiet=True)[1].strip()
    if has_repo == "yes":
        run(client, f"cd {REMOTE_DIR} && git fetch --force {BUNDLE_REMOTE} {BRANCH}:refs/remotes/bundle/{BRANCH} "
                   f"&& git reset --hard bundle/{BRANCH}", check=True)
        print("已更新现有仓库（git bundle fetch + reset）")
    else:
        run(
            client,
            f"cd {REMOTE_DIR} && git init -q && git fetch --force {BUNDLE_REMOTE} {BRANCH}:refs/remotes/bundle/{BRANCH} "
            f"&& git checkout -q -B {BRANCH} bundle/{BRANCH}",
            check=True,
        )
        print("已初始化远端仓库")

    print("==> 4/6 生成 .env（保留已有密钥）")
    env_path = posixpath.join(REMOTE_DIR, ".env")
    existing = run(client, f"cat {env_path} 2>/dev/null | grep '^UPVOTE_SECRET_KEY=' || true", quiet=True)[1].strip()
    if existing:
        print("复用已有 UPVOTE_SECRET_KEY")
    else:
        key = secrets.token_hex(32)
        run(
            client,
            f"cat > {env_path} <<'EOF'\nUPVOTE_SECRET_KEY={key}\nUPVOTE_COINS_PER_LIKE=1\nEOF\n"
            f"chmod 600 {env_path}",
            check=True,
        )
        print("已生成随机 UPVOTE_SECRET_KEY 写入 .env")
    run(client, f"mkdir -p {REMOTE_DIR}/data", check=True)

    print("==> 5/6 Docker 构建并启动（构建前保障 swap）")
    ensure_swap(client)
    rc, out, err = run(
        client,
        f"cd {REMOTE_DIR} && sudo -n docker compose -f docker-compose.vps.yml up -d --build 2>&1 | tail -30",
        timeout=3000,
        sudo=False,
    )
    if rc != 0:
        raise SystemExit(f"docker compose 构建失败:\n{err.strip()[:1500]}")

    print("==> 6/6 健康检查")
    for attempt in range(20):
        code, out, _ = run(
            client,
            f"curl -s --max-time 5 http://127.0.0.1:{PORT_HOST}/api/health || echo FAIL",
            quiet=True,
        )
        if out.strip() and "FAIL" not in out.strip():
            print(f"本地健康检查: {out.strip()}")
            break
        time.sleep(3)
    else:
        run(client, f"cd {REMOTE_DIR} && sudo -n docker compose -f docker-compose.vps.yml logs --tail 40")
        raise SystemExit("健康检查未通过，已输出容器日志")

    run(client, f"curl -s -o /dev/null -w 'HTTP %{{http_code}}\\n' --max-time 8 http://127.0.0.1:{PORT_HOST}/ || true", quiet=False)
    run(client, f"sudo -n docker ps --filter name=upvote --format '{{{{.Names}}}} {{{{.Status}}}} {{{{.Ports}}}}'", quiet=False)

    print(f"\n完成。访问地址：http://{HOST}:{PORT_HOST}/")
    print("首次启动会自动创建管理员 admin/admin123（请尽快改密）。")
    print("若外部无法访问，需在腾讯云控制台安全组放行 TCP", PORT_HOST, "；本脚本已尝试检查 ufw。")


def main():
    if not PASSWORD:
        raise SystemExit("请设置环境变量 DSH_SSH_PASSWORD")
    client = connect()
    try:
        if "--dry" in sys.argv:
            probe(client)
        else:
            deploy(client, skip_probe="--skip-probe" in sys.argv)
    finally:
        client.close()


if __name__ == "__main__":
    main()
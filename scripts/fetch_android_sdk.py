"""下载 Android cmdline-tools（Windows 自带 TLS 栈不可用，改用 Python 的 OpenSSL 实现）。"""

import os
import sys
import time
import urllib.request

URL = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(REPO_ROOT, "tools", "cmdline-tools.zip")


def main() -> int:
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    start = time.time()
    req = urllib.request.Request(URL, headers={"User-Agent": "upvote-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(DST, "wb") as fh:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        next_report = 20 << 20
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if done >= next_report:
                pct = (done / total * 100) if total else 0
                print("%.0f/%.0f MB (%.0f%%)" % (done / 1048576, total / 1048576, pct), flush=True)
                next_report += 20 << 20

    size = os.path.getsize(DST)
    print("DONE %d bytes (%.1f MB) in %.1fs" % (size, size / 1048576, time.time() - start))
    if total and size != total:
        print("WARN: size mismatch, expected %d" % total)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
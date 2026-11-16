"""桌面预览：复刻 APK 内 LocalServer 的行为（静态资源 + /api 反向代理）。

用途：不装模拟器时，先在桌面浏览器里验证「同一套前端产物 + 同一个代理」是否正常，
从而把问题范围收敛到「安卓壳」这一层。

用法：python scripts/android_web_preview.py [--port 8791]
"""

from __future__ import annotations

import argparse
import http.server
import mimetypes
import os
import socketserver
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST = REPO_ROOT / "frontend" / "dist"
API_ORIGIN = "http://43.133.86.206:9100"

MIME_OVERRIDES = {
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
}

SKIP_REQUEST_HEADERS = {
    "host", "connection", "keep-alive", "transfer-encoding", "content-length",
    "accept-encoding", "origin", "referer",
}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D102
        sys.stderr.write("[preview] %s %s\n" % (self.command, self.path))

    # ---------------------------------------------------------------- 路由

    def do_GET(self):
        self._route("GET")

    def do_HEAD(self):
        self._route("HEAD")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method: str):
        if self.path.startswith("/api"):
            self._proxy(method)
        else:
            self._static(method)

    # ---------------------------------------------------------------- 静态

    def _static(self, method: str):
        path = self.path.split("?", 1)[0]
        if path in ("", "/"):
            path = "/index.html"
        target = (DIST / path.lstrip("/")).resolve()
        if not str(target).startswith(str(DIST)) or not target.is_file():
            # SPA 回退：无扩展名时给 index.html
            if "." not in Path(path).name:
                target = DIST / "index.html"
            else:
                self._send(404, b"Not Found: " + path.encode(), "text/plain; charset=utf-8")
                return
        body = target.read_bytes()
        ctype = MIME_OVERRIDES.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        cache = "public, max-age=31536000, immutable" if path.startswith("/assets/") else "no-cache"
        self._send(200, body, ctype, cache, head_only=(method == "HEAD"))

    # ---------------------------------------------------------------- 代理

    def _proxy(self, method: str):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        upstream = urllib.request.Request(API_ORIGIN + self.path, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in SKIP_REQUEST_HEADERS:
                upstream.add_header(key, value)
        upstream.add_header("Accept-Encoding", "identity")

        try:
            with urllib.request.urlopen(upstream, timeout=30) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json; charset=utf-8")
                self._send(status, data, ctype)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            ctype = exc.headers.get("Content-Type", "application/json; charset=utf-8")
            self._send(exc.code, data, ctype)
        except Exception as exc:  # noqa: BLE001
            self._send(502, ("proxy error: %s" % exc).encode(), "text/plain; charset=utf-8")

    # ---------------------------------------------------------------- 输出

    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store", head_only: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("Connection", "close")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()

    if not (DIST / "index.html").is_file():
        print("缺少前端产物：%s（先 cd frontend && pnpm build）" % DIST, file=sys.stderr)
        return 1

    with Server(("127.0.0.1", args.port), Handler) as httpd:
        print("预览地址： http://127.0.0.1:%d/" % args.port)
        print("静态根：  %s" % DIST)
        print("API 上游：%s" % API_ORIGIN)
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
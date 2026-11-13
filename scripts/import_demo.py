"""把演示数据导入运行中的服务，并确保有激活学期。

用法：python scripts/import_demo.py [base_url] [xlsx路径]
"""
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
XLSX = sys.argv[2] if len(sys.argv) > 2 else "data/demo_import.xlsx"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def main():
    c = httpx.Client(base_url=BASE, timeout=120)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    admin = {"Authorization": f"Bearer {r.json()['token']}"}

    if c.get("/api/semesters/current", headers=admin).json() is None:
        r = c.post(
            "/api/semesters",
            headers=admin,
            json={"name": "2026-2027学年第一学期", "start_date": "2026-09-01", "end_date": "2027-01-15"},
        )
        r.raise_for_status()
        c.post(f"/api/semesters/{r.json()['id']}/activate", headers=admin).raise_for_status()
        print("已创建并激活学期：2026-2027学年第一学期")

    with open(XLSX, "rb") as f:
        r = c.post("/api/imports", headers=admin, files={"file": ("demo_import.xlsx", f, MIME)})
    r.raise_for_status()
    summary = r.json()
    for key, stat in summary.items():
        print(f"{key}: 新增 {stat['created']} 更新 {stat['updated']} 错误 {len(stat['errors'])}")
        for e in stat["errors"][:5]:
            print(f"  第{e['row']}行: {e['message']}")

    students = c.get("/api/students", headers=admin, params={"page_size": 1}).json()["total"]
    teachers = c.get("/api/teachers", headers=admin, params={"page_size": 1}).json()["total"]
    classes = c.get("/api/classes", headers=admin).json()
    groups = c.get("/api/groups", headers=admin).json()["items"]
    print(f"库内合计：学生 {students} | 教师 {teachers}（含 admin）| 班级 {len(classes)} | 小组 {len(groups)}")


if __name__ == "__main__":
    main()
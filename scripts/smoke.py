"""端到端冒烟测试：对运行中的服务走通全部核心流程。

用法：python scripts/smoke.py [base_url]
默认 http://127.0.0.1:8000，要求使用全新数据库（admin/admin123）。
"""
import io
import sys
import time

import httpx
from openpyxl import Workbook, load_workbook

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
passed = 0


def ok(name, cond, extra=""):
    global passed
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    passed += 1
    print(f"PASS: {name}")


def make_xlsx(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main():
    c = httpx.Client(base_url=BASE, timeout=30)
    for _ in range(30):
        try:
            if c.get("/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        print("FAIL: 服务未就绪")
        sys.exit(1)

    r = c.get("/")
    ok("首页托管", r.status_code == 200 and "星灿" in r.text)
    ok("PWA manifest", c.get("/manifest.webmanifest").status_code == 200)
    ok("Service Worker", c.get("/sw.js").status_code == 200)

    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    ok("管理员登录", r.status_code == 200, r.text)
    admin = {"Authorization": f"Bearer {r.json()['token']}"}

    r = c.get("/api/imports/template", headers=admin)
    wb = load_workbook(io.BytesIO(r.content))
    ok("导入模板", set(wb.sheetnames) == {"学生", "教师", "说明"})

    r = c.post("/api/semesters", headers=admin, json={"name": "2026-2027学年第一学期", "start_date": "2026-09-01", "end_date": "2027-01-15"})
    ok("创建学期", r.status_code == 200, r.text)
    sid = r.json()["id"]
    ok("激活学期", c.post(f"/api/semesters/{sid}/activate", headers=admin).status_code == 200)

    content = make_xlsx({
        "学生": [["学号", "姓名", "年级", "班级", "入学年份"],
               ["2026001", "张小明", "初一", "初一1班", 2026],
               ["2026002", "李小红", "初一", "初一1班", 2026]],
        "教师": [["工号", "姓名", "手机号", "初始密码", "角色"], ["T001", "王老师", None, None, None]],
        "小组": [["小组名称", "班级", "成员学号"], ["星辰组", "初一1班", "2026001,2026002"]],
        "任教": [["工号", "班级"], ["T001", "初一1班"]],
    })
    r = c.post("/api/imports", headers=admin, files={"file": ("smoke.xlsx", content, XLSX)})
    ok("Excel 导入", r.status_code == 200 and r.json()["students"]["created"] == 2, r.text)

    r = c.post("/api/auth/login", json={"username": "T001", "password": "123456"})
    ok("教师登录", r.status_code == 200, r.text)
    teacher = {"Authorization": f"Bearer {r.json()['token']}"}
    ok("任教班级", c.get("/api/my/classes", headers=teacher).json() == ["初一1班"])

    roster = c.get("/api/classes/初一1班/roster", headers=teacher).json()["items"]
    ids = {s["student_no"]: s["id"] for s in roster}
    ok("花名册初始余额", all(s["semester_balance"] == 0 for s in roster))

    r = c.post("/api/likes", headers=teacher, json={"target_type": "student", "target_id": ids["2026001"]})
    ok("个人点赞", r.status_code == 200 and r.json()["likes"][0]["semester_balance"] == 1, r.text)
    r = c.post("/api/likes", headers=teacher, json={"target_type": "group", "target_id": c.get("/api/groups", headers=teacher).json()["items"][0]["id"]})
    ok("小组点赞全员+1", r.status_code == 200 and r.json()["count"] == 2, r.text)
    group_batch = r.json()["batch_id"]

    roster = {s["student_no"]: s for s in c.get("/api/classes/初一1班/roster", headers=teacher).json()["items"]}
    ok("余额累计", roster["2026001"]["semester_balance"] == 2 and roster["2026002"]["semester_balance"] == 1)

    r = c.post("/api/likes/revoke", headers=teacher, json={"batch_id": group_batch})
    ok("撤销小组点赞", r.status_code == 200 and r.json()["revoked_count"] == 2, r.text)
    roster = {s["student_no"]: s for s in c.get("/api/classes/初一1班/roster", headers=teacher).json()["items"]}
    ok("撤销后余额", roster["2026001"]["semester_balance"] == 1 and roster["2026002"]["semester_balance"] == 0)

    r = c.post("/api/rewards", headers=admin, json={"name": "笔记本", "cost_coins": 1, "stock": 5})
    ok("创建奖励", r.status_code == 200, r.text)
    reward_id = r.json()["id"]
    r = c.post("/api/redemptions", headers=admin, json={"student_id": ids["2026001"], "reward_id": reward_id})
    ok("兑换扣分", r.status_code == 200 and r.json()["new_balance"] == 0, r.text)
    redemption_id = r.json()["id"]
    r = c.post(f"/api/redemptions/{redemption_id}/cancel", headers=admin)
    ok("取消兑换退还", r.status_code == 200 and r.json()["new_balance"] == 1, r.text)

    r = c.get("/api/stats/overview", headers=admin)
    ok("统计概览", r.status_code == 200 and r.json()["total_students"] == 2, r.text)
    r = c.get("/api/stats/export", headers=admin)
    ws = load_workbook(io.BytesIO(r.content)).active
    ok("统计导出", ws.max_row == 3 and "学期星灿币" in [c2.value for c2 in ws[1]])

    r = c.post("/api/students", headers=admin, json={"student_no": "2026099", "name": "新同学", "class_name": "初一1班"})
    ok("新增学生", r.status_code == 200, r.text)
    new_id = r.json()["id"]
    ok("编辑学生", c.patch(f"/api/students/{new_id}", headers=admin, json={"name": "新同学改"}).status_code == 200)
    ok("删除学生", c.delete(f"/api/students/{new_id}", headers=admin).status_code == 200)

    print(f"\nALL {passed} SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
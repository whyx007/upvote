"""Stats overview and Excel export."""
import io

from openpyxl import load_workbook


def test_overview_counts(client, admin_headers, school):
    sid = school["student_ids"]["2026001"]
    for _ in range(2):
        client.post("/api/likes", headers=school["teacher_headers"], json={"target_type": "student", "target_id": sid})
    client.post("/api/likes", headers=school["teacher_headers"], json={"target_type": "group", "target_id": school["group_id"]})
    r = client.get("/api/stats/overview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_students"] == 2
    assert body["total_likes"] == 4
    assert body["total_coins_issued"] == 4
    assert body["top_students"][0]["semester_balance"] == 3
    assert body["per_class"][0]["class_name"] == "初一1班"
    assert body["per_class"][0]["likes"] == 4


def test_export_xlsx_has_balances(client, admin_headers, school):
    client.post(
        "/api/likes",
        headers=school["teacher_headers"],
        json={"target_type": "student", "target_id": school["student_ids"]["2026001"]},
    )
    r = client.get("/api/stats/export", headers=admin_headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    header = [c.value for c in ws[1]]
    assert "学号" in header and "学期星灿币" in header and "累计星灿币" in header
    rows = {row[0]: row for row in ws.iter_rows(min_row=2, values_only=True)}
    assert rows["2026001"][header.index("学期星灿币")] == 1
    assert rows["2026002"][header.index("学期星灿币")] == 0
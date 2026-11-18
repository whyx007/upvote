import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ImportBatch
from ..security import get_db, require_admin
from ..services.importer import build_template, import_workbook

router = APIRouter(prefix="/api/imports", tags=["imports"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _merge_summary(target: dict, summary: dict) -> None:
    for key, stat in summary.items():
        if key not in target:
            target[key] = {"created": 0, "updated": 0, "errors": []}
        target[key]["created"] += stat["created"]
        target[key]["updated"] += stat["updated"]
        target[key]["errors"].extend(stat["errors"])


@router.post("")
async def do_import(
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    uploads = list(files or [])
    if file is not None:
        uploads.insert(0, file)
    if not uploads:
        raise HTTPException(status_code=400, detail="请选择要导入的 Excel 文件")

    results = []
    merged = {}
    for upload in uploads:
        filename = upload.filename or "import.xlsx"
        content = await upload.read()
        try:
            summary = import_workbook(db, content, filename, admin.id)
        except ValueError as exc:
            results.append({"filename": filename, "ok": False, "error": str(exc)})
            continue
        except Exception:
            results.append({"filename": filename, "ok": False, "error": "无法读取 Excel 文件，请使用 .xlsx 格式"})
            continue
        results.append({"filename": filename, "ok": True, "summary": summary})
        _merge_summary(merged, summary)

    if len(uploads) == 1:
        result = results[0]
        if not result["ok"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result["summary"]

    return {"ok": all(item["ok"] for item in results), "items": results, "summary": merged}


@router.get("/template")
def download_template(admin=Depends(require_admin)):
    return Response(
        content=build_template(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=upvote_template.xlsx"},
    )


@router.get("")
def import_history(admin=Depends(require_admin), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(ImportBatch.id)))
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(50)).all()
    return {
        "total": total,
        "items": [
            {
                "id": b.id,
                "filename": b.filename,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "summary": json.loads(b.summary_json),
            }
            for b in batches
        ],
    }
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ImportBatch
from ..security import get_db, require_admin
from ..services.importer import build_template, import_workbook

router = APIRouter(prefix="/api/imports", tags=["imports"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("")
async def do_import(file: UploadFile, admin=Depends(require_admin), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        summary = import_workbook(db, content, file.filename or "import.xlsx", admin.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=400, detail="无法读取 Excel 文件，请使用 .xlsx 格式")
    return summary


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
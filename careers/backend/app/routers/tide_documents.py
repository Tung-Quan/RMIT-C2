from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies import get_current_user
from app.routers.documents import get_document_for_user, get_document_for_text_access
from app.services.storage_service import StorageService

router = APIRouter(tags=["documents"])


@router.get("/documents/{document_id}/content")
def document_content(document_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        document = get_document_for_user(db, document_id, current_user)
    except HTTPException:
        document = get_document_for_text_access(db, document_id, current_user)
    storage = StorageService()
    if not document.s3_key:
        raise HTTPException(status_code=404, detail="Stored document is missing")
    data = storage.read_file_bytes(document.s3_key)
    filename = str(document.file_name or "document").replace('"', "_").replace("\r", "_").replace("\n", "_")
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

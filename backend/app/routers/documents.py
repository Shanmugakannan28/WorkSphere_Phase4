import datetime as dt
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Document, Employee, User
from ..security import current_user
from ..services import my_employee, notify, notify_hr

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
           ".jpeg": "image/jpeg", ".doc": "application/msword",
           ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAGIC = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff",
         ".docx": b"PK", ".doc": b"\xd0\xcf\x11\xe0"}
DOC_TYPES = {"ID proof", "Address proof", "Certificate", "Contract", "Resume", "Other"}


def _can_access(db, user, owner_id):
    if user.role in ("admin", "hr"):
        return True
    me = my_employee(db, user)
    return bool(me and me.id == owner_id)


def _ser(d: Document):
    return {"id": d.id, "employee_id": d.employee_id, "employee_name": d.employee.name,
            "file_name": d.file_name, "file_url": d.file_url, "doc_type": d.doc_type,
            "size": d.size, "content_type": d.content_type, "expiry_date": d.expiry_date,
            "uploaded_at": d.uploaded_at}


@router.post("", status_code=201)
def upload(file: UploadFile = File(...), employee_id: Optional[int] = Form(None),
           doc_type: str = Form("Other"), expiry_date: Optional[dt.date] = Form(None),
           db: Session = Depends(get_db), user: User = Depends(current_user)):
    me = my_employee(db, user)
    owner_id = employee_id if (employee_id and user.role in ("admin", "hr")) else (me.id if me else None)
    if not owner_id or not db.get(Employee, owner_id):
        raise HTTPException(400, "Employee not found")
    if employee_id and user.role not in ("admin", "hr") and me and employee_id != me.id:
        raise HTTPException(403, "You can only upload your own documents")
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, "Invalid document type")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", (file.filename or "file").replace("\\", "/").split("/")[-1])[:150]
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ALLOWED:
        raise HTTPException(400, "Allowed file types: PDF, PNG, JPG, DOC, DOCX")
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    if not data or not data.startswith(MAGIC[ext]):
        raise HTTPException(400, "File content does not match its extension")
    stored = uuid.uuid4().hex + ext
    (settings.storage_dir / stored).write_bytes(data)
    doc = Document(employee_id=owner_id, file_name=name, file_url="", stored_name=stored, doc_type=doc_type,
                   content_type=ALLOWED[ext], size=len(data), expiry_date=expiry_date)
    db.add(doc)
    db.flush()
    doc.file_url = f"/api/documents/{doc.id}/download"
    db.commit()
    return {"id": doc.id}


@router.get("")
def list_documents(employee_id: Optional[int] = None, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    me = my_employee(db, user)
    stmt = select(Document).order_by(Document.uploaded_at.desc())
    if user.role in ("admin", "hr"):
        if employee_id:
            stmt = stmt.where(Document.employee_id == employee_id)
    else:
        stmt = stmt.where(Document.employee_id == (me.id if me else 0))
    return [_ser(d) for d in db.scalars(stmt)]


@router.get("/{doc_id}/download")
def download(doc_id: int, inline: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(Document, doc_id)
    if not d or not _can_access(db, user, d.employee_id):
        raise HTTPException(404, "Document not found")
    path = settings.storage_dir / d.stored_name
    if not path.is_file():
        raise HTTPException(404, "File is missing on the server")
    return FileResponse(path, media_type=d.content_type, filename=d.file_name,
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{doc_id}")
def delete(doc_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(Document, doc_id)
    if not d or not _can_access(db, user, d.employee_id):
        raise HTTPException(404, "Document not found")
    (settings.storage_dir / d.stored_name).unlink(missing_ok=True)
    db.delete(d)
    db.commit()
    return {"ok": True}

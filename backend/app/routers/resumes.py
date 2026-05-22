import logging
import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..models import Resume, User
from ..schemas import ResumeOut
from ..services.parser import parse
from ..services.extractor import extract_resume
from ..services.chunker import chunk_resume_from_structured, chunk_resume_from_blocks
from ..services.vector_store import index_resume_chunks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["resumes"])

ALLOWED_EXTS = {".pdf", ".docx", ".txt"}
MAX_FILES_PER_UPLOAD = 10


@router.post("/upload", response_model=list[ResumeOut])
async def upload_resumes(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not files:
        raise HTTPException(400, "No files uploaded")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            400, f"Too many files. Max {MAX_FILES_PER_UPLOAD} per upload."
        )

    saved: list[Resume] = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_EXTS:
            logger.warning("Skipping unsupported file: %s", f.filename)
            continue

        content = await f.read()
        if not content:
            logger.warning("Empty file: %s", f.filename)
            continue

        try:
            parsed = parse(content, f.filename or "upload")
        except Exception as e:
            logger.exception("Failed to parse %s: %s", f.filename, e)
            raise HTTPException(400, f"Failed to parse {f.filename}: {e}")

        if not parsed.raw_text.strip():
            logger.warning("No text extracted from %s", f.filename)
            raise HTTPException(400, f"No text could be extracted from {f.filename}")

        structured = extract_resume(parsed.raw_text)
        chunks = chunk_resume_from_structured(structured) if structured else []
        if not chunks:
            chunks = chunk_resume_from_blocks(parsed)

        resume = Resume(
            user_id=user.id,
            filename=f.filename or "upload",
            raw_text=parsed.raw_text,
            structured=structured,
            name=structured.get("name") if structured else None,
            email=structured.get("email") if structured else None,
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)

        # Keep a copy of the raw file in data/uploads, named after the resume id.
        safe_name = f"{resume.id}_{os.path.basename(f.filename or 'upload')}"
        try:
            with open(os.path.join(settings.UPLOAD_DIR, safe_name), "wb") as out:
                out.write(content)
        except Exception as e:
            logger.warning("Could not save upload to disk: %s", e)

        # Push chunks into ChromaDB. We don't want this to fail the whole
        # upload - the resume is already in SQLite.
        try:
            index_resume_chunks(resume.id, chunks)
        except Exception as e:
            logger.warning("Vector indexing failed for resume %s: %s", resume.id, e)

        saved.append(resume)

    if not saved:
        raise HTTPException(400, "No resumes were processed. Supported: PDF, DOCX, TXT.")
    return saved


@router.get("", response_model=list[ResumeOut])
def list_resumes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Resume)
        .filter(Resume.user_id == user.id)
        .order_by(Resume.created_at.desc())
        .all()
    )


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == user.id)
        .first()
    )
    if not resume:
        raise HTTPException(404, "Resume not found")
    return resume


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == user.id)
        .first()
    )
    if not resume:
        raise HTTPException(404, "Resume not found")
    db.delete(resume)
    db.commit()
    return {"deleted": resume_id}

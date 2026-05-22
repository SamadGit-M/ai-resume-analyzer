import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Job, User
from ..schemas import JobCreate, JobOut
from ..services.extractor import extract_jd

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobOut)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    structured = extract_jd(payload.description)
    job = Job(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        structured=structured,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("user=%s created job id=%s title=%r", user.id, job.id, job.title)
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Job)
        .filter(Job.user_id == user.id)
        .order_by(Job.created_at.desc())
        .all()
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_id}

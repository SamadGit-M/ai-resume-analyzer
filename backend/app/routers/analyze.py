import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Job, Resume, AnalysisResult, User
from ..schemas import AnalyzeRequest, AnalyzeResponse, AnalyzeResultItem
from ..services.chunker import (
    chunk_resume_from_structured,
    chunk_resume_from_blocks,
    chunk_job_description,
)
from ..services.parser import ParsedDocument, TextBlock
from ..services.scorer import score_resume
from ..services.feedback import generate_feedback

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=AnalyzeResponse)
def analyze(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = (
        db.query(Job)
        .filter(Job.id == payload.job_id, Job.user_id == user.id)
        .first()
    )
    if not job:
        raise HTTPException(404, "Job not found")

    base = db.query(Resume).filter(Resume.user_id == user.id)
    if payload.resume_ids:
        resumes = base.filter(Resume.id.in_(payload.resume_ids)).all()
    else:
        resumes = base.order_by(Resume.created_at.desc()).all()
    if not resumes:
        raise HTTPException(400, "No resumes to analyze")

    jd_structured = job.structured or {}
    jd_chunks = chunk_job_description(job.description, jd_structured)

    # Reuse any AnalysisResult rows already stored for this (job, resume) pair
    # so we don't re-spend Gemini calls when the user re-runs the same combo.
    cached_rows = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.job_id == job.id,
            AnalysisResult.resume_id.in_([r.id for r in resumes]),
        )
        .all()
    )
    cached_by_resume = {a.resume_id: a for a in cached_rows}

    items: list[AnalyzeResultItem] = []
    for resume in resumes:
        cached = cached_by_resume.get(resume.id)
        if cached is not None:
            items.append(
                AnalyzeResultItem(
                    resume_id=resume.id,
                    filename=resume.filename,
                    name=resume.name,
                    email=resume.email,
                    total_score=cached.total_score,
                    skills_score=cached.skills_score,
                    experience_score=cached.experience_score,
                    education_score=cached.education_score,
                    matched_skills=cached.matched_skills or [],
                    missing_skills=cached.missing_skills or [],
                    feedback=cached.feedback or {"strengths": [], "improvements": []},
                )
            )
            continue

        structured = resume.structured or {}
        chunks = chunk_resume_from_structured(structured) if structured else []
        if not chunks:
            # Structured extraction must have failed at upload time. Rebuild
            # blocks from the raw text and use the heuristic chunker.
            blocks = [TextBlock(text=ln) for ln in (resume.raw_text or "").splitlines() if ln.strip()]
            chunks = chunk_resume_from_blocks(ParsedDocument(raw_text=resume.raw_text or "", blocks=blocks))

        breakdown = score_resume(
            resume_structured=structured,
            resume_chunks=chunks,
            jd_structured=jd_structured,
            jd_chunks=jd_chunks,
        )

        try:
            feedback = generate_feedback(
                resume_id=resume.id,
                job_structured=jd_structured,
                matched_skills=breakdown.matched_skills,
                missing_skills=breakdown.missing_skills,
            )
        except Exception as e:
            logger.warning("Feedback generation failed for resume %s: %s", resume.id, e)
            feedback = {"strengths": [], "improvements": []}

        ar = AnalysisResult(
            job_id=job.id,
            resume_id=resume.id,
            total_score=breakdown.total_score,
            skills_score=breakdown.skills_score,
            experience_score=breakdown.experience_score,
            education_score=breakdown.education_score,
            feedback=feedback,
            matched_skills=breakdown.matched_skills,
            missing_skills=breakdown.missing_skills,
        )
        db.add(ar)

        items.append(
            AnalyzeResultItem(
                resume_id=resume.id,
                filename=resume.filename,
                name=resume.name,
                email=resume.email,
                total_score=breakdown.total_score,
                skills_score=breakdown.skills_score,
                experience_score=breakdown.experience_score,
                education_score=breakdown.education_score,
                matched_skills=breakdown.matched_skills,
                missing_skills=breakdown.missing_skills,
                feedback=feedback,
            )
        )

    db.commit()
    items.sort(key=lambda x: x.total_score, reverse=True)
    return AnalyzeResponse(job_id=job.id, job_title=job.title, ranked=items)

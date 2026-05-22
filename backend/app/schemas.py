from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr


# ---------- Auth ----------
class AuthCredentials(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Jobs ----------
class JobCreate(BaseModel):
    title: str
    description: str


class JobOut(BaseModel):
    id: int
    title: str
    description: str
    structured: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Resumes ----------
class ResumeOut(BaseModel):
    id: int
    filename: str
    name: Optional[str] = None
    email: Optional[str] = None
    structured: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Analyze ----------
class AnalyzeRequest(BaseModel):
    job_id: int
    resume_ids: Optional[list[int]] = None  # None => all resumes


class AnalyzeResultItem(BaseModel):
    resume_id: int
    filename: str
    name: Optional[str]
    email: Optional[str]
    total_score: float
    skills_score: float
    experience_score: float
    education_score: float
    matched_skills: list[str]
    missing_skills: list[str]
    feedback: dict[str, list[str]]


class AnalyzeResponse(BaseModel):
    job_id: int
    job_title: str
    ranked: list[AnalyzeResultItem]

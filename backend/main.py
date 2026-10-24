"""CareerTrack AI - FastAPI backend.

Run locally (inside the backend folder):  uvicorn main:app --reload --port 8000
Interactive API docs:                    http://localhost:8000/docs
"""
import logging
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, Request, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

import ai_service
import auth
from resume_parser import extract_resume_text
from config import settings, validate_settings
from database import Database, DatabaseError, get_database
from demo import load_sample_data
from models import(
    ACTIVE_STATUSES, AnalyticsOut, ApplicationCreate, ApplicationOut, ApplicationStatus,
    ApplicationUpdate, DashboardStats, DemoSeedResponse, ExtractJobRequest, ExtractJobResponse,
    FollowUpEmailRequest, FollowUpEmailResponse, FollowUpItem, FollowUpsOut, HistoryOut,
    InterviewQuestionsRequest, InterviewQuestionsResponse, MonthlyCount, ResumeStat,
)
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("careertrack.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()   # stop early with a clear message if .env is incomplete
    get_database()        # create the DB client/tables once at startup
    logger.info("CareerTrack AI backend ready (demo=%s, ai=%s)", settings.demo_mode, ai_service.current_source())
    yield


app = FastAPI(
    title="CareerTrack AI API",
    version="1.0.0",
    description="Job application tracker with Gemini-powered helpers.",
    lifespan=lifespan,
)

# CORS: in production ONLY the configured frontend origin is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


# --------------------------------------------------------------------------
# Error handling: always answer with {"detail": "<readable message>"}
# --------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        msg = str(err["msg"]).replace("Value error, ", "")
        parts.append(f"{where}: {msg}" if where else msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "Invalid input."})


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ai_service.AIServiceError)
async def ai_error_handler(request: Request, exc: ai_service.AIServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Unexpected server error. Check the backend logs."})


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------
def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """If BACKEND_API_KEY is set, require it on every /api request."""
    if not settings.api_key:
        return
    supplied = (x_api_key or "").encode()
    if not secrets.compare_digest(supplied, settings.api_key.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid API key (X-API-Key header).")


def get_db() -> Database:
    return get_database()


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

def require_user(request: Request, authorization: Optional[str] = Header(default=None)) -> Dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    try:
        user = auth.verify_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired. Please sign in again.")
    request.state.user = user
    return user


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _uuid_str(value: str, label: str = "id") -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{label} is not a valid ID.")


def _get_or_404(db: Database, app_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    row = db.get_application(app_id, user_id=user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return row


api = APIRouter(prefix="/api", dependencies=[Depends(verify_api_key), Depends(require_user)])
auth_api = APIRouter(prefix="/api/auth", dependencies=[Depends(verify_api_key)])


# --------------------------------------------------------------------------
# Health (public, used by Render health checks)
# --------------------------------------------------------------------------
@app.get("/health", tags=["system"])
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "production",
        "database": "sqlite (demo)" if settings.demo_mode else "supabase",
        "ai": ai_service.current_source(),
        "demo_seed_allowed": settings.allow_demo_seed,
    }


@app.get("/", include_in_schema=False)
def root() -> Dict[str, str]:
    return {"app": "CareerTrack AI API", "docs": "/docs", "health": "/health"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Applications (CRUD + search/filter)
# --------------------------------------------------------------------------
@api.get("/applications", response_model=List[ApplicationOut], tags=["applications"])
def list_applications(
    company: Optional[str] = Query(default=None, max_length=200),
    role: Optional[str] = Query(default=None, max_length=200),
    status: Optional[ApplicationStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")
    return db.list_applications(
        user_id=user["id"], company=company.strip() if company else None,
        role=role.strip() if role else None,
        status=status.value if status else None,
        date_from=date_from, date_to=date_to,
    )


@api.post("/applications", response_model=ApplicationOut, status_code=201, tags=["applications"])
def create_application(payload: ApplicationCreate, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    return db.create_application(payload.model_dump(mode="json"), user_id=user["id"])


@api.get("/applications/{application_id}", response_model=ApplicationOut, tags=["applications"])
def get_application(application_id: UUID, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    return _get_or_404(db, str(application_id), user["id"])


@api.put("/applications/{application_id}", response_model=ApplicationOut, tags=["applications"])
def update_application(application_id: UUID, payload: ApplicationUpdate, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    changes = payload.model_dump(mode="json", exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Send at least one field to update.")
    existing = _get_or_404(db, str(application_id), user["id"])
    # Re-check the date rule against the merged result (partial updates).
    applied = changes.get("application_date", existing.get("application_date"))
    follow = changes.get("follow_up_date", existing.get("follow_up_date"))
    if applied and follow and str(follow) < str(applied):
        raise HTTPException(status_code=422, detail="Follow-up date cannot be before the application date.")
    updated = db.update_application(str(application_id), changes, user_id=user["id"])
    if updated is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return updated


@api.delete("/applications/{application_id}", status_code=204, tags=["applications"])
def delete_application(application_id: UUID, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    if not db.delete_application(str(application_id), user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Application not found.")
    return Response(status_code=204)


@api.get("/applications/{application_id}/history", response_model=List[HistoryOut], tags=["history"])
def application_history(application_id: UUID, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    _get_or_404(db, str(application_id), user["id"])
    return db.list_history(str(application_id), user_id=user["id"])


@api.get("/history", response_model=List[HistoryOut], tags=["history"])
def recent_history(limit: int = Query(default=30, ge=1, le=200), db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    return db.list_recent_history(limit, user_id=user["id"])


# --------------------------------------------------------------------------
# Dashboard, follow-ups, analytics (computed from the stored applications)
# --------------------------------------------------------------------------
def _as_date(value: Any) -> Optional[date]:
    if not value:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


@api.get("/dashboard/stats", response_model=DashboardStats, tags=["dashboard"])
def dashboard_stats(db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    apps = db.list_applications(user_id=user["id"])
    counts = Counter(a["status"] for a in apps)
    today = today_local()
    due = sum(
        1 for a in apps
        if a["status"] in ACTIVE_STATUSES and _as_date(a.get("follow_up_date")) and _as_date(a["follow_up_date"]) <= today
    )
    return DashboardStats(
        total_applications=len(apps),
        interviews=counts.get("Interview", 0),
        offers=counts.get("Offer", 0),
        rejections=counts.get("Rejected", 0),
        follow_ups_due=due,
        status_counts={s.value: counts.get(s.value, 0) for s in ApplicationStatus},
    )


@api.get("/followups", response_model=FollowUpsOut, tags=["follow-ups"])
def follow_ups(days: int = Query(default=7, ge=1, le=60), db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    today = today_local()
    horizon = today + timedelta(days=days)
    result: Dict[str, List[Dict[str, Any]]] = {"overdue": [], "today": [], "upcoming": []}
    for a in db.list_applications(user_id=user["id"]):
        due = _as_date(a.get("follow_up_date"))
        if a["status"] not in ACTIVE_STATUSES or due is None or due > horizon:
            continue
        item = {**a, "days_until": (due - today).days}
        key = "overdue" if due < today else ("today" if due == today else "upcoming")
        result[key].append(item)
    for items in result.values():
        items.sort(key=lambda x: x["follow_up_date"])
    return FollowUpsOut(**result)


@api.get("/analytics", response_model=AnalyticsOut, tags=["dashboard"])
def analytics(db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    apps = db.list_applications(user_id=user["id"])
    counts = Counter(a["status"] for a in apps)
    submitted = len(apps) - counts.get("Saved", 0)

    def pct(n: int) -> float:
        return round(100 * n / submitted, 1) if submitted else 0.0

    responded = sum(counts.get(s, 0) for s in ("Assessment", "Interview", "Offer", "Rejected"))
    by_month: Counter = Counter()
    resume: Dict[str, List[int]] = {}
    for a in apps:
        applied = _as_date(a.get("application_date"))
        if applied:
            by_month[applied.strftime("%Y-%m")] += 1
        if a.get("resume_version") and a["status"] != "Saved":
            row = resume.setdefault(a["resume_version"], [0, 0])
            row[0] += 1
            row[1] += 1 if a["status"] in ("Interview", "Offer") else 0
    return AnalyticsOut(
        total_applications=len(apps),
        status_counts={s.value: counts.get(s.value, 0) for s in ApplicationStatus},
        monthly_applications=[MonthlyCount(month=m, count=c) for m, c in sorted(by_month.items())],
        response_rate=pct(responded),
        interview_rate=pct(counts.get("Interview", 0) + counts.get("Offer", 0)),
        offer_rate=pct(counts.get("Offer", 0)),
        resume_performance=[
            ResumeStat(resume_version=v, applications=n[0], interviews_or_offers=n[1])
            for v, n in sorted(resume.items())
        ],
    )



# --------------------------------------------------------------------------
# Resumes (private Supabase Storage)
# --------------------------------------------------------------------------
import re as _re
import uuid as _uuid

RESUME_BUCKET = "resumes"
MAX_RESUME_BYTES = 5 * 1024 * 1024


def _resume_storage():
    """Use the configured server-side Supabase client; never expose its key."""
    if settings.demo_mode:
        raise HTTPException(status_code=501, detail="Resume uploads require Supabase mode. Set DEMO_MODE=false to use cloud storage.")
    db = get_database()
    client = getattr(db, "client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Resume storage is not configured.")
    return client.storage.from_(RESUME_BUCKET)


def _safe_resume_name(filename: str) -> str:
    name = (filename or "resume.pdf").replace("\\", "/").split("/")[-1]
    name = _re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .") or "resume.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are allowed.")
    return name[:120]


@api.post("/resumes", status_code=201, tags=["resumes"])
async def upload_resume(file: UploadFile = File(...), user: Dict[str, str] = Depends(require_user)):
    """Upload a PDF into this user's folder in the private bucket."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Please upload a PDF file.")
    content = await file.read(MAX_RESUME_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The selected file is empty.")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The file does not appear to be a valid PDF.")
    original_name = _safe_resume_name(file.filename or "resume.pdf")
    stored_name = f"{_uuid.uuid4().hex}__{original_name}"
    path = f"{user['id']}/{stored_name}"
    try:
        _resume_storage().upload(
            path, content,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Resume upload failed for user %s", user.get("id"))
        raise HTTPException(status_code=502, detail="Could not upload the resume. Check the resumes bucket and try again.")
    return {"name": stored_name, "display_name": original_name, "size_bytes": len(content)}


@api.get("/resumes", tags=["resumes"])
def list_resumes(user: Dict[str, str] = Depends(require_user)):
    """List only the current user's resume files."""
    try:
        objects = _resume_storage().list(user["id"])
        result = []
        for item in objects or []:
            name = item.get("name", "")
            if not name or "/" in name or name in (".", ".."):
                continue
            display_name = name.split("__", 1)[1] if "__" in name else name
            result.append({
                "name": name,
                "display_name": display_name,
                "created_at": item.get("created_at") or item.get("updated_at"),
                "size_bytes": (item.get("metadata") or {}).get("size"),
            })
        result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Resume listing failed for user %s", user.get("id"))
        raise HTTPException(status_code=502, detail="Could not load resumes. Check the resumes bucket and try again.")


@api.post("/resumes/{resume_name}/extract-text", tags=["resumes"])
def extract_resume_api(
    resume_name: str,
    user: Dict[str, str] = Depends(require_user),
):
    """Extract text from the signed-in user's stored PDF resume."""

    if (
        not resume_name
        or "/" in resume_name
        or "\\" in resume_name
        or resume_name in (".", "..")
    ):
        raise HTTPException(status_code=400, detail="Invalid resume name.")

    try:
        storage = _resume_storage()

        # Download only from the current user's private folder.
        path = f"{user['id']}/{resume_name}"
        pdf_bytes = storage.download(path)

        if not pdf_bytes:
            raise HTTPException(
                status_code=404,
                detail="Resume is empty or could not be found.",
            )

        # Extract readable text from the PDF.
        extracted_text = extract_resume_text(pdf_bytes)

        return {
            "resume_name": resume_name,
            "extracted_text": extracted_text,
            "character_count": len(extracted_text),
            "message": "Resume text extracted successfully.",
        }

    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except Exception:
        logger.exception(
            "Resume text extraction failed for user %s",
            user.get("id"),
        )
        raise HTTPException(
            status_code=502,
            detail="Could not read this resume from storage. Please check that the file exists.",
        )

class ResumeMatchRequest(BaseModel):
    job_description: str = Field(min_length=50, max_length=20000)


@api.post("/resumes/{resume_name}/match", tags=["ai"])
def match_resume_api(
    resume_name: str,
    payload: ResumeMatchRequest,
    user: Dict[str, str] = Depends(require_user),
):
    """Compare a user's private resume with a job description."""

    if (
        not resume_name
        or "/" in resume_name
        or "\\" in resume_name
        or resume_name in (".", "..")
    ):
        raise HTTPException(status_code=400, detail="Invalid resume name.")

    try:
        # Access only the signed-in user's resume folder.
        path = f"{user['id']}/{resume_name}"
        pdf_bytes = _resume_storage().download(path)

        if not pdf_bytes:
            raise HTTPException(
                status_code=404,
                detail="Resume not found or empty.",
            )

        # Convert the PDF into readable text.
        resume_text = extract_resume_text(pdf_bytes)

        # Compare the resume with the supplied job description.
        result = ai_service.match_resume_to_job(
            resume_text=resume_text,
            job_description=payload.job_description,
        )

        return {
            "resume_name": resume_name,
            **result,
        }

    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except Exception:
        logger.exception(
            "Resume matching failed for user %s",
            user.get("id"),
        )
        raise HTTPException(
            status_code=502,
            detail="Could not analyse this resume. Please try again.",
        )


@api.delete("/resumes/{resume_name}", status_code=204, tags=["resumes"])
def delete_resume(resume_name: str, user: Dict[str, str] = Depends(require_user)):
    """Delete a file only from the current user's folder."""
    if not resume_name or "/" in resume_name or "\\" in resume_name or resume_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid resume name.")
    try:
        _resume_storage().remove([f"{user['id']}/{resume_name}"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Resume deletion failed for user %s", user.get("id"))
        raise HTTPException(status_code=502, detail="Could not delete this resume.")
    return Response(status_code=204)


# --------------------------------------------------------------------------
# AI endpoints
# --------------------------------------------------------------------------
@api.post("/ai/extract-job", response_model=ExtractJobResponse, tags=["ai"])
def extract_job(payload: ExtractJobRequest):
    extracted = ai_service.extract_job_details(payload.job_description)
    return ExtractJobResponse(extracted=extracted, source=ai_service.current_source())


@api.post("/ai/follow-up-email", response_model=FollowUpEmailResponse, tags=["ai"])
def follow_up_email(payload: FollowUpEmailRequest, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    application = _get_or_404(db, _uuid_str(payload.application_id, "application_id"), user["id"])
    return ai_service.generate_follow_up_email(
        application, payload.tone, payload.sender_name, payload.extra_context
    )


@api.post("/ai/interview-questions", response_model=InterviewQuestionsResponse, tags=["ai"])
def interview_questions(payload: InterviewQuestionsRequest, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    title, description = payload.job_title, payload.job_description
    if payload.application_id:
        application = _get_or_404(db, _uuid_str(payload.application_id, "application_id"), user["id"])
        title = application["job_title"]
        description = application.get("job_description")
        if not description or len(description.strip()) < 30:
            raise HTTPException(
                status_code=400,
                detail="This application has no job description yet. Edit it and paste one first.",
            )
    return ai_service.generate_interview_questions(title, description, payload.count)


# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------
@api.post("/demo/seed", response_model=DemoSeedResponse, tags=["demo"])
def seed_demo_data(force: bool = False, db: Database = Depends(get_db), user: Dict[str, str] = Depends(require_user)):
    if not settings.allow_demo_seed:
        raise HTTPException(status_code=403, detail="Loading demo data is disabled (ALLOW_DEMO_SEED=false).")
    if db.count_applications(user_id=user["id"]) > 0 and not force:
        raise HTTPException(status_code=409, detail="The database already has applications; demo data was not added.")
    return DemoSeedResponse(inserted=load_sample_data(db, today_local()))



# --------------------------------------------------------------------------
# Authentication routes (public, except for optional backend API-key guard)
# --------------------------------------------------------------------------
@auth_api.post("/signup", tags=["authentication"])
def signup(payload: AuthCredentials):
    try:
        result = auth.sign_up_user(payload.email, payload.password)
        user = result.user
        if user is None:
            raise HTTPException(status_code=400, detail="Signup could not be completed. Check your details.")
        session = result.session
        response = {"message": "Account created. Check your email to verify it, then sign in.", "user_id": str(user.id), "email": user.email, "session_created": session is not None}
        if session:
            response.update({"access_token": session.access_token, "refresh_token": session.refresh_token})
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Signup failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Signup failed. Check your email and password; the email may already be registered.")

@auth_api.post("/login", tags=["authentication"])
def login(payload: AuthCredentials):
    try:
        result = auth.sign_in_user(payload.email, payload.password)
        if result.session is None or result.user is None:
            raise HTTPException(status_code=401, detail="Login unsuccessful. Verify your email or check your credentials.")
        return {"message": "Login successful.", "access_token": result.session.access_token, "refresh_token": result.session.refresh_token, "token_type": "bearer", "user_id": str(result.user.id), "email": result.user.email}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Login failed: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Login failed. Check your credentials and confirm your email address.")

@auth_api.post("/forgot-password", tags=["authentication"])
def forgot_password(payload: EmailRequest):
    try:
        auth.request_password_reset(payload.email)
        return {"message": "If the account exists, a password recovery email will be sent."}
    except Exception as exc:
        logger.warning("Password reset request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Could not request a password reset. Please try again.")

app.include_router(api)
app.include_router(auth_api)

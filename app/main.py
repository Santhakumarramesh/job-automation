import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from services.api_cors import install_cors_middleware
from services.prometheus_setup import install_prometheus
from services.rate_limit import install_rate_limit_middleware

from .auth import User, get_current_user, require_admin
from .tasks import enqueue_job

_OPENAPI_TAGS = [
    {"name": "service", "description": "Process health and root."},
    {"name": "jobs", "description": "Enqueue and inspect Celery background jobs."},
    {"name": "applications", "description": "Application tracker rows for the authenticated user."},
    {"name": "insights", "description": "Tracker aggregates, audit hints, and answerer rollups."},
    {"name": "ats", "description": "ATS/board form hints and platform metadata (v1 static; MCP parity)."},
    {"name": "follow-ups", "description": "Follow-up queue and digests per user."},
    {"name": "admin", "description": "Cross-user operations (requires admin role or API_KEY_IS_ADMIN)."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.observability import configure_structured_logging
    from services.startup_checks import run_startup_checks, validate_profile_path

    configure_structured_logging()
    run_startup_checks("app")
    validate_profile_path()
    yield


class _CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.correlation_id = rid
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


app = FastAPI(
    title="Career Co-Pilot Pro API",
    description=(
        "REST API for job pipelines, application tracking, follow-ups, and operations. "
        "Base URLs: **`/api`** (stable) and **`/api/v1`** (duplicate alias unless `API_V1_DUPLICATE_ROUTES=0`). "
        "Authenticate with **X-API-Key**, **Authorization: Bearer** "
        "(JWT: `JWT_SECRET` for HS256, or `JWT_JWKS_URL` / `JWT_ISSUER` for OIDC), "
        "optional **X-M2M-API-Key** when `M2M_API_KEY` is set (service / worker identity), "
        "or the open **demo-user** when `API_KEY` is unset (development only)."
    ),
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)
app.add_middleware(_CorrelationMiddleware)

install_prometheus(app)
install_rate_limit_middleware(app)
install_cors_middleware(app)

api_router = APIRouter()


class JobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)
    workspace_id: Optional[str] = Field(
        default=None,
        max_length=200,
        description=(
            "Stored on tracker rows for jobs from this enqueue (also accepts organization_id in payload). "
            "When API_ENFORCE_USER_WORKSPACE_ON_WRITES=1 and the caller has a JWT/header workspace, "
            "this must match that tenant (see workspace_write_guard)."
        ),
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=200,
        description=(
            "Optional key; same key+user returns the same job_id within TTL (see IDEMPOTENCY_TTL_HOURS). "
            "You may send Idempotency-Key HTTP header instead; if both are sent they must match."
        ),
    )


_ALLOWED_FOLLOW_UP_STATUS = frozenset({"", "pending", "done", "snoozed", "dismissed"})

_ALLOWED_INTERVIEW_STAGES = frozenset(
    {"", "none", "scheduled", "completed", "advanced", "rejected", "withdrew", "no_show"}
)
_ALLOWED_OFFER_OUTCOMES = frozenset(
    {"", "none", "pending", "extended", "accepted", "declined", "ghosted"}
)


class FollowUpPatch(BaseModel):
    follow_up_at: Optional[str] = Field(None, max_length=64, description="ISO 8601; omit to leave unchanged")
    follow_up_status: Optional[str] = Field(None, max_length=32)
    follow_up_note: Optional[str] = Field(None, max_length=2000)


def _follow_up_updates_from_body(body: FollowUpPatch) -> dict:
    try:
        raw = body.model_dump(exclude_unset=True)
    except AttributeError:
        raw = body.dict(exclude_unset=True)
    if "follow_up_status" in raw and raw["follow_up_status"] is not None:
        v = str(raw["follow_up_status"]).strip().lower()
        if v not in _ALLOWED_FOLLOW_UP_STATUS:
            raise HTTPException(
                status_code=400,
                detail="follow_up_status must be one of: pending, done, snoozed, dismissed (or empty)",
            )
        raw["follow_up_status"] = v
    return raw


class PipelinePatch(BaseModel):
    interview_stage: Optional[str] = Field(None, max_length=120)
    offer_outcome: Optional[str] = Field(None, max_length=120)


def _pipeline_updates_from_body(body: PipelinePatch) -> dict:
    try:
        raw = body.model_dump(exclude_unset=True)
    except AttributeError:
        raw = body.dict(exclude_unset=True)
    if "interview_stage" in raw and raw["interview_stage"] is not None:
        v = str(raw["interview_stage"]).strip().lower()
        if v not in _ALLOWED_INTERVIEW_STAGES:
            raise HTTPException(
                status_code=400,
                detail="interview_stage must be one of: none, scheduled, completed, advanced, rejected, withdrew, no_show (or empty)",
            )
        raw["interview_stage"] = v
    if "offer_outcome" in raw and raw["offer_outcome"] is not None:
        v = str(raw["offer_outcome"]).strip().lower()
        if v not in _ALLOWED_OFFER_OUTCOMES:
            raise HTTPException(
                status_code=400,
                detail="offer_outcome must be one of: none, pending, extended, accepted, declined, ghosted (or empty)",
            )
        raw["offer_outcome"] = v
    return raw


@app.get("/", tags=["service"])
def read_root():
    return {"status": "Job Automation API is active"}


@app.get("/health", tags=["service"])
def health():
    """Liveness: service is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["service"])
def ready():
    """Readiness: service can accept work."""
    return {"status": "ready"}


def _tracker_list_scope(user_id: str) -> Optional[str]:
    """None = list all rows (local dev demo-user). Else filter tracker by user_id."""
    if user_id in ("demo-user",):
        return None
    return user_id


def _workspace_filter(query_workspace_id: Optional[str], user: User) -> Optional[str]:
    from services.application_tracker import resolve_workspace_list_filter

    return resolve_workspace_list_filter(query_workspace_id, getattr(user, "workspace_id", None))


def _admin_workspace_filter(query_workspace_id: Optional[str], admin: User) -> Optional[str]:
    from services.workspace_write_guard import enforce_admin_workspace_on_read

    return enforce_admin_workspace_on_read(admin=admin, query_workspace_id=query_workspace_id)


def _artifacts_with_optional_signed_urls(artifacts: dict, signed_urls: bool) -> dict:
    """Phase 3.4 — add presigned GET URLs when ?signed_urls=true and S3 manifest + boto3 exist."""
    if not signed_urls:
        return artifacts
    from services.object_storage import presign_artifact_manifest

    try:
        exp = int(os.getenv("ARTIFACTS_PRESIGN_EXPIRES", "3600"))
    except ValueError:
        exp = 3600
    signed = presign_artifact_manifest(artifacts.get("artifacts_manifest") or {}, exp)
    if not signed:
        return artifacts
    return {**artifacts, "signed_urls": signed}


def _resolve_job_idempotency_key(
    header_key: Optional[str],
    body_key: Optional[str],
) -> Optional[str]:
    h = (header_key or "").strip()
    b = (body_key or "").strip()
    if h and b and h != b:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header and idempotency_key in JSON body must match when both are sent",
        )
    out = h or b or None
    if out and len(out) > 200:
        raise HTTPException(status_code=400, detail="idempotency key exceeds 200 characters")
    return out


@api_router.post("/jobs", status_code=202, tags=["jobs"])
def submit_job(
    req: JobRequest,
    request: Request,
    user=Depends(get_current_user),
    idempotency_key_header: Optional[str] = Header(
        None,
        alias="Idempotency-Key",
        description="Same semantics as idempotency_key in body; header and body must agree if both set.",
    ),
):
    idem = _resolve_job_idempotency_key(idempotency_key_header, req.idempotency_key)
    payload = {**req.payload, "user_id": user.id}
    if req.workspace_id is not None:
        w = str(req.workspace_id).strip()
        if w:
            payload["workspace_id"] = w[:200]
    else:
        wid = str(payload.get("workspace_id") or payload.get("organization_id") or "").strip()
        if wid:
            payload["workspace_id"] = wid[:200]

    from services.workspace_write_guard import enforce_user_workspace_on_job_payload

    enforce_user_workspace_on_job_payload(user=user, payload=payload)

    job_id = enqueue_job(
        req.name,
        payload,
        user.id,
        idempotency_key=idem,
    )
    try:
        from services.observability import audit_log

        cid = getattr(request.state, "correlation_id", "")
        audit_log(
            "job_enqueued",
            job_id=job_id,
            status="accepted",
            correlation_id=cid,
            extra={
                "name": req.name,
                "user_id": user.id,
                "workspace_id": (payload.get("workspace_id") or "") or None,
                "run_id": job_id,
            },
        )
    except Exception:
        pass
    return {"job_id": job_id, "run_id": job_id, "status": "accepted"}


@api_router.get("/applications", tags=["applications"])
def list_applications(
    user=Depends(get_current_user),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description=(
            "Filter to this workspace_id. Omit to use JWT workspace_id/org_id or X-Workspace-Id; "
            "send an empty value to list all workspaces for the user."
        ),
    ),
):
    """List tracker rows for the authenticated user (all rows for demo-user)."""
    from services.application_tracker import load_applications

    scope = _tracker_list_scope(user.id)
    wf = _workspace_filter(workspace_id, user)
    df = load_applications(for_user_id=scope, workspace_id=wf)
    records = df.fillna("").to_dict(orient="records")
    return {"count": len(records), "items": records[:500]}


class AnalyzeFormRequest(BaseModel):
    job_url: str = Field(default="", max_length=2000, description="Job listing URL")
    apply_url: str = Field(default="", max_length=2000, description="Apply target URL if different from listing")


class AnalyzeFormLiveRequest(AnalyzeFormRequest):
    max_fields: int = Field(40, ge=5, le=120, description="Max form controls to return from DOM")


class TruthInventoryRequest(BaseModel):
    """
    Same resolution order as MCP ``build_truth_inventory_from_master_resume``:
    long inline text wins; else optional **project-relative** ``master_resume_path``;
    else server default (``RESUME_PATH`` / ``MASTER_RESUME_PDF`` / ``Master_Resumes/*``).
    """

    master_resume_text: str = Field(default="", max_length=600_000)
    master_resume_path: str = Field(
        default="",
        max_length=2000,
        description="Path relative to project root only (no absolute paths).",
    )


class SearchJobsRequest(BaseModel):
    """
    LinkedIn job discovery via MCP (``search_jobs`` tool parity).
    Requires a running linkedin-mcp-server (``LINKEDIN_MCP_URL``, default ``http://127.0.0.1:8000/mcp``).
    """

    keywords: str = Field(default="", max_length=500)
    location: str = Field(default="United States", max_length=200)
    work_type: str = Field(default="remote", max_length=64)
    max_results: int = Field(25, ge=1, le=100)
    easy_apply: bool = False
    date_posted: str = Field(default="", max_length=32)
    job_type: str = Field(default="", max_length=64)
    experience_level: str = Field(default="", max_length=64)
    sort_order: str = Field(default="", max_length=64)


class ScoreJobFitRequest(BaseModel):
    """Fit gate + ATS snapshot (MCP ``score_job_fit`` parity)."""

    job_description: str = Field(..., min_length=1, max_length=600_000)
    master_resume_text: str = Field(..., min_length=1, max_length=600_000)
    job_title: str = Field(default="", max_length=300)
    company: str = Field(default="", max_length=300)
    location: str = Field(default="USA", max_length=200)


class AddressForJobRequest(BaseModel):
    """Mailing address selection (MCP ``get_address_for_job`` parity)."""

    job_location: str = Field(default="", max_length=2000)
    job_title: str = Field(default="", max_length=500)
    job_description: str = Field(default="", max_length=600_000)
    work_type: str = Field(default="", max_length=120)


class DecideApplyModeRequest(BaseModel):
    """Central apply policy (MCP ``decide_apply_mode`` parity; JSON body instead of stringified job)."""

    job: Dict[str, Any] = Field(default_factory=dict)
    fit_decision: str = Field(default="", max_length=64)
    ats_score: Optional[int] = None
    unsupported_requirements: List[str] = Field(default_factory=list)


class ApplicationDecisionRequest(BaseModel):
    """Full v0.1 decision (MCP ``get_application_decision`` parity): job_state, safe_to_submit, answers."""

    job: Dict[str, Any] = Field(default_factory=dict)
    profile_path: str = Field(
        default="",
        max_length=2000,
        description="Optional project-relative path to candidate_profile.json; empty uses default",
    )
    master_resume_text: str = Field(default="", max_length=600_000)
    blocked_reason: str = Field(
        default="",
        max_length=2000,
        description="Optional runner hard-stop reason (forces job_state=blocked)",
    )


class ValidateProfileRequest(BaseModel):
    """Optional ``profile_path`` (project-relative only); empty uses default/env profile."""

    profile_path: str = Field(default="", max_length=2000)


class AutofillValuesRequest(BaseModel):
    """Profile field suggestions (MCP ``get_autofill_values`` parity)."""

    form_type: str = Field(default="linkedin", max_length=64)
    question_hints: str = Field(default="", max_length=2000)


class BatchPrioritizeRequest(BaseModel):
    """Rank jobs by fit + ATS (MCP ``batch_prioritize_jobs`` parity). Max 500 jobs per request."""

    jobs: List[Dict[str, Any]] = Field(..., min_length=1)
    master_resume_text: str = Field(..., min_length=1, max_length=600_000)
    max_scored: int = Field(20, ge=1, le=200)


class PrepareApplicationPackageRequest(BaseModel):
    """Manual-assist bundle: resume path, autofill map, short answers, optional fit gate (MCP ``prepare_application_package``)."""

    job_title: str = Field(..., max_length=500)
    company: str = Field(..., max_length=300)
    job_description: str = Field(default="", max_length=600_000)
    master_resume_text: str = Field(default="", max_length=600_000)
    job_location: str = Field(default="", max_length=2000)
    work_type: str = Field(default="", max_length=120)


class RunResultsReportRequest(BaseModel):
    """Batch apply run rows (same JSON shape as MCP on-disk run results). Max 2000 rows."""

    run_results: List[Dict[str, Any]] = Field(default_factory=list, max_length=2000)


class RecruiterFollowupRequest(BaseModel):
    """LinkedIn + email follow-up drafts (MCP ``generate_recruiter_followup`` parity)."""

    job_title: str = Field(..., max_length=500)
    company: str = Field(..., max_length=300)
    application_date: str = Field(default="", max_length=120)


class PrepareResumeForJobRequest(BaseModel):
    """Copy/rename resume PDF for a job (MCP ``prepare_resume_for_job`` parity)."""

    job_title: str = Field(..., max_length=500)
    company: str = Field(..., max_length=300)
    resume_source_path: str = Field(default="", max_length=2000)


class ConfirmEasyApplyRequest(BaseModel):
    """LinkedIn listing URL to probe for Easy Apply (MCP ``confirm_easy_apply`` parity)."""

    job_url: str = Field(..., min_length=12, max_length=2000)


class ApplyToJobsRequest(BaseModel):
    """
    Batch apply (MCP ``apply_to_jobs`` / ``dry_run_apply_to_jobs`` parity).
    Requires ``ATS_ALLOW_LINKEDIN_BROWSER=1`` on the API. Max 50 jobs per request.

    Phase 3: optional per-job ``pilot_submit_allowed: true`` when
    ``AUTONOMY_LINKEDIN_PILOT_SUBMIT_ONLY=1`` on the worker/API host.
    """

    jobs: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)
    dry_run: bool = False
    shadow_mode: bool = Field(
        default=False,
        description=(
            "Phase 2 shadow: fill through pre-submit, never click submit; "
            "runner statuses shadow_would_apply / shadow_would_not_apply."
        ),
    )
    rate_limit_seconds: float = Field(90.0, ge=5.0, le=600.0)
    manual_assist: bool = False
    require_safeguards: bool = True
    workspace_id: Optional[str] = Field(
        default=None,
        max_length=200,
        description=(
            "Default workspace_id for jobs that omit it; logged on tracker rows when present. "
            "With API_ENFORCE_USER_WORKSPACE_ON_WRITES, must match the authenticated tenant."
        ),
    )
    operator_submit_approved: bool = Field(
        default=False,
        description=(
            "Supervised operators: explicit approval before live LinkedIn submit. "
            "When True and the request is a live submit (not dry_run, not shadow_mode), "
            "the API appends an audit line to application_audit.jsonl (AUDIT_LOG_PATH). "
            "When ATS_REQUIRE_OPERATOR_SUBMIT_APPROVAL=1, live submit is rejected unless this is True."
        ),
    )
    operator_submit_note: str = Field(
        default="",
        max_length=500,
        description="Optional note included in the operator_submit_approved audit event.",
    )


class DryRunApplyToJobsRequest(BaseModel):
    """
    Same as batch apply but always ``dry_run=True`` (MCP ``dry_run_apply_to_jobs`` parity).
    """

    jobs: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)
    shadow_mode: bool = Field(
        default=False,
        description="When True with dry_run, use shadow runner statuses instead of dry_run only.",
    )
    rate_limit_seconds: float = Field(90.0, ge=5.0, le=600.0)
    manual_assist: bool = False
    require_safeguards: bool = True
    workspace_id: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Same as ApplyToJobsRequest.workspace_id (batch default for per-job tracker metadata).",
    )


_RUN_RESULTS_REPORT_MAX = 2000


@api_router.post("/ats/truth-inventory", tags=["ats"])
def ats_truth_inventory(body: TruthInventoryRequest):
    """
    Parse master resume into a JSON truth inventory (MCP ``build_truth_inventory_from_master_resume`` parity).
    """
    from agents.master_resume_guard import (
        load_master_resume_text,
        parse_master_resume,
        read_resume_plaintext_file,
        resolve_project_relative_resume_path,
        truth_inventory_from_profile,
    )

    inline = (body.master_resume_text or "").strip()
    text, src = "", ""
    if len(inline) >= 100:
        text, src = inline, "inline_text"
    elif (body.master_resume_path or "").strip():
        try:
            p = resolve_project_relative_resume_path(body.master_resume_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        text = read_resume_plaintext_file(p)
        src = str(p)
        if len(text.strip()) < 100:
            return {
                "status": "error",
                "message": "Resolved file has insufficient text (need 100+ characters).",
                "source": src,
                "inventory": {},
            }
    else:
        text, src = load_master_resume_text("", "")

    if len((text or "").strip()) < 100:
        return {
            "status": "error",
            "message": "Need master resume text (100+ chars), a readable project-relative path, or server RESUME_PATH / Master_Resumes.",
            "source": src or "",
            "inventory": {},
        }
    profile = parse_master_resume(text)
    return {
        "status": "ok",
        "source": src or "inline_text",
        "char_count": len(text),
        "inventory": truth_inventory_from_profile(profile),
    }


@api_router.post("/ats/search-jobs", tags=["ats"])
def ats_search_jobs(body: SearchJobsRequest):
    """
    Search LinkedIn Jobs through the MCP bridge; each row matches the shared job schema (``JobListing.to_row()``).
    """
    from providers.linkedin_mcp_jobs import linkedin_mcp_search_jobs_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return linkedin_mcp_search_jobs_payload(**raw)


@api_router.post("/ats/score-job-fit", tags=["ats"])
def ats_score_job_fit(body: ScoreJobFitRequest):
    """
    Master-resume fit gate plus one comprehensive ATS check (same JSON as MCP ``score_job_fit``).
    """
    from services.ats_service import score_job_fit_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return score_job_fit_payload(**raw)


@api_router.post("/ats/address-for-job", tags=["ats"])
def ats_address_for_job(body: AddressForJobRequest):
    """Pick profile mailing address for a job location (same JSON as MCP ``get_address_for_job``)."""
    from services.address_for_job import address_for_job_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return address_for_job_payload(**raw)


@api_router.post("/ats/decide-apply-mode", tags=["ats"])
def ats_decide_apply_mode(body: DecideApplyModeRequest):
    """Return ``auto_easy_apply`` | ``manual_assist`` | ``skip`` plus ``policy_reason`` (MCP parity)."""
    from services.policy_service import decide_apply_mode_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return decide_apply_mode_payload(
        job=raw.get("job") or {},
        fit_decision=raw.get("fit_decision") or "",
        ats_score=raw.get("ats_score"),
        unsupported_requirements=raw.get("unsupported_requirements") or [],
    )


@api_router.post("/ats/application-decision", tags=["ats"])
def ats_application_decision(body: ApplicationDecisionRequest):
    """Return v0.1 application decision: ``job_state``, ``safe_to_submit``, per-field answer states (MCP parity)."""
    from services.application_decision import build_application_decision
    from services.profile_service import load_profile, resolve_profile_path_for_api

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    job = raw.get("job") or {}
    pp = (raw.get("profile_path") or "").strip()
    if pp:
        try:
            resolved = resolve_profile_path_for_api(pp)
            prof = load_profile(resolved)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        prof = load_profile()

    return build_application_decision(
        job,
        profile=prof,
        master_resume_text=raw.get("master_resume_text") or "",
        use_llm_preview=False,
        blocked_reason=(raw.get("blocked_reason") or "").strip() or None,
    )


@api_router.get("/ats/form-type", tags=["ats"])
def ats_form_type(url: str = Query("", max_length=2000, description="Job or apply page URL")):
    """Form family from URL (MCP ``detect_form_type`` parity)."""
    from services.form_type_detection import detect_form_type_payload

    return detect_form_type_payload(url)


@api_router.post("/ats/validate-profile", tags=["ats"])
def ats_validate_profile(body: ValidateProfileRequest):
    """Validate ``candidate_profile.json`` (MCP ``validate_candidate_profile`` parity)."""
    from services.profile_service import validate_candidate_profile_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return validate_candidate_profile_payload(
        raw.get("profile_path") or "",
        restrict_to_project_relative=True,
    )


@api_router.post("/ats/autofill-values", tags=["ats"])
def ats_autofill_values(body: AutofillValuesRequest):
    """Suggested autofill map from candidate profile (MCP ``get_autofill_values`` parity)."""
    from services.autofill_values import get_autofill_values_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return get_autofill_values_payload(
        form_type=raw.get("form_type") or "linkedin",
        question_hints=raw.get("question_hints") or "",
    )


@api_router.post("/ats/batch-prioritize-jobs", tags=["ats"])
def ats_batch_prioritize_jobs(body: BatchPrioritizeRequest):
    """Score and sort job dicts by Easy Apply flag, fit score, ATS score (MCP parity)."""
    from services.batch_prioritize_jobs import batch_prioritize_jobs_payload

    if len(body.jobs) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 jobs per request")
    return batch_prioritize_jobs_payload(
        body.jobs,
        body.master_resume_text,
        max_scored=body.max_scored,
    )


@api_router.post("/ats/prepare-application-package", tags=["ats"])
def ats_prepare_application_package(body: PrepareApplicationPackageRequest):
    """Resume path, autofill values, structured short answers, optional fit scores (MCP parity)."""
    from services.application_package import prepare_application_package_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return prepare_application_package_payload(
        job_title=raw.get("job_title") or "",
        company=raw.get("company") or "",
        job_description=raw.get("job_description") or "",
        master_resume_text=raw.get("master_resume_text") or "",
        job_location=raw.get("job_location") or "",
        work_type=raw.get("work_type") or "",
    )


@api_router.post("/ats/review-unmapped-fields", tags=["ats"])
def ats_review_unmapped_fields(body: RunResultsReportRequest):
    """Unmapped field counts and profile-key hints from run result rows (MCP parity via JSON body)."""
    from services.run_results_reports import review_unmapped_fields_payload

    rows = body.run_results
    if len(rows) > _RUN_RESULTS_REPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {_RUN_RESULTS_REPORT_MAX} run result rows per request",
        )
    return review_unmapped_fields_payload(rows)


@api_router.post("/ats/application-audit-report", tags=["ats"])
def ats_application_audit_report(body: RunResultsReportRequest):
    """Applied / skipped / failed counts and unmapped summary from run rows (MCP parity via JSON body)."""
    from services.run_results_reports import application_audit_report_payload

    rows = body.run_results
    if len(rows) > _RUN_RESULTS_REPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {_RUN_RESULTS_REPORT_MAX} run result rows per request",
        )
    return application_audit_report_payload(rows)


@api_router.post("/ats/generate-recruiter-followup", tags=["ats"])
def ats_generate_recruiter_followup(body: RecruiterFollowupRequest):
    """Draft LinkedIn message and email subject/body from profile + role (MCP parity)."""
    from services.recruiter_followup import generate_recruiter_followup_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return generate_recruiter_followup_payload(
        job_title=raw.get("job_title") or "",
        company=raw.get("company") or "",
        application_date=raw.get("application_date") or "",
    )


@api_router.post("/ats/prepare-resume-for-job", tags=["ats"])
def ats_prepare_resume_for_job(body: PrepareResumeForJobRequest):
    """Ensure a job-specific resume PDF path under ``generated_resumes/`` (MCP parity)."""
    from services.prepare_resume_for_job import prepare_resume_for_job_payload

    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    return prepare_resume_for_job_payload(
        job_title=raw.get("job_title") or "",
        company=raw.get("company") or "",
        resume_source_path=raw.get("resume_source_path") or "",
    )


@api_router.post(
    "/ats/confirm-easy-apply",
    tags=["ats"],
    responses={403: {"description": "LinkedIn browser automation disabled on API."}},
)
def ats_confirm_easy_apply(body: ConfirmEasyApplyRequest, user: User = Depends(get_current_user)):
    """
    Headless LinkedIn login + job page probe for Easy Apply (MCP parity).
    Requires ``ATS_ALLOW_LINKEDIN_BROWSER=1``, Playwright, and ``LINKEDIN_EMAIL`` / ``LINKEDIN_PASSWORD``.
    """
    from services.linkedin_browser_automation import confirm_easy_apply_payload
    from services.linkedin_browser_gate import (
        linkedin_browser_automation_disabled_response,
        linkedin_browser_automation_enabled,
    )
    from services.workspace_write_guard import assert_ats_linkedin_caller_allowed

    assert_ats_linkedin_caller_allowed(user)

    if not linkedin_browser_automation_enabled():
        return JSONResponse(status_code=403, content=linkedin_browser_automation_disabled_response())
    return confirm_easy_apply_payload(body.job_url.strip())


@api_router.post(
    "/ats/apply-to-jobs",
    tags=["ats"],
    responses={403: {"description": "LinkedIn browser automation disabled on API."}},
)
def ats_apply_to_jobs(body: ApplyToJobsRequest, user: User = Depends(get_current_user)):
    """
    Run the LinkedIn apply loop (or dry-run) for up to 50 jobs (MCP parity).
    Requires ``ATS_ALLOW_LINKEDIN_BROWSER=1``, Playwright, credentials, and (for default mode) Easy Apply–confirmed rows.

    Live submit (``dry_run=false`` and ``shadow_mode=false``): optional gate
    ``ATS_REQUIRE_OPERATOR_SUBMIT_APPROVAL=1`` requires ``operator_submit_approved=true``.
    When ``operator_submit_approved`` is true on a live submit, an audit line is written (``AUDIT_LOG_PATH``).
    """
    from services.linkedin_browser_automation import apply_to_jobs_payload
    from services.linkedin_browser_gate import (
        linkedin_browser_automation_disabled_response,
        linkedin_browser_automation_enabled,
    )
    from services.observability import audit_log
    from services.workspace_write_guard import (
        assert_ats_linkedin_caller_allowed,
        enforce_user_workspace_on_apply_jobs,
    )

    assert_ats_linkedin_caller_allowed(user)

    if not linkedin_browser_automation_enabled():
        return JSONResponse(status_code=403, content=linkedin_browser_automation_disabled_response())
    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    jobs = raw.get("jobs") or []
    enforce_user_workspace_on_apply_jobs(
        user=user,
        jobs=jobs,
        default_workspace_id=raw.get("workspace_id"),
    )
    dry_run = bool(raw.get("dry_run", False))
    shadow_mode = bool(raw.get("shadow_mode", False))
    live_submit = not dry_run and not shadow_mode
    op_ok = bool(raw.get("operator_submit_approved", False))
    op_note = str(raw.get("operator_submit_note") or "")[:500]
    require_op = os.getenv("ATS_REQUIRE_OPERATOR_SUBMIT_APPROVAL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if live_submit and require_op and not op_ok:
        raise HTTPException(
            status_code=400,
            detail=(
                "Live LinkedIn submit requires operator_submit_approved=true. "
                "Use dry_run or shadow_mode for unattended tests, or set "
                "ATS_REQUIRE_OPERATOR_SUBMIT_APPROVAL=0 to disable this gate."
            ),
        )
    if live_submit and op_ok:
        sample_urls: list[str] = []
        for j in jobs[:12]:
            if not isinstance(j, dict):
                continue
            u = str(j.get("url") or j.get("applyUrl") or "").strip()
            if u:
                sample_urls.append(u[:500])
        audit_log(
            "operator_submit_approved",
            status="before_apply_payload",
            extra={
                "user_id": user.id,
                "job_count": len(jobs),
                "operator_submit_note": op_note,
                "rate_limit_seconds": float(raw.get("rate_limit_seconds") or 90.0),
                "require_safeguards": bool(raw.get("require_safeguards", True)),
                "job_urls_sample": sample_urls,
            },
        )
    return apply_to_jobs_payload(
        jobs,
        dry_run=dry_run,
        shadow_mode=shadow_mode,
        rate_limit_seconds=body.rate_limit_seconds,
        manual_assist=body.manual_assist,
        require_safeguards=body.require_safeguards,
    )


@api_router.post(
    "/ats/apply-to-jobs/dry-run",
    tags=["ats"],
    responses={403: {"description": "LinkedIn browser automation disabled on API."}},
)
def ats_apply_to_jobs_dry_run(body: DryRunApplyToJobsRequest, user: User = Depends(get_current_user)):
    """
    Fill application flows without submitting (MCP ``dry_run_apply_to_jobs`` parity).
    Same gate and limits as ``POST /ats/apply-to-jobs`` with ``dry_run`` forced on.
    """
    from services.linkedin_browser_automation import apply_to_jobs_payload
    from services.linkedin_browser_gate import (
        linkedin_browser_automation_disabled_response,
        linkedin_browser_automation_enabled,
    )
    from services.workspace_write_guard import (
        assert_ats_linkedin_caller_allowed,
        enforce_user_workspace_on_apply_jobs,
    )

    assert_ats_linkedin_caller_allowed(user)

    if not linkedin_browser_automation_enabled():
        return JSONResponse(status_code=403, content=linkedin_browser_automation_disabled_response())
    try:
        raw = body.model_dump()
    except AttributeError:
        raw = body.dict()
    jobs = raw.get("jobs") or []
    enforce_user_workspace_on_apply_jobs(
        user=user,
        jobs=jobs,
        default_workspace_id=raw.get("workspace_id"),
    )
    return apply_to_jobs_payload(
        jobs,
        dry_run=True,
        shadow_mode=raw.get("shadow_mode", False),
        rate_limit_seconds=body.rate_limit_seconds,
        manual_assist=body.manual_assist,
        require_safeguards=body.require_safeguards,
    )


@api_router.post("/ats/analyze-form", tags=["ats"])
def ats_analyze_form(body: AnalyzeFormRequest):
    """
    Static form-flow hints per ATS/board plus platform metadata (same core as MCP ``analyze_form``).
    Does not open a browser.
    """
    from services.ats_form_analysis import run_analyze_form

    return run_analyze_form(job_url=body.job_url.strip(), apply_url=body.apply_url.strip())


@api_router.get("/ats/platform", tags=["ats"])
def ats_describe_platform_get(
    job_url: str = Query("", max_length=2000, description="Job listing URL"),
    apply_url: str = Query("", max_length=2000, description="Apply target URL if different"),
):
    """
    ATS/board metadata: provider labels, v1 auto-submit policy, manual-assist capabilities,
    and a preview of static ``analyze_form`` output (MCP ``describe_ats_platform`` parity).
    """
    from providers.ats.registry import describe_ats_platform

    return {"status": "ok", **describe_ats_platform(job_url=job_url.strip(), apply_url=apply_url.strip())}


@api_router.post(
    "/ats/analyze-form/live",
    tags=["ats"],
    responses={403: {"description": "Live probe disabled (same JSON shape as MCP ``analyze_form_live``)."}},
)
def ats_analyze_form_live(body: AnalyzeFormLiveRequest):
    """
    **Optional** headless Chromium probe: lists visible input/select/textarea metadata (read-only).
    Requires ``ATS_ALLOW_LIVE_FORM_PROBE=1`` and ``playwright`` + ``playwright install chromium``.
    Merges with static ``analyze_form`` payload. Many sites block bots or require login — expect partial data.
    """
    from services.ats_form_analysis import run_analyze_form
    from services.live_form_probe import (
        live_form_probe_disabled_response,
        live_form_probe_enabled,
        probe_apply_page_fields,
    )

    if not live_form_probe_enabled():
        return JSONResponse(status_code=403, content=live_form_probe_disabled_response())
    target = (body.apply_url or body.job_url or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Provide apply_url or job_url for the page to load.")
    live = probe_apply_page_fields(target, max_fields=body.max_fields)
    static = run_analyze_form(job_url=body.job_url.strip(), apply_url=body.apply_url.strip())
    return {"live": live, "static": static}


@api_router.get("/insights", tags=["insights"])
def application_insights(
    user=Depends(get_current_user),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="Same semantics as GET /api/applications?workspace_id=…",
    ),
    include_audit: bool = Query(
        True,
        description="Include tail summary of application_audit.jsonl (same user scope when not demo).",
    ),
    audit_max_lines: int = Query(2500, ge=100, le=20_000),
):
    """Phase 13 — tracker aggregates, optional audit tail, heuristic suggestions."""
    from services.application_insights import build_application_insights

    scope = _tracker_list_scope(user.id)
    wf = _workspace_filter(workspace_id, user)
    return build_application_insights(
        scope,
        workspace_id=wf,
        include_audit=include_audit,
        audit_max_lines=audit_max_lines,
    )


@api_router.get("/admin/insights", tags=["admin"])
def admin_application_insights(
    admin=Depends(require_admin),
    include_audit: bool = Query(True),
    audit_max_lines: int = Query(5000, ge=100, le=50_000),
):
    """All tracker rows + full audit tail (not filtered by user)."""
    from services.application_insights import build_application_insights

    return build_application_insights(
        None,
        include_audit=include_audit,
        audit_max_lines=audit_max_lines,
    )


@api_router.get("/applications/by-job/{job_id}", tags=["applications"])
def get_application_by_job_id(
    job_id: str,
    user=Depends(get_current_user),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="Same semantics as GET /api/applications?workspace_id=…",
    ),
    signed_urls: bool = Query(
        False,
        description="If true, include short-lived S3 presigned URLs (requires ARTIFACTS_S3_BUCKET + boto3).",
    ),
):
    """
    One tracker row by external job_id, scoped to the authenticated user.
    demo-user sees all rows (same as list). Includes Phase 3.2.3 artifact metadata.
    """
    from services.application_tracker import get_application_row_by_job_id
    from services.artifact_metadata import build_artifact_metadata

    scope = _tracker_list_scope(user.id)
    wf = _workspace_filter(workspace_id, user)
    row = get_application_row_by_job_id(job_id, for_user_id=scope, workspace_id=wf)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    artifacts = _artifacts_with_optional_signed_urls(
        build_artifact_metadata(row),
        signed_urls,
    )
    return {"application": row, "artifacts": artifacts}


@api_router.get("/admin/applications/by-job/{job_id}", tags=["admin"])
def admin_get_application_by_job_id(
    job_id: str,
    admin=Depends(require_admin),
    signed_urls: bool = Query(
        False,
        description="If true, include short-lived S3 presigned URLs when S3 manifest is present.",
    ),
):
    """Resolve tracker row by job_id across all users (admin)."""
    from services.application_tracker import get_application_row_by_job_id
    from services.artifact_metadata import build_artifact_metadata

    row = get_application_row_by_job_id(job_id, for_user_id=None)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    artifacts = _artifacts_with_optional_signed_urls(
        build_artifact_metadata(row),
        signed_urls,
    )
    return {"application": row, "artifacts": artifacts}


@api_router.get("/admin/applications", tags=["admin"])
def admin_list_applications(
    admin=Depends(require_admin),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="When non-empty, only rows with this workspace_id.",
    ),
):
    """
    List all tracker rows (no user_id filter). Phase 3.1.4 — requires admin role.
    """
    from services.application_tracker import load_applications

    wf = _admin_workspace_filter(workspace_id, admin)
    df = load_applications(for_user_id=None, workspace_id=wf)
    records = df.fillna("").to_dict(orient="records")
    return {"count": len(records), "items": records[:2000], "scoped": False}


@api_router.get("/admin/tracker-analytics/summary", tags=["admin"])
def admin_tracker_analytics_summary(
    admin=Depends(require_admin),
    user_id: Optional[str] = Query(
        None,
        max_length=240,
        description="When set, restrict analytics to this tracker user_id.",
    ),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="When non-empty, only rows with this workspace_id.",
    ),
    max_rows: int = Query(
        50_000,
        ge=1,
        le=200_000,
        description="Cap rows analyzed after load (large multi-tenant trackers).",
    ),
):
    """
    Phase 4 — aggregated tracker counts: status, submission_status, recruiter_response,
    cross-tabs for response rates by status, applied rows by recruiter_response, and
    ``by_applied_iso_week`` (UTC ISO week of ``applied_at``), parseable timestamp count,
    ``by_job_state`` when the indexed ``job_state`` column is present, and
    ``shadow_metrics_v0`` (Phase 2: shadow_positive_rate, runner_issue_proxy_*, closed_loop_hints_v0, policy_reference, FP/FN definitions).
    """
    from services.application_tracker import load_applications
    from services.tracker_analytics import build_admin_tracker_analytics_summary

    uid = user_id.strip() if user_id else None
    wf = _admin_workspace_filter(workspace_id, admin)
    df = load_applications(for_user_id=uid, workspace_id=wf)
    total_matching = len(df)
    truncated = total_matching > max_rows
    if truncated:
        df = df.head(max_rows)
    summary = build_admin_tracker_analytics_summary(df)
    summary.pop("row_count", None)
    return {
        "user_id_filter": uid,
        "workspace_id_filter": wf,
        "rows_analyzed": int(len(df)),
        "total_matching_before_cap": total_matching,
        "truncated": truncated,
        **summary,
    }


@api_router.get("/admin/metrics/summary", tags=["admin"])
def admin_metrics_summary(admin=Depends(require_admin)):
    """
    Celery aggregate counters from Redis (Phase 3.6). Enable workers with CELERY_METRICS_REDIS=1.
    """
    from services.metrics_redis import get_celery_metrics_summary

    return get_celery_metrics_summary()


@api_router.get("/admin/applications/export", tags=["admin"])
def admin_export_tracker_for_user(
    admin=Depends(require_admin),
    user_id: str = Query(..., min_length=1, max_length=240, description="Tracker user_id to export"),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="When non-empty, further restrict export to this workspace_id.",
    ),
    limit: int = Query(5000, ge=1, le=20000),
):
    """
    Phase 4.4.2 — JSON export of tracker rows for one user (contains PII / job text).

    Requires admin. Use for data-access requests; treat the response as sensitive.
    """
    from services.application_tracker import load_applications

    uid = user_id.strip()
    wf = _admin_workspace_filter(workspace_id, admin)
    df = load_applications(for_user_id=uid, workspace_id=wf)
    total = len(df)
    df = df.head(limit)
    records = df.fillna("").to_dict(orient="records")
    return {
        "user_id": uid,
        "workspace_id_filter": wf,
        "count": len(records),
        "total_matching": total,
        "truncated": total > limit,
        "items": records,
    }


@api_router.delete("/admin/applications/by-user", tags=["admin"])
def admin_delete_tracker_rows_for_user(
    admin=Depends(require_admin),
    user_id: str = Query(..., min_length=1, max_length=240),
    confirm_user_id: str = Query(
        ...,
        min_length=1,
        max_length=240,
        description="Must match user_id exactly (double-check before destructive delete)",
    ),
):
    """
    Phase 4.4.2 — delete all tracker rows for ``user_id``. Also removes matching
    ``job_idempotency`` rows when ``IDEMPOTENCY_USE_DB=1``.

    Irreversible. ``confirm_user_id`` must equal ``user_id``.
    """
    uid = user_id.strip()
    if confirm_user_id.strip() != uid:
        raise HTTPException(
            status_code=400,
            detail="confirm_user_id must match user_id exactly",
        )
    from services.application_tracker import delete_applications_for_user

    deleted = delete_applications_for_user(uid)
    idem_deleted = 0
    try:
        from services.idempotency_db import delete_idempotency_rows_for_user

        idem_deleted = delete_idempotency_rows_for_user(uid)
    except Exception:
        pass
    return {"deleted": deleted, "idempotency_deleted": idem_deleted, "user_id": uid}


@api_router.get("/admin/celery/inspect", tags=["admin"])
def admin_celery_inspect(
    admin=Depends(require_admin),
    timeout: Optional[float] = Query(
        None,
        ge=0.5,
        le=30.0,
        description="Broker RPC timeout for inspect (default from CELERY_INSPECT_TIMEOUT or 2s)",
    ),
):
    """
    Phase 4.2.3 — live Celery worker snapshot: ping, active, reserved, scheduled, stats.

    **None** values usually mean no worker replied (workers off, wrong broker, or cold start).
    Disable entirely with ``CELERY_ADMIN_INSPECT=0`` on the API.
    """
    if os.getenv("CELERY_ADMIN_INSPECT", "").strip().lower() in ("0", "false", "no"):
        raise HTTPException(
            status_code=403,
            detail="Admin Celery inspect disabled (CELERY_ADMIN_INSPECT=0).",
        )
    from services.celery_admin_inspect import celery_inspect_snapshot

    return celery_inspect_snapshot(timeout_sec=timeout)


@api_router.get("/admin/apply-runner-metrics", tags=["admin"])
def admin_apply_runner_metrics(admin=Depends(require_admin)):
    """
    Phase 3 — read apply-runner Redis counters (LinkedIn live submit attempt / success / blocked).

    Does not require ``APPLY_RUNNER_METRICS_REDIS=1`` to call; response includes ``enabled``
    and may report Redis connection errors when metrics are off or misconfigured.
    """
    from services.apply_runner_metrics_redis import read_apply_runner_metrics_summary

    return read_apply_runner_metrics_summary()


@api_router.get("/follow-ups", tags=["follow-ups"])
def list_follow_ups(
    user=Depends(get_current_user),
    workspace_id: Optional[str] = Query(
        None,
        max_length=200,
        description="Same semantics as GET /api/applications?workspace_id=…",
    ),
    due_only: bool = Query(True, description="Only rows with follow_up_at <= now (UTC)"),
    include_snoozed: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    sort_by_priority: bool = Query(
        True,
        description="Sort by follow_up_priority_score (ATS, fit, recency, overdue)",
    ),
):
    """Phase 12 — tracker rows with active follow-up, scoped to the authenticated user."""
    from services.follow_up_service import list_follow_ups as _list

    scope = _tracker_list_scope(user.id)
    wf = _workspace_filter(workspace_id, user)
    items = _list(
        scope,
        workspace_id=wf,
        due_only=due_only,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    return {"count": len(items), "items": items}


@api_router.get("/follow-ups/digest", tags=["follow-ups"])
def follow_ups_digest(
    user=Depends(get_current_user),
    workspace_id: Optional[str] = Query(None, max_length=200),
    include_snoozed: bool = Query(True),
    limit: int = Query(30, ge=1, le=100),
    sort_by_priority: bool = Query(True),
):
    """Plain-text + structured digest of due follow-ups (copy into email / reminders)."""
    from services.follow_up_service import format_follow_up_digest, list_follow_ups as _list

    scope = _tracker_list_scope(user.id)
    wf = _workspace_filter(workspace_id, user)
    items = _list(
        scope,
        workspace_id=wf,
        due_only=True,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    text = format_follow_up_digest(items)
    return {"count": len(items), "items": items, "text": text}


@api_router.get("/admin/follow-ups/digest", tags=["admin"])
def admin_follow_ups_digest(
    admin=Depends(require_admin),
    include_snoozed: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    sort_by_priority: bool = Query(True),
):
    from services.follow_up_service import format_follow_up_digest, list_follow_ups as _list

    items = _list(
        None,
        due_only=True,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    text = format_follow_up_digest(items, title="Follow-up reminders (all users)")
    return {"count": len(items), "items": items, "text": text}


@api_router.get("/admin/follow-ups", tags=["admin"])
def admin_list_follow_ups(
    admin=Depends(require_admin),
    due_only: bool = Query(True),
    include_snoozed: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    sort_by_priority: bool = Query(True),
):
    """All users' follow-up queue."""
    from services.follow_up_service import list_follow_ups as _list

    items = _list(
        None,
        due_only=due_only,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    return {"count": len(items), "items": items}


@api_router.patch("/applications/{application_id}/follow-up", tags=["applications"])
def patch_application_follow_up(
    application_id: str,
    body: FollowUpPatch,
    user=Depends(get_current_user),
):
    """Update follow-up fields on a tracker row (by row ``id``)."""
    from services.application_tracker import update_follow_up_for_row

    patch = _follow_up_updates_from_body(body)
    if not patch:
        raise HTTPException(400, detail="No fields to update")
    scope = _tracker_list_scope(user.id)
    ok = update_follow_up_for_row(application_id, scope, patch)
    if not ok:
        raise HTTPException(404, detail="Application not found or not owned by this user")
    return {"ok": True, "id": application_id}


@api_router.patch("/admin/applications/{application_id}/follow-up", tags=["admin"])
def admin_patch_application_follow_up(
    application_id: str,
    body: FollowUpPatch,
    admin=Depends(require_admin),
):
    from services.application_tracker import update_follow_up_for_row

    patch = _follow_up_updates_from_body(body)
    if not patch:
        raise HTTPException(400, detail="No fields to update")
    ok = update_follow_up_for_row(application_id, None, patch)
    if not ok:
        raise HTTPException(404, detail="Application not found")
    return {"ok": True, "id": application_id}


@api_router.patch("/applications/{application_id}/pipeline", tags=["applications"])
def patch_application_pipeline(
    application_id: str,
    body: PipelinePatch,
    user=Depends(get_current_user),
):
    """Update interview_stage / offer_outcome on a tracker row (by row ``id``)."""
    from services.application_tracker import update_pipeline_for_row

    patch = _pipeline_updates_from_body(body)
    if not patch:
        raise HTTPException(400, detail="No fields to update")
    scope = _tracker_list_scope(user.id)
    ok = update_pipeline_for_row(application_id, scope, patch)
    if not ok:
        raise HTTPException(404, detail="Application not found or not owned by this user")
    return {"ok": True, "id": application_id}


@api_router.patch("/admin/applications/{application_id}/pipeline", tags=["admin"])
def admin_patch_application_pipeline(
    application_id: str,
    body: PipelinePatch,
    admin=Depends(require_admin),
):
    from services.application_tracker import update_pipeline_for_row

    patch = _pipeline_updates_from_body(body)
    if not patch:
        raise HTTPException(400, detail="No fields to update")
    ok = update_pipeline_for_row(application_id, None, patch)
    if not ok:
        raise HTTPException(404, detail="Application not found")
    return {"ok": True, "id": application_id}


@api_router.get("/jobs/{job_id}", tags=["jobs"])
def get_job_status(
    job_id: str,
    user=Depends(get_current_user),
    include_result: bool = Query(
        False,
        description="When true and task finished, include Celery result payload.",
    ),
    include_task_state: bool = Query(
        False,
        description="When true, include last task_state_store snapshot (file / DB / S3 per TASK_STATE_BACKEND).",
    ),
):
    """Job status (Celery). ``run_id`` equals ``job_id`` (pipeline correlation, Phase 4.5.2)."""
    try:
        from .tasks import get_job_public_view

        return get_job_public_view(
            job_id,
            include_result=include_result,
            include_task_state=include_task_state,
        )
    except Exception as e:
        raise HTTPException(500, str(e)[:200])


def _api_v1_duplicate_enabled() -> bool:
    return (os.getenv("API_V1_DUPLICATE_ROUTES", "1").lower() in ("1", "true", "yes"))


app.include_router(api_router, prefix="/api")
if _api_v1_duplicate_enabled():
    app.include_router(api_router, prefix="/api/v1")


def _build_openapi_schema():
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    components = openapi_schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "JWT: HS256 with `JWT_SECRET`, or RS256/ES* via `JWT_JWKS_URL` or `JWT_ISSUER` discovery; "
            "optional `JWT_AUDIENCE`. Claims `sub` or `user_id`; optional roles for admin."
        ),
    }
    schemes["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Must match server `API_KEY` when that env var is set.",
    }
    m2m_header = (os.getenv("M2M_API_KEY_HEADER") or "X-M2M-API-Key").strip()
    schemes["M2MApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": m2m_header,
        "description": (
            "Optional worker / automation key when `M2M_API_KEY` is set "
            "(default header name `X-M2M-API-Key`; override with `M2M_API_KEY_HEADER`). "
            "User id from `M2M_USER_ID` (default `m2m-service`); roles from `M2M_SERVICE_ROLES`."
        ),
    }
    optional_auth = [{}, {"BearerAuth": []}, {"ApiKeyAuth": []}, {"M2MApiKeyAuth": []}]
    for _path, path_item in openapi_schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            op["security"] = optional_auth
    return openapi_schema


def custom_openapi():
    if app.openapi_schema is None:
        app.openapi_schema = _build_openapi_schema()
    return app.openapi_schema


app.openapi = custom_openapi

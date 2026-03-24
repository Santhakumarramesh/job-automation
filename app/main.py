import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .auth import get_current_user, require_admin
from .tasks import enqueue_job

_OPENAPI_TAGS = [
    {"name": "service", "description": "Process health and root."},
    {"name": "jobs", "description": "Enqueue and inspect Celery background jobs."},
    {"name": "applications", "description": "Application tracker rows for the authenticated user."},
    {"name": "insights", "description": "Tracker aggregates, audit hints, and answerer rollups."},
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
        "Authenticate with **X-API-Key**, **Authorization: Bearer** (JWT when `JWT_SECRET` is set), "
        "or the open **demo-user** when `API_KEY` is unset (development only)."
    ),
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)
app.add_middleware(_CorrelationMiddleware)

from services.prometheus_setup import install_prometheus
from services.rate_limit import install_rate_limit_middleware

install_prometheus(app)
install_rate_limit_middleware(app)

class JobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)
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


@app.post("/api/jobs", status_code=202, tags=["jobs"])
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
            extra={"name": req.name, "user_id": user.id},
        )
    except Exception:
        pass
    return {"job_id": job_id, "status": "accepted"}


@app.get("/api/applications", tags=["applications"])
def list_applications(user=Depends(get_current_user)):
    """List tracker rows for the authenticated user (all rows for demo-user)."""
    from services.application_tracker import load_applications

    scope = _tracker_list_scope(user.id)
    df = load_applications(for_user_id=scope)
    records = df.fillna("").to_dict(orient="records")
    return {"count": len(records), "items": records[:500]}


@app.get("/api/insights", tags=["insights"])
def application_insights(
    user=Depends(get_current_user),
    include_audit: bool = Query(
        True,
        description="Include tail summary of application_audit.jsonl (same user scope when not demo).",
    ),
    audit_max_lines: int = Query(2500, ge=100, le=20_000),
):
    """Phase 13 — tracker aggregates, optional audit tail, heuristic suggestions."""
    from services.application_insights import build_application_insights

    scope = _tracker_list_scope(user.id)
    return build_application_insights(
        scope,
        include_audit=include_audit,
        audit_max_lines=audit_max_lines,
    )


@app.get("/api/admin/insights", tags=["admin"])
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


@app.get("/api/applications/by-job/{job_id}", tags=["applications"])
def get_application_by_job_id(
    job_id: str,
    user=Depends(get_current_user),
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
    row = get_application_row_by_job_id(job_id, for_user_id=scope)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    artifacts = _artifacts_with_optional_signed_urls(
        build_artifact_metadata(row),
        signed_urls,
    )
    return {"application": row, "artifacts": artifacts}


@app.get("/api/admin/applications/by-job/{job_id}", tags=["admin"])
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


@app.get("/api/admin/applications", tags=["admin"])
def admin_list_applications(admin=Depends(require_admin)):
    """
    List all tracker rows (no user_id filter). Phase 3.1.4 — requires admin role.
    """
    from services.application_tracker import load_applications

    df = load_applications(for_user_id=None)
    records = df.fillna("").to_dict(orient="records")
    return {"count": len(records), "items": records[:2000], "scoped": False}


@app.get("/api/admin/metrics/summary", tags=["admin"])
def admin_metrics_summary(admin=Depends(require_admin)):
    """
    Celery aggregate counters from Redis (Phase 3.6). Enable workers with CELERY_METRICS_REDIS=1.
    """
    from services.metrics_redis import get_celery_metrics_summary

    return get_celery_metrics_summary()


@app.get("/api/follow-ups", tags=["follow-ups"])
def list_follow_ups(
    user=Depends(get_current_user),
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
    items = _list(
        scope,
        due_only=due_only,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    return {"count": len(items), "items": items}


@app.get("/api/follow-ups/digest", tags=["follow-ups"])
def follow_ups_digest(
    user=Depends(get_current_user),
    include_snoozed: bool = Query(True),
    limit: int = Query(30, ge=1, le=100),
    sort_by_priority: bool = Query(True),
):
    """Plain-text + structured digest of due follow-ups (copy into email / reminders)."""
    from services.follow_up_service import format_follow_up_digest, list_follow_ups as _list

    scope = _tracker_list_scope(user.id)
    items = _list(
        scope,
        due_only=True,
        include_snoozed=include_snoozed,
        limit=limit,
        sort_by_priority=sort_by_priority,
    )
    text = format_follow_up_digest(items)
    return {"count": len(items), "items": items, "text": text}


@app.get("/api/admin/follow-ups/digest", tags=["admin"])
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


@app.get("/api/admin/follow-ups", tags=["admin"])
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


@app.patch("/api/applications/{application_id}/follow-up", tags=["applications"])
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


@app.patch("/api/admin/applications/{application_id}/follow-up", tags=["admin"])
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


@app.patch("/api/applications/{application_id}/pipeline", tags=["applications"])
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


@app.patch("/api/admin/applications/{application_id}/pipeline", tags=["admin"])
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


@app.get("/api/jobs/{job_id}", tags=["jobs"])
def get_job_status(
    job_id: str,
    user=Depends(get_current_user),
    include_result: bool = Query(
        False,
        description="When true and task finished, include Celery result payload.",
    ),
    include_task_state: bool = Query(
        False,
        description="When true, include last filesystem snapshot from services/task_state_store.",
    ),
):
    """Job status (Celery). Optional result + trimmed task_state snapshot (Phase 3.3)."""
    try:
        from .tasks import get_job_public_view

        return get_job_public_view(
            job_id,
            include_result=include_result,
            include_task_state=include_task_state,
        )
    except Exception as e:
        raise HTTPException(500, str(e)[:200])


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
        "description": "JWT when `JWT_SECRET` is set (`sub` or `user_id`; optional role claims for admin).",
    }
    schemes["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Must match server `API_KEY` when that env var is set.",
    }
    optional_auth = [{}, {"BearerAuth": []}, {"ApiKeyAuth": []}]
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

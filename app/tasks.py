import os
import time
import uuid
from typing import Any, Dict, Optional

from celery import Celery

from agents.state import AgentState

# Get Redis URLs from env or use defaults
REDIS_BROKER = os.getenv("REDIS_BROKER", "redis://localhost:6379/0")
REDIS_BACKEND = os.getenv("REDIS_BACKEND", "redis://localhost:6379/1")

_MAX_RETRIES = int(os.getenv("CELERY_TASK_MAX_RETRIES", "3"))


def _stamp_run_id_on_artifacts_manifest(state: Dict[str, Any], run_id: str) -> None:
    """Phase 4.5.2 — top-level ``run_id`` on tracker JSON (same as Celery task id)."""
    import json

    if not run_id:
        return
    raw = state.get("artifacts_manifest")
    d: Dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            d = {}
    elif isinstance(raw, dict):
        d = dict(raw)
    d["run_id"] = run_id
    try:
        state["artifacts_manifest"] = json.dumps(d, default=str)[:8000]
    except Exception:
        state["artifacts_manifest"] = json.dumps({"run_id": run_id})[:8000]


def _transient_exc(exc: BaseException) -> bool:
    """Phase 3.3.4 — coarse transient vs permanent hint for workers / ops."""
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    try:
        import urllib3.exceptions as u3

        if isinstance(exc, (u3.HTTPError, u3.TimeoutError, u3.ConnectionError)):
            return True
    except ImportError:
        pass
    try:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
    except ImportError:
        pass
    return False


def _save_fail(task_id: str, message: str, failure_class: str, retries: int) -> None:
    try:
        from services.task_state_store import save_task_failure

        save_task_failure(task_id, message, failure_class, retries=retries)
    except Exception:
        pass


def _celery_task_started(task_id: str, job_name: str, user_id: str) -> None:
    try:
        from services.observability import audit_log

        audit_log(
            "celery_task_started",
            job_id=task_id,
            status="started",
            extra={"job_name": job_name, "user_id": user_id, "run_id": task_id},
        )
    except Exception:
        pass


def _celery_task_finished(
    task_id: str,
    job_name: str,
    user_id: str,
    started_monotonic: float,
    outcome: str,
    failure_class: str = "",
) -> None:
    """Phase 3.6 — Redis counters + audit (skip on intermediate retry attempts)."""
    duration = max(0.0, time.monotonic() - started_monotonic)
    try:
        from services.metrics_redis import incr_celery_task

        incr_celery_task(
            outcome=outcome,
            failure_class=failure_class or "",
            duration_seconds=duration,
        )
    except Exception:
        pass
    try:
        from services.observability import audit_log

        audit_log(
            "celery_task_finished",
            job_id=task_id,
            status=outcome,
            extra={
                "job_name": job_name,
                "user_id": user_id,
                "run_id": task_id,
                "duration_sec": round(duration, 4),
                "failure_class": failure_class or None,
            },
        )
    except Exception:
        pass
    try:
        import logging

        logging.getLogger("career_co_pilot.celery").info(
            "celery_task %s outcome=%s duration_sec=%.3f task_id=%s",
            job_name,
            outcome,
            duration,
            task_id,
        )
    except Exception:
        pass


celery = Celery("career_co_pilot_pro", broker=REDIS_BROKER, backend=REDIS_BACKEND)


@celery.task(
    bind=True,
    acks_late=True,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=_MAX_RETRIES,
)
def run_job(self, job_name: str, payload: Dict[str, Any], user_id: str):
    """
    Background task: LangGraph agent pipeline (Phase 3.3.1) or legacy sequential mode.

    Set CELERY_USE_LANGGRAPH=0 to use the old inlined pipeline.
    """
    task_id = getattr(self.request, "id", "") or ""
    t0 = time.monotonic()
    print(f"🚀 Starting job: {job_name} for user: {user_id} task_id={task_id}")
    _celery_task_started(task_id, job_name, user_id)

    state: AgentState = dict(payload) if isinstance(payload, dict) else payload
    if isinstance(state, dict):
        state.setdefault("user_id", user_id)
        if task_id:
            state.setdefault("run_id", task_id)
            _stamp_run_id_on_artifacts_manifest(state, task_id)

    use_graph = os.getenv("CELERY_USE_LANGGRAPH", "1").lower() not in ("0", "false", "no")

    try:
        if use_graph:
            from agents.celery_workflow import get_celery_job_graph
            from services.task_state_store import save_task_snapshot

            graph = get_celery_job_graph()
            final_state: Dict[str, Any] = dict(state)
            for update in graph.stream(state, stream_mode="values"):
                final_state = dict(update)
                save_task_snapshot(task_id, final_state, step="langgraph_stream")
            state = final_state
        else:
            state = _run_sequential_pipeline(state)

        if not state.get("is_eligible", True):
            from services.task_state_store import save_task_snapshot

            save_task_snapshot(task_id, state, step="rejected")
            _celery_task_finished(task_id, job_name, user_id, t0, "rejected", "")
            return {
                "status": "rejected",
                "run_id": task_id,
                "reason": state.get("eligibility_reason", "Ineligible"),
            }

        # Optional S3 upload (Phase 3.4)
        try:
            from services.object_storage import merge_manifest_json, upload_artifacts_from_state

            frag = upload_artifacts_from_state(state)
            if frag:
                state["artifacts_manifest"] = merge_manifest_json(
                    state.get("artifacts_manifest"),
                    frag,
                )
        except Exception as ex:
            print(f"⚠️ Object storage upload skipped: {ex}")

        from services.task_state_store import save_task_snapshot

        save_task_snapshot(task_id, state, step="completed")
        _celery_task_finished(task_id, job_name, user_id, t0, "success", "")
        return {
            "status": "success",
            "job_name": job_name,
            "run_id": task_id,
            "final_pdf_path": state.get("final_pdf_path"),
            "cover_letter_pdf_path": state.get("cover_letter_pdf_path"),
            "artifacts_manifest": state.get("artifacts_manifest"),
        }
    except (ConnectionError, TimeoutError, OSError) as e:
        if self.request.retries < (self.max_retries or _MAX_RETRIES):
            raise self.retry(exc=e, countdown=min(600, 2 ** (self.request.retries + 2)))
        print(f"❌ Job error (network, exhausted retries): {e}")
        _save_fail(task_id, str(e), "transient", self.request.retries)
        _celery_task_finished(task_id, job_name, user_id, t0, "error", "transient")
        return {
            "status": "error",
            "run_id": task_id,
            "failure_class": "transient",
            "message": str(e)[:2000],
        }
    except Exception as e:
        print(f"❌ Job error: {e}")
        fclass = "transient" if _transient_exc(e) else "permanent"
        _save_fail(task_id, str(e), fclass, self.request.retries)
        if fclass == "transient" and self.request.retries < (self.max_retries or _MAX_RETRIES):
            raise self.retry(exc=e, countdown=min(600, 2 ** (self.request.retries + 2)))
        _celery_task_finished(task_id, job_name, user_id, t0, "error", fclass)
        return {
            "status": "error",
            "run_id": task_id,
            "failure_class": fclass,
            "message": str(e)[:2000],
        }


def _run_sequential_pipeline(state: AgentState) -> AgentState:
    """Legacy orchestration (pre–LangGraph Celery)."""
    from agents.cover_letter_generator import generate_cover_letter
    from agents.file_manager import save_documents
    from agents.humanize_cover_letter import humanize_cover_letter
    from agents.humanize_resume import humanize_resume
    from agents.intelligent_project_generator import intelligent_project_generator
    from agents.job_analyzer import analyze_job_description
    from agents.job_guard import guard_job_quality
    from agents.resume_editor import tailor_resume

    guard_res = guard_job_quality(state)
    state.update(guard_res)
    if not state.get("is_eligible", True):
        return state

    state.update(analyze_job_description(state))
    state.update(tailor_resume(state))
    state.update(humanize_resume(state))
    state.update(intelligent_project_generator(state))
    state.update(generate_cover_letter(state))
    state.update(humanize_cover_letter(state))
    state.update(save_documents(state))
    return state


def enqueue_job(
    name: str,
    payload: Dict[str, Any],
    user_id: str,
    *,
    idempotency_key: Optional[str] = None,
) -> str:
    """Enqueue a new job and return its UUID (Celery task id).

    Phase 4.5.2: ``run_id`` in the worker payload is always the Celery task id so tracker,
    audit JSONL, and ``GET /api/jobs/{id}`` share one correlation id (including idempotent replays).
    """
    base = dict(payload) if isinstance(payload, dict) else {}
    if idempotency_key:
        from services.idempotency_keys import (
            resolve_idempotent_enqueue,
            store_idempotent_job,
            uses_db_for_idempotency,
        )

        job_id, do_enqueue = resolve_idempotent_enqueue(user_id, idempotency_key)
        if not do_enqueue:
            return job_id
    else:
        job_id = str(uuid.uuid4())

    send_payload = dict(base)
    send_payload["run_id"] = job_id
    run_job.apply_async(args=(name, send_payload, user_id), task_id=job_id)

    if idempotency_key and not uses_db_for_idempotency():
        from services.idempotency_keys import store_idempotent_job

        store_idempotent_job(user_id, idempotency_key, job_id)
    return job_id


def get_job_status(job_id: str) -> str:
    """Celery task state: PENDING, STARTED, SUCCESS, FAILURE, RETRY, etc."""
    try:
        result = run_job.AsyncResult(job_id)
        return result.status or "PENDING"
    except Exception:
        return "UNKNOWN"


def get_job_public_view(
    job_id: str,
    *,
    include_result: bool = False,
    include_task_state: bool = False,
) -> Dict[str, Any]:
    """API-friendly job status + optional result / filesystem snapshot."""
    out: Dict[str, Any] = {"job_id": job_id, "run_id": job_id, "status": get_job_status(job_id)}
    try:
        r = run_job.AsyncResult(job_id)
        if include_result and r.ready():
            try:
                out["result"] = r.result
            except Exception as e:
                out["result_error"] = str(e)[:500]
        if r.failed():
            try:
                out["failure_hint"] = str(r.result)[:2000]
            except Exception:
                out["failure_hint"] = "task failed"
    except Exception as e:
        out["error"] = str(e)[:200]

    if include_task_state:
        try:
            from services.task_state_store import load_task_snapshot

            snap = load_task_snapshot(job_id)
            if snap:
                out["task_state"] = snap
        except Exception:
            pass
    return out

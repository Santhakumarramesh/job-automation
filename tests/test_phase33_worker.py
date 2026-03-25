"""Phase 3.3 — LangGraph Celery workflow, idempotency, task state store."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from agents.celery_workflow import build_celery_job_graph


def test_celery_job_graph_compiles():
    g = build_celery_job_graph()
    assert g is not None


def test_task_state_trim_truncates_long_fields():
    from services.task_state_store import trim_state_for_storage

    s = {"job_description": "x" * 10000, "user_id": "u1"}
    t = trim_state_for_storage(s)
    assert len(t["job_description"]) < len(s["job_description"])
    assert "truncated" in t["job_description"] or "…" in t["job_description"]
    assert t["user_id"] == "u1"


def test_task_state_roundtrip_file():
    from services import task_state_store as tss

    with tempfile.TemporaryDirectory() as td:
        os.environ["TASK_STATE_DIR"] = td
        try:
            tss.save_task_snapshot("task-abc", {"user_id": "x", "job_description": "short"})
            loaded = tss.load_task_snapshot("task-abc")
            assert loaded is not None
            assert loaded["state"]["user_id"] == "x"
        finally:
            os.environ.pop("TASK_STATE_DIR", None)


def test_task_state_roundtrip_db_sqlite():
    from services import task_state_store as tss

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        os.environ["DATABASE_URL"] = f"sqlite:///{path}"
        os.environ["TASK_STATE_BACKEND"] = "db"
        tss.save_task_snapshot("task-db-1", {"user_id": "db-user", "job_description": "j"})
        loaded = tss.load_task_snapshot("task-db-1")
        assert loaded is not None
        assert loaded["state"]["user_id"] == "db-user"
    finally:
        os.environ.pop("TASK_STATE_BACKEND", None)
        os.environ.pop("DATABASE_URL", None)
        try:
            os.unlink(path)
        except OSError:
            pass


def test_task_state_roundtrip_s3_mock():
    from unittest.mock import MagicMock

    from services import task_state_store as tss

    stored: dict = {}

    def put_object(**kwargs):
        stored["key"] = kwargs["Key"]
        stored["body"] = kwargs["Body"]

    def get_object(Bucket, Key):
        assert Key == stored["key"]
        body = MagicMock()
        body.read.return_value = stored["body"]
        return {"Body": body}

    mock_cli = MagicMock()
    mock_cli.put_object.side_effect = put_object
    mock_cli.get_object.side_effect = get_object

    try:
        os.environ["TASK_STATE_BACKEND"] = "s3"
        os.environ["TASK_STATE_S3_BUCKET"] = "test-bucket"
        with patch.object(tss, "_s3_client", return_value=mock_cli):
            tss.save_task_snapshot("celery-task-s3", {"role": "engineer"})
            out = tss.load_task_snapshot("celery-task-s3")
        assert out is not None
        assert out["state"]["role"] == "engineer"
        mock_cli.put_object.assert_called_once()
        mock_cli.get_object.assert_called_once()
    finally:
        os.environ.pop("TASK_STATE_BACKEND", None)
        os.environ.pop("TASK_STATE_S3_BUCKET", None)


def test_idempotency_lookup_within_ttl():
    from services import idempotency_keys as ik

    with tempfile.TemporaryDirectory() as td:
        os.environ["IDEMPOTENCY_DIR"] = td
        os.environ["IDEMPOTENCY_TTL_HOURS"] = "48"
        try:
            assert ik.lookup_idempotent_job("alice", "apply-1") is None
            ik.store_idempotent_job("alice", "apply-1", "job-uuid-1")
            assert ik.lookup_idempotent_job("alice", "apply-1") == "job-uuid-1"
            assert ik.lookup_idempotent_job("bob", "apply-1") is None
        finally:
            os.environ.pop("IDEMPOTENCY_DIR", None)
            os.environ.pop("IDEMPOTENCY_TTL_HOURS", None)


def test_get_job_public_view_success():
    pytest.importorskip("celery")
    from app.tasks import get_job_public_view

    mock_r = MagicMock()
    mock_r.status = "SUCCESS"
    mock_r.ready.return_value = True
    mock_r.result = {"status": "success", "final_pdf_path": "/tmp/a.pdf"}
    mock_r.failed.return_value = False

    with patch("app.tasks.run_job.AsyncResult", return_value=mock_r):
        out = get_job_public_view("jid-1", include_result=True)
    assert out["job_id"] == "jid-1"
    assert out["run_id"] == "jid-1"
    assert out["status"] == "SUCCESS"
    assert out["result"]["status"] == "success"


def test_enqueue_idempotency_returns_same_id():
    pytest.importorskip("celery")
    from app.tasks import enqueue_job

    with tempfile.TemporaryDirectory() as td:
        os.environ["IDEMPOTENCY_DIR"] = td
        try:
            with patch("app.tasks.run_job.apply_async") as mock_apply:
                mock_apply.return_value = MagicMock()
                j1 = enqueue_job("n", {}, "u1", idempotency_key="k1")
                j2 = enqueue_job("n", {}, "u1", idempotency_key="k1")
                assert j1 == j2
                assert mock_apply.call_count == 1
                call = mock_apply.call_args
                args_tuple = call.kwargs.get("args") if call.kwargs else call[0]
                send = args_tuple[1]
                assert send["run_id"] == j1
        finally:
            os.environ.pop("IDEMPOTENCY_DIR", None)

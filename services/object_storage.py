"""
Phase 3.4 — optional S3 object storage for tracker artifacts (resumes, cover letters).

Env:
  ARTIFACTS_S3_BUCKET   — if set, uploads are enabled (requires boto3 + AWS credentials)
  ARTIFACTS_S3_PREFIX   — key prefix, default "artifacts"
  AWS_REGION / AWS_DEFAULT_REGION — default us-east-1
  ARTIFACTS_PRESIGN_EXPIRES — default seconds for API presigned URLs (default 3600)
  ARTIFACTS_S3_SSE      — optional "AES256" for server-side encryption on upload

manifest entries written by upload_artifacts_from_state:
  { "resume": {"bucket": "...", "key": "..."}, "cover_letter": {...}, "screenshots": [...] }

GCS is not implemented here; use S3-compatible endpoints (MinIO, etc.) via AWS SDK if needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ManifestEntry = Dict[str, str]
ArtifactManifest = Dict[str, Union[ManifestEntry, List[ManifestEntry]]]


def is_object_storage_configured() -> bool:
    return bool(os.getenv("ARTIFACTS_S3_BUCKET", "").strip())


def _s3_client():
    import boto3

    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    ).strip()
    return boto3.client("s3", region_name=region)


def _safe_segment(s: str, max_len: int = 180) -> str:
    raw = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(s).strip())[:max_len]
    return raw or "anon"


def _upload_one(local_path: str, object_key: str) -> Optional[ManifestEntry]:
    bucket = os.getenv("ARTIFACTS_S3_BUCKET", "").strip()
    if not bucket or not local_path:
        return None
    path = Path(local_path)
    if not path.is_file():
        return None

    prefix = (os.getenv("ARTIFACTS_S3_PREFIX") or "artifacts").strip().strip("/")
    full_key = f"{prefix}/{object_key}" if prefix else object_key
    extra: Dict[str, str] = {}
    sse = (os.getenv("ARTIFACTS_S3_SSE") or "").strip()
    if sse:
        extra["ServerSideEncryption"] = sse

    try:
        cli = _s3_client()
    except ImportError:
        return None
    if extra:
        cli.upload_file(str(path), bucket, full_key, ExtraArgs=extra)
    else:
        cli.upload_file(str(path), bucket, full_key)
    return {"bucket": bucket, "key": full_key}


def upload_artifacts_from_state(state: dict) -> ArtifactManifest:
    """
    Upload resume/cover PDFs from graph/Celery state when S3 is configured.
    Returns a manifest fragment to merge into artifacts_manifest (not JSON string).
    """
    out: ArtifactManifest = {}
    if not is_object_storage_configured():
        return out

    uid = _safe_segment(state.get("user_id") or state.get("authenticated_user_id") or "anon")
    jid = _safe_segment(state.get("job_id") or "no-job-id")

    resume = (state.get("final_pdf_path") or "").strip()
    if resume:
        ext = Path(resume).suffix or ".pdf"
        ent = _upload_one(resume, f"{uid}/{jid}/resume{ext}")
        if ent:
            out["resume"] = ent

    cover = (state.get("cover_letter_pdf_path") or "").strip()
    if cover:
        ext = Path(cover).suffix or ".pdf"
        ent = _upload_one(cover, f"{uid}/{jid}/cover_letter{ext}")
        if ent:
            out["cover_letter"] = ent

    shots: List[str] = []
    raw_shots = state.get("screenshot_paths") or state.get("application_screenshot_paths")
    if isinstance(raw_shots, list):
        shots = [str(p).strip() for p in raw_shots if str(p).strip()]
    uploaded_shots: List[ManifestEntry] = []
    for i, p in enumerate(shots):
        ext = Path(p).suffix or ".png"
        ent = _upload_one(p, f"{uid}/{jid}/screenshot_{i}{ext}")
        if ent:
            uploaded_shots.append(ent)
    if uploaded_shots:
        out["screenshots"] = uploaded_shots

    return out


def presign_artifact_manifest(
    manifest: Any,
    expires_seconds: Optional[int] = None,
) -> Dict[str, Union[str, List[str]]]:
    """
    Build presigned GET URLs for manifest values shaped like {"bucket","key"} or lists of those.
    Accepts tracker JSON either flat or nested under ``s3`` (see merge_manifest_json).
    Returns a flat dict suitable for JSON (labels -> url or list of urls).
    """
    if not manifest or not isinstance(manifest, dict):
        return {}

    inner: Dict[str, Any] = manifest
    s3_block = manifest.get("s3")
    if isinstance(s3_block, dict):
        inner = s3_block

    exp = expires_seconds
    if exp is None:
        try:
            exp = int(os.getenv("ARTIFACTS_PRESIGN_EXPIRES", "3600"))
        except ValueError:
            exp = 3600
    exp = max(60, min(exp, 604800))  # 1 min .. 7 days

    try:
        cli = _s3_client()
    except ImportError:
        return {}

    signed: Dict[str, Union[str, List[str]]] = {}

    def _one(entry: ManifestEntry) -> Optional[str]:
        b, k = entry.get("bucket"), entry.get("key")
        if not b or not k:
            return None
        try:
            return cli.generate_presigned_url(
                "get_object",
                Params={"Bucket": b, "Key": k},
                ExpiresIn=exp,
            )
        except Exception:
            return None

    for label, spec in inner.items():
        if isinstance(spec, dict) and "bucket" in spec and "key" in spec:
            u = _one(spec)
            if u:
                signed[label] = u
        elif isinstance(spec, list):
            urls: List[str] = []
            for item in spec:
                if isinstance(item, dict):
                    u = _one(item)
                    if u:
                        urls.append(u)
            if urls:
                signed[label] = urls
    return signed


def merge_manifest_json(existing: Any, fragment: ArtifactManifest) -> str:
    """Merge fragment into existing artifacts_manifest (str or dict); return JSON string for tracker."""
    import json

    base: dict = {}
    if isinstance(existing, str) and existing.strip():
        try:
            base = json.loads(existing)
        except json.JSONDecodeError:
            base = {}
    elif isinstance(existing, dict):
        base = dict(existing)
    if not isinstance(base, dict):
        base = {}
    s3_block = base.get("s3")
    if not isinstance(s3_block, dict):
        s3_block = {}
    for k, v in fragment.items():
        s3_block[k] = v
    base["s3"] = s3_block
    return json.dumps(base)[:8000]

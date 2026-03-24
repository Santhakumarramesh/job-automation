"""
Optional AWS Secrets Manager integration (Phase 3.5).

Set ``AWS_SECRETS_MANAGER_SECRET_ID`` to a secret that stores a **JSON object**
of key/value strings (e.g. ``OPENAI_API_KEY``, ``API_KEY``, ``JWT_SECRET``).
Values are applied to ``os.environ`` only for keys that are **not already set**
(local .env and process env win).

Requires: ``pip install boto3`` (same as ``.[s3]``) and IAM ``secretsmanager:GetSecretValue``.

Optional: ``AWS_SECRETS_MANAGER_REGION`` overrides the boto3 client region.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict


def load_aws_secrets_manager_into_environ() -> list[str]:
    """
    If ``AWS_SECRETS_MANAGER_SECRET_ID`` is set, fetch JSON and merge into os.environ.

    Returns a list of keys that were **set** from the secret (for logging, no values).
    Raises RuntimeError on misconfiguration or AWS errors when the secret id is set.
    """
    secret_id = (os.getenv("AWS_SECRETS_MANAGER_SECRET_ID") or "").strip()
    if not secret_id:
        return []

    try:
        import boto3
    except ImportError as e:
        raise RuntimeError(
            "AWS_SECRETS_MANAGER_SECRET_ID is set but boto3 is not installed. "
            "pip install boto3  (or pip install .[s3])"
        ) from e

    region = (os.getenv("AWS_SECRETS_MANAGER_REGION") or os.getenv("AWS_REGION") or "").strip()
    client_kw: Dict[str, Any] = {}
    if region:
        client_kw["region_name"] = region
    client = boto3.client("secretsmanager", **client_kw)

    try:
        resp = client.get_secret_value(SecretId=secret_id)
    except Exception as e:
        raise RuntimeError(f"Secrets Manager GetSecretValue failed for {secret_id!r}: {e}") from e

    raw = resp.get("SecretString")
    if not raw:
        raise RuntimeError(f"Secret {secret_id!r} has no SecretString (binary secrets not supported).")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Secret {secret_id!r} must be a JSON object of string keys/values.") from e

    if not isinstance(data, dict):
        raise RuntimeError(f"Secret {secret_id!r} JSON root must be an object, not {type(data).__name__}.")

    applied: list[str] = []
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if key in os.environ and (os.environ[key] or "").strip():
            continue
        if value is None:
            continue
        os.environ[key] = str(value)
        applied.append(key)

    return applied

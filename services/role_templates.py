"""
Phase 4 — optional **role templates**: map a single JWT claim (e.g. ``role_template``)
to additional RBAC role strings without stuffing every role into the IdP token.

Env
---

- ``JWT_ROLE_TEMPLATE_MAP`` — JSON object mapping **template name** (lowercased) →
  list of role strings **or** a single comma-separated string.
  Example: ``{"operator_approver":["approver"],"ops":"reader,auditor"}``

Expansion is applied in ``app.auth`` after normal JWT role claims are collected; extra
roles are appended (deduped, lowercased). Unknown template names are ignored.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _template_map_from_env() -> Dict[str, List[str]]:
    raw = (os.getenv("JWT_ROLE_TEMPLATE_MAP") or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(obj, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for k, v in obj.items():
        if k is None:
            continue
        key = str(k).strip().lower()
        if not key:
            continue
        items: List[str] = []
        if isinstance(v, list):
            items = [str(x).strip().lower() for x in v if x is not None and str(x).strip()]
        elif isinstance(v, str):
            items = [x.strip().lower() for x in v.split(",") if x.strip()]
        if items:
            out[key] = items
    return out


def expand_roles_from_template(base_roles: List[str], template: Optional[str]) -> List[str]:
    """Return ``base_roles`` plus any roles defined for ``template`` in ``JWT_ROLE_TEMPLATE_MAP``."""
    t = str(template or "").strip().lower()
    if not t:
        return list(base_roles)
    extra = _template_map_from_env().get(t)
    if not extra:
        return list(base_roles)
    seen = set(base_roles)
    out = list(base_roles)
    for r in extra:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def normalize_role_template_claim(raw: Any) -> Optional[str]:
    """Normalize optional JWT template claim to a short string or ``None``."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return s[:120]

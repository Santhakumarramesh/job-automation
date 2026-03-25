import hmac
import json
import os
import time
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from fastapi import Depends, Header, HTTPException, Request

from services.role_templates import expand_roles_from_template, normalize_role_template_claim

_OIDC_JWKS_CACHE_URL: Optional[str] = None
_OIDC_JWKS_CACHE_MONO: float = 0.0
_OIDC_JWKS_TTL_SEC = 3600.0


def jwt_auth_configured() -> bool:
    """True when Bearer JWT validation is enabled (HS256 secret and/or OIDC JWKS)."""
    return bool(
        (os.getenv("JWT_SECRET") or "").strip()
        or (os.getenv("JWT_JWKS_URL") or "").strip()
        or (os.getenv("JWT_ISSUER") or "").strip()
    )


def _discover_jwks_uri(issuer: str) -> Optional[str]:
    """Fetch ``{issuer}/.well-known/openid-configuration`` and return ``jwks_uri`` (cached)."""
    global _OIDC_JWKS_CACHE_URL, _OIDC_JWKS_CACHE_MONO
    iss = issuer.rstrip("/")
    if not iss:
        return None
    now = time.monotonic()
    if _OIDC_JWKS_CACHE_URL and (now - _OIDC_JWKS_CACHE_MONO) < _OIDC_JWKS_TTL_SEC:
        return _OIDC_JWKS_CACHE_URL
    url = f"{iss}/.well-known/openid-configuration"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            doc = json.loads(resp.read().decode())
        jwks = doc.get("jwks_uri")
        if isinstance(jwks, str) and jwks.strip():
            _OIDC_JWKS_CACHE_URL = jwks.strip()
            _OIDC_JWKS_CACHE_MONO = now
            return _OIDC_JWKS_CACHE_URL
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def _effective_jwks_url() -> Optional[str]:
    explicit = (os.getenv("JWT_JWKS_URL") or "").strip()
    if explicit:
        return explicit
    issuer = (os.getenv("JWT_ISSUER") or "").strip()
    if issuer:
        return _discover_jwks_uri(issuer)
    return None


def _decode_with_jwks(token: str, jwks_url: str) -> dict:
    import jwt
    from jwt import PyJWKClient

    client = PyJWKClient(jwks_url, cache_keys=True)
    sk = client.get_signing_key_from_jwt(token)
    algs_raw = (os.getenv("JWT_JWKS_ALGORITHMS") or "RS256,RS384,RS512,ES256").strip()
    algs = [x.strip() for x in algs_raw.split(",") if x.strip()]
    if not algs:
        algs = ["RS256"]
    opts: dict = {"algorithms": algs}
    aud = (os.getenv("JWT_AUDIENCE") or "").strip()
    if aud:
        opts["audience"] = [x.strip() for x in aud.split(",") if x.strip()] if "," in aud else aud
    iss = (os.getenv("JWT_ISSUER") or "").strip()
    if iss:
        opts["issuer"] = iss
    return jwt.decode(token, sk.key, **opts)


def _admin_role_set() -> set[str]:
    """Role names (lowercase) that count as admin. From JWT_ADMIN_ROLES env."""
    raw = os.getenv("JWT_ADMIN_ROLES", "admin")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


class User:
    """Authenticated API user with optional RBAC roles (Phase 3.1.4) and workspace (4.1.2)."""

    def __init__(
        self,
        user_id: str,
        roles: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        role_template: Optional[str] = None,
    ):
        self.id = user_id
        self.roles = [str(r).strip().lower() for r in (roles or []) if r is not None and str(r).strip()]
        self.workspace_id: Optional[str] = workspace_id
        rt = str(role_template or "").strip()
        self.role_template: Optional[str] = rt[:120] if rt else None

    @property
    def is_admin(self) -> bool:
        adm = _admin_role_set()
        if not adm:
            return False
        return bool(adm.intersection(set(self.roles)))


def _jwt_roles_from_payload(payload: dict) -> List[str]:
    out: List[str] = []
    role = payload.get("role")
    if isinstance(role, str) and role.strip():
        out.append(role.strip().lower())
    roles = payload.get("roles")
    if isinstance(roles, list):
        out.extend(str(x).strip().lower() for x in roles if x is not None and str(x).strip())
    ra = payload.get("realm_access")
    if isinstance(ra, dict):
        for x in ra.get("roles") or []:
            if x is not None and str(x).strip():
                out.append(str(x).strip().lower())
    seen: set[str] = set()
    uniq: List[str] = []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def _secret_keys_equal(expected: str, got: str) -> bool:
    """Constant-time compare for API-style secrets (equal length only)."""
    if len(expected) != len(got):
        return False
    return hmac.compare_digest(expected.encode("utf-8"), got.encode("utf-8"))


def _comma_roles(raw: str) -> List[str]:
    return [x.strip().lower() for x in (raw or "").split(",") if x.strip()]


def _try_m2m_user(request: Request) -> Optional[User]:
    """
    Phase 4.1.3 — optional service-to-service key (workers, cron, internal callers).

    When ``M2M_API_KEY`` is set and the client sends a non-empty value in
    ``M2M_API_KEY_HEADER`` (default ``X-M2M-API-Key``), that path wins over JWT
    and ``X-API-Key``. Wrong key → 401.
    """
    expected = (os.getenv("M2M_API_KEY") or "").strip()
    if not expected:
        return None
    hdr_name = (os.getenv("M2M_API_KEY_HEADER") or "X-M2M-API-Key").strip()
    incoming = (request.headers.get(hdr_name) or "").strip()
    if not incoming:
        return None
    if not _secret_keys_equal(expected, incoming):
        raise HTTPException(status_code=401, detail="Invalid M2M API key")
    uid = (os.getenv("M2M_USER_ID") or "m2m-service").strip() or "m2m-service"
    roles = _comma_roles(os.getenv("M2M_SERVICE_ROLES") or "")
    if os.getenv("M2M_API_KEY_IS_ADMIN", "").lower() in ("1", "true", "yes"):
        adm = _admin_role_set()
        roles = roles + ([next(iter(adm))] if adm else ["admin"])
    rtm = normalize_role_template_claim(os.getenv("M2M_ROLE_TEMPLATE"))
    roles = expand_roles_from_template(roles, rtm)
    return User(user_id=uid, roles=roles, role_template=rtm)


def _header_workspace_id(request: Request) -> Optional[str]:
    raw = (request.headers.get("X-Workspace-Id") or "").strip()
    return raw[:200] if raw else None


def _apply_request_workspace(user: User, request: Request, jwt_workspace: Optional[str]) -> None:
    """Header wins over JWT ``workspace_id`` / ``org_id`` claims."""
    hw = _header_workspace_id(request)
    if hw:
        user.workspace_id = hw
        return
    jw = (jwt_workspace or "").strip()
    user.workspace_id = jw[:200] if jw else None


def _decode_jwt_identity(
    authorization: Optional[str],
) -> Optional[Tuple[str, List[str], Optional[str], Optional[str]]]:
    """
    Bearer JWT: HS256 via ``JWT_SECRET``, or RS256/ES* via ``JWT_JWKS_URL`` or ``JWT_ISSUER`` discovery.

    Returns (sub, roles, workspace_id, role_template) or None if not a JWT request.
    """
    if not authorization or not jwt_auth_configured():
        return None
    auth = authorization.strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        import jwt
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="JWT auth requires PyJWT. pip install 'PyJWT>=2.8'",
        )
    secret = (os.getenv("JWT_SECRET") or "").strip()
    jwks_url = _effective_jwks_url()
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid JWT")
    alg = (header.get("alg") or "").upper()

    try:
        if alg == "HS256" and secret:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        elif jwks_url:
            payload = _decode_with_jwks(token, jwks_url)
        elif secret:
            fallback_alg = os.getenv("JWT_ALGORITHM", "HS256")
            payload = jwt.decode(token, secret, algorithms=[fallback_alg])
        else:
            return None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT")
    sub = payload.get("sub") or payload.get("user_id")
    if not sub:
        raise HTTPException(status_code=401, detail="JWT missing sub/user_id claim")
    roles = _jwt_roles_from_payload(payload)
    claim = (os.getenv("JWT_ROLE_TEMPLATE_CLAIM") or "role_template").strip() or "role_template"
    rt = normalize_role_template_claim(payload.get(claim))
    roles = expand_roles_from_template(roles, rt)
    jw_raw = payload.get("workspace_id") or payload.get("org_id")
    jw: Optional[str] = None
    if jw_raw is not None:
        s = str(jw_raw).strip()
        if s:
            jw = s[:200]
    return (str(sub), roles, jw, rt)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    """
    Auth (Phase 3.1.3 / 3.1.4 / 4.1.1 / 4.1.3):
    - M2M: ``M2M_API_KEY`` + header ``M2M_API_KEY_HEADER`` (default ``X-M2M-API-Key``).
    - JWT: HS256 (``JWT_SECRET``) or OIDC (``JWT_JWKS_URL`` / ``JWT_ISSUER`` + optional ``JWT_AUDIENCE``).
    - JWT roles from `role`, `roles`, or Keycloak `realm_access.roles`.
    - Optional role **template** claim (`JWT_ROLE_TEMPLATE_CLAIM`, default `role_template`) expanded via `JWT_ROLE_TEMPLATE_MAP`.
    - API key: user id api-key-user; admin if API_KEY_IS_ADMIN=1.
    - No API_KEY: demo-user (non-admin unless DEMO_USER_IS_ADMIN=1).
    """
    m2m_user = _try_m2m_user(request)
    if m2m_user is not None:
        _apply_request_workspace(m2m_user, request, None)
        return m2m_user

    jwt_identity = _decode_jwt_identity(authorization)
    if jwt_identity is not None:
        sub, roles, jw, rt = jwt_identity
        u = User(user_id=sub, roles=roles, role_template=rt)
        _apply_request_workspace(u, request, jw)
        return u

    api_key = os.getenv("API_KEY", "")
    if not api_key:
        demo_roles: List[str] = []
        if os.getenv("DEMO_USER_IS_ADMIN", "").lower() in ("1", "true", "yes"):
            adm = _admin_role_set()
            demo_roles = [next(iter(adm))] if adm else ["admin"]
        u = User(user_id="demo-user", roles=demo_roles)
        _apply_request_workspace(u, request, None)
        return u
    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    key_roles: List[str] = []
    if os.getenv("API_KEY_IS_ADMIN", "").lower() in ("1", "true", "yes"):
        adm = _admin_role_set()
        key_roles = [next(iter(adm))] if adm else ["admin"]
    u = User(user_id="api-key-user", roles=key_roles)
    _apply_request_workspace(u, request, None)
    return u


def require_admin(user: User = Depends(get_current_user)) -> User:
    """403 unless user.is_admin (JWT role, or API_KEY_IS_ADMIN / DEMO_USER_IS_ADMIN)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user

import os
from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException, Header


def _admin_role_set() -> set[str]:
    """Role names (lowercase) that count as admin. From JWT_ADMIN_ROLES env."""
    raw = os.getenv("JWT_ADMIN_ROLES", "admin")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


class User:
    """Authenticated API user with optional RBAC roles (Phase 3.1.4)."""

    def __init__(self, user_id: str, roles: Optional[List[str]] = None):
        self.id = user_id
        self.roles = [str(r).strip().lower() for r in (roles or []) if r is not None and str(r).strip()]

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


def _decode_jwt_identity(authorization: Optional[str]) -> Optional[Tuple[str, List[str]]]:
    """
    If JWT_SECRET is set and Bearer token present, return (sub, roles).
    Otherwise None (not a JWT request).
    """
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret or not authorization:
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
            detail="JWT_SECRET is set but PyJWT is not installed. pip install 'PyJWT>=2.8'",
        )
    alg = os.getenv("JWT_ALGORITHM", "HS256")
    try:
        payload = jwt.decode(token, secret, algorithms=[alg])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT")
    sub = payload.get("sub") or payload.get("user_id")
    if not sub:
        raise HTTPException(status_code=401, detail="JWT missing sub/user_id claim")
    roles = _jwt_roles_from_payload(payload)
    return (str(sub), roles)


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    """
    Auth (Phase 3.1.3 / 3.1.4):
    - JWT: user id = sub; roles from `role`, `roles`, or Keycloak `realm_access.roles`.
    - API key: user id api-key-user; admin if API_KEY_IS_ADMIN=1.
    - No API_KEY: demo-user (non-admin unless DEMO_USER_IS_ADMIN=1).
    """
    jwt_identity = _decode_jwt_identity(authorization)
    if jwt_identity is not None:
        sub, roles = jwt_identity
        return User(user_id=sub, roles=roles)

    api_key = os.getenv("API_KEY", "")
    if not api_key:
        demo_roles: List[str] = []
        if os.getenv("DEMO_USER_IS_ADMIN", "").lower() in ("1", "true", "yes"):
            adm = _admin_role_set()
            demo_roles = [next(iter(adm))] if adm else ["admin"]
        return User(user_id="demo-user", roles=demo_roles)
    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    key_roles: List[str] = []
    if os.getenv("API_KEY_IS_ADMIN", "").lower() in ("1", "true", "yes"):
        adm = _admin_role_set()
        key_roles = [next(iter(adm))] if adm else ["admin"]
    return User(user_id="api-key-user", roles=key_roles)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """403 unless user.is_admin (JWT role, or API_KEY_IS_ADMIN / DEMO_USER_IS_ADMIN)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user

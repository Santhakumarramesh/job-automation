"""
Phase 12 — recruiter / application follow-up queue from tracker rows.

Uses columns: follow_up_at (ISO 8601), follow_up_status, follow_up_note.
Priority scoring (#40): ATS, fit_decision, applied_at recency, overdue follow_up_at.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _is_active_follow_up(status: str) -> bool:
    x = (status or "").strip().lower()
    return x not in ("done", "dismissed")


def _normalize_ats(raw: Any) -> float:
    """Map ATS to 0..1; unknown -> 0.5."""
    if raw is None or raw == "":
        return 0.5
    try:
        s = str(raw).strip().replace("%", "")
        v = float(s)
        if v > 1.0 and v <= 100.0:
            v = v / 100.0
        elif v > 100.0:
            v = 1.0
        elif v < 0.0:
            v = 0.0
        else:
            v = min(max(v, 0.0), 1.0)
        return v
    except (TypeError, ValueError):
        return 0.5


def _fit_weight(fit_decision: Any) -> float:
    x = (str(fit_decision or "")).strip().lower()
    if x == "apply":
        return 1.0
    if x in ("manual_review", "manual_assist", "manual review", "review"):
        return 0.7
    if x == "reject":
        return 0.2
    return 0.45


def _recency_factor(applied_at: Any, now: datetime) -> float:
    """1.0 = applied today, decays to 0 by ~30 days."""
    dt = _parse_iso(str(applied_at or ""))
    if dt is None:
        return 0.5
    delta = now - dt
    days = max(delta.total_seconds() / 86400.0, 0.0)
    return max(0.0, 1.0 - min(days / 30.0, 1.0))


def _overdue_factor(follow_up_at: str, now: datetime) -> float:
    """0 if follow-up is in the future; up to 1 if weeks overdue."""
    dt = _parse_iso(follow_up_at)
    if dt is None:
        return 0.0
    if dt > now:
        return 0.0
    hours = (now - dt).total_seconds() / 3600.0
    return min(hours / 168.0, 1.0)  # full weight at ~1 week past due


def compute_follow_up_priority_score(
    row: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Heuristic 0–100 score: higher = follow up first.
    Components: ATS (35%), fit (25%), application recency (25%), overdue urgency (15%).
    """
    now = now or _now_utc()
    ats_n = _normalize_ats(row.get("ats_score"))
    fit_n = _fit_weight(row.get("fit_decision"))
    rec = _recency_factor(row.get("applied_at"), now)
    ovd = _overdue_factor(str(row.get("follow_up_at") or ""), now)
    score = 100.0 * (0.35 * ats_n + 0.25 * fit_n + 0.25 * rec + 0.15 * ovd)
    breakdown = {
        "ats_component": round(100.0 * 0.35 * ats_n, 2),
        "fit_component": round(100.0 * 0.25 * fit_n, 2),
        "recency_component": round(100.0 * 0.25 * rec, 2),
        "overdue_component": round(100.0 * 0.15 * ovd, 2),
    }
    return round(score, 2), breakdown


def list_follow_ups(
    for_user_id: Optional[str],
    *,
    due_only: bool = True,
    include_snoozed: bool = True,
    limit: int = 100,
    sort_by_priority: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return tracker rows with a follow-up scheduled and not closed.
    due_only: require follow_up_at <= now (UTC).
    """
    from services.application_tracker import load_applications

    df = load_applications(for_user_id=for_user_id)
    if df.empty:
        return []

    for col in ("follow_up_at", "follow_up_status", "follow_up_note"):
        if col not in df.columns:
            df[col] = ""

    at = df["follow_up_at"].fillna("").astype(str)
    st = df["follow_up_status"].fillna("").astype(str)

    mask = at.str.len() > 0
    mask &= st.map(_is_active_follow_up)

    if not include_snoozed:
        mask &= st.str.lower() != "snoozed"

    if due_only:
        now = _now_utc()

        def _due(cell: str) -> bool:
            dt = _parse_iso(cell)
            return dt is not None and dt <= now

        mask &= at.map(_due)

    sub = df.loc[mask]
    records = sub.fillna("").to_dict(orient="records")
    now = _now_utc()
    for rec in records:
        sc, _ = compute_follow_up_priority_score(rec, now=now)
        rec["follow_up_priority_score"] = sc
    if sort_by_priority:
        records.sort(key=lambda r: float(r.get("follow_up_priority_score") or 0), reverse=True)
    cap = max(1, min(limit, 500))
    return records[:cap]


def format_follow_up_digest(items: List[Dict[str, Any]], *, title: str = "Follow-up reminders") -> str:
    """
    Plain-text digest for email body, cron logs, or clipboard.
    Expects tracker-shaped dicts (company, position, job_url, follow_up_at, follow_up_note, ...).
    """
    lines = [title, "=" * max(len(title), 12), f"Generated (UTC): {_now_utc().strftime('%Y-%m-%d %H:%M')}", ""]
    if not items:
        lines.append("(No due follow-ups in this scope.)")
        return "\n".join(lines)
    for i, row in enumerate(items, start=1):
        co = str(row.get("company") or row.get("target_company") or "—")
        pos = str(row.get("position") or row.get("target_position") or "—")
        when = str(row.get("follow_up_at") or "")
        note = str(row.get("follow_up_note") or "").strip()
        url = str(row.get("job_url") or row.get("apply_url") or "").strip()
        pri = row.get("follow_up_priority_score")
        block = [f"{i}. {pos} @ {co}", f"   When: {when}"]
        if pri is not None:
            block.append(f"   Priority (est.): {pri}")
        if note:
            block.append(f"   Note: {note}")
        if url:
            block.append(f"   URL: {url}")
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

"""
Approved answer memory store (Phase X).

Stores user-approved answers keyed by canonical question keys, with context tags and history.
Memory accelerates reuse but never bypasses truth/policy gates.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class AnswerMemoryRecord:
    question_key: str
    question_text: str
    answer_text: str
    answer_state: str
    source: str
    context_json: str
    approved_by: str
    approved_at: str
    confidence: str
    auto_use_allowed: bool
    version: int
    updated_at: str
    created_at: str
    context_match: bool = True

    def as_dict(self) -> dict:
        return {
            "question_key": self.question_key,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "answer_state": self.answer_state,
            "source": self.source,
            "context": _safe_json_loads(self.context_json),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "confidence": self.confidence,
            "auto_use_allowed": bool(self.auto_use_allowed),
            "version": self.version,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "context_match": bool(self.context_match),
        }


def _resolve_db_path() -> Path:
    env_path = os.getenv("ANSWER_MEMORY_DB_PATH", "").strip()
    if env_path:
        return Path(env_path)
    tracker_path = os.getenv("TRACKER_DB_PATH", "").strip()
    if tracker_path:
        return Path(tracker_path)
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", ""))
    return PROJECT_ROOT / "job_applications.db"


def _db() -> sqlite3.Connection:
    path = _resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS answer_memory (
            question_key TEXT PRIMARY KEY,
            question_text TEXT DEFAULT '',
            answer_text TEXT DEFAULT '',
            answer_state TEXT DEFAULT 'review',
            source TEXT DEFAULT '',
            context_json TEXT DEFAULT '{}',
            approved_by TEXT DEFAULT '',
            approved_at TEXT DEFAULT '',
            confidence TEXT DEFAULT '',
            auto_use_allowed INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS answer_memory_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_key TEXT,
            version INTEGER DEFAULT 1,
            question_text TEXT DEFAULT '',
            answer_text TEXT DEFAULT '',
            answer_state TEXT DEFAULT 'review',
            source TEXT DEFAULT '',
            context_json TEXT DEFAULT '{}',
            approved_by TEXT DEFAULT '',
            approved_at TEXT DEFAULT '',
            confidence TEXT DEFAULT '',
            auto_use_allowed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );
        """
    )
    conn.commit()


def _safe_json_loads(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_context_json(context: Optional[dict | str]) -> str:
    if context is None:
        return "{}"
    if isinstance(context, str):
        s = context.strip()
        if not s:
            return "{}"
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError:
            return json.dumps({"raw": s})
    if isinstance(context, dict):
        return json.dumps(context, ensure_ascii=False)
    return json.dumps({"value": str(context)})


def _context_matches(context_json: str, job_context: Optional[dict]) -> bool:
    if not job_context:
        return True
    ctx = _safe_json_loads(context_json)
    if not ctx:
        return True
    for k, v in ctx.items():
        if v is None or v == "":
            continue
        jv = job_context.get(k) if isinstance(job_context, dict) else None
        if jv is None or jv == "":
            continue
        if str(v).strip().lower() != str(jv).strip().lower():
            return False
    return True


def _normalize_slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "_", (text or "").lower()).strip("_")
    return s[:80]


def derive_question_key(question_text: str, question_type: Optional[str] = None) -> str:
    try:
        from agents.application_answerer import classify_question

        qtype = question_type or classify_question(question_text) or "generic"
    except Exception:
        qtype = question_type or "generic"
    q_lower = (question_text or "").lower()
    if qtype == "years":
        if "python" in q_lower:
            return "years_python"
        if "sql" in q_lower:
            return "years_sql"
        if "machine learning" in q_lower or "ml" in q_lower:
            return "years_ml"
        if "aws" in q_lower:
            return "years_aws"
        if "nlp" in q_lower:
            return "years_nlp"
        return "years_generic"
    if qtype and qtype != "generic":
        return qtype
    return _normalize_slug(question_text) or "generic"


def save_approved_answer(
    *,
    question_text: str,
    approved_answer: str,
    context: Optional[dict | str] = None,
    answer_state: str = "safe",
    source: str = "user_approved",
    approved_by: str = "user",
    confidence: str = "high",
    auto_use_allowed: bool = True,
) -> dict:
    question_key = derive_question_key(question_text)
    ctx_json = _safe_context_json(context)
    now = datetime.now().isoformat()

    with _db() as conn:
        row = conn.execute(
            "SELECT version, created_at FROM answer_memory WHERE question_key = ?",
            (question_key,),
        ).fetchone()
        version = int(row["version"] or 0) + 1 if row else 1
        created_at = row["created_at"] if row and row["created_at"] else now

        conn.execute(
            """
            INSERT INTO answer_memory_history (
                question_key, version, question_text, answer_text, answer_state,
                source, context_json, approved_by, approved_at, confidence,
                auto_use_allowed, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                question_key,
                version,
                (question_text or "")[:400],
                (approved_answer or "")[:1000],
                (answer_state or "review")[:20],
                (source or "")[:120],
                ctx_json,
                (approved_by or "")[:200],
                now,
                (confidence or "")[:40],
                1 if auto_use_allowed else 0,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO answer_memory (
                question_key, question_text, answer_text, answer_state,
                source, context_json, approved_by, approved_at,
                confidence, auto_use_allowed, version, updated_at, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(question_key) DO UPDATE SET
                question_text=excluded.question_text,
                answer_text=excluded.answer_text,
                answer_state=excluded.answer_state,
                source=excluded.source,
                context_json=excluded.context_json,
                approved_by=excluded.approved_by,
                approved_at=excluded.approved_at,
                confidence=excluded.confidence,
                auto_use_allowed=excluded.auto_use_allowed,
                version=excluded.version,
                updated_at=excluded.updated_at
            """,
            (
                question_key,
                (question_text or "")[:400],
                (approved_answer or "")[:1000],
                (answer_state or "review")[:20],
                (source or "")[:120],
                ctx_json,
                (approved_by or "")[:200],
                now,
                (confidence or "")[:40],
                1 if auto_use_allowed else 0,
                version,
                now,
                created_at,
            ),
        )
        conn.commit()

    return {
        "question_key": question_key,
        "version": version,
        "approved_at": now,
        "auto_use_allowed": bool(auto_use_allowed),
    }


def get_saved_answer(
    *,
    question_text: str,
    job_context: Optional[dict] = None,
    question_key: Optional[str] = None,
    require_context_match: bool = False,
) -> dict:
    key = question_key or derive_question_key(question_text)
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM answer_memory WHERE question_key = ?",
            (key,),
        ).fetchone()
    if not row:
        return {"found": False, "question_key": key}

    context_json = row["context_json"] or "{}"
    match = _context_matches(context_json, job_context)
    if require_context_match and not match:
        return {"found": False, "question_key": key, "context_match": False}

    rec = AnswerMemoryRecord(
        question_key=row["question_key"],
        question_text=row["question_text"],
        answer_text=row["answer_text"],
        answer_state=row["answer_state"],
        source=row["source"],
        context_json=context_json,
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        confidence=row["confidence"],
        auto_use_allowed=bool(row["auto_use_allowed"]),
        version=int(row["version"] or 1),
        updated_at=row["updated_at"],
        created_at=row["created_at"],
        context_match=match,
    )
    return {"found": True, **rec.as_dict()}


def list_answer_memory(limit: int = 200) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM answer_memory ORDER BY updated_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        rec = AnswerMemoryRecord(
            question_key=row["question_key"],
            question_text=row["question_text"],
            answer_text=row["answer_text"],
            answer_state=row["answer_state"],
            source=row["source"],
            context_json=row["context_json"],
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
            confidence=row["confidence"],
            auto_use_allowed=bool(row["auto_use_allowed"]),
            version=int(row["version"] or 1),
            updated_at=row["updated_at"],
            created_at=row["created_at"],
            context_match=True,
        )
        out.append(rec.as_dict())
    return out


def mark_answer_requires_review(question_key: str) -> bool:
    key = (question_key or "").strip()
    if not key:
        return False
    now = datetime.now().isoformat()
    with _db() as conn:
        cur = conn.execute(
            """
            UPDATE answer_memory SET
                answer_state='review',
                auto_use_allowed=0,
                updated_at=?
            WHERE question_key=?
            """,
            (now, key),
        )
        conn.commit()
        return cur.rowcount > 0


def suggest_answers_from_memory(
    fields: list[str],
    *,
    job_context: Optional[dict] = None,
) -> dict:
    suggestions = {}
    for field in fields:
        res = get_saved_answer(
            question_text=str(field),
            job_context=job_context,
            require_context_match=True,
        )
        if not res.get("found"):
            suggestions[str(field)] = {"found": False}
            continue
        ok = bool(res.get("auto_use_allowed")) and str(res.get("answer_state")) == "safe"
        suggestions[str(field)] = {
            "found": True,
            "answer": res.get("answer_text", ""),
            "question_key": res.get("question_key", ""),
            "answer_state": res.get("answer_state", ""),
            "auto_use_allowed": bool(res.get("auto_use_allowed")),
            "context_match": bool(res.get("context_match", False)),
            "use_suggested": ok,
        }
    return suggestions

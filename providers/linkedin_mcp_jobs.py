"""
LinkedIn MCP job provider using linkedin-mcp-server.
Search flow: search_jobs -> job_ids -> get_job_details for each -> JobListing.
Supports: date_posted, job_type, experience_level, work_remote, easy_apply, sort_order.
Requires: pip install mcp, linkedin-mcp-server running (uv run linkedin-mcp-server --transport streamable-http --port 8000)
"""

import asyncio
import json
import os
from typing import Any, Optional

from providers.common_schema import JobListing, normalize_to_schema
from providers.base_provider import JobProvider, SearchFilters

LINKEDIN_MCP_URL = os.getenv("LINKEDIN_MCP_URL", "http://127.0.0.1:8000/mcp")


def _extract_from_sections(sections: dict, key: str) -> str:
    """Extract value from nested sections (job_posting or page_N)."""
    for name, data in (sections or {}).items():
        if isinstance(data, dict):
            v = data.get(key) or data.get(key.replace("_", ""))
            if v:
                return str(v)
            entities = data.get("entities") or data.get("items") or []
            for e in entities[:1]:
                if isinstance(e, dict) and e.get(key):
                    return str(e.get(key, ""))
    return ""


def _extract_easy_apply_confirmed(detail: dict, sections: dict, first_entity: dict) -> bool:
    """Try to get per-job Easy Apply from MCP response. Returns False if not confirmed."""
    for d in [detail or {}, first_entity or {}]:
        for key in ("easyApply", "easy_apply", "applyMethod", "isEasyApply"):
            v = d.get(key)
            if v is True or (isinstance(v, str) and v.lower() in ("true", "yes", "1", "easy")):
                return True
            if v is False:
                return False
    for name, data in (sections or {}).items():
        if isinstance(data, dict):
            v = data.get("easyApply") or data.get("easy_apply")
            if v is True:
                return True
    return False


def _call_mcp_tool(tool: str, arguments: dict, url: str = LINKEDIN_MCP_URL) -> dict | list | None:
    """Call MCP tool and return parsed result."""
    try:
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import StreamableHTTPTransport
    except ImportError:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import StreamableHTTPTransport
        except ImportError:
            print("⚠️ LinkedIn MCP: pip install mcp")
            return None

    async def _run():
        transport = StreamableHTTPTransport(url)
        async with ClientSession(transport) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments=arguments)
            out = None
            if result.content:
                for block in result.content:
                    txt = getattr(block, "text", None)
                    if txt:
                        try:
                            out = json.loads(txt)
                            break
                        except json.JSONDecodeError:
                            pass
            return out

    try:
        return asyncio.run(_run())
    except Exception as e:
        print(f"⚠️ LinkedIn MCP ({tool}): {e}")
        return None


def fetch_linkedin_mcp_jobs(
    keywords: str | list[str],
    location: str = "United States",
    work_type: str = "remote",
    max_results: int = 25,
    easy_apply: bool = False,
    date_posted: str = "",
    job_type: str = "",
    experience_level: str = "",
    sort_order: str = "",
) -> list[JobListing]:
    """
    Fetch jobs from LinkedIn via MCP.
    1. search_jobs(keywords, location, work_type, filters) -> job_ids
    2. get_job_details(job_id) for each -> full job
    3. Build JobListing with url = https://linkedin.com/jobs/view/{id}/
    """
    if isinstance(keywords, list):
        keywords = " ".join(keywords[:5])

    args = {
        "keywords": keywords,
        "location": location or "United States",
        "work_type": work_type or "remote",
        "max_pages": min(3, (max_results // 25) + 1),
        "easy_apply": easy_apply,
    }
    if date_posted:
        args["date_posted"] = date_posted  # 24h, 1w, 1m
    if job_type:
        args["job_type"] = job_type  # full_time, part_time, contract, internship
    if experience_level:
        args["experience_level"] = experience_level
    if sort_order:
        args["sort_order"] = sort_order  # most_recent, most_relevant

    search_result = _call_mcp_tool("search_jobs", args)
    if not search_result or not isinstance(search_result, dict):
        return []

    job_ids = search_result.get("job_ids") or []
    jobs = []
    for jid in job_ids[:max_results]:
        if not jid:
            continue
        detail = _call_mcp_tool("get_job_details", {"job_id": str(jid)})
        if not detail or not isinstance(detail, dict):
            continue
        url = detail.get("url") or f"https://www.linkedin.com/jobs/view/{jid}/"
        sections = detail.get("sections") or {}
        job_posting = sections.get("job_posting") or {}
        if isinstance(job_posting, dict):
            entities = job_posting.get("entities") or job_posting.get("items") or [job_posting]
            first = entities[0] if entities else job_posting
            easy_apply_confirmed = _extract_easy_apply_confirmed(detail, sections, first if isinstance(first, dict) else None)
            if isinstance(first, dict):
                # Use per-job confirmation when available; else fall back to filter assumption
                raw = {
                    "title": first.get("title") or first.get("name") or _extract_from_sections(sections, "title"),
                    "company": first.get("company") or first.get("company_name") or _extract_from_sections(sections, "company"),
                    "location": first.get("location") or first.get("place") or _extract_from_sections(sections, "location"),
                    "description": first.get("description") or first.get("details") or _extract_from_sections(sections, "description"),
                    "url": url,
                    "job_id": str(jid),
                    "easy_apply": easy_apply_confirmed,  # Only True when MCP confirms; prevents false auto-apply
                    "easy_apply_filter_used": easy_apply,
                    "easy_apply_confirmed": easy_apply_confirmed,
                }
            else:
                raw = {"title": "Job", "company": "", "location": "", "description": "", "url": url, "job_id": str(jid), "easy_apply_filter_used": easy_apply, "easy_apply_confirmed": False}
        else:
            raw = {"title": "Job", "company": "", "location": "", "description": "", "url": url, "job_id": str(jid), "easy_apply_filter_used": easy_apply, "easy_apply_confirmed": False}
        jobs.append(normalize_to_schema(raw, "linkedin_mcp"))
    return jobs


def linkedin_mcp_search_jobs_payload(
    keywords: str = "",
    location: str = "United States",
    work_type: str = "remote",
    max_results: int = 25,
    easy_apply: bool = False,
    date_posted: str = "",
    job_type: str = "",
    experience_level: str = "",
    sort_order: str = "",
) -> dict:
    """
    Shared MCP + REST response: normalized job rows from LinkedIn MCP.
    Returns ``{status, count, jobs, message?}``.
    """
    kw = (keywords or "").strip()
    if not kw:
        return {"status": "error", "message": "keywords is required", "jobs": [], "count": 0}
    try:
        jobs = fetch_linkedin_mcp_jobs(
            keywords=kw,
            location=location or "United States",
            work_type=work_type or "remote",
            max_results=min(max(1, int(max_results)), 100),
            easy_apply=bool(easy_apply),
            date_posted=date_posted or "",
            job_type=job_type or "",
            experience_level=experience_level or "",
            sort_order=sort_order or "",
        )
        rows = [j.to_row() for j in jobs]
        return {"status": "ok", "count": len(rows), "jobs": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200], "jobs": [], "count": 0}


class LinkedInMCPProvider(JobProvider):
    """LinkedIn MCP implementation of JobProvider."""

    @property
    def provider_id(self) -> str:
        return "linkedin_mcp"

    def search(
        self,
        keywords: list[str],
        location: str,
        filters: SearchFilters,
        max_results: int,
    ) -> list[JobListing]:
        work_type = filters.work_remote or "remote"
        return fetch_linkedin_mcp_jobs(
            keywords=keywords,
            location=location or "United States",
            work_type=work_type,
            max_results=max_results,
            easy_apply=filters.easy_apply,
            date_posted=filters.date_posted,
            job_type=filters.job_type,
            experience_level=filters.experience_level,
            sort_order=filters.sort_order,
        )

    def get_job_details(self, job_id: str) -> Optional[JobListing]:
        detail = _call_mcp_tool("get_job_details", {"job_id": str(job_id)})
        if not detail or not isinstance(detail, dict):
            return None
        url = detail.get("url") or f"https://www.linkedin.com/jobs/view/{job_id}/"
        sections = detail.get("sections") or {}
        job_posting = sections.get("job_posting") or {}
        raw = {"title": "Job", "company": "", "location": "", "description": "", "url": url, "job_id": job_id}
        if isinstance(job_posting, dict):
            entities = job_posting.get("entities") or job_posting.get("items") or [job_posting]
            first = entities[0] if entities else job_posting
            if isinstance(first, dict):
                raw = {
                    "title": first.get("title") or first.get("name") or _extract_from_sections(sections, "title"),
                    "company": first.get("company") or first.get("company_name") or _extract_from_sections(sections, "company"),
                    "location": first.get("location") or first.get("place") or _extract_from_sections(sections, "location"),
                    "description": first.get("description") or first.get("details") or _extract_from_sections(sections, "description"),
                    "url": url,
                    "job_id": job_id,
                }
        return normalize_to_schema(raw, "linkedin_mcp")

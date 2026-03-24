"""
URL → application form family (LinkedIn, Greenhouse, Lever, Workday, generic).
Shared by MCP ``detect_form_type`` and REST ``GET /api/ats/form-type``.
"""


def detect_form_type_payload(url: str) -> dict:
    u = (url or "").strip()
    if not u:
        return {"url": "", "form_type": "generic", "error": "url is required"}
    try:
        from agents.application_runner import detect_form_type as _detect

        return {"url": u, "form_type": _detect(u)}
    except Exception as e:
        return {"url": u, "form_type": "generic", "error": str(e)[:100]}

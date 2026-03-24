"""
Application Answerer - Answers employer form questions from candidate profile + master resume.
Stays truthful; no fabrication. Returns short, humanized text (≤150 chars for most fields).

Structured path: answer_question_structured() adds manual_review_required + reason_codes
for automation gates (WORKFLOW_MODULE_MAP — answerer confidence).
"""

import re
from typing import List, Optional, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


MAX_ANSWER_LENGTH = 150
MAX_ANSWER_LENGTH_LONG = 280  # For why_role, why_company when needed

REASON_PLACEHOLDER_MANUAL = "placeholder_manual_text"
REASON_EMPTY = "empty_no_profile_data"
REASON_GENERIC_LLM = "generic_llm_answer"
REASON_MISSING_SPONSORSHIP = "missing_sponsorship_or_work_auth"
REASON_MISSING_RELOCATION = "missing_relocation_preference"
REASON_MISSING_SALARY = "missing_salary_expectation"
REASON_MISSING_YEARS = "missing_years_experience_short_answers"
REASON_MISSING_WHY_ROLE = "missing_why_this_role"
REASON_MISSING_WHY_COMPANY = "missing_why_this_company"
REASON_MISSING_AVAILABILITY = "missing_availability_or_notice"
REASON_MISSING_URL = "missing_url_field"
REASON_TRUNCATED = "answer_truncated"

# Question type keywords for auto-classification
QUESTION_PATTERNS = [
    (r"sponsor|work\s*(auth|permit|visa|authorization)|require\s*sponsor|h1.?b|green\s*card", "sponsorship"),
    (r"relocat|willing\s*to\s*move|remote|work\s*location|on.?site", "relocation"),
    (r"salary|compensation|pay\s*expect|expected\s*salary|hourly|annual", "salary"),
    (r"years?\s*(of\s*)?(experience\s*)?(in\s*)?(python|sql|ml|machine\s*learning|nlp|aws|data)", "years"),
    (r"years?\s*(of\s*)?(experience|exp\.?)", "years"),
    (r"why\s*(do\s*you\s*want\s*)?(this\s*)?(role|position)", "why_role"),
    (r"why\s*(do\s*you\s*want\s*)?(this\s*)?(company|us)", "why_company"),
    (r"when\s*(can\s*you\s*)?start|availability|start\s*date", "availability"),
    (r"notice\s*period|how\s*much\s*notice|two\s*weeks", "notice_period"),
    (r"linkedin|linked\s*in", "linkedin_url"),
    (r"github|git\s*hub", "github_url"),
    (r"portfolio|website", "portfolio_url"),
]


class AnswerResult(TypedDict):
    """Structured answer for gating auto-submit vs manual review."""

    answer: str
    manual_review_required: bool
    reason_codes: List[str]
    classified_type: str


def classify_question(question_text: str) -> Optional[str]:
    """Classify question type from text. Returns type string or None."""
    q = (question_text or "").lower().strip()
    if not q:
        return None
    for pattern, qtype in QUESTION_PATTERNS:
        if re.search(pattern, q, re.I):
            return qtype
    return "generic"


def answer_question_structured(
    question_text: str,
    question_type: Optional[str] = None,
    profile: Optional[dict] = None,
    master_resume_text: str = "",
    job_description: str = "",
    job_context: Optional[dict] = None,
    use_llm: bool = False,
) -> AnswerResult:
    """
    Same as answer_question but includes manual_review_required and reason_codes.
    manual_review_required is True when the answer is empty, a manual placeholder,
    or produced by generic LLM (low structural confidence).
    """
    profile = profile or {}
    job_context = job_context or {}
    company = job_context.get("company", "")
    role = job_context.get("title", job_context.get("role", ""))

    qtype = question_type or classify_question(question_text) or "unknown"
    reasons: List[str] = []
    answer = ""
    manual = False
    pre_len = 0

    if qtype == "sponsorship":
        answer = profile.get("work_authorization_note") or profile.get("short_answers", {}).get("sponsorship", "")
        if not answer and profile.get("visa_status"):
            answer = str(profile.get("visa_status", "")).strip()
        if not answer:
            answer = "Please review manually"
            manual = True
            reasons.append(REASON_MISSING_SPONSORSHIP)
            reasons.append(REASON_PLACEHOLDER_MANUAL)

    elif qtype == "relocation":
        answer = profile.get("relocation_preference", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_RELOCATION)
            reasons.append(REASON_EMPTY)

    elif qtype == "salary":
        answer = profile.get("salary_expectation_rule", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_SALARY)
            reasons.append(REASON_EMPTY)

    elif qtype == "years":
        short = profile.get("short_answers", {})
        q_lower = (question_text or "").lower()
        for key in ["years_python", "years_ml", "years_sql", "years_aws", "years_nlp"]:
            if key.replace("years_", "") in q_lower or key in q_lower:
                answer = short.get(key, "")
                break
        if not answer:
            answer = short.get("years_python", short.get("years_ml", ""))
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_YEARS)
            reasons.append(REASON_EMPTY)

    elif qtype == "why_role":
        answer = profile.get("short_answers", {}).get("why_this_role", "")
        if role and answer and use_llm:
            answer = _tailor_with_llm(question_text, answer, profile, job_description, company, role, max_len=MAX_ANSWER_LENGTH)
        elif not answer:
            answer = "Please review manually"
            manual = True
            reasons.append(REASON_MISSING_WHY_ROLE)
            reasons.append(REASON_PLACEHOLDER_MANUAL)

    elif qtype == "why_company":
        answer = profile.get("short_answers", {}).get("why_this_company", "")
        if company and answer:
            answer = answer.replace("the company", company).replace("this company", company)
        if not answer:
            answer = "Please review manually"
            manual = True
            reasons.append(REASON_MISSING_WHY_COMPANY)
            reasons.append(REASON_PLACEHOLDER_MANUAL)

    elif qtype == "availability":
        answer = profile.get("short_answers", {}).get("availability") or profile.get("notice_period", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_AVAILABILITY)
            reasons.append(REASON_EMPTY)

    elif qtype == "notice_period":
        answer = profile.get("notice_period", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_AVAILABILITY)
            reasons.append(REASON_EMPTY)

    elif qtype == "linkedin_url":
        answer = profile.get("linkedin_url", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_URL)
            reasons.append(REASON_EMPTY)

    elif qtype == "github_url":
        answer = profile.get("github_url", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_URL)
            reasons.append(REASON_EMPTY)

    elif qtype == "portfolio_url":
        answer = profile.get("portfolio_url", "") or profile.get("github_url", "")
        if not str(answer).strip():
            manual = True
            reasons.append(REASON_MISSING_URL)
            reasons.append(REASON_EMPTY)

    elif qtype == "generic" and use_llm:
        answer = _answer_generic_llm(question_text, profile, master_resume_text, job_description, job_context)
        manual = True
        reasons.append(REASON_GENERIC_LLM)
        if not str(answer).strip():
            reasons.append(REASON_EMPTY)

    # Fallback: try short_answers by normalized key
    if not answer and question_text:
        key = re.sub(r"[^\w]+", "_", question_text.lower())[:40].strip("_")
        answer = profile.get("short_answers", {}).get(key, "")

    answer = str(answer).strip()
    max_len = MAX_ANSWER_LENGTH_LONG if qtype in ("why_role", "why_company") else MAX_ANSWER_LENGTH
    if answer and len(answer) > max_len:
        answer = answer[: max_len - 3].rsplit(" ", 1)[0] + "..."
        reasons.append(REASON_TRUNCATED)

    if not answer:
        manual = True
        if REASON_EMPTY not in reasons:
            reasons.append(REASON_EMPTY)

    # De-dupe while preserving order
    seen: set[str] = set()
    uniq: List[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    return AnswerResult(
        answer=answer,
        manual_review_required=manual,
        reason_codes=uniq,
        classified_type=qtype,
    )


def answer_question(
    question_text: str,
    question_type: Optional[str] = None,
    profile: Optional[dict] = None,
    master_resume_text: str = "",
    job_description: str = "",
    job_context: Optional[dict] = None,
    use_llm: bool = False,
) -> str:
    """
    Answer an employer form question from profile + master resume.
    Stays truthful; no fabrication. Returns short text (≤150 chars for most).
    """
    return answer_question_structured(
        question_text,
        question_type,
        profile,
        master_resume_text,
        job_description,
        job_context,
        use_llm,
    )["answer"]


def _tailor_with_llm(question: str, base: str, profile: dict, jd: str, company: str, role: str, max_len: int = 150) -> str:
    """Light LLM tailoring to personalize base answer. Keeps truthful."""
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
        prompt = f"""Shorten to max {max_len} chars. Use ONLY facts from the candidate profile.
Question: {question}
Base answer: {base}
Company: {company}
Role: {role}
Return ONLY the tailored answer, no quotes or explanation."""
        r = llm.invoke([HumanMessage(content=prompt)])
        return (r.content or base)[:max_len].strip()
    except Exception:
        return base[:max_len]


def _answer_generic_llm(question: str, profile: dict, resume: str, jd: str, job_ctx: dict) -> str:
    """LLM fallback for unclassified questions. Must stay truthful to profile + resume."""
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        prompt = f"""Answer this job application question using ONLY the candidate profile and resume. Max 150 chars. No fabrication.

Question: {question}

Profile (use only this): {str(profile)[:800]}

Resume excerpt: {resume[:600]}

Return ONLY the answer, nothing else."""
        r = llm.invoke([HumanMessage(content=prompt)])
        ans = (r.content or "").strip()
        return ans[:MAX_ANSWER_LENGTH]
    except Exception:
        return ""


def answer_batch(
    questions: list[dict],
    profile: dict,
    master_resume_text: str = "",
    job_context: Optional[dict] = None,
    use_llm: bool = False,
) -> list[dict]:
    """
    Answer multiple questions. questions: list of {text, type?}.
    Returns list of {question, answer, manual_review_required, reason_codes, classified_type}.
    """
    job_context = job_context or {}
    jd = job_context.get("description", "")
    out: list[dict] = []
    for q in questions:
        text = q.get("text", q.get("question", ""))
        qtype = q.get("type", q.get("question_type"))
        meta = answer_question_structured(
            text,
            qtype,
            profile,
            master_resume_text,
            jd,
            job_context,
            use_llm,
        )
        out.append({"question": text, **meta})
    return out

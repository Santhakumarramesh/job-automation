"""
Headless LangGraph workflow for Celery workers (Phase 3.3.1).

Mirrors the linear agent pipeline previously inlined in ``app.tasks.run_job``.
Streamlit uses a richer graph in ``ui/streamlit_app.build_graph`` (ATS UI, services layer).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.state import AgentState
from agents.cover_letter_generator import generate_cover_letter
from agents.file_manager import save_documents
from agents.humanize_cover_letter import humanize_cover_letter
from agents.humanize_resume import humanize_resume
from agents.intelligent_project_generator import intelligent_project_generator
from agents.job_analyzer import analyze_job_description
from agents.job_guard import guard_job_quality
from agents.resume_editor import tailor_resume


def _route_after_guard(state: AgentState) -> str:
    return "analyze_jd" if state.get("is_eligible", True) else END


def build_celery_job_graph():
    """
    Linear pipeline: guard → analyze → tailor → humanize resume → project →
    cover → humanize cover → save PDFs. Ineligible jobs end after guard.
    """
    g = StateGraph(AgentState)
    g.add_node("guard_job", guard_job_quality)
    g.add_node("analyze_jd", analyze_job_description)
    g.add_node("tailor_resume", tailor_resume)
    g.add_node("humanize_resume", humanize_resume)
    g.add_node("intelligent_project", intelligent_project_generator)
    g.add_node("generate_cover_letter", generate_cover_letter)
    g.add_node("humanize_cover_letter", humanize_cover_letter)
    g.add_node("save_documents", save_documents)

    g.set_entry_point("guard_job")
    g.add_conditional_edges(
        "guard_job",
        _route_after_guard,
        {"analyze_jd": "analyze_jd", END: END},
    )
    g.add_edge("analyze_jd", "tailor_resume")
    g.add_edge("tailor_resume", "humanize_resume")
    g.add_edge("humanize_resume", "intelligent_project")
    g.add_edge("intelligent_project", "generate_cover_letter")
    g.add_edge("generate_cover_letter", "humanize_cover_letter")
    g.add_edge("humanize_cover_letter", "save_documents")
    g.add_edge("save_documents", END)
    return g.compile()


_compiled = None


def get_celery_job_graph():
    """Singleton compiled graph (workers are long-lived)."""
    global _compiled
    if _compiled is None:
        _compiled = build_celery_job_graph()
    return _compiled

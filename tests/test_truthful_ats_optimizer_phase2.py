from __future__ import annotations

from services.resume_content_selector import select_relevant_content


def _simple_keyword_score(resume_text: str, keywords: list[str]) -> int:
    resume_lower = resume_text.lower()
    hits = sum(1 for kw in keywords if kw in resume_lower)
    return 50 + hits * 20


def test_keyword_expansion_improves_score():
    resume_text = """
SUMMARY
- Built retrieval systems using Pinecone and GPT-4 for enterprise search.
- Deployed LLM assistants with vector stores and RAG pipelines.

EXPERIENCE
- Implemented Pinecone vector store integrations for low-latency semantic search.
- Integrated GPT-4 into production-grade Q&A workflows.

SKILLS
Python, Pinecone, OpenAI, RAG, FastAPI, AWS
""".strip()
    job_description = """
We are seeking experience with vector databases and large language models
to build retrieval-augmented generation systems.
""".strip()

    base_score = _simple_keyword_score(resume_text, ["vector database", "large language models"])
    selected = select_relevant_content(resume_text, job_description)
    new_score = _simple_keyword_score(selected.tailored_resume_text, ["vector database", "large language models"])

    assert new_score > base_score


def test_unsupported_keywords_not_added():
    resume_text = """
SUMMARY
AI engineer with Python and AWS experience.

EXPERIENCE
- Built NLP pipelines in Python.

SKILLS
Python, AWS, NLP
""".strip()
    job_description = "Must have Kubernetes experience."

    selected = select_relevant_content(
        resume_text,
        job_description,
        additional_keywords=["kubernetes"],
    )

    assert "kubernetes" not in selected.tailored_resume_text.lower()


def test_run_iterative_ats_returns_ceiling_and_summary(monkeypatch):
    from services import ats_service

    class _DummyATSChecker:
        def comprehensive_ats_check(self, *, resume_text: str, **kwargs):
            return {
                "ats_score": 60,
                "feedback": [],
                "detailed_breakdown": {"missing_keywords": []},
                "truthful_missing_keywords": [],
            }

        def save_ats_results_to_excel(self, ats_results, filename: str):
            return f"/tmp/{filename}"

    def _dummy_optimizer(**kwargs):
        return {
            "tailored_resume_text": "base",
            "humanized_resume_text": "base",
            "initial_ats_score": 60,
            "final_ats_score": 60,
            "feedback": [],
            "missing_keywords": [],
            "truthful_missing_keywords": [],
            "converged": False,
            "no_truthful_improvement": True,
        }

    monkeypatch.setattr(ats_service, "EnhancedATSChecker", _DummyATSChecker)
    monkeypatch.setattr(ats_service, "run_iterative_ats_optimizer", _dummy_optimizer)

    result = ats_service.run_iterative_ats(
        {
            "base_resume_text": "Resume text with Python and AWS experience.",
            "job_description": "Role requires Python and AWS.",
            "target_position": "ML Engineer",
            "target_company": "ExampleCo",
            "target_location": "USA",
        },
        target_score=90,
    )

    assert result["truth_safe_ats_ceiling"] == result["final_ats_score"]
    assert "Stopped: no further truthful improvement possible." in result["optimization_summary"]

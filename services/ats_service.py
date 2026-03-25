"""
ATS service. score_resume, iterative_optimizer, fit gate.
"""


from enhanced_ats_checker import EnhancedATSChecker
from agents.iterative_ats_optimizer import run_iterative_ats_optimizer
from agents.master_resume_guard import parse_master_resume, is_job_fit, compute_job_fit_score
from agents.resume_editor import tailor_resume
from agents.humanize_resume import humanize_resume
from services.truth_safe_ats import compute_truth_safe_ats_ceiling


def score_resume(
    state: dict,
    target_score: int = 100,
) -> dict:
    """
    Run comprehensive ATS check. Returns state updates: initial_ats_score,
    feedback, ats_report_path, missing_skills.
    """
    checker = EnhancedATSChecker()
    master_text = state.get("base_resume_text", "")
    ats_results = checker.comprehensive_ats_check(
        resume_text=state["base_resume_text"],
        job_description=state["job_description"],
        job_title=state["target_position"],
        company_name=state["target_company"],
        location=state["target_location"],
        target_truthful_score=target_score,
        master_resume_text=master_text,
    )
    report_filename = f"ATS_Report_{state['target_company']}.xlsx".replace("/", "_")
    ats_report_path = checker.save_ats_results_to_excel(ats_results, filename=report_filename)
    missing = ats_results.get("detailed_breakdown", {}).get("missing_keywords", [])
    truthful_left = ats_results.get("truthful_missing_keywords") or []
    ceiling = compute_truth_safe_ats_ceiling(
        ats_results["ats_score"],
        target_score=target_score,
        truth_safe=True,
        converged=ats_results["ats_score"] >= target_score,
        no_truthful_improvement=not bool(truthful_left),
        unsupported_requirements=ats_results.get("unsupported_requirements") or [],
        truthful_missing_keywords=truthful_left,
    )
    return {
        "initial_ats_score": ats_results["ats_score"],
        "feedback": "\n".join(ats_results["feedback"]) if isinstance(ats_results["feedback"], list) else ats_results["feedback"],
        "ats_report_path": ats_report_path,
        "missing_skills": missing,
        "truth_safe_ats_ceiling": ceiling["truth_safe_ats_ceiling"],
        "truth_safe_ceiling_reason": ceiling["truth_safe_ceiling_reason"],
        "ceiling_limited_by": ceiling.get("ceiling_limited_by", []),
    }


def run_iterative_ats(
    state: dict,
    target_score: int = 100,
    max_attempts: int = 5,
    truth_safe: bool = True,
) -> dict:
    """
    Run iterative ATS optimizer until target or no truthful improvement.
    Returns dict with tailored_resume_text, humanized_resume_text, final_ats_score,
    feedback, job_fit_score, fit_decision, unsupported_requirements.
    """
    checker = EnhancedATSChecker()
    opt_result = run_iterative_ats_optimizer(
        state=state,
        ats_checker=checker,
        tailor_fn=tailor_resume,
        humanize_fn=humanize_resume,
        target_score=target_score,
        max_attempts=max_attempts,
        truth_safe=truth_safe,
    )
    master_inv = parse_master_resume(state.get("base_resume_text", ""))
    fit = compute_job_fit_score(
        state.get("job_description", ""),
        master_inv,
        ats_score=opt_result.get("final_ats_score", 0),
    )
    ats_results = checker.comprehensive_ats_check(
        resume_text=opt_result["humanized_resume_text"],
        job_description=state.get("job_description", ""),
        job_title=state.get("target_position", ""),
        company_name=state.get("target_company", ""),
        location=state.get("target_location", ""),
        target_truthful_score=target_score,
        master_resume_text=state.get("base_resume_text", ""),
    )
    report_filename = f"ATS_Report_{state['target_company']}.xlsx".replace("/", "_")
    ats_report_path = checker.save_ats_results_to_excel(ats_results, filename=report_filename)
    fit_decision = "apply" if fit.get("apply") else ("reject" if fit.get("reject") else "manual_review")
    truthful_final = ats_results.get("truthful_missing_keywords") or opt_result.get("truthful_missing_keywords") or []
    ceiling = compute_truth_safe_ats_ceiling(
        opt_result.get("final_ats_score", 0),
        target_score=target_score,
        truth_safe=truth_safe,
        converged=bool(opt_result.get("converged")),
        no_truthful_improvement=bool(opt_result.get("no_truthful_improvement")),
        stopped_after_max_attempts=bool(opt_result.get("stopped_after_max_attempts")),
        unsupported_requirements=fit.get("unsupported_requirements", []),
        truthful_missing_keywords=truthful_final,
        initial_ats_score=opt_result.get("initial_ats_score"),
    )
    return {
        "tailored_resume_text": opt_result["tailored_resume_text"],
        "humanized_resume_text": opt_result["humanized_resume_text"],
        "initial_ats_score": opt_result.get("initial_ats_score", opt_result.get("final_ats_score", 0)),
        "final_ats_score": opt_result.get("final_ats_score", 0),
        "feedback": "\n".join(opt_result.get("feedback", [])) if isinstance(opt_result.get("feedback"), list) else str(opt_result.get("feedback", "")),
        "ats_report_path": ats_report_path,
        "job_fit_score": fit.get("score"),
        "fit_decision": fit_decision,
        "unsupported_requirements": fit.get("unsupported_requirements", []),
        "missing_keywords": opt_result.get("missing_keywords", []),
        "truthful_missing_keywords": truthful_final,
        "truth_safe_ats_ceiling": ceiling["truth_safe_ats_ceiling"],
        "truth_safe_ceiling_reason": ceiling["truth_safe_ceiling_reason"],
        "ceiling_limited_by": ceiling.get("ceiling_limited_by", []),
    }


def check_fit_gate(state: dict) -> dict:
    """
    Master-resume fit gate. Returns is_eligible, fit_decision, job_fit_score,
    unsupported_requirements, eligibility_reason (if rejected).
    """
    profile = parse_master_resume(state.get("base_resume_text", ""))
    job = {
        "description": state.get("job_description", ""),
        "title": state.get("target_position", ""),
        "company": state.get("target_company", ""),
    }
    result = is_job_fit(profile, job, ats_score=0)
    if result.reject:
        return {
            "is_eligible": False,
            "eligibility_reason": f"Master-resume fit gate: {'; '.join(result.reasons[:3])}",
            "fit_decision": result.decision,
            "job_fit_score": result.score,
            "unsupported_requirements": result.unsupported_requirements,
        }
    return {
        "is_eligible": True,
        "fit_decision": result.decision,
        "job_fit_score": result.score,
        "unsupported_requirements": result.unsupported_requirements,
    }


def score_job_fit_payload(
    job_description: str,
    master_resume_text: str,
    job_title: str = "",
    company: str = "",
    location: str = "USA",
) -> dict:
    """
    MCP ``score_job_fit`` + REST parity: fit gate + one ATS check + truth-safe ceiling metadata.
    Returns ``{status, fit_score, fit_decision, ...}`` or ``{status: error, message}``.
    """
    try:
        state = {
            "base_resume_text": master_resume_text,
            "job_description": job_description,
            "target_position": job_title or "Role",
            "target_company": company or "Company",
            "target_location": location or "USA",
        }
        fit_result = check_fit_gate(state)
        checker = EnhancedATSChecker()
        ats_results = checker.comprehensive_ats_check(
            resume_text=master_resume_text,
            job_description=job_description,
            job_title=job_title or "Role",
            company_name=company or "Company",
            location=location or "USA",
            target_truthful_score=100,
            master_resume_text=master_resume_text,
        )
        missing = ats_results.get("detailed_breakdown", {}).get("missing_keywords", [])
        merged_unsup = sorted(
            {
                str(x).strip()
                for x in (fit_result.get("unsupported_requirements") or [])
                + (ats_results.get("unsupported_requirements") or [])
                if str(x).strip()
            }
        )
        truthful_left = ats_results.get("truthful_missing_keywords") or []
        ceiling = compute_truth_safe_ats_ceiling(
            final_ats_score=ats_results.get("ats_score", 0),
            target_score=100,
            truth_safe=True,
            converged=int(ats_results.get("ats_score", 0) or 0) >= 100,
            no_truthful_improvement=not bool(truthful_left),
            stopped_after_max_attempts=False,
            unsupported_requirements=merged_unsup,
            truthful_missing_keywords=truthful_left,
        )
        return {
            "status": "ok",
            "fit_score": fit_result.get("job_fit_score", 0),
            "fit_decision": fit_result.get("fit_decision", "manual_review"),
            "ats_score": ats_results.get("ats_score", 0),
            "missing_keywords": missing[:15],
            "unsupported_requirements": merged_unsup[:10] or fit_result.get("unsupported_requirements", [])[:10],
            "ats_feasible": ats_results.get("ats_score", 0) >= 85,
            "truth_safe_ats_ceiling": ceiling["truth_safe_ats_ceiling"],
            "truth_safe_ceiling_reason": ceiling["truth_safe_ceiling_reason"],
            "ceiling_limited_by": ceiling.get("ceiling_limited_by", []),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


def run_live_optimizer(
    state: dict,
    target_ats: int = 100,
    truth_safe: bool = True,
) -> dict:
    """
    Standalone live ATS optimizer (for tab 4). Returns opt_result + fit info.
    """
    opt_result = run_iterative_ats(state, target_score=target_ats, truth_safe=truth_safe)
    master_inv = parse_master_resume(state.get("base_resume_text", ""))
    fit = compute_job_fit_score(
        state.get("job_description", ""),
        master_inv,
        ats_score=opt_result.get("final_ats_score", 0),
    )
    fit_decision = "apply" if fit.get("apply") else ("reject" if fit.get("reject") else "manual_review")
    return {
        **opt_result,
        "fit_decision": fit_decision,
        "fit_reasons": fit.get("reasons", []),
    }

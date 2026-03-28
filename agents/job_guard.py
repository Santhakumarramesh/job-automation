
import os
import re
from agents.state import AgentState
from services import model_router

def guard_job_quality(state: AgentState):
    """
    Evaluates raw job descriptions using an LLM to instantly reject scams,
    low-quality posts, or jobs with absurd requirements.
    This replaces the old, brittle scikit-learn model.
    """
    print("🛡️ Running LLM-Powered Job Guard...")
    
    jd_text = state.get("job_description", "")
    if not jd_text.strip():
        return {"is_eligible": False, "eligibility_reason": "Job description is empty."}

    # First, run the simple heuristic checks for extreme seniority or security clearances
    if re.search(r'(10\+|12\+|15\+)\s*years?', jd_text, re.IGNORECASE) or \
       re.search(r'(top secret|ts/sci|dod clearance|security clearance)', jd_text, re.IGNORECASE):
        reason = "Inferred requirement for Security Clearance or 10+ YOE"
        print(f"🛡️ Job Guard blocked: {reason}")
        return {"is_eligible": False, "eligibility_reason": reason}

    # Now, use the LLM to check for more subtle red flags
    fast = os.getenv("CCP_FAST_PIPELINE", "").strip().lower() in ("1", "true", "yes")
    system_prompt = """You are an expert fraud detection model. Your task is to analyze a job description and determine if it is a scam, a multi-level marketing scheme, or has absurd requirements (e.g., 10+ years of experience for an entry-level role). 

    You must respond in a valid JSON format with two keys:
    1.  `"is_scam"`: a boolean (`true` if it is a scam/low-quality, `false` otherwise).
    2.  `"reason"`: a brief, one-sentence explanation for your decision.
    """

    human_prompt = f"Analyze the following job description:\n\n---\n{jd_text}"

    try:
        out = model_router.generate_json(
            prompt=human_prompt,
            system_prompt=system_prompt,
            task="fast" if fast else "reasoning",
            temperature=0.0,
            max_tokens=280,
            required_keys=("is_scam", "reason"),
        )
        result = out.get("data", {}) if out.get("status") == "ok" else {}
        if not isinstance(result, dict):
            result = {}

        if result.get("is_scam", False):
            reason = result.get("reason", "LLM detected it as low-quality or potential scam.")
            print(f"🛡️ Job Guard blocked: {reason}")
            return {"is_eligible": False, "eligibility_reason": reason}
        
        print("✅ Job Guard passed.")
        return {"is_eligible": True}

    except Exception as e:
        print(f"⚠️ Job Guard LLM failed: {e}. Allowing job to proceed as a fallback.")
        # Gracefully fallback if the LLM fails for any reason
        return {"is_eligible": True}

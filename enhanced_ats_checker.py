"""
Robust ATS Checker - Combines rule-based validation with LLM semantic analysis.
Designed to maximize resume pass rate on real ATS systems.
Adds: target_score, unsupported_requirements, truthful_missing_keywords,
job_fit_score, ats_format_score when master_resume_text is provided.
"""

import re
import json
import pandas as pd
from datetime import datetime
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# ATS compliance constants (from 100% ATS template)
ACTION_VERBS = [
    'achieved', 'exceeded', 'surpassed', 'accomplished', 'attained',
    'led', 'managed', 'directed', 'supervised', 'coordinated', 'orchestrated',
    'developed', 'created', 'designed', 'built', 'established', 'launched',
    'improved', 'enhanced', 'optimized', 'streamlined', 'upgraded', 'modernized',
    'analyzed', 'evaluated', 'assessed', 'researched', 'investigated',
    'implemented', 'executed', 'delivered', 'deployed', 'integrated',
    'increased', 'decreased', 'reduced', 'generated', 'saved', 'accelerated',
    'collaborated', 'partnered', 'facilitated', 'mentored', 'trained',
    'innovated', 'pioneered', 'transformed', 'automated', 'architected',
    'worked', 'utilized', 'supported', 'performed', 'applied', 'pioneered',
]
STANDARD_SECTIONS = [
    'summary', 'professional summary', 'profile', 'skills', 'technical skills',
    'experience', 'work experience', 'professional experience', 'employment',
    'education', 'academic', 'projects', 'certifications', 'certificates',
]
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
}


class EnhancedATSChecker:
    """Robust ATS checker: rule-based validation + LLM semantic analysis."""

    WEIGHTS = {
        'semantic_match': 0.35,   # LLM semantic relevance
        'keyword_match': 0.35,    # JD keywords in resume
        'formatting': 0.15,      # ATS-friendly format
        'action_verbs_metrics': 0.10,  # Strong bullets
        'structure': 0.05,       # Standard sections
    }

    def _extract_keywords(self, text, min_len=3):
        """Extract meaningful keywords from text (skills, tools, technologies)."""
        text_lower = text.lower()
        tech_phrases = [
            'python', 'sql', 'aws', 'azure', 'gcp', 'tensorflow', 'pytorch', 'scikit-learn',
            'machine learning', 'deep learning', 'nlp', 'data pipeline', 'etl', 'docker',
            'kubernetes', 'spark', 'pyspark', 'tableau', 'power bi', 'excel', 'git', 'ci/cd',
            'rest api', 'api', 'javascript', 'react', 'java', 'scala', 'r programming',
            'pandas', 'numpy', 'keras', 'cnn', 'lstm', 'xgboost', 'random forest',
            'agile', 'scrum', 'jira', 'confluence', 'snowflake', 'databricks', 'redshift',
        ]
        words = set(re.findall(r'\b[a-z0-9+#\.\-]{2,}\b', text_lower))
        phrases = [p for p in tech_phrases if p in text_lower]
        filtered = {w for w in words if w not in STOP_WORDS and len(w) >= min_len}
        return list(set(phrases) | filtered)

    def _check_formatting(self, resume_text):
        """Rule-based formatting check. Returns (score 0-100, issues list)."""
        issues = []
        score = 100
        text = resume_text[:15000]

        if re.search(r'\b(I|me|my|we|us|our)\b', text, re.I):
            issues.append('Contains pronouns (I, me, my) - use active voice')
            score -= 15
        if re.search(r'\b(responsible for|duties include|job was)\b', text, re.I):
            issues.append('Passive phrasing detected - use action verbs')
            score -= 10
        if not re.search(r'[•\-\*]\s', text):
            issues.append('Missing bullet points for achievements')
            score -= 20
        if re.search(r'<table|colspan|rowspan|┌|└|│', text, re.I):
            issues.append('Tables detected - ATS may misparse')
            score -= 25
        if re.search(r'https?://\S+', text) and len(re.findall(r'https?://\S+', text)) > 2:
            issues.append('Multiple raw URLs - use plain text (e.g., linkedin.com/in/name)')
            score -= 10

        return max(0, score), issues

    def _check_structure(self, resume_text):
        """Check for standard ATS section names. Returns (score 0-100, missing sections)."""
        text_upper = resume_text.upper()
        missing = []
        if not any(x in text_upper for x in ['SUMMARY', 'PROFILE', 'PROFESSIONAL SUMMARY']):
            missing.append('Summary/Profile')
        if not any(x in text_upper for x in ['SKILLS', 'TECHNICAL SKILLS', 'CORE COMPETENCIES']):
            missing.append('Skills')
        if not any(x in text_upper for x in ['EXPERIENCE', 'EMPLOYMENT', 'WORK EXPERIENCE', 'PROFESSIONAL EXPERIENCE']):
            missing.append('Experience')
        if not any(x in text_upper for x in ['EDUCATION', 'ACADEMIC']):
            missing.append('Education')
        score = max(0, 100 - len(missing) * 25)
        return score, missing

    def _check_action_verbs_and_metrics(self, resume_text):
        """Count bullets with action verbs and quantifiable metrics. Returns (score 0-100, details)."""
        bullets = re.findall(r'^[•\-\*]\s*(.+)$', resume_text, re.M) or re.findall(r'^\s*[-*]\s+(.+)$', resume_text, re.M)
        if not bullets:
            return 0, {'action_verbs': 0, 'metrics': 0, 'total_bullets': 0}

        action_count = 0
        metrics_count = 0
        for b in bullets:
            content = b.strip()
            if len(content) < 15:
                continue
            start = (content + ' ')[:60].lower()
            if any(v in start for v in ACTION_VERBS):
                action_count += 1
            if re.search(r'\d+%|\d+\s*(percent|%|million|thousand|k|K)\b|\$\d|reduced by|increased by|improved by|\d+\+', b, re.I):
                metrics_count += 1

        total = len(bullets)
        verb_score = min(100, (action_count / max(1, total)) * 130)
        metric_score = min(100, (metrics_count / max(1, total)) * 130)
        score = (verb_score + metric_score) / 2
        return round(score, 1), {'action_verbs': action_count, 'metrics': metrics_count, 'total_bullets': total}

    def _check_keyword_match(self, resume_text, job_description):
        """Extract JD keywords and check match in resume. Returns (score 0-100, missing list)."""
        jd_keywords = self._extract_keywords(job_description, min_len=2)
        resume_lower = resume_text.lower()
        matched = [k for k in jd_keywords if k in resume_lower or k.replace('-', ' ') in resume_lower]
        missing = [k for k in jd_keywords if k not in matched and k.replace('-', ' ') not in resume_lower]
        top_missing = [k for k in missing if len(k) >= 4][:15]
        score = (len(matched) / len(jd_keywords) * 100) if jd_keywords else 80
        return min(100, round(score, 1)), top_missing

    def _llm_semantic_check(self, resume_text, job_description, job_title, company_name, location):
        """LLM-based semantic analysis. Returns dict or None on failure."""
        system_prompt = """You are an expert ATS reviewer. Analyze the resume against the job and return ONLY valid JSON:
{
    "semantic_match_score": <0-100 integer>,
    "missing_keywords": [<5-10 critical skills/tech from JD missing in resume>],
    "strengths": "<one sentence>",
    "weaknesses": "<one sentence>",
    "overall_assessment": "<one sentence verdict>"
}"""

        human_prompt = f"""Job: {job_title} at {company_name} ({location})

Job Description:
{job_description[:4000]}

Resume:
{resume_text[:6000]}

Return ONLY the JSON object, no markdown or extra text."""

        for attempt in range(2):
            try:
                llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
                response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
                content = response.content.strip()
                if '```' in content:
                    content = re.sub(r'```json?\s*', '', content).replace('```', '').strip()
                analysis = json.loads(content)
                return analysis
            except (json.JSONDecodeError, Exception) as e:
                if attempt == 1:
                    print(f"⚠️ LLM ATS parse failed: {e}")
                    return None
        return None

    def comprehensive_ats_check(
        self,
        resume_text,
        job_description,
        job_title,
        company_name,
        location,
        target_score: int = 100,
        master_resume_text: Optional[str] = None,
    ):
        """Robust ATS check: rule-based + LLM, weighted combined score.
        When master_resume_text is provided: adds unsupported_requirements,
        truthful_missing_keywords, job_fit_score, ats_format_score.
        """
        print("🔬 Running robust ATS analysis (rule-based + semantic)...")

        resume_text = resume_text or ""
        job_description = job_description or ""

        # 1. Rule-based checks (always run)
        fmt_score, fmt_issues = self._check_formatting(resume_text)
        struct_score, missing_sections = self._check_structure(resume_text)
        avm_score, avm_details = self._check_action_verbs_and_metrics(resume_text)
        kw_score, missing_keywords = self._check_keyword_match(resume_text, job_description)

        # 2. LLM semantic (with fallback)
        llm_result = self._llm_semantic_check(resume_text, job_description, job_title, company_name, location)
        semantic_score = llm_result.get("semantic_match_score", 70) if llm_result else 70
        llm_missing = llm_result.get("missing_keywords", []) if llm_result else []
        if llm_missing and len(missing_keywords) < 5:
            missing_keywords = list(set(missing_keywords + llm_missing))[:15]

        # 3. Combined score (weighted)
        combined = (
            semantic_score * self.WEIGHTS['semantic_match'] +
            kw_score * self.WEIGHTS['keyword_match'] +
            fmt_score * self.WEIGHTS['formatting'] +
            avm_score * self.WEIGHTS['action_verbs_metrics'] +
            struct_score * self.WEIGHTS['structure']
        )
        ats_score = min(100, max(0, round(combined)))

        # ATS format score: formatting + structure (separate from keyword/semantic)
        ats_format_score = round((fmt_score + struct_score) / 2)

        # 4. Truth-safe outputs (when master resume provided)
        unsupported_requirements = []
        truthful_missing_keywords = []
        job_fit_score = None
        if master_resume_text and master_resume_text.strip():
            try:
                from agents.master_resume_guard import (
                    parse_master_resume,
                    get_truthful_missing_keywords,
                    get_unsupported_requirements,
                    compute_job_fit_score,
                )
                master_inv = parse_master_resume(master_resume_text)
                unsupported_requirements = get_unsupported_requirements(missing_keywords, master_inv)
                truthful_missing_keywords = get_truthful_missing_keywords(master_inv, missing_keywords)
                fit = compute_job_fit_score(job_description, master_inv, ats_score=ats_score)
                job_fit_score = fit.get("score", 0)
            except Exception as e:
                print(f"⚠️ Master resume guard failed: {e}")

        # 5. Build feedback
        feedback = []
        if llm_result:
            feedback.append(f"- **Overall Assessment:** {llm_result.get('overall_assessment', 'N/A')}")
            feedback.append(f"- **Strengths:** {llm_result.get('strengths', 'N/A')}")
            feedback.append(f"- **Weaknesses:** {llm_result.get('weaknesses', 'N/A')}")
        feedback.append(f"- **Formatting:** {fmt_score}% — {'OK' if not fmt_issues else '; '.join(fmt_issues)}")
        feedback.append(f"- **Keyword Match:** {kw_score}% — {'Strong' if kw_score >= 70 else f'Add: {", ".join(missing_keywords[:5])}'}")
        feedback.append(f"- **Action Verbs & Metrics:** {avm_score}% — {avm_details['action_verbs']} action verbs, {avm_details['metrics']} metrics in {avm_details['total_bullets']} bullets")
        if missing_sections:
            feedback.append(f"- **Missing Sections:** {', '.join(missing_sections)}")
        if unsupported_requirements:
            feedback.append(f"- **Unsupported JD requirements (do not add):** {', '.join(unsupported_requirements[:5])}")

        keyword_matches = {kw: False for kw in missing_keywords}
        formatting_issues = fmt_issues + ([f"Missing: {s}" for s in missing_sections] if missing_sections else [])

        print(f"✅ ATS Analysis complete. Score: {ats_score}% (semantic={semantic_score}, keywords={kw_score}, format={fmt_score})")

        result = {
            'ats_score': ats_score,
            'target_score': target_score,
            'ats_format_score': ats_format_score,
            'job_fit_score': job_fit_score,
            'unsupported_requirements': unsupported_requirements,
            'truthful_missing_keywords': truthful_missing_keywords,
            'feedback': feedback,
            'keyword_matches': keyword_matches,
            'formatting_issues': formatting_issues,
            'detailed_breakdown': {
                'semantic_score': semantic_score,
                'keyword_score': kw_score,
                'formatting_score': fmt_score,
                'action_verbs_metrics_score': avm_score,
                'structure_score': struct_score,
                'missing_keywords': missing_keywords,
                'missing_sections': missing_sections,
            }
        }
        return result

    def save_ats_results_to_excel(self, results, filename='ats_check_results.xlsx'):
        """Save comprehensive ATS results to Excel with full breakdown."""
        main_data = {
            'Check Date': [datetime.now()],
            'ATS Score': [results['ats_score']],
            'Semantic': [results['detailed_breakdown'].get('semantic_score', 0)],
            'Keywords': [results['detailed_breakdown'].get('keyword_score', 0)],
            'Formatting': [results['detailed_breakdown'].get('formatting_score', 0)],
            'Action Verbs & Metrics': [results['detailed_breakdown'].get('action_verbs_metrics_score', 0)],
            'Structure': [results['detailed_breakdown'].get('structure_score', 0)],
        }
        main_df = pd.DataFrame(main_data)

        feedback_data = {'Feedback': results['feedback']}
        feedback_df = pd.DataFrame(feedback_data)

        missing = results['detailed_breakdown'].get('missing_keywords', [])
        keyword_df = pd.DataFrame({'Missing Keywords & Skills': missing if missing else ['None']})

        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name='ATS_Score', index=False)
            feedback_df.to_excel(writer, sheet_name='Feedback', index=False)
            keyword_df.to_excel(writer, sheet_name='Missing_Keywords', index=False)

        print(f"✅ ATS results saved to {filename}")
        return filename

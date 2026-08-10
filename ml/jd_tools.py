"""
ml/jd_tools.py
Job Description Cleaner & Generator (#12)

Uses Llama 3 via Ollama to:
1. Clean JDs  — remove bias, standardise format, improve keyword targeting
2. Generate JDs — create full JD from job title + required skills list
3. Summarise JDs — short recruiter-friendly summary

Usage:
    from ml.jd_tools import clean_jd, generate_jd, summarise_jd

    cleaned   = clean_jd(raw_jd_text)
    generated = generate_jd("Senior Python Developer", ["Python", "AWS", "Docker"])
    summary   = summarise_jd(jd_text)
"""
import logging
from typing import Optional

from data.logger import get_logger
from ml.performance import timed

logger = get_logger("ml.jd_tools")

# ── System prompts ────────────────────────────────────────────────────────────

CLEANER_SYSTEM = """You are an expert technical recruiter and HR specialist.
Your job is to rewrite job descriptions to be:
1. Bias-free (remove gender-coded language, unnecessary requirements)
2. Clear and concise (remove jargon and corporate fluff)
3. Well-structured (Summary, Responsibilities, Requirements, Nice-to-have)
4. ATS-optimised (include relevant technical keywords naturally)
5. Inclusive (welcoming tone, focus on skills over credentials)

Return ONLY the rewritten job description. No preamble or explanation."""

GENERATOR_SYSTEM = """You are an expert technical recruiter writing job descriptions
for IT staffing. Write professional, clear, and inclusive job descriptions.
Structure: Brief summary, Key responsibilities (5-7 bullets), Required skills,
Nice-to-have skills, and a brief note about the work environment.
Keep it under 400 words. Return ONLY the job description."""

SUMMARISER_SYSTEM = """You are a technical recruiter assistant.
Summarise job descriptions into 2-3 sentences covering:
the role, key skills required, and type of candidate needed.
Be specific and factual. Return ONLY the summary."""

BIAS_CHECKER_SYSTEM = """You are an HR bias detection specialist.
Analyse the job description and identify:
1. Gender-coded words (e.g. 'rockstar', 'ninja', 'dominant')
2. Unnecessary requirements (e.g. degree requirements for technical roles)
3. Exclusionary language
4. Age-biased terms

Return a JSON object with keys:
- biased_words: list of problematic words/phrases found
- suggestions: list of replacement suggestions
- bias_score: 0-10 (0=no bias, 10=highly biased)
- summary: one sentence assessment

Return ONLY valid JSON, no markdown."""


# ── JD Cleaner ────────────────────────────────────────────────────────────────

@timed("clean_jd")
def clean_jd(raw_jd: str) -> dict:
    """
    Clean and standardise a job description.

    Args:
        raw_jd: raw job description text

    Returns:
        {
          "cleaned_jd": "...",
          "bias_report": {...},
          "word_count_before": 350,
          "word_count_after": 280,
        }
    """
    from ml.llm_client import chat

    if not raw_jd or not raw_jd.strip():
        raise ValueError("Job description cannot be empty")

    # First check for bias
    bias_report = check_bias(raw_jd)

    # Clean the JD
    prompt = f"""Please rewrite this job description following the guidelines:

ORIGINAL JD:
{raw_jd[:3000]}

Rewrite it now:"""

    cleaned = chat(prompt, system=CLEANER_SYSTEM, temperature=0.3)

    result = {
        "cleaned_jd":         cleaned.strip(),
        "bias_report":         bias_report,
        "word_count_before":   len(raw_jd.split()),
        "word_count_after":    len(cleaned.split()),
    }

    logger.info(
        f"JD cleaned: {result['word_count_before']} → {result['word_count_after']} words, "
        f"bias_score={bias_report.get('bias_score', 'N/A')}"
    )
    return result


@timed("check_bias")
def check_bias(jd_text: str) -> dict:
    """
    Check a JD for biased language and return a structured report.

    Returns dict with biased_words, suggestions, bias_score, summary
    """
    import json
    from ml.llm_client import chat

    prompt = f"""Analyse this job description for bias:

{jd_text[:2000]}

Return your analysis as JSON:"""

    try:
        response = chat(prompt, system=BIAS_CHECKER_SYSTEM, temperature=0.1)
        # Strip markdown fences if present
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        return json.loads(response.strip())
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Bias check JSON parse failed: {e}")
        return {
            "biased_words": [],
            "suggestions":  [],
            "bias_score":   0,
            "summary":      "Bias analysis unavailable",
        }


# ── JD Generator ─────────────────────────────────────────────────────────────

@timed("generate_jd")
def generate_jd(
    job_title: str,
    required_skills: list[str],
    nice_to_have: Optional[list[str]] = None,
    location: str = "Remote",
    yoe_min: float = 3.0,
    yoe_max: Optional[float] = None,
    additional_context: str = "",
) -> str:
    """
    Generate a complete job description from a title and skills list.

    Args:
        job_title:          e.g. "Senior Python Developer"
        required_skills:    e.g. ["Python", "AWS", "Docker"]
        nice_to_have:       optional bonus skills
        location:           work location
        yoe_min:            minimum years of experience
        yoe_max:            maximum years of experience
        additional_context: any extra context about the role

    Returns:
        Full job description string
    """
    from ml.llm_client import chat

    skills_str = ", ".join(required_skills)
    nice_str   = ", ".join(nice_to_have) if nice_to_have else "Not specified"
    yoe_str    = f"{yoe_min}+ years" if not yoe_max else f"{yoe_min}–{yoe_max} years"

    prompt = f"""Generate a job description for:

Title: {job_title}
Location: {location}
Experience Required: {yoe_str}
Required Skills: {skills_str}
Nice-to-have: {nice_str}
Additional Context: {additional_context or "Standard IT staffing role"}

Write the full job description now:"""

    result = chat(prompt, system=GENERATOR_SYSTEM, temperature=0.6)
    logger.info(f"JD generated for: {job_title} ({len(result.split())} words)")
    return result.strip()


# ── JD Summariser ─────────────────────────────────────────────────────────────

@timed("summarise_jd")
def summarise_jd(jd_text: str) -> str:
    """
    Generate a 2-3 sentence recruiter summary of a job description.

    Args:
        jd_text: full job description text

    Returns:
        Short summary string
    """
    from ml.llm_client import chat

    prompt = f"""Summarise this job description in 2-3 sentences:

{jd_text[:2000]}

Summary:"""

    result = chat(prompt, system=SUMMARISER_SYSTEM, temperature=0.2)
    logger.info(f"JD summarised: {len(result.split())} words")
    return result.strip()

"""Prompt construction for the job description parser.

Builds a structured prompt that instructs the generative LLM to convert
a ``JobParsingInput`` into a ``ParsedJobProfile`` JSON object.

The prompt is designed for use with a chat template — the system
instruction and user content are separated by the
``--- JOB POSTING ---`` marker so that
:meth:`~ai_service.llm.qwen_client.QwenGenerativeClient._build_messages`
can split them into ``system`` and ``user`` roles.
"""

from __future__ import annotations

from ai_service.job_schemas import JobParsingInput


# -------------------------------------------------------------------
# System instruction — compact but precise
# -------------------------------------------------------------------

_SYSTEM_INSTRUCTION = """\
You are a structured job-description parser.

TASK:
Convert the job posting below into a single JSON object matching the schema.

RULES:
1. Return ONLY valid JSON. No markdown fences, no prose, no explanation.
2. Create one criterion per distinct requirement, skill, certification, \
education item, or language requirement.
3. Use "required" for items stated as mandatory. Use "preferred" for items \
described as "a plus", "nice to have", "preferred", or "not required".
4. Do NOT treat preferred items as required.
5. Do NOT invent requirements absent from the input.
6. Do NOT infer experience years from seniority titles alone.
7. Do NOT infer proficiency (e.g. "expert") unless explicitly stated.
8. Do NOT convert responsibilities into skills unless the JD explicitly \
frames them as requirements.
9. Responsibilities go under criterion_type "responsibility" with \
importance "required".
10. Set source_text to the exact supporting fragment from the input.
11. Use null for missing optional fields. Use empty lists when none apply.
12. Keep names and canonical_name concise (no full sentences).
13. Do NOT generate IDs for criteria.
14. Do NOT translate source_text.
15. IGNORE company introduction, marketing, perks, and benefits — \
these are NOT candidate requirements.
16. Detect seniority from explicit terms: "intern", "junior", "mid", \
"senior", "lead", "principal". Do not guess."""

# -------------------------------------------------------------------
# Compact schema description
# -------------------------------------------------------------------

_SCHEMA_DESCRIPTION = """\
OUTPUT SCHEMA:
{
  "normalized_title": "string (concise standardized title)",
  "job_family": "string | null (e.g. 'Backend Development')",
  "seniority": "string | null (e.g. 'intern', 'junior', 'mid', 'senior')",
  "domains": ["string (industry/domain tags)"],
  "criteria": [
    {
      "criterion_type": "technical_skill | soft_skill | responsibility | \
experience | education | certification | language | domain_knowledge | \
location | work_authorization | other",
      "name": "string (concise name)",
      "canonical_name": "string | null (lowercase normalized, e.g. 'python')",
      "importance": "required | preferred",
      "minimum_years": "number | null",
      "proficiency": "string | null",
      "source_text": "string (exact fragment from input)"
    }
  ],
  "search_keywords": ["string"]
}"""


def build_parser_prompt(job: JobParsingInput) -> str:
    """Build the complete prompt for the generative parser.

    Parameters
    ----------
    job:
        Cleaned, structured job data.

    Returns
    -------
    str
        Full prompt string ready for the LLM.  The system instruction
        and schema come first, followed by the ``--- JOB POSTING ---``
        marker and the actual job data.
    """
    sections: list[str] = [
        _SYSTEM_INSTRUCTION,
        "",
        _SCHEMA_DESCRIPTION,
        "",
        "--- JOB POSTING ---",
        f"Title: {job.job_title}",
    ]

    if job.description:
        sections.append(f"\nDescription:\n{job.description}")

    if job.requirements:
        sections.append("\nRequirements:")
        for item in job.requirements:
            sections.append(f"- {item}")

    if job.responsibilities:
        sections.append("\nResponsibilities:")
        for item in job.responsibilities:
            sections.append(f"- {item}")

    sections.append("\n--- END JOB POSTING ---")
    sections.append("\nReturn the JSON object now:")

    return "\n".join(sections)


def build_repair_prompt(
    invalid_output: str,
    error_message: str,
) -> str:
    """Build a repair prompt after a failed parse attempt.

    Parameters
    ----------
    invalid_output:
        The raw LLM output that failed validation.
    error_message:
        The validation/parsing error description.

    Returns
    -------
    str
        Repair prompt requesting corrected JSON only.
    """
    return (
        "Your previous response was invalid.\n\n"
        "ERROR:\n"
        f"{error_message}\n\n"
        "YOUR PREVIOUS OUTPUT:\n"
        f"{invalid_output[:3000]}\n\n"
        "Return ONLY the corrected JSON object. "
        "No markdown fences, no prose, no explanation."
    )

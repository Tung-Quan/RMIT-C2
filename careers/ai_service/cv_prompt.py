"""Prompt construction for the CV parser.

Builds a structured prompt that instructs the generative LLM to convert
a ``CVParsingInput`` into a ``CandidateProfile`` JSON object.
"""

from __future__ import annotations

from ai_service.cv_schemas import CVParsingInput

_SYSTEM_INSTRUCTION = """\
You are a structured CV parser.

TASK:
Convert the candidate's CV text below into a single JSON object matching the schema.

RULES:
1. Return ONLY valid JSON. No markdown fences, no prose, no explanation.
2. Create one atomic evidence item per distinct skill, experience, project, education, etc.
3. Handle arbitrary section names logically.
4. Support English, Vietnamese, or mixed-language content seamlessly.
5. Set source_text to the exact or near-exact supporting fragment from the input. DO NOT TRANSLATE.
6. Do NOT invent skills, dates, organizations, qualifications, or experience.
7. Do NOT interpret hobbies as professional qualifications unless explicitly relevant.
8. EXCLUDE any contact details or protected personal attributes (name, email, phone, address, photo, age, gender, marital status, religion, ethnicity, political affiliation, health).
9. Use null for missing optional fields. Use empty lists when none apply.
10. Keep names and canonical_name concise (no full sentences).
11. Do NOT generate IDs for evidence items.
12. Do not reveal chain-of-thought."""

_SCHEMA_DESCRIPTION = """\
OUTPUT SCHEMA:
{
  "headline": "string | null (e.g. 'Software Engineer')",
  "summary": "string | null",
  "evidence_items": [
    {
      "evidence_type": "technical_skill | soft_skill | work_experience | project_experience | research_experience | education | certification | language | achievement | activity | availability | other",
      "name": "string (concise name)",
      "canonical_name": "string | null (lowercase normalized)",
      "description": "string | null",
      "organization": "string | null",
      "role": "string | null",
      "start_date": "string | null",
      "end_date": "string | null",
      "skills": ["string"],
      "source_text": "string (exact fragment from input)"
    }
  ],
  "search_keywords": ["string"]
}"""

def build_parser_prompt(cv: CVParsingInput) -> str:
    sections = [
        _SYSTEM_INSTRUCTION,
        "",
        _SCHEMA_DESCRIPTION,
        "",
        "--- CV TEXT ---",
        cv.document_text,
        "",
        "--- END CV TEXT ---",
        "Return the JSON object now:"
    ]
    return "\n".join(sections)

def build_repair_prompt(invalid_output: str, error_message: str) -> str:
    return (
        "Your previous response was invalid.\n\n"
        "ERROR:\n"
        f"{error_message}\n\n"
        "YOUR PREVIOUS OUTPUT:\n"
        f"{invalid_output[:3000]}\n\n"
        "Return ONLY the corrected JSON object. "
        "No markdown fences, no prose, no explanation."
    )

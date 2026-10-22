import logging
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

SKILL_DICTIONARY = [
    "Python",
    "JavaScript",
    "TypeScript",
    "React",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "AWS",
    "EC2",
    "S3",
    "RDS",
    "Lambda",
    "API Gateway",
    "CloudWatch",
    "Docker",
    "Git",
    "GitHub",
    "Machine Learning",
    "Deep Learning",
    "NLP",
    "Computer Vision",
    "Data Analysis",
    "REST API",
    "HTML",
    "CSS",
    "Tailwind",
    "Linux",
]


def _skill_regex(skill: str) -> str:
    escaped = re.escape(skill).replace(r"\ ", r"\s+")
    return rf"(?<![A-Za-z0-9+#-]){escaped}(?![A-Za-z0-9+#-])"


def extract_skills(text: str) -> list[str]:
    if not text:
        return []
    skills: list[str] = []
    for skill in SKILL_DICTIONARY:
        if re.search(_skill_regex(skill), text, flags=re.IGNORECASE):
            skills.append(skill)
    return skills


def calculate_text_similarity(cv_text: str, job_description: str) -> float:
    if not cv_text.strip() or not job_description.strip():
        return 0.0
    try:
        vectors = TfidfVectorizer(stop_words="english").fit_transform([cv_text, job_description])
        return float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0])
    except ValueError:
        logger.exception("Unable to calculate TF-IDF similarity")
        return 0.0


def build_suggested_improvements(missing_skills: list[str], matched_skills: list[str]) -> list[str]:
    suggestions: list[str] = []
    if missing_skills:
        suggestions.append(
            "Add concrete project or coursework evidence for: "
            + ", ".join(missing_skills[:8])
            + "."
        )
    if matched_skills:
        suggestions.append(
            "Move your strongest matching skills near the top of the CV: "
            + ", ".join(matched_skills[:6])
            + "."
        )
    suggestions.extend(
        [
            "Quantify work, class project, or lab outcomes with metrics where possible.",
            "Mirror important keywords from the job description while keeping the CV truthful.",
            "Add a short technical projects section if the role is engineering or data focused.",
        ]
    )
    return suggestions


def build_cover_letter(
    company_name: str,
    position_title: str,
    matched_skills: list[str],
    missing_skills: list[str],
) -> str:
    skill_sentence = (
        "My background includes " + ", ".join(matched_skills[:5]) + "."
        if matched_skills
        else "My academic projects and experience align with the role requirements."
    )
    growth_sentence = (
        "I am also actively strengthening my experience with " + ", ".join(missing_skills[:3]) + "."
        if missing_skills
        else "I am excited to contribute quickly and keep learning from your engineering team."
    )
    return (
        f"Dear Hiring Team,\n\n"
        f"I am excited to apply for the {position_title} role at {company_name}. "
        f"{skill_sentence} I enjoy turning technical concepts into practical solutions "
        f"and would welcome the chance to contribute to real projects with your team. "
        f"{growth_sentence}\n\n"
        f"Thank you for considering my application. I would be grateful for the "
        f"opportunity to discuss how my skills and motivation fit this role.\n\n"
        f"Sincerely,\n"
        f"Your Name"
    )


def analyze_match(
    cv_text: str,
    job_description: str,
    company_name: str = "the company",
    position_title: str = "this role",
) -> dict:
    job_skills = extract_skills(job_description)
    cv_skills = extract_skills(cv_text)
    matched_skills = [skill for skill in job_skills if skill in cv_skills]
    missing_skills = [skill for skill in job_skills if skill not in cv_skills]

    skill_score = len(matched_skills) / len(job_skills) if job_skills else 0.0
    text_similarity_score = calculate_text_similarity(cv_text, job_description)
    final_score = round((0.7 * skill_score + 0.3 * text_similarity_score) * 100)
    final_score = max(0, min(100, int(final_score)))

    return {
        "match_score": final_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "suggested_improvements": build_suggested_improvements(missing_skills, matched_skills),
        "cover_letter": build_cover_letter(
            company_name, position_title, matched_skills, missing_skills
        ),
    }


def generate_interview_questions(
    job_description: str,
    missing_skills: list[str] | None = None,
    count: int = 5,
) -> list[dict[str, str]]:
    job_skills = extract_skills(job_description)
    focus_skills = (missing_skills or []) + [
        skill for skill in job_skills if skill not in (missing_skills or [])
    ]
    questions: list[dict[str, str]] = []

    for skill in focus_skills[:count]:
        questions.append(
            {
                "question": f"How have you used {skill} in a project or coursework setting?",
                "answer_hint": (
                    "Use a short STAR answer and mention the problem, your action, and the result."
                ),
            }
        )

    default_questions = [
        {
            "question": "Tell me about a technical project you are proud of.",
            "answer_hint": "Explain the goal, tools used, your contribution, and what you learned.",
        },
        {
            "question": "How do you approach learning an unfamiliar technology?",
            "answer_hint": (
                "Mention documentation, small experiments, feedback, and applying it in a project."
            ),
        },
        {
            "question": "Describe a time you debugged a difficult issue.",
            "answer_hint": (
                "Focus on evidence gathering, narrowing the cause, and validating the fix."
            ),
        },
    ]

    for question in default_questions:
        if len(questions) >= count:
            break
        questions.append(question)

    return questions[:count]

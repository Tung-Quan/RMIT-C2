from app.services.ai_service import analyze_match, extract_skills


def test_skill_extraction_and_scoring():
    cv_text = "Built Python FastAPI REST API services with PostgreSQL, Docker, Git, and AWS S3."
    job_description = "Need Python, FastAPI, SQL, PostgreSQL, AWS, S3, Docker, and React."

    result = analyze_match(cv_text, job_description, "CloudCo", "Backend Intern")

    assert "Python" in extract_skills(cv_text)
    assert "React" in result["missing_skills"]
    assert "Python" in result["matched_skills"]
    assert 0 <= result["match_score"] <= 100
    assert result["match_score"] > 50

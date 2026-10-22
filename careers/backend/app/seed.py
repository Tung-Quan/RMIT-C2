import random
from datetime import datetime, timedelta

from app.core.security import get_password_hash
from app.db.database import Base, SessionLocal, engine
from app.db.models import (
    CandidateProfile,
    Company,
    CandidateApplication,
    JobPosting,
    User,
)


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Starting seed process...")

        # 1. Create Demo Candidate
        candidate_email = "demo@student.edu"
        candidate = db.query(User).filter(User.email == candidate_email).first()
        if not candidate:
            candidate = User(
                email=candidate_email,
                full_name="Demo Candidate",
                hashed_password=get_password_hash("password123"),
                role="candidate",
            )
            db.add(candidate)
            db.commit()
            db.refresh(candidate)

        # 2. Create Candidate Profile
        if not candidate.candidate_profile:
            profile = CandidateProfile(
                user_id=candidate.id,
                full_name="Demo Candidate",
                university="Tech University",
                major="Computer Science",
                graduation_year=2025,
                bio="Passionate software engineering student.",
            )
            db.add(profile)
            db.commit()

        # 3. Create Demo HR
        hr_email = "hr@company.com"
        hr_user = db.query(User).filter(User.email == hr_email).first()
        if not hr_user:
            hr_user = User(
                email=hr_email,
                full_name="Demo HR",
                hashed_password=get_password_hash("password123"),
                role="hr",
            )
            db.add(hr_user)
            db.commit()
            db.refresh(hr_user)

        # 4. Create Company
        company = db.query(Company).filter(Company.owner_user_id == hr_user.id).first()
        if not company:
            company = Company(
                owner_user_id=hr_user.id,
                name="Tech Innovators Inc.",
                description="Leading tech company in AI and Cloud.",
                website="https://techinnovators.com",
                industry="Technology",
                location="San Francisco, CA",
            )
            db.add(company)
            db.commit()
            db.refresh(company)

        # Helper lists for random data
        titles = [
            "Software Engineer Intern",
            "Data Scientist Intern",
            "Product Manager Intern",
            "UI/UX Designer Intern",
            "Cloud Engineer Intern",
            "DevOps Intern",
            "Marketing Intern",
            "Business Analyst Intern",
        ]
        companies = [
            "Google",
            "Amazon",
            "Microsoft",
            "Meta",
            "Apple",
            "Netflix",
            "Tesla",
            "Stripe",
            "Airbnb",
            "Uber",
            "Tech Innovators Inc.",
            "Startup X",
            "Global Systems",
        ]
        locations = [
            "San Francisco, CA",
            "New York, NY",
            "Seattle, WA",
            "Austin, TX",
            "London, UK",
            "Remote",
            "Berlin, Germany",
        ]

        # 5. Create Job Postings (for pagination, let's create 50)
        existing_jobs = db.query(JobPosting).count()
        if existing_jobs < 50:
            print("Creating Job Postings...")
            for i in range(50 - existing_jobs):
                job = JobPosting(
                    company_id=company.id,
                    created_by_user_id=hr_user.id,
                    title=f"{random.choice(titles)} - Batch {i}",
                    description=(
                        "We are looking for enthusiastic interns to join our amazing team. "
                        "You will work on cutting-edge technologies."
                    ),
                    requirements=(
                        "Experience with Python, JavaScript, or similar technologies. "
                        "Strong problem-solving skills."
                    ),
                    location=random.choice(locations),
                    employment_type=random.choice(["early_career", "full_time", "part_time"]),
                    work_mode=random.choice(["onsite", "hybrid", "remote"]),
                    salary_min=random.randint(4000, 6000),
                    salary_max=random.randint(6000, 9000),
                    status="published",
                    deadline=datetime.now().date() + timedelta(days=random.randint(10, 90)),
                )
                db.add(job)
            db.commit()

        # 6. Create candidate application records (50 for pagination)
        existing_apps = (
            db.query(CandidateApplication)
            .filter(CandidateApplication.user_id == candidate.id)
            .count()
        )
        if existing_apps < 50:
            print("Creating candidate application records...")
            statuses = [
                "Saved",
                "Applied",
                "Interview",
                "Offer",
                "Rejected",
                "Accepted",
            ]
            for i in range(50 - existing_apps):
                app = CandidateApplication(
                    user_id=candidate.id,
                    company_name=random.choice(companies),
                    position_title=f"{random.choice(titles)} #{i}",
                    job_description=(
                        "Standard software engineering role focusing on "
                        "backend systems and API design."
                    ),
                    application_status=random.choice(statuses),
                    deadline=datetime.now().date() + timedelta(days=random.randint(5, 60)),
                    notes=f"Application {i} note. Prepared resume and cover letter.",
                )
                db.add(app)
            db.commit()

        print("Seed data ready!")
        print(f"Candidate Account: {candidate_email} / password123")
        print(f"HR Account: {hr_email} / password123")
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run()

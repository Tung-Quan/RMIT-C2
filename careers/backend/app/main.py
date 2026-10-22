from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tide_gateway import install_tide_gateway
from app.core.logging_config import setup_logging
from app.db.database import Base, engine
from app.dependencies import get_db
from app.routers import (
    ai,
    applications,
    auth,
    candidate,
    companies,
    dashboard,
    documents,
    hr,
    jobs,
    processing_jobs,
)
from app.routers import tide_documents

setup_logging()
settings = get_settings()

if settings.STORAGE_BACKEND.lower() == "local":
    Path(settings.LOCAL_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.PROJECT_NAME, debug=settings.APP_DEBUG)
install_tide_gateway(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local files are served only by the authenticated document ownership endpoint.


@app.on_event("startup")
def create_tables_for_local_mvp() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in columns:
            with engine.begin() as connection:
                if engine.dialect.name == "sqlite":
                    connection.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN role "
                            "VARCHAR(20) NOT NULL DEFAULT 'candidate'"
                        )
                    )
                else:
                    connection.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                            "role VARCHAR(20) NOT NULL DEFAULT 'candidate'"
                        )
                    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/live", include_in_schema=False)
def liveness():
    return {
        "status": "alive",
        "service": "careers-api",
    }


@app.get("/health/ready", include_in_schema=False)
def readiness(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "service": "careers-api",
        "dependencies": {
            "postgres": True,
        },
    }


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(auth.router)
app.include_router(tide_documents.router)
app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(ai.router)
app.include_router(dashboard.router)
app.include_router(candidate.router)
app.include_router(companies.router)
app.include_router(jobs.router)
app.include_router(hr.router)
app.include_router(processing_jobs.router)

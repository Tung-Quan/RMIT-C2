import os

# ruff: noqa: E402

POSTGRES_TEST_DATABASE_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = POSTGRES_TEST_DATABASE_URL or "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_UPLOAD_DIR"] = ".test_uploads"

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from app.db.database import Base, engine
from app.main import app


def _reset_postgres_schema() -> None:
    engine.dispose()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def _run_postgres_migrations() -> None:
    _reset_postgres_schema()
    config = Config("alembic.ini")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def reset_database():
    if POSTGRES_TEST_DATABASE_URL:
        _run_postgres_migrations()
    else:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    yield
    if POSTGRES_TEST_DATABASE_URL:
        _reset_postgres_schema()
    else:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

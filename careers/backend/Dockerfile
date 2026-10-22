ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ARG INSTALL_PYTHON_DEPENDENCIES=1
USER root

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN if [ "$INSTALL_PYTHON_DEPENDENCIES" = "1" ]; then pip install --no-cache-dir -r requirements.txt; fi

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser pytest.ini .
COPY --chown=appuser:appuser tide_tests ./tide_tests

RUN mkdir -p uploads && \
    if ! id -u appuser >/dev/null 2>&1; then useradd -m -s /bin/bash appuser; fi && \
    chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

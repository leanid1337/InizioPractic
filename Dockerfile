# Stages: base -> test (pytest), base -> runtime (gunicorn).
# `runtime` is LAST, so a plain `docker build` (and Render) produces the server image.

# ---- base: runtime deps + app code ----
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 appuser

# ---- test: dev deps + tests (used by the `tests` compose service) ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY pyproject.toml .
COPY tests ./tests
# /srv is root-owned; keep coverage data in a writable place.
ENV COVERAGE_FILE=/tmp/.coverage
USER appuser
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]

# ---- runtime: production server (default target) ----
FROM base AS runtime
USER appuser
# Render (and most PaaS) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 30 --access-logfile - "app:create_app()"

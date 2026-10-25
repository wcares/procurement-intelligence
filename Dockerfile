# Backend image: the API (default command) and, with another command, a job worker:
#   docker run ... procintel-api                                         -> uvicorn procintel.api.app:app
#   docker run ... procintel-api python -m procintel.jobs.worker         -> a worker (needs PROCINTEL_DB_URL)
# Every endpoint (database, vector store, models) is an environment setting; see .env.example and compose.yaml.
ARG PYTHON_IMAGE=python:3.13-slim

# packages are installed here; some (PyStemmer) compile from source, so this stage has a compiler
FROM ${PYTHON_IMAGE} AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/
RUN pip install --prefix=/install -r /tmp/requirements.lock

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PROCINTEL_DATA_DIR=/data
WORKDIR /app
COPY --from=deps /install /usr/local
COPY src ./src
COPY eval ./eval
RUN useradd --create-home --uid 1001 app && mkdir -p /data && chown app /data /app/eval
USER app
# DuckDB's postgres extension, so PROCINTEL_DB_URL can point at Postgres
RUN python -m procintel.core.db install
EXPOSE 8000
CMD ["uvicorn", "procintel.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

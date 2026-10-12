# Build from the repo root:  docker build -f demo_api/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

RUN pip install --no-cache-dir \
        "fastapi==0.143.0" "uvicorn==0.53.0" "presidio-analyzer==2.2.364" "spacy==3.8.16" \
    && python -m spacy download en_core_web_sm

# Only the inline fast path ships. No LLM, database, or learning code is in the image.
COPY agentshield/__init__.py agentshield/types.py agentshield/pipeline.py agentshield/ner.py agentshield/
COPY demo_api/__init__.py demo_api/app.py demo_api/

RUN useradd --create-home --uid 10001 shield
USER shield

CMD exec uvicorn demo_api.app:app --host 0.0.0.0 --port ${PORT} --no-access-log --workers 1

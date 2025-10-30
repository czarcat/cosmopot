# syntax=docker/dockerfile:1.4
FROM python:3.11-slim as builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/app
COPY frontend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --shell /bin/bash appuser

WORKDIR /srv/app
ENV PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONPATH=/srv/app

COPY --from=builder /wheels /wheels
COPY --from=builder /tmp/app/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --find-links=/wheels -r /tmp/requirements.txt

COPY frontend/app ./app

RUN chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=20s CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

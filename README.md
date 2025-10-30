# Backend Service

This repository contains a FastAPI-based backend scaffold with structured logging, async database
support via SQLAlchemy, and Alembic migrations.

## Development

Install dependencies (development extras include linting and testing tools):

```bash
pip install -e .[dev]
```

Run the application locally:

```bash
uvicorn backend.main:app --reload
```

Or via Docker Compose (includes Postgres):

```bash
docker compose up --build
```

Execute the tests:

```bash
pytest
```

Additional tooling is configured via `pre-commit`, `ruff`, `black`, and `mypy` for quality gates.

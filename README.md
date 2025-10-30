# User Service Domain

This repository defines a minimal user domain consisting of SQLAlchemy models, Alembic migrations, Pydantic schemas, repository helpers, and a lightweight service layer. The accompanying pytest suite exercises the main workflows and database constraints.

## Components

- **Models**: Located in `src/user_service/models.py`, covering `users`, `user_profiles`, `user_sessions`, and the supporting `subscriptions` table.
- **Schemas**: Pydantic DTOs in `src/user_service/schemas.py` provide strict validation for create/update/read operations.
- **Repositories & Services**: Encapsulate database access patterns and high-level orchestration under `src/user_service/repository.py` and `src/user_service/services.py`.
- **Migrations**: Alembic migration scripts live under `migrations/`. Apply them with `alembic upgrade head`.
- **Tests**: Async pytest coverage in `tests/` ensures constraints, cascades, and service logic behave as expected.
- **Documentation**: An ERD-style overview is documented in `docs/user_domain.md`.

## Running the tests

Install the project dependencies and execute the tests:

```bash
pip install -e .
pytest
```

The tests automatically run the Alembic migrations against an isolated SQLite database for each scenario.

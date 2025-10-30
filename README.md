feat/compose-dev-stack-p0
# Compose developer stack

This repository ships a batteries-included Docker Compose stack for local development. It bundles the
FastAPI backend, Celery worker, Python-powered frontend, and the required infrastructure services:
PostgreSQL 15, Redis 7, RabbitMQ 3.12, MinIO (S3 compatible storage), Nginx reverse proxy, Prometheus,
Grafana, and a Sentry relay.

All application containers are built from multi-stage Dockerfiles using Python 3.11 slim images with
production-friendly defaults (non-root users, health checks, dependency wheels, minimal base packages).

## Prerequisites

- Docker Engine 24+
- Docker Compose plugin (bundled with Docker Desktop / Engine)
- GNU Make (optional, but all helper commands assume it is available)

## Getting started

1. **Clone & configure environment variables**

   ```bash
   cp .env.example .env.docker
   # Adjust passwords/keys if desired
   ```

   The `.env.docker` file is committed with sane defaults for local usage. Update values if you require
   custom credentials.

2. **Start the stack**

   ```bash
   make up
   ```

   This builds the Python backend/worker/frontend images (caching dependency wheels in a builder stage)
   and launches every service with sensible restart policies, resource limits, named volumes, and shared
   networks.

3. **Verify connectivity**

   Once `docker compose ps` shows all containers as `running`/`healthy`, execute:

   ```bash
   make connectivity
   ```

   The helper script hits the nginx reverse proxy on `http://localhost:8080` and checks:

   - `/api/health` → FastAPI backend health (database, Redis, RabbitMQ, MinIO probes)
   - `/grafana/api/health` → Grafana API availability
   - `/prometheus/-/healthy` → Prometheus target
   - `/minio/metrics` → MinIO console endpoint

   You can also explore:

   - API docs: [http://localhost:8080/api/docs](http://localhost:8080/api/docs)
   - Frontend dashboard: [http://localhost:8080/](http://localhost:8080/)
   - Grafana: [http://localhost:8080/grafana/](http://localhost:8080/grafana/)
   - Prometheus: [http://localhost:8080/prometheus/](http://localhost:8080/prometheus/)
   - MinIO console: [http://localhost:8080/minio/](http://localhost:8080/minio/)

## Helpful commands

All commands automatically use `.env.docker`. Override with `ENV_FILE=<path>` if required.

| Command | Description |
| --- | --- |
| `make up` | Build and start the entire stack in the background |
| `make down` | Stop containers but keep volumes |
| `make destroy` | Stop everything and remove named volumes |
| `make logs` | Tail logs for every service |
| `make tail TAIL_SERVICE=backend` | Tail logs for a specific service |
| `make ps` | Show container status |
| `make connectivity` | Run HTTP connectivity checks via nginx |

## Service inventory

| Service | Tech | Notes |
| --- | --- | --- |
| `backend` | FastAPI + Uvicorn | Exposes `/api`, instrumented with Prometheus metrics, publishes Celery tasks |
| `worker` | Celery | Consumes tasks via RabbitMQ broker, persists results in Redis |
| `frontend` | FastAPI (Jinja) | Simple status dashboard consuming backend health |
| `nginx` | nginx:1.25-alpine | The only service exposed to the host (`localhost:8080`) |
| `postgres` | PostgreSQL 15 | Persistent data volume `postgres_data` |
| `redis` | Redis 7 | Volume-backed cache/queue |
| `rabbitmq` | RabbitMQ 3.12 | Management + Prometheus plugins enabled, volume `rabbitmq_data` |
| `minio` | MinIO | S3-compatible storage, console reachable through nginx |
| `prometheus` | Prometheus v2.47 | Scrapes backend, self, and RabbitMQ metrics |
| `grafana` | Grafana 10 | Auto-provisioned Prometheus data source |
| `sentry-relay` | getsentry/relay | Relays SDK traffic to upstream Sentry (defaults to sentry.io) |

Two networks are defined:

- `core`: default bridge network for application and infrastructure containers
- `monitoring`: shared by Prometheus, Grafana, and nginx to isolate observability traffic

Persistent named volumes keep state (`postgres_data`, `redis_data`, `rabbitmq_data`, `minio_data`,
`grafana_data`, `prometheus_data`).

## Default credentials

| Service | Via nginx | Username | Password |
| --- | --- | --- | --- |
| Grafana | http://localhost:8080/grafana/ | `${GRAFANA_ADMIN_USER}` | `${GRAFANA_ADMIN_PASSWORD}` |
| MinIO console | http://localhost:8080/minio/ | `${MINIO_ROOT_USER}` | `${MINIO_ROOT_PASSWORD}` |
| RabbitMQ management | _internal only_ (`http://rabbitmq:15672`) | `${RABBITMQ_DEFAULT_USER}` | `${RABBITMQ_DEFAULT_PASS}` |

Update these values in `.env.docker` before sharing the stack with a wider team. Prometheus reuses the
RabbitMQ credentials for metrics scraping, so adjust `prometheus/prometheus.yml` if you change them.

## Configuration reference

The following environment variables are consumed by the stack (see `.env.example` for details):

- **PostgreSQL**: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`
- **Celery / messaging**: `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`
- **Object storage**: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_ENDPOINT`, `MINIO_REGION`
- **Sentry**: `SENTRY_DSN`, `SENTRY_RELAY_UPSTREAM_URL`, `SENTRY_RELAY_PORT`
- **Frontend/backend tuning**: `BACKEND_UVICORN_WORKERS`
- **Grafana**: `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`

The Sentry relay entrypoint renders a configuration file at runtime using the variables above. Replace `SENTRY_DSN` with a valid DSN that routes through the relay (`http://<public>:<secret>@sentry-relay:3000/<project>`), and point `SENTRY_RELAY_UPSTREAM_URL` to your upstream Sentry instance.

## Troubleshooting

- **Containers not healthy**: Run `docker compose ps` to identify failing services, then inspect logs with
  `make tail TAIL_SERVICE=<service>`.
- **Port collisions**: The stack binds nginx to `localhost:8080`. Adjust the port in `docker-compose.yml` if
  the host already uses it.
- **Database migrations**: The backend ships without migrations. Use `docker compose exec backend bash`
  to apply schema changes as needed.
- **Slow startup**: The Celery worker waits for RabbitMQ and Redis to become reachable. Initial health checks
  might report `degraded` until all dependencies pass.
- **Cleaning state**: Run `make destroy` to wipe data volumes and start from a clean slate.
- **Connectivity script fails**: Ensure nginx is running (`make tail TAIL_SERVICE=nginx`) and that your
  firewall allows connections to `localhost:8080`.

## Extending the stack

- Add additional API routers inside `backend/app` and Celery tasks in `backend/app/tasks.py`.
- Attach new services (e.g., Jaeger, Loki) by following the established pattern: create a directory with
  service-specific config, mount it in `docker-compose.yml`, and wire the service through nginx if it needs
  host access.
- Update `prometheus/prometheus.yml` and Grafana provisioning files to capture new metrics endpoints.

## License

This project is distributed under the MIT License. Modify and adapt the stack as needed for your
engineering workflows.

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
main

# Continuous Integration and Delivery Playbook

This document describes the CI/CD workflows configured in this repository.

## Overview

The pipeline is powered by GitHub Actions and consists of the following workflows:

- **CI (`.github/workflows/ci.yml`)**: Runs linting, type checking, and automated tests for backend, bot, and frontend code with coverage enforced at >80%.
- **Docker Build & Security Scan (`.github/workflows/docker.yml`)**: Builds container images, caches build artifacts, and runs Trivy vulnerability scans.
- **Semantic PR (`.github/workflows/semantic-pr.yml`)**: Enforces Conventional Commit semantics on pull request titles and commit messages.
- **Release (`.github/workflows/release.yml`)**: Creates tagged releases and generates changelogs. Provides an optional workflow dispatch to bump versions.
- **Deploy (`.github/workflows/deploy.yml`)**: Implements manual deployment gates for staging and production tied to release tags.

## CI Workflow Details

### Python

- `Lint Python Code`: Runs Ruff linting and Black formatting checks.
- `Type Check Python`: Runs mypy with strict settings.
- `Test Backend`: Executes backend pytest suite with PostgreSQL and Redis services, generating coverage reports.
- `Test Bot`: Executes bot pytest suite (Redis-backed), generating coverage reports.

### Frontend

- `Lint Frontend`: Runs ESLint, Stylelint, and Prettier checks using pnpm 8.15.8 with cached dependencies.
- `Type Check Frontend`: Runs TypeScript/Vue type checks via `pnpm typecheck`.
- `Test Frontend`: Runs Vitest with coverage enforcement (>80%).

### Coverage Reporting

Coverage artifacts are uploaded for backend, bot, and frontend components. The combined coverage summary is appended to the GitHub Actions job summary.

## Docker and Security

- Builds backend, bot (if Dockerfile exists), worker, and frontend images using Buildx with GitHub Actions cache storage (`type=gha`).
- Pushes images to GitHub Container Registry on non-PR events.
- Runs Trivy scans on each image and uploads SARIF reports to GitHub Security tab.

## Semantic Commits

- Validates PR titles using `amannn/action-semantic-pull-request`.
- Validates commit messages using a custom Git script that enforces Conventional Commits format.
- Produces a summary in the PR checks for easy visibility.

## Release Management

- Automatically generates changelog entries based on commit history between tags.
- Publishes GitHub releases with instructions for pulling Docker images.
- Optional workflow dispatch to bump versions and tag releases.

## Deployment Process

- Manual workflow dispatch that requires selecting environment (staging/production) and release tag.
- Validates that release tags exist and follow semantic versioning.
- Optionally runs pre-deployment smoke tests.
- Pulls container images, runs Trivy scans, and simulates deployment steps (placeholder commands to be replaced with real deployment automation).
- Provides rollback and notification steps.

## Branch Policies

Refer to [`.github/BRANCH_PROTECTION.md`](../.github/BRANCH_PROTECTION.md) for recommended branch protection and naming rules.

## Required Secrets

The workflows assume the following GitHub Secrets are available:

- `GITHUB_TOKEN` (provided automatically by GitHub Actions)
- `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` (optional if pushing to Docker Hub)

## Local Development

- Use `pre-commit run --all-files` to mirror linting and test checks locally.
- Use `make` targets from `Makefile` for Docker-based workflows.
- Frontend SPA requires pnpm 8.15.8. The `packageManager` field in `frontend/spa/package.json` pins the version to ensure consistency between local development and CI.

## Troubleshooting

- **Missing Coverage Summary**: Ensure tests generate coverage artifacts (`coverage-*` files in backend/bot and `coverage/` directory in frontend).
- **Semantic Check Failures**: Update PR titles and commit messages to match Conventional Commit format.
- **Docker Build Failures**: Confirm Dockerfiles exist and build locally with `docker build`.
- **Trivy Alerts**: Review SARIF reports in the Security tab and patch vulnerabilities promptly.

## Future Enhancements

- Integrate automated database migrations during deployments.
- Add dynamic application security testing (DAST) stage.
- Push release notes to external communication channels (Slack, Teams).

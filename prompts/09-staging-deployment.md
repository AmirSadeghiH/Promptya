# Phase 09 — Staging Deployment

## Objective

Create a repeatable staging environment that behaves sufficiently like production to expose deployment failures before launch.

## Required Investigation

Inspect:
- deployment files
- Docker image/build
- environment variables
- database initialization
- migrations
- static collection
- media storage
- reverse proxy
- TLS assumptions
- logging
- health checks
- provider configuration
- backup/restore procedure

## Required Work

Establish:

1. reproducible build
2. deterministic configuration
3. database migration procedure
4. static/media procedure
5. health checks
6. log inspection procedure
7. rollback procedure
8. smoke-test checklist
9. secret injection procedure

Staging must not use production credentials accidentally.

## Hard Prohibitions

- Do not deploy using hard-coded secrets.
- Do not skip migrations.
- Do not treat a successful container build as proof of application health.
- Do not make production data disposable without explicit approval.
- Do not introduce Kubernetes or microservices.

## Acceptance Criteria

A clean environment can be deployed using documented steps.

Smoke tests must cover:
- homepage
- auth
- email verification flow
- prompt/post creation
- AI Studio
- credits
- challenge/mission paths
- static/media
- staff/admin access
- health checks

## Verification

Perform a fresh staging deployment and execute the smoke-test checklist.

## Final Report

Include exact deployment steps, environment requirements, smoke-test results, and rollback procedure.

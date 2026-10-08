# Phase 02 — Production Architecture

## Objective

Harden the application architecture so Promptya can be deployed and operated reliably as a real product.

## Required Investigation

Inspect:
- settings and environment configuration
- database configuration
- static/media handling
- Dockerfile and compose/deployment files
- WSGI/ASGI server configuration
- reverse proxy assumptions
- logging
- health checks
- cache/session configuration
- background jobs if present
- provider integration boundaries
- backup/restore assumptions

Use the findings from Phase 01 if available.

## Required Work

Implement only architecture changes justified by the current application and launch requirements.

At minimum evaluate:

1. Production settings must fail closed.
2. Database choice must be appropriate for expected production writes.
3. Static/media behavior must be explicit.
4. Secrets must come from environment/configuration, never source code.
5. Request timeouts must exist for external providers.
6. Expensive operations must have controlled concurrency/rate behavior.
7. Health checks must distinguish application health from dependency health where useful.
8. Logs must be useful without leaking secrets or sensitive user data.
9. Configuration must be reproducible between environments.
10. Deployment boundaries must be understandable to a future maintainer.

## Hard Prohibitions

- Do not migrate infrastructure merely because another stack is fashionable.
- Do not introduce Kubernetes.
- Do not introduce microservices.
- Do not introduce React/Vue/etc.
- Do not rewrite working application architecture without evidence.
- Do not hard-code production secrets.
- Do not silently change data semantics.

## Acceptance Criteria

- Production configuration is explicit and safe.
- Deployment-critical settings are documented.
- External provider failures are bounded.
- Static/media/database behavior is deterministic.
- Health and logging behavior is sufficient for initial production operation.

## Verification

Run Django checks, tests, container/build checks where available, and inspect the final configuration for fail-open behavior.

## Final Report

Include architecture changes, deployment assumptions, and any remaining infrastructure risks.

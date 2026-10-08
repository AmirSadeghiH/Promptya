# Phase 10 — Production Launch

## Objective

Launch Promptya carefully, with observability, rollback, and abuse controls in place.

## Preconditions

Do not proceed if a known `CRITICAL` launch blocker remains.

Confirm:
- production secrets configured securely
- DEBUG disabled
- hosts configured
- TLS active
- database healthy
- migrations applied
- static/media correct
- email delivery operational
- provider credentials valid
- generation cost controls active
- rate limits active
- backups verified
- admin access verified
- monitoring/logging available

## Launch Procedure

1. Create/verify backup.
2. Deploy the exact release artifact.
3. Apply migrations.
4. Collect/serve static assets as required.
5. Run health checks.
6. Run smoke tests.
7. Verify authentication.
8. Verify AI generation with a controlled test.
9. Verify credit transaction behavior.
10. Verify moderation/admin access.
11. Monitor logs and error rates.
12. Record release state and rollback point.

## Hard Prohibitions

- Do not launch while critical security blockers remain.
- Do not run destructive migrations without a backup/rollback plan.
- Do not test expensive generation repeatedly with production credits.
- Do not expose staging credentials in production.
- Do not perform unrelated refactors during release.

## Acceptance Criteria

Production passes the smoke checklist and remains stable under normal test traffic.

A rollback can be performed using documented steps.

## Post-Launch

For the initial period, monitor:
- signups
- verification completion
- first generation
- generation failures
- credit issuance/spend
- error rates
- latency
- provider failures
- abuse signals

## Final Report

Report release identifier, smoke-test results, monitoring status, and rollback readiness.

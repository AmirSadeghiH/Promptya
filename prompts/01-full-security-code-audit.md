# Phase 01 — Full Security and Code Audit

## Objective

Perform a repository-wide engineering, security, and production-readiness audit before public launch.

This phase is primarily investigative. Do not perform broad fixes until findings are understood and prioritized.

## Required Investigation

Audit at minimum:

### Authentication and Authorization
- signup/login/logout
- password handling
- session behavior
- authorization boundaries
- object ownership
- staff/admin permissions
- password reset if present
- email verification if present

### Web Security
- CSRF
- XSS
- SQL injection
- unsafe redirects
- clickjacking
- security headers
- cookie flags
- CORS
- host validation
- debug configuration
- error disclosure

### File and Media Handling
- upload validation
- file size limits
- storage paths
- media access
- image processing
- dangerous file types

### AI Provider Boundaries
- API credentials
- provider URLs
- request validation
- timeouts
- rate limits
- retry behavior
- cost abuse
- prompt/input limits

### Credits and Rewards
- transaction atomicity
- duplicate reward paths
- race conditions
- negative balances
- client-side trust
- idempotency

### Social Features
- posts
- comments
- likes
- saves
- follows
- notifications
- user-generated URLs/content

### Infrastructure
- settings
- environment variables
- Docker
- database
- static/media
- logging
- health checks
- backup assumptions

### Dependency and Code Quality
- obvious vulnerable patterns
- unused or dangerous dependencies
- dead security controls
- inconsistent authorization patterns
- duplicated business logic

## Deliverable

Create a prioritized audit report:

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `INFORMATIONAL`

Every finding must include:
- location
- evidence
- impact
- exploit/abuse scenario where appropriate
- recommended remediation
- whether it blocks launch

## Hard Prohibitions

- Do not hide or downplay findings.
- Do not mark a finding fixed without verification.
- Do not disable security controls.
- Do not make broad refactors during the audit.
- Do not expose secrets in the report.

## Acceptance Criteria

- All major attack surfaces were reviewed.
- Findings are evidence-based.
- Launch blockers are explicitly identified.
- The report is actionable enough for later agents to remediate.

## Verification

Run available automated security checks and the relevant test suite where possible.

## Final Report

Return the audit severity summary and the exact launch blockers.

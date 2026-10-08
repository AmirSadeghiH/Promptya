# Phase 00 — Product Freeze

## Objective

Establish a written product contract before making additional feature changes.

The purpose of this phase is to stop uncontrolled feature expansion and create a stable reference for all later agents.

## Required Investigation

Inspect:
- current README and project documentation
- Django apps and major domain models
- current user flows
- authentication
- AI Studio
- credits
- posts/interactions
- notifications
- challenges/missions if present
- admin interfaces
- deployment configuration
- tests
- static/PWA assets
- SEO configuration

Do not change application behavior during the audit portion.

## Required Work

Create or update a concise product specification covering:

1. Product positioning
2. Primary user personas
3. Core user loop
4. MVP capabilities
5. Explicitly deferred capabilities
6. Credit economy principles
7. AI Studio behavior
8. Social/community behavior
9. Moderation expectations
10. Authentication expectations
11. Launch definition
12. Success metrics

The initial positioning should support:

**AI Prompt Library + AI Studio**, with community mechanics reinforcing discovery, creation, sharing, and return.

## Scope

Documentation and product-contract work only, except for tiny corrections required to make the documentation factually accurate.

## Hard Prohibitions

- Do not add new product features.
- Do not refactor application code.
- Do not introduce frontend frameworks.
- Do not change database schema merely for cleanliness.
- Do not redesign the UI.
- Do not deploy.
- Do not add dependencies.

## Acceptance Criteria

- Product scope is explicitly documented.
- MVP and post-MVP are separated.
- Future phases have a clear dependency order.
- No speculative feature is treated as launch-critical.
- The repository has a clear product source of truth.

## Verification

Review the documentation for contradictions with the actual repository.

## Final Report

Report:
- documents created/updated
- confirmed MVP scope
- explicitly deferred features
- unresolved product decisions

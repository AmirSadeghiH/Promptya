# Phase 05 — Challenge and Mission Engine

## Objective

Create a reusable server-side system for permanent missions and temporary challenges.

## Concepts

### Missions

Permanent or long-lived actions such as:
- complete profile
- first generation
- first post
- invite a friend
- share content
- other verified activation actions

### Challenges

Time-bounded campaigns with:
- title
- description
- start/end
- reward
- eligibility/rules
- active state
- reward limits
- optional sponsor
- evidence/verification where needed

## Required Investigation

Inspect existing challenge/completion models and reward services before changing schema.

Prefer extending existing concepts over duplicating them.

## Required Engineering

Design for:
- deterministic eligibility
- server-side verification
- one completion per intended user/action
- idempotent reward issuance
- atomic reward transaction
- start/end enforcement
- global/user reward caps
- admin lifecycle control
- manual verification where automation is impossible

Rules should be represented explicitly rather than hidden in templates.

## Social-Media Mission

Support a mission where a user can submit evidence such as a social post URL.

Treat evidence as untrusted.

The first implementation may use manual/semi-manual verification. Do not pretend that a URL proves publication or ownership.

## Hard Prohibitions

- Never trust a client-submitted `verified=true`.
- Never let the client choose reward amount.
- Never issue duplicate rewards because of retries.
- Do not build a generic rules engine unless current requirements justify it.
- Do not add sponsor billing/payout infrastructure in this phase.

## Acceptance Criteria

- Missions can be configured and completed safely.
- Challenges enforce their time window.
- Reward issuance is atomic and duplicate-safe.
- Admins can manage lifecycle and rewards.
- Evidence submission cannot directly mint credits.
- Tests cover race/retry/duplicate cases.

## Verification

Run domain tests, transaction tests, permission tests, and the full suite.

## Final Report

Include the domain model, state transitions, reward guarantees, and deferred campaign features.

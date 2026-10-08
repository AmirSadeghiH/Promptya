# Phase 07 — Moderation and Abuse Prevention

## Objective

Make Promptya safe enough for real user-generated growth.

## Required Capabilities

Implement or complete:

- report post
- report comment
- report user
- block user
- moderation queue
- user restriction/suspension/ban states where justified
- moderation action history
- abuse/rate limits for high-risk endpoints
- basic anti-spam controls
- safe handling of generated content

## Abuse Scenarios

Explicitly test:
- fake-account credit farming
- referral farming
- generation spam
- repeated challenge completion
- comment spam
- report spam
- unauthorized access to another user's content/actions
- brute-force authentication
- expensive endpoint flooding

## Moderation Design

Prefer explicit states and auditable actions.

Do not permanently delete data merely because a user reports it unless the product contract requires deletion. Preserve appropriate moderation evidence while respecting privacy requirements.

## Hard Prohibitions

- Do not implement security solely in JavaScript.
- Do not rely on hidden UI controls as authorization.
- Do not create unbounded logs containing personal or sensitive data.
- Do not automatically punish users based on weak heuristics without a safe recovery path.
- Do not build a complex ML moderation system for MVP.

## Acceptance Criteria

- Users can report abusive content.
- Users can block where appropriate.
- Staff can review reports.
- High-risk endpoints have meaningful abuse protection.
- Moderation actions are permission-controlled and auditable.
- Abuse tests exist for economically sensitive flows.

## Verification

Run security, permissions, rate-limit, and moderation tests plus the full suite.

## Final Report

Summarize abuse controls and remaining trust/safety limitations.

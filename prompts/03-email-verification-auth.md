# Phase 03 — Email Verification and Production Authentication

## Objective

Make user identity and authentication suitable for public launch.

## Required Investigation

Inspect the current:
- signup
- login
- logout
- password validation
- email storage
- session behavior
- referral handling
- account activation state
- password reset
- templates
- authentication tests

Preserve the project's existing Django architecture unless a change is required.

## Required Behavior

Implement a production-grade authentication flow with:

1. Branded standalone login and registration surfaces where appropriate.
2. Strong server-side password validation.
3. Email verification before granting trust-sensitive rewards.
4. Secure verification tokens with expiry and one-time use.
5. Safe resend behavior with rate limits.
6. Clear handling of already verified/expired/invalid links.
7. Referral attribution that cannot itself grant rewards.
8. Secure session behavior.
9. Appropriate enumeration resistance where practical.
10. Tests for abuse and invalid flows.

## Referral Rule

Do not reward a referrer merely because a referred account was created.

The reward must require a meaningful server-side activation condition defined by the product contract, and must be protected against self-referral and trivial farming.

## Hard Prohibitions

- Do not disable CSRF.
- Do not put verification tokens in logs.
- Do not reveal passwords or sensitive token values.
- Do not grant credits on raw signup.
- Do not trust referral identity supplied by the browser.
- Do not redesign unrelated pages.
- Do not introduce a new auth framework unless existing Django auth is proven insufficient.

## Acceptance Criteria

- Unverified users cannot access functionality that explicitly requires verification.
- Verification links expire and cannot be reused.
- Resend is rate-limited.
- Referral rewards cannot be trivially farmed.
- Login/logout/session behavior remains correct.
- Tests cover success and abuse cases.

## Verification

Run auth tests, security tests, full test suite, and Django checks.

## Final Report

Report authentication changes, token lifecycle, referral rules, tests, and known risks.

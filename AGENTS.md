# Promptya — Agent Instructions

## 1. Project Context

Promptya is a production-oriented AI prompt community and AI creation platform.

The product combines:
- AI prompt discovery and publishing
- User-generated content and social interactions
- AI Studio generation
- Credits and reward mechanics
- Missions and time-limited challenges
- Moderation and trust/safety
- PWA/mobile-friendly delivery
- SEO and discoverability
- A future developer hub
- A future sponsor/campaign platform

The product goal is not maximum feature count. The goal is to ship a secure, understandable, maintainable product, operate it reliably, learn from real users, and iterate from evidence.

Core product loop:

**Discover → Create → Share → Earn → Return**

The initial product should be strong as an AI prompt library + AI Studio. Social mechanics and campaign mechanics should strengthen that loop rather than distract from it.

---

## 2. Mandatory Startup Procedure

Before changing code:

1. Read this file completely.
2. Read the requested phase document under `prompts/`.
3. Inspect the current repository state.
4. Inspect relevant models, services, views, URLs, templates, tests, settings, migrations, and deployment files before designing changes.
5. Search for existing implementations before introducing new abstractions.
6. Identify the smallest safe implementation that satisfies the active phase.
7. Follow the phase's explicit scope, non-goals, acceptance criteria, and hard prohibitions.

Do not implement a phase from its title alone.

---

## 3. Architecture Principles

- Prefer Django's existing architecture and server-rendered templates.
- Do not introduce React, Vue, Tailwind, Bootstrap, or another frontend framework unless a phase explicitly requires it and the reason is documented.
- Reuse existing domain models, services, utilities, templates, components, and conventions.
- Keep business rules in Python/domain/service layers rather than duplicating them in templates or client-side JavaScript.
- Prefer explicit, boring, maintainable code over clever abstractions.
- Prefer small changes over rewrites.
- Do not rename, delete, or restructure unrelated code for aesthetic reasons.
- Do not add dependencies without a concrete technical justification.
- Do not introduce a second implementation of an existing capability without proving the current one is unsuitable.
- Preserve existing behavior unless the active phase explicitly changes it.

---

## 4. Security Non-Negotiables

These rules override convenience.

- Never commit secrets, API keys, passwords, tokens, private certificates, production credentials, or sensitive user data.
- Never disable CSRF protection for convenience.
- Never trust client-provided ownership, permissions, credit balances, prices, reward amounts, moderation status, or security-sensitive state.
- Enforce authorization server-side for every protected mutation.
- Treat all uploaded files and user-generated content as untrusted.
- Validate upload size, type, extension, storage behavior, and access policy.
- Never expose stack traces, provider credentials, internal configuration, or sensitive errors to users.
- Protect expensive AI/provider calls against abuse, retries, duplicate requests, and unauthorized access.
- Rate-limit abuse-prone endpoints.
- Credit issuance and spending must be atomic and auditable.
- Make retry-sensitive operations idempotent where appropriate.
- Server-side watermarking is a security/business boundary; client-side watermarking is not.
- Production configuration must fail closed, not open, when critical environment configuration is missing.
- Do not weaken authentication, authorization, validation, rate limiting, or logging to make a feature easier to implement.

---

## 5. Product and Domain Rules

### Credits

Credits are product currency, not a cosmetic counter.

Rules:
- Credit mutations belong in the authoritative service/ledger layer.
- Never accept a final credit balance from the browser.
- Reward issuance must be server-controlled.
- Duplicate reward execution must be prevented.
- Provider cost and reward economics must be considered for expensive operations.

### Referrals

A referral query parameter is not proof of a valid referral.

Referral rewards must require server-side eligibility and must not be trivially farmable with fake accounts.

### AI Generation

AI generation is an expensive, abuse-prone operation.

Every generation flow must consider:
- authentication
- authorization
- credit availability
- provider availability
- rate limits
- duplicate submissions
- retry behavior
- timeout/failure behavior
- output storage
- auditability
- user-visible failure behavior

### Challenges and Missions

Rewards, eligibility, dates, status, limits, and verification must be controlled server-side.

A user must never be able to grant themselves a reward by modifying browser state.

### User-Generated Content

Treat prompts, captions, comments, links, uploaded media, and evidence as untrusted input.

---

## 6. Testing Rules

For every implementation:

1. Run the smallest relevant tests during development.
2. Add regression tests for security-sensitive and business-critical behavior.
3. Run the full test suite before declaring completion.
4. Do not delete, weaken, skip, or rewrite tests merely to obtain a green result.
5. Investigate failures instead of assuming they are unrelated.
6. Run migrations/checks/static checks when relevant.
7. Test negative paths, not only the happy path.

A feature is not complete because the happy path works.

---

## 7. Scope Discipline

The active phase is the current contract.

Do not implement future-phase functionality unless:
- it is strictly required for correctness of the current phase, and
- it cannot reasonably be deferred.

If an unrelated issue is discovered:
- fix it only if it blocks security, correctness, tests, or deployment of the active phase;
- otherwise document it as a follow-up.

Do not turn one phase into a general refactor.

---

## 8. Change Discipline

Before editing:
- map affected files and dependencies;
- inspect call sites;
- inspect tests;
- identify migration/data risks;
- identify security implications;
- identify backwards-compatibility concerns.

After editing:
- review the diff;
- remove accidental changes;
- check for secrets/debug artifacts;
- run tests/checks;
- verify migrations;
- verify user-visible behavior where relevant.

---

## 9. Git Discipline

- Never force-push.
- Never rewrite history.
- Never delete branches.
- Never claim a commit or push occurred unless it actually occurred.
- Keep commits focused when commits are requested.
- Do not modify production infrastructure unless the active phase includes it.
- Do not silently mix unrelated fixes into a phase.

---

## 10. Definition of Done

A phase is complete only when:

- Requested behavior is implemented.
- Existing intended behavior still works.
- Security requirements are satisfied.
- Relevant tests exist and pass.
- Full tests pass, or every remaining failure is explicitly explained.
- Migrations/static/deployment implications are handled when applicable.
- Documentation is updated when required.
- The final report includes:
  - what changed
  - files changed
  - tests/checks run
  - migration/deployment notes
  - known risks
  - explicitly deferred work

---

## 11. Required Final Report

At the end of every phase, report:

### Summary
What was implemented and why.

### Files Changed
List files grouped by purpose.

### Verification
List commands/checks/tests executed and their results.

### Security Review
List security-sensitive areas reviewed.

### Data/Migration Impact
State whether migrations or data changes were introduced.

### Known Risks
List unresolved risks honestly.

### Deferred Work
List items intentionally left for later phases.

### Phase Verdict
Use one of:
- `COMPLETE`
- `COMPLETE WITH KNOWN RISK`
- `BLOCKED`

Never declare `COMPLETE` when acceptance criteria are not met.

---

## 12. Priority Order

When requirements conflict, prioritize:

**Security → Data Integrity → Correctness → Maintainability → Product Requirements → Convenience**

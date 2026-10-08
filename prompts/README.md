# Promptya Agent Phase Library

These phase documents are execution contracts for AI coding agents.

Read `../AGENTS.md` first, then read exactly the requested phase document.

## Phase Order

1. `00-product-freeze.md` — Freeze scope and establish the product contract.
2. `01-full-security-code-audit.md` — Audit the current codebase before public launch.
3. `02-production-architecture.md` — Harden architecture, configuration, persistence, deployment boundaries, and observability.
4. `03-email-verification-auth.md` — Make authentication production-grade.
5. `04-admin-ops-dashboard.md` — Build an operational control plane.
6. `05-challenge-mission-engine.md` — Build configurable missions and time-limited challenges.
7. `06-ai-studio-credit-economy-watermark.md` — Make generation economics and watermarking authoritative.
8. `07-moderation-abuse-prevention.md` — Add trust, safety, reporting, blocking, and abuse controls.
9. `08-ui-auth-logo-pwa-copy.md` — Finish production UX, authentication surfaces, branding, PWA, and copy.
10. `09-staging-deployment.md` — Establish a repeatable staging deployment.
11. `10-production-launch.md` — Launch safely and verify production.
12. `11-instagram-content-engine.md` — Establish the content/distribution system.
13. `12-developer-hub.md` — Build the Promptya developer resource layer.
14. `13-first-sponsored-challenge.md` — Prepare and execute the first sponsor campaign.

## Agent Rule

Do not skip ahead because a later feature looks attractive.

The active phase is the only implementation scope unless a later-phase dependency is strictly necessary for correctness.

Each document contains:
- objective
- context
- required investigation
- implementation procedure
- hard prohibitions
- acceptance criteria
- testing requirements
- final report requirements

If the repository state conflicts with an assumption in a phase document, inspect the real code and adapt the implementation while preserving the phase's intent. Do not blindly recreate architecture described in the document.

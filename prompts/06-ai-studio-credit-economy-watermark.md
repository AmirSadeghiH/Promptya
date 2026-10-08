# Phase 06 — AI Studio, Credit Economy, and Watermarking

## Objective

Make AI generation economically correct, abuse-resistant, and enforceable at the server boundary.

## Required Investigation

Inspect:
- generation views/services
- provider adapter
- AI configuration
- credit transaction service
- generated image model/storage
- existing watermark logic
- retry/failure handling
- authorization
- rate limiting

## Required Behavior

Support two output tiers if the current product contract requires them:

1. Watermarked generation
2. No-watermark premium generation

The exact credit prices must come from a single server-side configuration/domain source, not from browser values.

## Watermark Rule

The watermark must be applied server-side to the authoritative output.

Do not rely on CSS, JavaScript overlays, canvas overlays, or UI-only watermarks.

A user must not be able to obtain the premium/no-watermark asset by modifying browser state.

## Credit Flow

For a generation request:

1. Validate identity and authorization.
2. Validate generation parameters.
3. Determine authoritative server-side cost.
4. Verify sufficient credits.
5. Reserve/deduct safely according to the existing transaction model.
6. Call the provider with bounded timeout behavior.
7. On failure, apply the documented refund/rollback behavior.
8. Persist output only after successful generation.
9. Apply server-side watermarking when required.
10. Return only the authorized asset/result.

Avoid charging twice on retries.

## Economics

Do not hard-code business assumptions throughout the codebase.

Make it possible to inspect:
- credits charged
- credits spent
- reward credits issued
- provider cost if available
- generation success/failure

## Hard Prohibitions

- Never trust client-provided credit cost.
- Never allow negative balances through race conditions.
- Never expose provider API keys.
- Never perform watermarking only in the browser.
- Never silently refund/charge without an auditable transaction.
- Do not introduce multiple provider implementations unless required.

## Acceptance Criteria

- Both output tiers enforce server-side authorization.
- Watermark cannot be trivially removed from the authoritative asset.
- Credits are charged exactly once per successful generation.
- Failures have deterministic credit behavior.
- Retries are safe.
- Tests cover concurrent/duplicate requests and unauthorized premium access.

## Verification

Run generation, credit, failure, retry, authorization, and media tests.

## Final Report

Include the final generation state machine and credit/watermark enforcement points.

# Phase 04 — Admin and Operations Dashboard

## Objective

Build an operational control plane that lets the product owner safely operate Promptya without editing database records manually.

## Required Investigation

Inspect the existing Django Admin and domain services for:
- users
- posts
- categories/tags
- credits
- generated images
- challenges
- notifications
- interactions
- moderation candidates

Reuse existing service-layer operations.

## Required Capabilities

The operations interface should support, where applicable:

- user lookup and status management
- safe credit adjustments through the ledger/service layer
- challenge lifecycle management
- mission configuration
- generated-content inspection
- moderation actions
- notification operations
- operational search/filtering
- audit visibility for sensitive actions

Sensitive operations should show confirmation/context and should not directly mutate critical fields when a domain service exists.

## Hard Prohibitions

- Do not create a second business-logic implementation inside admin views.
- Do not allow arbitrary credit balance editing.
- Do not expose API keys unnecessarily.
- Do not give ordinary users access to staff operations.
- Do not build a huge custom SPA admin.
- Do not redesign the entire Django Admin ecosystem.

## Acceptance Criteria

- Common operational tasks can be performed safely.
- Sensitive actions are permission-protected.
- Credit operations remain ledger-backed.
- Staff actions are auditable where appropriate.
- Existing admin functionality remains intact.

## Verification

Test staff permissions, object access, sensitive mutations, credit operations, and regression behavior.

## Final Report

List operational capabilities added and the permissions model.

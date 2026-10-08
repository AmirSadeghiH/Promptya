# Phase 08 — UI, Auth Surfaces, Branding, PWA, and Production Copy

## Objective

Turn the current interface into a coherent production experience without changing the underlying architecture unnecessarily.

## Required Work

### Authentication UX
- standalone branded login
- standalone branded registration
- verification states
- password/error states
- mobile usability

### Branding
- consistent Promptya logo usage
- transparent brand asset where appropriate
- favicon
- PWA icons
- maskable icon where appropriate
- correct manifest references

### PWA
Verify:
- manifest
- icons
- theme/background colors
- installability
- service worker scope
- offline behavior
- cache invalidation
- authenticated pages are not incorrectly cached
- admin/API routes are not incorrectly cached

### Copy
Review MVP-visible copy for:
- clarity
- Persian quality
- consistency
- action-oriented wording
- empty states
- errors
- onboarding
- AI generation states

## Design Direction

Use the existing design language:
- minimal
- premium
- dark/light support
- strong typography
- restrained motion
- product-first layouts

Do not replace the entire UI system.

## Hard Prohibitions

- No React/Vue migration.
- No Tailwind/Bootstrap migration.
- No unrelated redesign.
- No client-side security logic.
- Do not cache private/authenticated responses in a public service-worker cache.
- Do not put sensitive data into installable/offline caches.

## Acceptance Criteria

- Login/register are appropriate standalone product surfaces.
- Branding assets are consistent.
- PWA behavior is validated on supported browsers/devices.
- Private content is not incorrectly cached.
- MVP copy is production-quality and consistent.

## Verification

Run browser/device checks where available, Django/static checks, PWA validation, and the full test suite.

## Final Report

Include UI areas changed, PWA checks, and any browser-specific limitations.

# Phase 11 — UX Design & Experience Workflow

## Overview
Phase 11 implements the complete `ux` lifecycle stage across five connected, versioned workspaces:
1. **Personas** (`/projects/:id/personas`, `artifact_type="personas"`)
2. **User Journeys** (`/projects/:id/journeys`, `artifact_type="journeys"`)
3. **Information Architecture** (`/projects/:id/ia`, `artifact_type="ia"`)
4. **Wireframes** (`/projects/:id/wireframes`, `artifact_type="wireframes"`)
5. **UX Review** (`/projects/:id/ux-review`, `artifact_type="ux_review"`)

## Upstream & Cross-Artifact Gates
- Requires approved, non-stale Phase 9 `Research` (`research == complete`), Phase 10 `Strategy` (referencing approved Research), and Phase 10 `PRD` (referencing approved Strategy, `product == complete`).
- Within Phase 11:
  - `journeys` requires approved `personas`.
  - `ia` requires approved `personas` and `journeys`.
  - `wireframes` requires approved `personas`, `journeys`, and `ia`.
  - `ux_review` requires approved `personas`, `journeys`, `ia`, and `wireframes`.
- Reopening or updating any upstream artifact marks dependent UX artifacts stale (`is_stale = true`) and reopens the `ux` lifecycle stage to `in_progress`.

## Lifecycle Completion Criteria (`ux` stage)
The `ux` stage becomes `complete` (and cannot be manually forced complete via `PUT /stages/ux` once UX work has started) only when:
1. Upstream `Research`, `Strategy`, and `PRD` are approved and current with no open drafts.
2. All 5 UX artifacts (`personas`, `journeys`, `ia`, `wireframes`, `ux_review`) have an `approved` version, no open draft/in-review version, and match current upstream versions (`is_stale == false`).
3. The approved `ux_review` has zero unresolved `critical` findings (`status in ('open', 'needs_evidence')`). Critical findings must be `resolved` or `accepted` with a non-empty `resolution_note`.

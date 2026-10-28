# Phase 12 — Design System & Interactive Prototype

## Overview
Phase 12 implements the `design` lifecycle stage across two connected, versioned workspaces:
1. **Design System** (`/projects/:id/design-system`, `artifact_type="design_system"`)
2. **Interactive Prototype** (`/projects/:id/prototype`, `artifact_type="prototype"`)

## Upstream & Cross-Artifact Gates
- Requires approved, non-stale Phase 9 `Research`, Phase 10 `Strategy` and `PRD`, and all 5 Phase 11 `UX` artifacts (`personas`, `journeys`, `ia`, `wireframes`, `ux_review` with zero open critical findings, `ux == complete`).
- `prototype` additionally requires an approved, non-stale `design_system` version with no open draft.
- Reopening or editing any upstream UX artifact or `design_system` marks dependent Design artifacts stale (`is_stale = true`) and reopens the `design` lifecycle stage to `in_progress`.

## Lifecycle Completion Criteria (`design` stage)
The `design` stage becomes `complete` (advancing project progress to `4 of 19 stages complete` and `next_action` to `"architecture"`) only when:
1. Upstream `Research`, `Strategy`, `PRD`, and all 5 `UX` artifacts are approved and current (`ux == complete`).
2. `design_system` has an `approved` version, no open draft/in-review version, and matches current upstream versions (`is_stale == false`).
3. `prototype` has an `approved` version built on that approved `design_system` version, represents all required wireframes (`WF-N`) and journeys (`J-N`) with valid screen navigation targets (`SCR-N`), has no open draft/in-review version, and is not stale.

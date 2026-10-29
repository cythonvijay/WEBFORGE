"""Phase 17: Deterministic Project Documentation Generation, Validation, Provenance & Export Service.

Builds human-readable Markdown documentation bundles, consolidated Markdown, validated JSON specifications,
and deterministic ZIP archives from persisted WebForge project artifacts (Phases 0–16).
Strictly separates project specification exports from Phase 15 database backups (`scripts/db_ops.py`).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import architecture as arch
from . import design as ds
from . import optimization as opt
from . import prd as prd_mod
from . import research as res_mod
from . import strategy as stg_mod
from . import ux
from .infrastructure_verification import evaluate_project_infrastructure_and_deployment
from .lifecycle import STAGE_DEPS, STAGES, unmet_deps
from .models import (
    ArchitectureDocument,
    BrainRevision,
    DesignArtifact,
    DiscoveryQuestion,
    DiscoverySession,
    DocumentationExport,
    OptimizationArtifact,
    PrdDocument,
    Project,
    ProjectStage,
    ResearchReport,
    StrategyDocument,
    UxArtifact,
)
from .research import content_hash as compute_content_hash
from .security import as_utc
from .security_verification import evaluate_project_security_and_testing

ExportMode = Literal["official", "preview"]
ExportFormat = Literal["zip", "markdown", "json"]
FindingSeverity = Literal["blocking_error", "warning", "info"]

FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)

SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")
FORBIDDEN_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".git",
    ".gitignore",
    "id_rsa",
    "private.key",
}
ALLOWED_ARCHIVE_EXTENSIONS = (".md", ".json")
FORBIDDEN_EXTENSIONS = (
    ".db", ".sqlite", ".sqlite3", ".wfbackup.json", ".pgdump", ".sql",
    ".pem", ".key", ".pfx", ".sh", ".exe", ".bat", ".dll", ".so",
)

SECRET_PATTERNS = [
    ("SECRET_GOOGLE_API_KEY", re.compile(r"AIza[0-9A-Za-z\-_]{20,}")),
    ("SECRET_OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("SECRET_GITHUB_PAT", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("SECRET_AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SECRET_PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("SECRET_DB_URL_PASSWORD", re.compile(r"postgresql(?:\+psycopg)?://[^:\s/]+:[^@\s]+@")),
    ("SECRET_JWT_SECRET", re.compile(r"(?i)\bJWT_SECRET\s*=\s*['\"]?[A-Za-z0-9_\-]{8,}")),
    ("SECRET_PASSWORD_HASH", re.compile(r"\$argon2id\$v=\d+\$")),
]

INTERNAL_PATH_RE = re.compile(r"(/working_dir/|/home/[a-zA-Z0-9_-]+/|/root/|/tmp/tmp[a-zA-Z0-9_]+)")

SECTION_DEFINITIONS = [
    ("README.md", "Project Summary, Scope & Bundle Inventory", True),
    ("01-research.md", "User & Market Research Specification", True),
    ("02-strategy-and-prd.md", "Product Strategy & Product Requirements Document (PRD)", True),
    ("03-ux-specification.md", "UX Specification (Personas, Journeys, IA, Wireframes, UX Review)", True),
    ("04-design-system.md", "Design System Foundations, Tokens, Components & Decisions", True),
    ("05-prototype.md", "Interactive Prototype Screens, Interactions & Flows", True),
    ("06-architecture.md", "Product Architecture, Data Model, API Contracts & ADRs", True),
    ("07-testing-and-security.md", "Testing & Security Verification Report", True),
    ("08-infrastructure-and-deployment.md", "Infrastructure, DevOps & Deployment Specification", True),
    ("09-seo.md", "Search Engine Optimization (SEO), Sitemap & Robots Specification", True),
    ("10-analytics.md", "Product Analytics, Event Taxonomy & Privacy Governance", True),
    ("11-performance.md", "Performance Budgets, Core Web Vitals & Measurement Evidence", True),
    ("12-traceability.md", "End-to-End Requirement Traceability Matrix", True),
]


class ExportValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: FindingSeverity
    section: str
    title: str
    message: str
    remediation: str
    workspace_path: str | None = None


class ArtifactInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_key: str
    label: str
    phase: str = ""
    stage: str = ""
    workspace_path: str
    required_for_official: bool
    present: bool
    selected_version: int | None = None
    selected_status: str = "missing"
    approved_version: int | None = None
    open_draft_version: int | None = None
    content_hash: str | None = None
    hash_verified: bool = False
    stale: bool = False
    staleness_reasons: list[str] = Field(default_factory=list)
    approved_at: str | None = None
    updated_at: str | None = None
    included_in_export: bool = False
    omission_reason: str | None = None


def _iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def validate_safe_archive_path(filename: str) -> str:
    """Validate that an export archive entry path is safe, relative, UTF-8, and free of traversal or secret files."""
    if not filename or not isinstance(filename, str):
        raise ValueError("Archive filename must be a non-empty string.")
    cleaned = filename.strip()
    if cleaned != filename or "\x00" in cleaned:
        raise ValueError(f"Unsafe whitespace or null byte in archive filename: {filename!r}")
    if cleaned.startswith("/") or cleaned.startswith("\\") or "\\" in cleaned or ":" in cleaned:
        raise ValueError(f"Absolute path, backslash, or drive prefix is forbidden in archive path: {filename!r}")
    parts = cleaned.split("/")
    for part in parts:
        if not part or part in (".", "..") or part.startswith("."):
            raise ValueError(f"Path traversal or hidden segment '{part}' is forbidden in archive path: {filename!r}")
        if part.lower() in FORBIDDEN_FILENAMES:
            raise ValueError(f"Forbidden sensitive filename '{part}' in archive path: {filename!r}")
    lower_name = cleaned.lower()
    if any(lower_name.endswith(ext) for ext in FORBIDDEN_EXTENSIONS):
        raise ValueError(f"Database, executable, or key file extension is forbidden in documentation export: {filename!r}")
    if not any(lower_name.endswith(ext) for ext in ALLOWED_ARCHIVE_EXTENSIONS):
        raise ValueError(f"Only .md and .json files are permitted in documentation export archives: {filename!r}")
    if not SAFE_PATH_RE.match(cleaned):
        raise ValueError(f"Archive path contains disallowed characters: {filename!r}")
    return cleaned


def scan_export_for_secrets(documents: dict[str, str], manifest_json: str) -> list[dict[str, str]]:
    """Scan generated export files and manifest for accidentally embedded credentials, private keys, or internal paths."""
    hits: list[dict[str, str]] = []
    all_blobs = list(documents.items()) + [("MANIFEST.json", manifest_json)]
    for fname, text in all_blobs:
        for rule_name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(
                    {
                        "file": fname,
                        "code": rule_name,
                        "rule": rule_name,
                        "message": f"Potential secret or credential pattern '{rule_name}' detected in {fname}.",
                    }
                )
        if INTERNAL_PATH_RE.search(text):
            hits.append(
                {
                    "file": fname,
                    "code": "INTERNAL_FILESYSTEM_PATH",
                    "rule": "INTERNAL_FILESYSTEM_PATH",
                    "message": f"Internal server filesystem path detected in {fname}.",
                }
            )
    return hits


def _select_latest_approved_and_open(rows: list[Any]) -> tuple[Any | None, Any | None]:
    valid = [r for r in rows if getattr(r, "status", None) != "failed"]
    approved = next((r for r in valid if r.status == "approved"), None)
    open_doc = next((r for r in valid if r.status in ("draft", "in_review", "generating")), None)
    return approved, open_doc


def collect_export_snapshot(
    db: Session,
    project_id: str,
    include_drafts_or_stale: bool = False,
) -> dict[str, Any]:
    """Collect a consistent, read-only snapshot of all persisted project artifacts, versions, hashes, and staleness."""
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    brain_rev = db.scalar(
        select(BrainRevision)
        .where(BrainRevision.project_id == project_id)
        .order_by(BrainRevision.version.desc())
    )
    brain_snap = dict(brain_rev.snapshot) if brain_rev and brain_rev.snapshot else {}

    stages_rows = list(
        db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id))
    )
    stage_statuses = {s: "not_started" for s in STAGES}
    for sr in stages_rows:
        stage_statuses[sr.stage] = sr.status

    disc_session = db.scalar(select(DiscoverySession).where(DiscoverySession.project_id == project_id))
    disc_questions: list[DiscoveryQuestion] = []
    if disc_session:
        disc_questions = list(
            db.scalars(
                select(DiscoveryQuestion)
                .where(DiscoveryQuestion.session_id == disc_session.id)
                .order_by(DiscoveryQuestion.position.asc())
            )
        )

    res_rows = list(
        db.scalars(
            select(ResearchReport)
            .where(ResearchReport.project_id == project_id)
            .order_by(ResearchReport.version.desc())
        )
    )
    stg_rows = list(
        db.scalars(
            select(StrategyDocument)
            .where(StrategyDocument.project_id == project_id)
            .order_by(StrategyDocument.version.desc())
        )
    )
    prd_rows = list(
        db.scalars(
            select(PrdDocument)
            .where(PrdDocument.project_id == project_id)
            .order_by(PrdDocument.version.desc())
        )
    )
    ux_rows = list(
        db.scalars(
            select(UxArtifact)
            .where(UxArtifact.project_id == project_id)
            .order_by(UxArtifact.version.desc())
        )
    )
    design_rows = list(
        db.scalars(
            select(DesignArtifact)
            .where(DesignArtifact.project_id == project_id)
            .order_by(DesignArtifact.version.desc())
        )
    )
    arch_rows = list(
        db.scalars(
            select(ArchitectureDocument)
            .where(ArchitectureDocument.project_id == project_id)
            .order_by(ArchitectureDocument.version.desc())
        )
    )
    opt_rows = list(
        db.scalars(
            select(OptimizationArtifact)
            .where(OptimizationArtifact.project_id == project_id)
            .order_by(OptimizationArtifact.version.desc())
        )
    )

    res_app, res_open = _select_latest_approved_and_open(res_rows)
    stg_app, stg_open = _select_latest_approved_and_open(stg_rows)
    prd_app, prd_open = _select_latest_approved_and_open(prd_rows)
    arch_app, arch_open = _select_latest_approved_and_open(arch_rows)

    ux_by_type: dict[str, tuple[UxArtifact | None, UxArtifact | None]] = {}
    for ut in ux.ARTIFACT_TYPES:
        u_sub = [r for r in ux_rows if r.artifact_type == ut]
        ux_by_type[ut] = _select_latest_approved_and_open(u_sub)

    design_by_type: dict[str, tuple[DesignArtifact | None, DesignArtifact | None]] = {}
    for dt in ds.DESIGN_ARTIFACT_TYPES:
        d_sub = [r for r in design_rows if r.artifact_type == dt]
        design_by_type[dt] = _select_latest_approved_and_open(d_sub)

    opt_by_area: dict[str, tuple[OptimizationArtifact | None, OptimizationArtifact | None]] = {}
    for area in opt.OPTIMIZATION_AREAS:
        o_sub = [r for r in opt_rows if r.area == area]
        opt_by_area[area] = _select_latest_approved_and_open(o_sub)

    def _pick(app_row: Any | None, open_row: Any | None) -> Any | None:
        if include_drafts_or_stale and open_row is not None and getattr(open_row, "content", None):
            return open_row
        return app_row

    selected: dict[str, Any | None] = {
        "research": _pick(res_app, res_open),
        "strategy": _pick(stg_app, stg_open),
        "prd": _pick(prd_app, prd_open),
        "personas": _pick(*ux_by_type["personas"]),
        "journeys": _pick(*ux_by_type["journeys"]),
        "ia": _pick(*ux_by_type["ia"]),
        "wireframes": _pick(*ux_by_type["wireframes"]),
        "ux_review": _pick(*ux_by_type["ux_review"]),
        "design_system": _pick(*design_by_type["design_system"]),
        "prototype": _pick(*design_by_type["prototype"]),
        "architecture": _pick(arch_app, arch_open),
        "seo": _pick(*opt_by_area["seo"]),
        "analytics": _pick(*opt_by_area["analytics"]),
        "performance": _pick(*opt_by_area["performance"]),
    }

    approved_map: dict[str, Any | None] = {
        "research": res_app,
        "strategy": stg_app,
        "prd": prd_app,
        "personas": ux_by_type["personas"][0],
        "journeys": ux_by_type["journeys"][0],
        "ia": ux_by_type["ia"][0],
        "wireframes": ux_by_type["wireframes"][0],
        "ux_review": ux_by_type["ux_review"][0],
        "design_system": design_by_type["design_system"][0],
        "prototype": design_by_type["prototype"][0],
        "architecture": arch_app,
        "seo": opt_by_area["seo"][0],
        "analytics": opt_by_area["analytics"][0],
        "performance": opt_by_area["performance"][0],
    }

    open_map: dict[str, Any | None] = {
        "research": res_open,
        "strategy": stg_open,
        "prd": prd_open,
        "personas": ux_by_type["personas"][1],
        "journeys": ux_by_type["journeys"][1],
        "ia": ux_by_type["ia"][1],
        "wireframes": ux_by_type["wireframes"][1],
        "ux_review": ux_by_type["ux_review"][1],
        "design_system": design_by_type["design_system"][1],
        "prototype": design_by_type["prototype"][1],
        "architecture": arch_open,
        "seo": opt_by_area["seo"][1],
        "analytics": opt_by_area["analytics"][1],
        "performance": opt_by_area["performance"][1],
    }

    # Evaluate staleness per artifact
    def _staleness_for(key: str, row: Any | None) -> list[str]:
        if row is None:
            return []
        reasons: list[str] = []
        basis = getattr(row, "basis", None) or getattr(row, "basis_summary", None) or {}
        if key == "strategy":
            if res_app and basis.get("research_version") not in (None, res_app.version):
                reasons.append(f"Built from Research v{basis.get('research_version')}, while Research v{res_app.version} is approved.")
        elif key == "prd":
            if stg_app and basis.get("strategy_version") not in (None, stg_app.version):
                reasons.append(f"Built from Strategy v{basis.get('strategy_version')}, while Strategy v{stg_app.version} is approved.")
            if res_app and basis.get("research_version") not in (None, res_app.version):
                reasons.append(f"Built from Research v{basis.get('research_version')}, while Research v{res_app.version} is approved.")
        elif key in ux.ARTIFACT_TYPES:
            if prd_app and basis.get("prd_version") not in (None, prd_app.version):
                reasons.append(f"Built from PRD v{basis.get('prd_version')}, while PRD v{prd_app.version} is approved.")
            if stg_app and basis.get("strategy_version") not in (None, stg_app.version):
                reasons.append(f"Built from Strategy v{basis.get('strategy_version')}, while Strategy v{stg_app.version} is approved.")
        elif key in ds.DESIGN_ARTIFACT_TYPES:
            if prd_app and basis.get("prd_version") not in (None, prd_app.version):
                reasons.append(f"Built from PRD v{basis.get('prd_version')}, while PRD v{prd_app.version} is approved.")
            for ut in ux.ARTIFACT_TYPES:
                u_app = approved_map[ut]
                if u_app and basis.get(f"{ut}_version") not in (None, u_app.version):
                    reasons.append(f"Built from UX {ut} v{basis.get(f'{ut}_version')}, while v{u_app.version} is approved.")
                elif u_app and basis.get(f"{ut}_hash") and basis.get(f"{ut}_hash") != u_app.content_hash:
                    reasons.append(f"Upstream UX {ut} content hash changed since this {key} version was created.")
            if key == "prototype":
                ds_app = approved_map["design_system"]
                if ds_app and basis.get("design_system_version") not in (None, ds_app.version):
                    reasons.append(f"Built from Design System v{basis.get('design_system_version')}, while v{ds_app.version} is approved.")
                elif ds_app and basis.get("design_system_hash") and basis.get("design_system_hash") != ds_app.content_hash:
                    reasons.append("Upstream Design System content hash changed since this prototype version was created.")
        elif key == "architecture":
            if prd_app and (basis.get("prd_version") != prd_app.version or (basis.get("prd_hash") and basis.get("prd_hash") != prd_app.content_hash)):
                reasons.append("Upstream PRD changed since this Architecture version was created.")
            for dt in ds.DESIGN_ARTIFACT_TYPES:
                d_app = approved_map[dt]
                if d_app and (basis.get(f"{dt}_version") != d_app.version or (basis.get(f"{dt}_hash") and basis.get(f"{dt}_hash") != d_app.content_hash)):
                    reasons.append(f"Upstream {dt.replace('_', ' ').title()} changed since this Architecture version was created.")
            for ut in ux.ARTIFACT_TYPES:
                u_app = approved_map[ut]
                if u_app and basis.get(f"{ut}_version") != u_app.version:
                    reasons.append(f"Upstream UX {ut} changed since this Architecture version was created.")
        elif key in opt.OPTIMIZATION_AREAS:
            if arch_app and (basis.get("architecture_version") != arch_app.version or (basis.get("architecture_content_hash") and basis.get("architecture_content_hash") != arch_app.content_hash)):
                reasons.append(f"Built from Architecture v{basis.get('architecture_version')}, while Architecture v{arch_app.version} is approved.")
            if prd_app and (basis.get("prd_version") != prd_app.version or (basis.get("prd_content_hash") and basis.get("prd_content_hash") != prd_app.content_hash)):
                reasons.append("Upstream PRD changed since this optimization specification was created.")
            proto_app = approved_map["prototype"]
            if proto_app and (basis.get("prototype_version") != proto_app.version or (basis.get("prototype_hash") and basis.get("prototype_hash") != proto_app.content_hash)):
                reasons.append("Upstream Interactive Prototype changed since this optimization specification was created.")
        return reasons

    artifact_meta = [
        ("research", "User & Market Research", "Phase 9", "research", f"/projects/{project_id}/research", True),
        ("strategy", "Product Strategy", "Phase 10", "product", f"/projects/{project_id}/strategy", True),
        ("prd", "Product Requirements Document (PRD)", "Phase 10", "product", f"/projects/{project_id}/prd", True),
        ("personas", "UX Personas", "Phase 11", "ux", f"/projects/{project_id}/personas", True),
        ("journeys", "UX User Journeys", "Phase 11", "ux", f"/projects/{project_id}/journeys", True),
        ("ia", "UX Information Architecture", "Phase 11", "ux", f"/projects/{project_id}/ia", True),
        ("wireframes", "UX Wireframes", "Phase 11", "ux", f"/projects/{project_id}/wireframes", True),
        ("ux_review", "UX Review", "Phase 11", "ux", f"/projects/{project_id}/ux-review", True),
        ("design_system", "Design System", "Phase 12", "design", f"/projects/{project_id}/design-system", True),
        ("prototype", "Interactive Prototype", "Phase 12", "design", f"/projects/{project_id}/prototype", True),
        ("architecture", "Product Architecture", "Phase 13", "architecture", f"/projects/{project_id}/architecture", True),
        ("seo", "SEO Specification", "Phase 16", "seo", f"/projects/{project_id}/seo", True),
        ("analytics", "Analytics & Privacy Specification", "Phase 16", "analytics", f"/projects/{project_id}/analytics", True),
        ("performance", "Performance Budgets & Evidence", "Phase 16", "analytics", f"/projects/{project_id}/performance", True),
    ]

    inventory: list[ArtifactInventoryEntry] = []
    idea_hash = compute_content_hash(brain_snap.get("idea", {}))
    disc_hash = compute_content_hash(brain_snap.get("discovery", {}))
    fingerprint_parts: list[str] = [f"project:{project.id}:{project.name}:{idea_hash}:{disc_hash}"]

    for key, label, phase_lbl, stage_key, wpath, req_official in artifact_meta:
        sel = selected[key]
        app_r = approved_map[key]
        open_r = open_map[key]
        stale_reasons = _staleness_for(key, sel)
        hash_ok = False
        recomputed_hash: str | None = None
        if sel is not None and getattr(sel, "content", None) is not None:
            if key in opt.OPTIMIZATION_AREAS:
                try:
                    recomputed_hash = opt.compute_optimization_hash(key, sel.content)  # type: ignore[arg-type]
                except Exception:
                    recomputed_hash = ""
            else:
                recomputed_hash = compute_content_hash(sel.content)
            hash_ok = bool(sel.content_hash and sel.content_hash == recomputed_hash)

        included = sel is not None and getattr(sel, "content", None) is not None
        omission_reason: str | None = None
        if not included:
            if open_r is not None and not include_drafts_or_stale:
                omission_reason = f"{label} has an unapproved draft (v{open_r.version}) but no approved version."
            else:
                omission_reason = f"{label} has not been generated and approved yet."

        entry = ArtifactInventoryEntry(
            artifact_key=key,
            label=label,
            phase=phase_lbl,
            stage=stage_key,
            workspace_path=wpath,
            required_for_official=req_official,
            present=sel is not None,
            selected_version=sel.version if sel else None,
            selected_status=sel.status if sel else "missing",
            approved_version=app_r.version if app_r else None,
            open_draft_version=open_r.version if open_r else None,
            content_hash=sel.content_hash if sel else None,
            hash_verified=hash_ok,
            stale=len(stale_reasons) > 0,
            staleness_reasons=stale_reasons,
            approved_at=_iso(getattr(sel, "approved_at", None)) if sel else None,
            updated_at=_iso(getattr(sel, "updated_at", None)) if sel else None,
            included_in_export=included,
            omission_reason=omission_reason,
        )
        inventory.append(entry)
        fingerprint_parts.append(
            f"{key}:{entry.selected_version}:{entry.selected_status}:{entry.content_hash}:{entry.open_draft_version}:{int(entry.stale)}"
        )

    sec_report = evaluate_project_security_and_testing(db, project_id)
    infra_report = evaluate_project_infrastructure_and_deployment(db, project_id)
    opt_basis = opt.build_optimization_basis(db, project_id)

    seo_sel = selected["seo"]
    an_sel = selected["analytics"]
    pf_sel = selected["performance"]
    opt_checks = opt.run_product_verification_checks(
        seo_content=seo_sel.content if seo_sel else None,
        analytics_content=an_sel.content if an_sel else None,
        performance_content=pf_sel.content if pf_sel else None,
    )

    snapshot_fingerprint = hashlib.sha256("|".join(fingerprint_parts).encode("utf-8")).hexdigest()

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "created_at": _iso(project.created_at),
            "updated_at": _iso(project.updated_at),
        },
        "brain_version": brain_rev.version if brain_rev else 1,
        "brain": brain_snap,
        "stage_statuses": stage_statuses,
        "discovery": {
            "status": disc_session.status if disc_session else "not_started",
            "round": disc_session.round if disc_session else 0,
            "completed_at": _iso(disc_session.completed_at) if disc_session else None,
            "questions_count": len(disc_questions),
            "answered_count": sum(1 for q in disc_questions if q.status == "answered"),
        },
        "selected_rows": selected,
        "approved_rows": approved_map,
        "open_rows": open_map,
        "inventory": [e.model_dump() for e in inventory],
        "security_verification": sec_report,
        "infrastructure_verification": infra_report,
        "optimization_basis": opt_basis,
        "optimization_verification": opt_checks,
        "include_drafts_or_stale": include_drafts_or_stale,
        "snapshot_fingerprint": snapshot_fingerprint,
    }


def _provenance_banner(
    mode: ExportMode,
    entries: list[dict[str, Any]],
) -> list[str]:
    lines = [
        f"> **Export Classification**: {'`OFFICIAL APPROVED SPECIFICATION`' if mode == 'official' else '`PREVIEW / NON-OFFICIAL EXPORT (INCLUDES DRAFT OR STALE CONTENT)`'}",
    ]
    for e in entries:
        status_tag = e["selected_status"].upper()
        stale_tag = " · **STALE**" if e.get("stale") else " · `CURRENT`"
        hash_short = (e.get("content_hash") or "none")[:16]
        lines.append(
            f"> - **Source Artifact**: `{e['artifact_key']}` ({e['label']}) · **Version**: `v{e['selected_version']}` · **Status**: `{status_tag}`{stale_tag} · **Content Hash**: `{hash_short}...` · **Approved At**: `{e.get('approved_at') or 'unapproved'}`"
        )
        for sr in e.get("staleness_reasons", []):
            lines.append(f">   - *Staleness Warning*: {sr}")
    lines.append("")
    return lines


def generate_markdown_documents(
    snapshot: dict[str, Any],
    mode: ExportMode = "official",
) -> tuple[dict[str, str], list[dict[str, str]], list[dict[str, str]]]:
    """Deterministically generate Markdown documentation files from the collected project snapshot.
    Returns (documents_by_filename, included_sections, omitted_sections)."""
    proj = snapshot["project"]
    brain = snapshot["brain"]
    inv_by_key = {e["artifact_key"]: e for e in snapshot["inventory"]}
    sel = snapshot["selected_rows"]
    stages = snapshot["stage_statuses"]

    docs: dict[str, str] = {}
    included_sections: list[dict[str, str]] = []
    omitted_sections: list[dict[str, str]] = []

    def _can_include(keys: list[str]) -> tuple[bool, list[dict[str, Any]], str | None]:
        entries = [inv_by_key[k] for k in keys]
        missing = [e for e in entries if not e["included_in_export"]]
        if missing:
            reasons = "; ".join(e["omission_reason"] or f"{e['label']} unavailable" for e in missing)
            return False, entries, reasons
        if mode == "official":
            non_app = [e for e in entries if e["selected_status"] != "approved" or e["stale"] or e["open_draft_version"] is not None]
            if non_app and not snapshot.get("include_drafts_or_stale"):
                # Still include approved content in preview, or mark status accurately
                pass
        return True, entries, None

    # 1. 01-research.md
    ok_res, res_entries, res_omit = _can_include(["research"])
    if ok_res and sel["research"] and sel["research"].content:
        r_doc = sel["research"]
        r_content = r_doc.content
        brief = r_content.get("brief", {})
        lines = [
            f"# 01 — User & Market Research Specification: {proj['name']}",
            "",
            *_provenance_banner(mode, res_entries),
            "## 1. Research Mode & Provenance Disclosure",
            f"- **Execution Mode**: `{r_doc.mode}` ({'No live external web retrieval was performed; findings synthesize user-confirmed discovery facts, user-supplied sources, and labeled hypotheses' if r_doc.mode == 'preliminary' else 'External research mode'})",
            f"- **Unverified Findings Acknowledged at Approval**: `{bool(r_doc.acknowledged_unverified)}`",
            "",
            "## 2. Research Brief",
            f"- **Domain**: {brief.get('domain', 'N/A')}",
            f"- **Target Audience**: {brief.get('target_audience', 'N/A')}",
            f"- **Core Problem**: {brief.get('core_problem', 'N/A')}",
            f"- **Geographic/Market Scope**: {brief.get('geographic_or_market_scope', 'N/A')}",
            "",
            "## 3. Research Findings",
            "| ID | Category | Confidence / Provenance | Title & Summary | Source Refs |",
            "|---|---|---|---|---|",
        ]
        for f in r_content.get("findings", []):
            srcs = ", ".join(f.get("source_ids", [])) or "None"
            lines.append(
                f"| `{f.get('id')}` | `{f.get('category')}` | `{f.get('confidence')}` | **{f.get('title')}** — {f.get('summary')} | `{srcs}` |"
            )
        lines.extend(
            [
                "",
                "## 4. Registered Sources",
                "| Source ID | Origin | Title | URL / Reference | Relevance |",
                "|---|---|---|---|---|",
            ]
        )
        for s in r_content.get("sources", []):
            lines.append(
                f"| `{s.get('id')}` | `{s.get('origin', 'user_provided')}` | {s.get('title')} | `{s.get('url', 'N/A')}` | {s.get('relevance_note', '')} |"
            )
        open_q = r_content.get("open_questions", [])
        if open_q:
            lines.extend(["", "## 5. Unresolved Research Questions"])
            for q in open_q:
                lines.append(f"- {q}")
        docs["01-research.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "01-research.md", "title": "User & Market Research Specification", "source_artifacts": "research"})
    else:
        omitted_sections.append({"filename": "01-research.md", "title": "User & Market Research Specification", "reason": res_omit or "Research report unavailable."})

    # 2. 02-strategy-and-prd.md
    ok_sp, sp_entries, sp_omit = _can_include(["strategy", "prd"])
    if ok_sp and sel["strategy"] and sel["prd"]:
        s_content = sel["strategy"].content
        p_content = sel["prd"].content
        ov = s_content.get("overview", {})
        lines = [
            f"# 02 — Product Strategy & Product Requirements Document (PRD): {proj['name']}",
            "",
            *_provenance_banner(mode, sp_entries),
            "## 1. Product Strategy Overview",
            f"- **Vision**: {ov.get('vision', 'N/A')}",
            f"- **Positioning Statement**: {ov.get('positioning_statement', 'N/A')}",
            f"- **Value Proposition**: {ov.get('value_proposition', 'N/A')}",
            f"- **Business Model**: {ov.get('business_model', 'N/A')}",
            f"- **Differentiation**: {ov.get('differentiation', 'N/A')}",
            "",
            "## 2. Strategic Recommendations & Provenance",
            "| ID | Priority | Provenance Classification | Recommendation & Rationale | Source Refs |",
            "|---|---|---|---|---|",
        ]
        for rec in s_content.get("recommendations", []):
            lines.append(
                f"| `{rec.get('id')}` | `{rec.get('priority')}` | `{rec.get('provenance')}` | **{rec.get('title')}** — {rec.get('rationale')} | `{', '.join(rec.get('source_refs', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. Product Requirements Document (PRD) — Problem & Scope",
                f"- **Problem Statement**: {p_content.get('problem_statement', 'N/A')}",
                f"- **Product Summary**: {p_content.get('product_summary', 'N/A')}",
                "",
                "### 3.1 User Stories (`US-*`)",
                "| ID | Persona / Role | Story | Acceptance Criteria |",
                "|---|---|---|---|",
            ]
        )
        for us in p_content.get("user_stories", []):
            ac_str = "; ".join(us.get("acceptance_criteria", []))
            lines.append(
                f"| `{us.get('id')}` | {us.get('persona')} | {us.get('story', us.get('want', ''))} | {ac_str} |"
            )
        lines.extend(
            [
                "",
                "### 3.2 Functional Requirements (`FR-*`)",
                "| ID | Priority | MVP Scope | Approval Status | Title & Statement | Acceptance Criteria |",
                "|---|---|---|---|---|---|",
            ]
        )
        for fr in p_content.get("functional_requirements", []):
            ac_str = "; ".join(fr.get("acceptance_criteria", []))
            lines.append(
                f"| `{fr.get('id')}` | `{fr.get('priority')}` | `{fr.get('mvp_scope', 'in_mvp')}` | `{fr.get('status', 'approved')}` | **{fr.get('title')}** — {fr.get('statement', '')} | {ac_str} |"
            )
        lines.extend(
            [
                "",
                "### 3.3 Non-Functional Requirements (`NFR-*`)",
                "| ID | Category | Approval Status | Requirement | Verification Criteria |",
                "|---|---|---|---|---|",
            ]
        )
        for nfr in p_content.get("non_functional_requirements", []):
            vc_str = nfr.get("measurable_target") or "; ".join(nfr.get("acceptance_criteria", []))
            lines.append(
                f"| `{nfr.get('id')}` | `{nfr.get('category')}` | `{nfr.get('status', 'approved')}` | {nfr.get('requirement', nfr.get('title', ''))} | {vc_str} |"
            )
        docs["02-strategy-and-prd.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "02-strategy-and-prd.md", "title": "Product Strategy & PRD", "source_artifacts": "strategy, prd"})
    else:
        omitted_sections.append({"filename": "02-strategy-and-prd.md", "title": "Product Strategy & PRD", "reason": sp_omit or "Strategy or PRD unavailable."})

    # 3. 03-ux-specification.md
    ux_keys = ["personas", "journeys", "ia", "wireframes", "ux_review"]
    ok_ux, ux_entries, ux_omit = _can_include(ux_keys)
    if ok_ux:
        p_c = sel["personas"].content
        j_c = sel["journeys"].content
        ia_c = sel["ia"].content
        wf_c = sel["wireframes"].content
        rev_c = sel["ux_review"].content
        lines = [
            f"# 03 — UX Specification: {proj['name']}",
            "",
            *_provenance_banner(mode, ux_entries),
            "## 1. User Personas (`P-*`)",
            "| ID | Name & Role | Evidence Status | Goals | Frustrations | PRD Links |",
            "|---|---|---|---|---|---|",
        ]
        for p in p_c.get("personas", []):
            lines.append(
                f"| `{p.get('id')}` | **{p.get('name')}** ({p.get('role_or_segment', '')}) | `{p.get('evidence_status')}` | {'; '.join(p.get('goals', []))} | {'; '.join(p.get('frustrations', []))} | `{', '.join(p.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 2. User Journeys (`J-*`)",
                "| ID | Name | Persona | Primary Goal | Failure & Recovery Paths | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for j in j_c.get("journeys", []):
            lines.append(
                f"| `{j.get('id')}` | **{j.get('name')}** | `{j.get('persona_id')}` | {j.get('goal', j.get('primary_goal', ''))} | {'; '.join(j.get('failure_recovery_paths', j.get('edge_and_error_flows', [])))} | `{', '.join(j.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. Information Architecture (`IA-*`)",
                "| Node ID | Label | Parent ID | Navigation Group | Route / View | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for node in ia_c.get("nodes", ia_c.get("sitemap_nodes", [])):
            lines.append(
                f"| `{node.get('id')}` | **{node.get('label')}** | `{node.get('parent_id') or 'ROOT'}` | `{node.get('nav_group', 'primary')}` | `{node.get('path_or_route', node.get('route', '/'))}` | `{', '.join(node.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 4. Low-Fidelity Wireframes (`WF-*`)",
                "| Wireframe ID | Screen Name | IA Node | Purpose | UI States Covered | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for wf in wf_c.get("wireframes", wf_c.get("screens", [])):
            st_keys = list((wf.get("states") or {}).keys()) if isinstance(wf.get("states"), dict) else ["default", "loading", "empty", "error", "success"]
            lines.append(
                f"| `{wf.get('id')}` | **{wf.get('name')}** | `{wf.get('ia_node_id')}` | {wf.get('purpose', '')} | `{', '.join(st_keys)}` | `{', '.join(wf.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 5. UX Review & Heuristic Findings (`UXF-*`)",
                "| Finding ID | Origin | Severity | Status | Issue & Recommendation | Resolution Note |",
                "|---|---|---|---|---|---|",
            ]
        )
        for f in rev_c.get("findings", []):
            lines.append(
                f"| `{f.get('id')}` | `{f.get('origin')}` | `{f.get('severity')}` | `{f.get('status')}` | **{f.get('title')}** — {f.get('recommendation', '')} | {f.get('resolution_note') or 'N/A'} |"
            )
        docs["03-ux-specification.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "03-ux-specification.md", "title": "UX Specification", "source_artifacts": ", ".join(ux_keys)})
    else:
        omitted_sections.append({"filename": "03-ux-specification.md", "title": "UX Specification", "reason": ux_omit or "UX artifacts incomplete."})

    # 4. 04-design-system.md
    ok_ds, ds_entries, ds_omit = _can_include(["design_system"])
    if ok_ds and sel["design_system"] and sel["design_system"].content:
        d_c = sel["design_system"].content
        found = d_c.get("foundations", {})
        lines = [
            f"# 04 — Design System Specification: {proj['name']}",
            "",
            *_provenance_banner(mode, ds_entries),
            "## 1. Visual Foundations & Color Tokens",
            "| Token Name | Hex Value | Role & Usage | Contrast / Accessibility Note |",
            "|---|---|---|---|",
        ]
        for ct in found.get("color_tokens", []):
            lines.append(
                f"| `{ct.get('name')}` | `{ct.get('hex_value', ct.get('value', ''))}` | {ct.get('role', ct.get('usage', ''))} | {ct.get('contrast_note', '')} |"
            )
        lines.extend(
            [
                "",
                "## 2. Reusable Component Specifications (`CMP-*`)",
                "| Component ID | Name | Category | Variants | States | Wireframe Links | PRD Links |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for cmp in d_c.get("components", []):
            lines.append(
                f"| `{cmp.get('id')}` | **{cmp.get('name')}** | `{cmp.get('category')}` | `{', '.join(cmp.get('variants', []))}` | `{', '.join(cmp.get('states', []))}` | `{', '.join(cmp.get('wireframe_ids', []))}` | `{', '.join(cmp.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. Design Decisions (`DD-*`)",
                "| Decision ID | Status | Evidence Basis | Title & Rationale |",
                "|---|---|---|---|",
            ]
        )
        for dd in d_c.get("decisions", []):
            lines.append(
                f"| `{dd.get('id')}` | `{dd.get('status')}` | `{dd.get('evidence_basis', 'design_heuristic')}` | **{dd.get('title')}** — {dd.get('rationale', '')} |"
            )
        docs["04-design-system.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "04-design-system.md", "title": "Design System Specification", "source_artifacts": "design_system"})
    else:
        omitted_sections.append({"filename": "04-design-system.md", "title": "Design System Specification", "reason": ds_omit or "Design System unavailable."})

    # 5. 05-prototype.md
    ok_pr, pr_entries, pr_omit = _can_include(["prototype"])
    if ok_pr and sel["prototype"] and sel["prototype"].content:
        pt_c = sel["prototype"].content
        lines = [
            f"# 05 — Interactive Prototype Specification: {proj['name']}",
            "",
            *_provenance_banner(mode, pr_entries),
            "> **Implementation Boundary Note**: This specification defines interactive screen layouts, triggers, and user journey flows. It is a validated product prototype specification, not a deployed end-user production frontend.",
            "",
            "## 1. Prototype Screens (`SCR-*`)",
            "| Screen ID | Name | Route / View | Wireframe Ref | Primary Goal | Components Used | PRD Links |",
            "|---|---|---|---|---|---|---|",
        ]
        for scr in pt_c.get("screens", []):
            lines.append(
                f"| `{scr.get('id')}` | **{scr.get('name')}** | `{scr.get('route_or_view', '/')}` | `{scr.get('wireframe_id')}` | {scr.get('primary_goal', '')} | `{', '.join(scr.get('design_component_ids', []))}` | `{', '.join(scr.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 2. Interactive Flows (`FLOW-*`)",
                "| Flow ID | Name | Linked Journey | Entry Screen | Steps | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for fl in pt_c.get("flows", []):
            step_count = len(fl.get("steps", []))
            lines.append(
                f"| `{fl.get('id')}` | **{fl.get('name')}** | `{fl.get('journey_id')}` | `{fl.get('entry_screen_id', '')}` | {step_count} step(s) | `{', '.join(fl.get('prd_requirement_ids', []))}` |"
            )
        docs["05-prototype.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "05-prototype.md", "title": "Interactive Prototype Specification", "source_artifacts": "prototype"})
    else:
        omitted_sections.append({"filename": "05-prototype.md", "title": "Interactive Prototype Specification", "reason": pr_omit or "Interactive Prototype unavailable."})

    # 6. 06-architecture.md
    ok_ar, ar_entries, ar_omit = _can_include(["architecture"])
    if ok_ar and sel["architecture"] and sel["architecture"].content:
        a_c = sel["architecture"].content
        sys_ov = a_c.get("system_overview", {})
        data_arch = a_c.get("data_architecture", {})
        api_arch = a_c.get("api_architecture", {})
        dep_arch = a_c.get("deployment_architecture", {})
        lines = [
            f"# 06 — Product Architecture, Data Model, API Contracts & ADRs: {proj['name']}",
            "",
            *_provenance_banner(mode, ar_entries),
            "## 1. System Overview & Architectural Style",
            f"- **Architectural Style**: {sys_ov.get('architectural_style', 'N/A')}",
            f"- **System Summary**: {sys_ov.get('system_summary', 'N/A')}",
            "",
            "### 1.1 System Components (`COMP-*`)",
            "| Component ID | Name | Layer | Responsibilities | Communicates With | PRD Links |",
            "|---|---|---|---|---|---|",
        ]
        for c in sys_ov.get("components", []):
            lines.append(
                f"| `{c.get('id')}` | **{c.get('name')}** | `{c.get('layer')}` | {c.get('responsibility', '')} | `{', '.join(c.get('communicates_with', []))}` | `{', '.join(c.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 2. Data Architecture & Domain Entities (`ENT-*`)",
                "| Entity ID | Name | Owning Component | Status | Key Fields | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for ent in data_arch.get("entities", []):
            f_names = [f.get("name", "") for f in ent.get("fields", [])]
            lines.append(
                f"| `{ent.get('id')}` | **{ent.get('name')}** | `{ent.get('owning_component_id')}` | `{ent.get('status', 'confirmed')}` | `{', '.join(f_names)}` | `{', '.join(ent.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. API & Integration Contracts (`API-*`)",
                "| Endpoint ID | Method & Path | Component | Auth | Implementation Status | Purpose | PRD Links |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for ep in api_arch.get("endpoints", []):
            lines.append(
                f"| `{ep.get('id')}` | `{ep.get('method')} {ep.get('path')}` | `{ep.get('component_id')}` | `{ep.get('auth_requirement', 'authenticated')}` | `{ep.get('implementation_status', 'proposed_target')}` | {ep.get('purpose', '')} | `{', '.join(ep.get('prd_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 4. Deployment & Runtime Services (`SVC-*`)",
                "| Service ID | Name | Runtime | Status | Components Hosted | Scaling & Health Strategy |",
                "|---|---|---|---|---|---|",
            ]
        )
        for svc in dep_arch.get("services_and_infrastructure", []):
            lines.append(
                f"| `{svc.get('id')}` | **{svc.get('name')}** | `{svc.get('runtime_or_technology', '')}` | `{svc.get('status', 'proposed_target')}` | `{', '.join(svc.get('component_ids', []))}` | {svc.get('scaling_and_resilience', '')} |"
            )
        lines.extend(
            [
                "",
                "## 5. Architecture Decision Records (`ADR-*`)",
                "| ADR ID | Status | Title | Decision | Consequences & Risks | PRD Links |",
                "|---|---|---|---|---|---|",
            ]
        )
        for adr in a_c.get("decisions", []):
            lines.append(
                f"| `{adr.get('id')}` | `{adr.get('status')}` | **{adr.get('title')}** | {adr.get('decision', '')} | {'; '.join(adr.get('consequences_and_risks', []))} | `{', '.join(adr.get('prd_requirement_ids', []))}` |"
            )
        docs["06-architecture.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "06-architecture.md", "title": "Product Architecture & API/Data Contracts", "source_artifacts": "architecture"})
    else:
        omitted_sections.append({"filename": "06-architecture.md", "title": "Product Architecture & API/Data Contracts", "reason": ar_omit or "Product Architecture unavailable."})

    # 7. 07-testing-and-security.md
    sec_rep = snapshot["security_verification"]
    sec_lines = [
        f"# 07 — Testing & Security Verification Report: {proj['name']}",
        "",
        f"> **Export Classification**: {'`OFFICIAL APPROVED SPECIFICATION`' if mode == 'official' else '`PREVIEW / NON-OFFICIAL EXPORT`'}",
        f"> - **Source**: Deterministic Phase 14 Security & Testing Verification (`security_verification.py`) · **Testing Stage**: `{stages.get('testing')}` · **Security Stage**: `{stages.get('security')}`",
        "",
        "## 1. Verification Summary",
        f"- **Testing Ready**: `{sec_rep.get('testing_ready')}`",
        f"- **Security Ready**: `{sec_rep.get('security_ready')}`",
        "",
        "## 2. Automated Verification Checks (`CHK-*`)",
        "| Check ID | Category | Status | Title & Details |",
        "|---|---|---|---|",
    ]
    for chk in sec_rep.get("checks", []):
        sec_lines.append(
            f"| `{chk.get('id')}` | `{chk.get('category')}` | `{chk.get('status')}` | **{chk.get('title')}** — {chk.get('detail')} |"
        )
    sec_lines.extend(
        [
            "",
            "## 3. Unverified Runtime & External Boundaries",
        ]
    )
    for lim in sec_rep.get("unverified_boundaries", []):
        sec_lines.append(f"- {lim}")
    docs["07-testing-and-security.md"] = "\n".join(sec_lines) + "\n"
    included_sections.append({"filename": "07-testing-and-security.md", "title": "Testing & Security Verification Report", "source_artifacts": "security_verification"})

    # 8. 08-infrastructure-and-deployment.md
    inf_rep = snapshot["infrastructure_verification"]
    inf_lines = [
        f"# 08 — Infrastructure, DevOps & Deployment Specification: {proj['name']}",
        "",
        f"> **Export Classification**: {'`OFFICIAL APPROVED SPECIFICATION`' if mode == 'official' else '`PREVIEW / NON-OFFICIAL EXPORT`'}",
        f"> - **Source**: Deterministic Phase 15 Infrastructure Verification (`infrastructure_verification.py`) · **Deployment Stage**: `{stages.get('deployment')}` · **Monitoring Stage**: `{stages.get('monitoring')}`",
        "",
        "## 1. Infrastructure & Deployment Readiness",
        f"- **All Phase 15 Checks Passed**: `{inf_rep.get('all_checks_passed')}`",
        "",
        "## 2. Infrastructure Verification Checks (`INF-*`)",
        "| Check ID | Stage | Status | Title & Details |",
        "|---|---|---|---|",
    ]
    for chk in inf_rep.get("checks", []):
        inf_lines.append(
            f"| `{chk.get('id')}` | `{chk.get('stage')}` | `{chk.get('status')}` | **{chk.get('title')}** — {chk.get('detail')} |"
        )
    inf_lines.extend(
        [
            "",
            "## 3. Environment & Operational Boundaries",
        ]
    )
    for lim in inf_rep.get("unverified_boundaries", []):
        inf_lines.append(f"- {lim}")
    docs["08-infrastructure-and-deployment.md"] = "\n".join(inf_lines) + "\n"
    included_sections.append({"filename": "08-infrastructure-and-deployment.md", "title": "Infrastructure, DevOps & Deployment Specification", "source_artifacts": "infrastructure_verification"})

    # 9. 09-seo.md
    ok_seo, seo_entries, seo_omit = _can_include(["seo"])
    if ok_seo and sel["seo"] and sel["seo"].content:
        seo_c = sel["seo"].content
        seo_model = opt.SeoContent.model_validate(seo_c)
        strat = seo_c.get("seo_strategy", {})
        lines = [
            f"# 09 — Search Engine Optimization (SEO) Specification: {proj['name']}",
            "",
            *_provenance_banner(mode, seo_entries),
            "## 1. SEO Strategy & Indexing Policy",
            f"- **Primary Search Intent**: {strat.get('primary_search_intent', '')}",
            f"- **Target Audience Summary**: {strat.get('target_audience_summary', '')}",
            f"- **Canonical Domain Strategy**: {strat.get('canonical_domain_strategy', '')}",
            f"- **Crawl & Indexing Policy**: {strat.get('crawl_and_indexing_policy', '')}",
            "",
            "## 2. Page Metadata & Indexability (`SEO-PAGE-*`)",
            "| ID | Screen | Route Path | Visibility | Robots Directive | In Sitemap | Title Template | Structured Data | PRD Links |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for pm in seo_c.get("page_metadata", []):
            lines.append(
                f"| `{pm.get('id')}` | `{pm.get('screen_id')}` | `{pm.get('route_path')}` | `{pm.get('visibility')}` | `{pm.get('robots_index')},{pm.get('robots_follow')}` | `{pm.get('include_in_sitemap')}` | {pm.get('title_template')} | `{pm.get('structured_data_type')}` | `{', '.join(pm.get('linked_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. Generated `/sitemap.xml` Preview",
                "```xml",
                opt.generate_sitemap_xml_preview(seo_model).strip(),
                "```",
                "",
                "## 4. Generated `/robots.txt` Preview",
                "```text",
                opt.generate_robots_txt_preview(seo_model).strip(),
                "```",
            ]
        )
        docs["09-seo.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "09-seo.md", "title": "SEO Specification", "source_artifacts": "seo"})
    else:
        omitted_sections.append({"filename": "09-seo.md", "title": "SEO Specification", "reason": seo_omit or "SEO specification unavailable."})

    # 10. 10-analytics.md
    ok_an, an_entries, an_omit = _can_include(["analytics"])
    if ok_an and sel["analytics"] and sel["analytics"].content:
        an_c = sel["analytics"].content
        mp = an_c.get("measurement_plan", {})
        cp = an_c.get("consent_and_privacy", {})
        lines = [
            f"# 10 — Product Analytics, Event Taxonomy & Privacy Governance: {proj['name']}",
            "",
            *_provenance_banner(mode, an_entries),
            "## 1. Measurement Plan & KPIs",
            f"- **Objective**: {mp.get('measurement_objective', '')}",
            f"- **Data Retention Policy**: {mp.get('data_retention_policy', '')}",
            f"- **IP Anonymization**: `{mp.get('ip_anonymization_enabled')}` · **Respect Do-Not-Track**: `{mp.get('respect_do_not_track')}`",
            "",
            "## 2. Consent & Privacy Governance",
            f"- **Default Consent State**: `{cp.get('default_consent_state')}`",
            f"- **Third-Party Transmission Enabled**: `{cp.get('third_party_transmission_enabled')}`",
            f"- **User Opt-Out Mechanism**: {cp.get('user_opt_out_mechanism', '')}",
            f"- **Prohibited Sensitive Fields**: `{', '.join(cp.get('prohibited_fields', []))}`",
            "",
            "## 3. Event Taxonomy (`EVT-*`)",
            "| ID | Event Name | Category | Screen | Journey | Consent Category | Requires Opt-In | Properties | PRD Links |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for ev in an_c.get("events", []):
            p_names = [f"{p.get('name')}:{p.get('data_type')}" for p in ev.get("properties", [])]
            lines.append(
                f"| `{ev.get('id')}` | `{ev.get('event_name')}` | `{ev.get('category')}` | `{ev.get('screen_id')}` | `{ev.get('journey_id') or 'N/A'}` | `{ev.get('consent_category')}` | `{ev.get('requires_opt_in')}` | `{', '.join(p_names)}` | `{', '.join(ev.get('linked_requirement_ids', []))}` |"
            )
        docs["10-analytics.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "10-analytics.md", "title": "Analytics & Privacy Specification", "source_artifacts": "analytics"})
    else:
        omitted_sections.append({"filename": "10-analytics.md", "title": "Analytics & Privacy Specification", "reason": an_omit or "Analytics specification unavailable."})

    # 11. 11-performance.md
    ok_pf, pf_entries, pf_omit = _can_include(["performance"])
    if ok_pf and sel["performance"] and sel["performance"].content:
        pf_c = sel["performance"].content
        cwv = pf_c.get("core_web_vitals", {})
        lines = [
            f"# 11 — Performance Budgets, Core Web Vitals & Measurement Evidence: {proj['name']}",
            "",
            *_provenance_banner(mode, pf_entries),
            "## 1. Core Web Vitals Budgets & Measurement Posture",
            f"- **Measurement Posture**: `{cwv.get('measurement_posture', 'target_budget_only')}`",
            f"- **LCP Target**: `<={cwv.get('lcp_ms')}ms` · **INP Target**: `<={cwv.get('inp_ms')}ms` · **CLS Max**: `<={cwv.get('cls_max')}` · **FCP Target**: `<={cwv.get('fcp_ms')}ms` · **TTFB Target**: `<={cwv.get('ttfb_ms')}ms`",
            "",
            "## 2. Route Asset Budgets (`PERF-ROUTE-*`)",
            "| ID | Screen | Route Path | Max JS (KiB) | Max CSS (KiB) | Max Image (KiB) | Caching Policy | PRD Links |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for rb in pf_c.get("route_budgets", []):
            lines.append(
                f"| `{rb.get('id')}` | `{rb.get('screen_id')}` | `{rb.get('route_path')}` | `{rb.get('max_js_kb')}` | `{rb.get('max_css_kb')}` | `{rb.get('max_image_kb')}` | {rb.get('caching_policy')} | `{', '.join(rb.get('linked_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 3. Backend API Latency & Payload Budgets (`PERF-API-*`)",
                "| ID | Endpoint ID | Route Pattern | p95 (ms) | p99 (ms) | Max Payload (KiB) | Caching & Query Strategy | PRD Links |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for ab in pf_c.get("api_budgets", []):
            lines.append(
                f"| `{ab.get('id')}` | `{ab.get('endpoint_id')}` | `{ab.get('route_pattern')}` | `{ab.get('p95_latency_ms')}` | `{ab.get('p99_latency_ms')}` | `{ab.get('max_payload_kb')}` | {ab.get('caching_and_query_strategy')} | `{', '.join(ab.get('linked_requirement_ids', []))}` |"
            )
        lines.extend(
            [
                "",
                "## 4. Recorded Measurement Evidence (`EVD-*`)",
                "| Evidence ID | Metric | Target | Measured Value | Status | Environment | Tool | Measured At | Limitations |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for evd in pf_c.get("measurement_evidence", []):
            lines.append(
                f"| `{evd.get('id')}` | {evd.get('metric_name')} | `{evd.get('target_value')} {evd.get('unit')}` | `{evd.get('measured_value') or 'Unmeasured (Target Only)'}` | `{evd.get('status')}` | `{evd.get('environment')}` | {evd.get('measurement_tool')} | `{evd.get('measured_at') or 'N/A'}` | {evd.get('limitations')} |"
            )
        docs["11-performance.md"] = "\n".join(lines) + "\n"
        included_sections.append({"filename": "11-performance.md", "title": "Performance Budgets & Evidence", "source_artifacts": "performance"})
    else:
        omitted_sections.append({"filename": "11-performance.md", "title": "Performance Budgets & Evidence", "reason": pf_omit or "Performance specification unavailable."})

    # 12. 12-traceability.md
    if sel["prd"] and sel["prd"].content and sel["architecture"] and sel["architecture"].content:
        tr_entries = [inv_by_key[k] for k in ("prd", "architecture") if inv_by_key[k]["included_in_export"]]
        arch_tr = sel["architecture"].content.get("traceability", [])
        opt_basis = snapshot["optimization_basis"]
        seo_cov_map: dict[str, str] = {}
        an_cov_map: dict[str, str] = {}
        pf_cov_map: dict[str, str] = {}
        if sel["seo"] and sel["seo"].content:
            st = opt.compute_seo_traceability(opt.SeoContent.model_validate(sel["seo"].content), opt_basis)
            seo_cov_map = {r.requirement_id: (",".join(r.mapped_item_ids) or r.coverage_status) for r in st.requirement_coverage}
        if sel["analytics"] and sel["analytics"].content:
            at = opt.compute_analytics_traceability(opt.AnalyticsContent.model_validate(sel["analytics"].content), opt_basis)
            an_cov_map = {r.requirement_id: (",".join(r.mapped_item_ids) or r.coverage_status) for r in at.requirement_coverage}
        if sel["performance"] and sel["performance"].content:
            pt = opt.compute_performance_traceability(opt.PerformanceContent.model_validate(sel["performance"].content), opt_basis)
            pf_cov_map = {r.requirement_id: (",".join(r.mapped_item_ids) or r.coverage_status) for r in pt.requirement_coverage}

        t_lines = [
            f"# 12 — End-to-End Requirement Traceability Matrix: {proj['name']}",
            "",
            *_provenance_banner(mode, tr_entries),
            "## 1. Cross-Lifecycle Requirement Traceability (`PRD -> UX/Design -> Architecture -> Optimization`)",
            "| PRD Req ID | Kind | Title | Components (`COMP-*`) | Entities / APIs | Design / Prototype Refs | SEO | Analytics | Performance | Traced |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in arch_tr:
            rid = row.get("requirement_id", "")
            ent_api = row.get("entity_ids", []) + row.get("endpoint_ids", []) + row.get("backend_module_ids", [])
            t_lines.append(
                f"| `{rid}` | `{row.get('requirement_kind')}` | {row.get('requirement_title')} | `{', '.join(row.get('component_ids', []))}` | `{', '.join(ent_api)}` | `{', '.join(row.get('design_refs', []))}` | `{seo_cov_map.get(rid, 'N/A')}` | `{an_cov_map.get(rid, 'N/A')}` | `{pf_cov_map.get(rid, 'N/A')}` | `{row.get('fully_traced')}` |"
            )
        docs["12-traceability.md"] = "\n".join(t_lines) + "\n"
        included_sections.append({"filename": "12-traceability.md", "title": "End-to-End Requirement Traceability Matrix", "source_artifacts": "prd, architecture, seo, analytics, performance"})
    else:
        omitted_sections.append({"filename": "12-traceability.md", "title": "End-to-End Requirement Traceability Matrix", "reason": "Requires both PRD and Product Architecture artifacts."})

    # Always generate README.md summarizing project, scope, included documents, omitted sections, and known limitations
    idea = brain.get("idea", {})
    readme_lines = [
        f"# {proj['name']} — WebForge Product Specification & Documentation Bundle",
        "",
        f"> **Export Classification**: {'`OFFICIAL APPROVED SPECIFICATION BUNDLE`' if mode == 'official' else '`PREVIEW / NON-OFFICIAL EXPORT BUNDLE`'}",
        f"> **Project ID**: `{proj['id']}` · **Brain Revision**: `v{snapshot['brain_version']}` · **Snapshot Fingerprint**: `{snapshot['snapshot_fingerprint'][:24]}...`",
        "",
        "## 1. Project Overview & Scope",
        f"- **Product Name**: {idea.get('product_name') or proj['name']}",
        f"- **Product Type**: {idea.get('product_type') or 'Web Application'}",
        f"- **Core Problem**: {idea.get('problem') or proj['description'] or 'N/A'}",
        f"- **Discovery Status**: `{snapshot['discovery']['status']}` ({snapshot['discovery']['answered_count']}/{snapshot['discovery']['questions_count']} questions answered)",
        "",
        "## 2. Artifact Provenance & Approval Inventory",
        "| Artifact | Version | Status | Staleness | Content Hash (SHA-256) | Included |",
        "|---|---|---|---|---|---|",
    ]
    for e in snapshot["inventory"]:
        stale_lbl = "STALE" if e["stale"] else "current"
        h_lbl = f"`{e['content_hash'][:16]}...`" if e["content_hash"] else "`none`"
        ver_lbl = f"v{e['selected_version']}" if e['selected_version'] else "—"
        readme_lines.append(
            f"| **{e['label']}** (`{e['artifact_key']}`) | `{ver_lbl}` | `{e['selected_status']}` | `{stale_lbl}` | {h_lbl} | `{'YES' if e['included_in_export'] else 'NO'}` |"
        )

    all_inc = [{"filename": "README.md", "title": "Project Summary, Scope & Bundle Inventory", "source_artifacts": "project, brain"}] + included_sections
    readme_lines.extend(
        [
            "",
            "## 3. Included Bundle Documents",
            "| Filename | Document Title | Source Artifacts |",
            "|---|---|---|",
        ]
    )
    for inc in all_inc:
        readme_lines.append(f"| `{inc['filename']}` | {inc['title']} | `{inc['source_artifacts']}` |")
    readme_lines.append("| `MANIFEST.json` | Machine-Readable Export Manifest, Hashes & Validation Findings | `all` |")

    if omitted_sections:
        readme_lines.extend(
            [
                "",
                "## 4. Omitted / Unavailable Sections",
                "| Filename | Section Title | Omission Reason |",
                "|---|---|---|",
            ]
        )
        for om in omitted_sections:
            readme_lines.append(f"| `{om['filename']}` | {om['title']} | {om['reason']} |")

    readme_lines.extend(
        [
            "",
            "## 5. Known Limitations & Evidence Boundaries",
            "- This bundle exports **validated product specifications, architecture contracts, and verification evidence** persisted in WebForge.",
            "- Specifications marked `proposed_target` or `target_budget_only` define engineering targets for the generated product and must not be interpreted as live production traffic metrics unless accompanied by a `measured_pass` evidence record (`EVD-*`).",
            "- No credentials, API keys, JWT secrets, session tokens, or database passwords are included in this export.",
        ]
    )

    ordered_docs: dict[str, str] = {"README.md": "\n".join(readme_lines) + "\n"}
    for k, v in docs.items():
        ordered_docs[k] = v

    return ordered_docs, all_inc, omitted_sections


def validate_project_export(
    snapshot: dict[str, Any],
    documents: dict[str, str],
    mode: ExportMode = "official",
) -> dict[str, Any]:
    """Run deterministic pre-export validation checks and classify findings into blocking_error, warning, and info."""
    findings: list[ExportValidationFinding] = []
    inv_by_key = {e["artifact_key"]: e for e in snapshot["inventory"]}
    sel = snapshot["selected_rows"]
    brain = snapshot["brain"]
    pid = snapshot["project"]["id"]

    # 1. Check required artifacts, approval state, open drafts, staleness, and hash integrity
    for e in snapshot["inventory"]:
        key = e["artifact_key"]
        label = e["label"]
        wpath = e["workspace_path"]
        if not e["present"]:
            findings.append(
                ExportValidationFinding(
                    code="MISSING_REQUIRED_ARTIFACT",
                    severity="blocking_error",
                    section=key,
                    title=f"Missing required artifact: {label}",
                    message=f"{label} has no approved version available for export.",
                    remediation=f"Open {label} ({wpath}), generate or initialize the specification, submit for review, and approve it.",
                    workspace_path=wpath,
                )
            )
            continue

        if e["selected_status"] != "approved":
            findings.append(
                ExportValidationFinding(
                    code="UNAPPROVED_SOURCE_ARTIFACT",
                    severity="blocking_error",
                    section=key,
                    title=f"Unapproved source artifact: {label} v{e['selected_version']}",
                    message=f"{label} v{e['selected_version']} is currently in status '{e['selected_status']}' and has not been approved.",
                    remediation=f"Submit and approve {label} v{e['selected_version']} in {wpath} before generating an official export.",
                    workspace_path=wpath,
                )
            )
        elif e["open_draft_version"] is not None:
            findings.append(
                ExportValidationFinding(
                    code="OPEN_DRAFT_EXISTS",
                    severity="blocking_error",
                    section=key,
                    title=f"Open unapproved draft exists for {label} (v{e['open_draft_version']})",
                    message=f"{label} has an approved version (v{e['approved_version']}), but an unapproved draft (v{e['open_draft_version']}) is currently open.",
                    remediation=f"Complete and approve draft v{e['open_draft_version']} in {wpath} so official documentation reflects current work.",
                    workspace_path=wpath,
                )
            )

        if e["stale"]:
            findings.append(
                ExportValidationFinding(
                    code="STALE_SOURCE_ARTIFACT",
                    severity="blocking_error",
                    section=key,
                    title=f"Stale source artifact: {label} v{e['selected_version']}",
                    message="; ".join(e["staleness_reasons"]),
                    remediation=f"Update and re-approve {label} in {wpath} against the latest upstream artifacts.",
                    workspace_path=wpath,
                )
            )

        if not e["hash_verified"]:
            findings.append(
                ExportValidationFinding(
                    code="ARTIFACT_HASH_MISMATCH",
                    severity="blocking_error",
                    section=key,
                    title=f"Content hash mismatch on {label} v{e['selected_version']}",
                    message=f"Stored content_hash for {label} v{e['selected_version']} does not match recomputed SHA-256 digest.",
                    remediation=f"Re-save and re-approve {label} in {wpath} to restore cryptographic provenance integrity.",
                    workspace_path=wpath,
                )
            )

    # 2. Verify ProjectBrain provenance pointers match approved artifacts
    brain_pointer_checks = [
        ("research", brain.get("research", {}).get("content_hash")),
        ("strategy", brain.get("strategy", {}).get("content_hash")),
        ("prd", brain.get("prd", {}).get("content_hash")),
        ("architecture", brain.get("architecture_spec", {}).get("content_hash")),
        ("seo", brain.get("optimization_spec", {}).get("seo", {}).get("content_hash")),
        ("analytics", brain.get("optimization_spec", {}).get("analytics", {}).get("content_hash")),
        ("performance", brain.get("optimization_spec", {}).get("performance", {}).get("content_hash")),
    ]
    for key, brain_hash in brain_pointer_checks:
        e = inv_by_key[key]
        if e["present"] and e["selected_status"] == "approved" and brain_hash and e["content_hash"] != brain_hash:
            findings.append(
                ExportValidationFinding(
                    code="BRAIN_PROVENANCE_MISMATCH",
                    severity="blocking_error",
                    section=key,
                    title=f"Project Brain pointer mismatch for {e['label']}",
                    message=f"ProjectBrain pointer hash ({brain_hash[:12]}...) does not match approved {e['label']} hash ({(e['content_hash'] or '')[:12]}...).",
                    remediation=f"Re-approve {e['label']} in {e['workspace_path']} to synchronize Project Brain provenance.",
                    workspace_path=e["workspace_path"],
                )
            )

    # 3. Check cross-artifact traceability & PRD requirement coverage
    arch_row = sel.get("architecture")
    if arch_row and arch_row.content:
        comp_check = arch.evaluate_architecture_completeness(arch_row.content)
        if not comp_check["complete_traceability"]:
            findings.append(
                ExportValidationFinding(
                    code="INCOMPLETE_REQUIREMENT_TRACEABILITY",
                    severity="blocking_error",
                    section="architecture",
                    title="Incomplete PRD requirement traceability in Product Architecture",
                    message=f"Uncovered PRD requirements: {comp_check['uncovered_requirements']}; unreferenced components: {comp_check['unreferenced_components']}.",
                    remediation=f"Map all PRD requirements in /projects/{pid}/architecture.",
                    workspace_path=f"/projects/{pid}/architecture",
                )
            )

    opt_basis = snapshot["optimization_basis"]
    for area in opt.OPTIMIZATION_AREAS:
        o_row = sel.get(area)
        if o_row and o_row.content:
            comp_opt = opt.evaluate_optimization_completeness(area, o_row.content, opt_basis)
            if comp_opt.uncovered_requirement_ids or comp_opt.unresolved_constraint_errors:
                findings.append(
                    ExportValidationFinding(
                        code=f"{area.upper()}_TRACEABILITY_ERROR",
                        severity="blocking_error",
                        section=area,
                        title=f"{area.upper()} specification has unresolved traceability or coverage gaps",
                        message=f"Uncovered requirements: {comp_opt.uncovered_requirement_ids}; errors: {comp_opt.unresolved_constraint_errors}",
                        remediation=f"Resolve coverage or reference errors in /projects/{pid}/{area}.",
                        workspace_path=f"/projects/{pid}/{area}",
                    )
                )

    # 4. Check UX Review critical findings & Security/Infrastructure verification checks
    ux_rev_row = sel.get("ux_review")
    if ux_rev_row and ux_rev_row.content:
        rc = ux.review_counts(ux_rev_row.content)
        if rc["critical_open"] > 0:
            findings.append(
                ExportValidationFinding(
                    code="UNRESOLVED_CRITICAL_UX_FINDING",
                    severity="blocking_error",
                    section="ux_review",
                    title=f"UX Review has {rc['critical_open']} unresolved critical finding(s)",
                    message="Critical UX review findings must be resolved or have documented risk acceptance before official export.",
                    remediation=f"Resolve critical findings in /projects/{pid}/ux-review.",
                    workspace_path=f"/projects/{pid}/ux-review",
                )
            )

    sec_rep = snapshot["security_verification"]
    failed_sec_checks = [c for c in sec_rep.get("checks", []) if c.get("status") != "passed"]
    if failed_sec_checks:
        findings.append(
            ExportValidationFinding(
                code="SECURITY_VERIFICATION_INCOMPLETE",
                severity="blocking_error",
                section="testing_and_security",
                title="Security & Testing verification checks are not all passing",
                message="; ".join(f"{c['id']}: {c['details']}" for c in failed_sec_checks),
                remediation="Resolve failing security or hash provenance checks before exporting official documentation.",
                workspace_path=f"/projects/{pid}/overview",
            )
        )

    # 5. Informational / warning disclosures for preliminary research, unverified AI acknowledgments, and target-only budgets
    res_row = sel.get("research")
    if res_row and res_row.mode == "preliminary":
        findings.append(
            ExportValidationFinding(
                code="PRELIMINARY_RESEARCH_MODE",
                severity="info",
                section="research",
                title="Research report was generated in preliminary mode",
                message="Research findings synthesize user-confirmed discovery facts and user-provided sources without live web crawling.",
                remediation="No action required for specification export; disclosed in 01-research.md and MANIFEST.json.",
                workspace_path=f"/projects/{pid}/research",
            )
        )

    pf_row = sel.get("performance")
    if pf_row and pf_row.content:
        posture = pf_row.content.get("core_web_vitals", {}).get("measurement_posture", "target_budget_only")
        if posture == "target_budget_only":
            findings.append(
                ExportValidationFinding(
                    code="PERFORMANCE_TARGET_BUDGET_ONLY",
                    severity="info",
                    section="performance",
                    title="Performance specification records target budgets without live benchmark observations",
                    message="Core Web Vitals and API latency figures are documented as engineering target budgets (target_budget_only).",
                    remediation="Record measured observations in /projects/:id/performance once benchmark runs are executed.",
                    workspace_path=f"/projects/{pid}/performance",
                )
            )

    # 6. Secret & sensitive data scan across generated documents
    secret_hits = scan_export_for_secrets(documents, "{}")
    for hit in secret_hits:
        findings.append(
            ExportValidationFinding(
                code="SECRET_DETECTED_IN_EXPORT",
                severity="blocking_error",
                section=hit["file"],
                title=f"Sensitive value or secret pattern detected in {hit['file']}",
                message=hit["message"],
                remediation="Remove credentials, private keys, or internal filesystem paths from source artifacts before exporting.",
                workspace_path=f"/projects/{pid}/overview",
            )
        )

    blocking = [f for f in findings if f.severity == "blocking_error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    return {
        "ready_for_official_export": len(blocking) == 0,
        "blocking_error_count": len(blocking),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "findings": [f.model_dump() for f in findings],
    }


def build_export_manifest(
    snapshot: dict[str, Any],
    documents: dict[str, str],
    included_sections: list[dict[str, str]],
    omitted_sections: list[dict[str, str]],
    validation_summary: dict[str, Any],
    mode: ExportMode = "official",
    export_version: int | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Build deterministic MANIFEST.json dictionary, serialized JSON string, and SHA-256 digest."""
    file_digests: dict[str, dict[str, Any]] = {}
    for fname, content in documents.items():
        safe_name = validate_safe_archive_path(fname)
        raw_bytes = content.encode("utf-8")
        file_digests[safe_name] = {
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "size_bytes": len(raw_bytes),
        }

    known_limitations: list[str] = [
        "Exported documents represent validated product specifications and verification reports persisted in WebForge, not live end-user production telemetry.",
    ]
    if snapshot["selected_rows"].get("research") and snapshot["selected_rows"]["research"].mode == "preliminary":
        known_limitations.append("Research report was generated in preliminary mode without live external web crawling.")
    pf_row = snapshot["selected_rows"].get("performance")
    if pf_row and pf_row.content:
        posture = pf_row.content.get("core_web_vitals", {}).get("measurement_posture", "target_budget_only")
        if posture == "target_budget_only":
            known_limitations.append("Performance budgets are currently in target_budget_only posture (no live Lighthouse/load-test run claimed).")

    manifest: dict[str, Any] = {
        "schema_version": "webforge.documentation_export.v1",
        "export_mode": mode,
        "official_approved_bundle": mode == "official" and validation_summary["ready_for_official_export"],
        "export_version": export_version,
        "project": {
            "id": snapshot["project"]["id"],
            "name": snapshot["project"]["name"],
            "description": snapshot["project"]["description"],
            "brain_version": snapshot["brain_version"],
        },
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "artifact_inventory": snapshot["inventory"],
        "included_documents": included_sections,
        "omitted_sections": omitted_sections,
        "files": file_digests,
        "validation_summary": validation_summary,
        "known_limitations": known_limitations,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    return manifest, manifest_json, manifest_sha256


def build_deterministic_zip_bytes(
    documents: dict[str, str],
    manifest_json: str,
) -> tuple[bytes, str]:
    """Package UTF-8 Markdown documents and MANIFEST.json into a deterministic ZIP archive."""
    seen_paths: set[str] = set()
    entries: list[tuple[str, bytes]] = []

    # Canonicalize entries instead of trusting dict insertion order. SQLite preserves JSON
    # insertion order, but PostgreSQL JSONB may return object keys in a different order.
    # Keep README first for human-friendly archive browsing, then sort the numbered documents.
    ordered_documents = sorted(documents.items(), key=lambda item: (item[0] != "README.md", item[0]))
    for fname, content in ordered_documents:
        safe_path = validate_safe_archive_path(fname)
        if safe_path in seen_paths:
            raise ValueError(f"Duplicate archive entry path: {safe_path}")
        seen_paths.add(safe_path)
        entries.append((safe_path, content.encode("utf-8")))

    manifest_path = validate_safe_archive_path("MANIFEST.json")
    if manifest_path in seen_paths:
        raise ValueError("MANIFEST.json conflicts with an existing document path.")
    seen_paths.add(manifest_path)
    entries.append((manifest_path, manifest_json.encode("utf-8")))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc_path, data in entries:
            zinfo = zipfile.ZipInfo(filename=arc_path, date_time=FIXED_ZIP_DATETIME)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o644 << 16
            zf.writestr(zinfo, data)

    zip_bytes = buf.getvalue()
    bundle_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    return zip_bytes, bundle_sha256


def build_consolidated_markdown(documents: dict[str, str], manifest: dict[str, Any]) -> str:
    """Combine all generated Markdown documents into a single consolidated UTF-8 Markdown specification."""
    proj_name = manifest["project"]["name"]
    mode = manifest["export_mode"].upper()
    parts: list[str] = [
        f"# {proj_name} — Consolidated Product Specification & Documentation ({mode})",
        "",
        f"- **Schema Version**: `{manifest['schema_version']}`",
        f"- **Snapshot Fingerprint**: `{manifest['snapshot_fingerprint']}`",
        f"- **Included Documents**: `{len(documents)}`",
        f"- **Omitted Sections**: `{len(manifest.get('omitted_sections', []))}`",
        "",
    ]
    for fname, content in documents.items():
        parts.append(f"<!-- BEGIN FILE: {fname} -->")
        parts.append(content.strip())
        parts.append(f"<!-- END FILE: {fname} -->")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def build_validated_json_export(
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    """Build a clean, deterministic JSON export of validated project specifications without ORM internals or secrets."""
    sel = snapshot["selected_rows"]
    artifacts_payload: dict[str, Any] = {}
    for e in snapshot["inventory"]:
        key = e["artifact_key"]
        row = sel.get(key)
        if row is not None and e["included_in_export"]:
            artifacts_payload[key] = {
                "version": row.version,
                "status": row.status,
                "content_hash": row.content_hash,
                "approved_at": _iso(getattr(row, "approved_at", None)),
                "stale": e["stale"],
                "staleness_reasons": e["staleness_reasons"],
                "content": row.content,
            }
    payload = {
        "schema_version": "webforge.project_specification_json.v1",
        "manifest": manifest,
        "project": snapshot["project"],
        "discovery": snapshot["discovery"],
        "artifacts": artifacts_payload,
        "security_verification": {
            "testing_ready": snapshot["security_verification"].get("testing_ready"),
            "security_ready": snapshot["security_verification"].get("security_ready"),
            "checks": snapshot["security_verification"].get("checks", []),
        },
        "infrastructure_verification": {
            "all_checks_passed": all(c.get("status") == "passed" for c in snapshot["infrastructure_verification"].get("checks", [])),
            "checks": snapshot["infrastructure_verification"].get("checks", []),
        },
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

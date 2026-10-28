"""Phase 17: Documentation & Export FastAPI Router, Lifecycle Completion Guard & Invalidation Hooks."""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import documentation_export as doc_exp
from .api import commit_brain, current_user, owned
from .brain import DocumentationBrain
from .db import get_db
from .lifecycle import STAGE_DEPS, STAGES, unmet_deps
from .models import DocumentationExport, Project, ProjectStage, User, now
from .security import as_utc

router = APIRouter(prefix="/projects/{project_id}/documentation", tags=["documentation"])


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_drafts_or_stale: bool = False


class GenerateExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["official", "preview"] = "official"
    include_drafts_or_stale: bool = False
    export_note: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=1000)] = None
    expected_snapshot_fingerprint: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=128)] = None


SUPPORTED_EXPORT_FORMATS = [
    {
        "format": "zip",
        "label": "Markdown Documentation Bundle (.zip)",
        "content_type": "application/zip",
        "extension": ".zip",
        "description": "Complete UTF-8 Markdown documentation archive (README.md, 01..12 section files, and MANIFEST.json).",
    },
    {
        "format": "markdown",
        "label": "Consolidated Specification (.md)",
        "content_type": "text/markdown; charset=utf-8",
        "extension": ".md",
        "description": "Single consolidated Markdown document combining all included specification sections in canonical order.",
    },
    {
        "format": "json",
        "label": "Validated Project Specification (.json)",
        "content_type": "application/json; charset=utf-8",
        "extension": ".json",
        "description": "Machine-readable JSON bundle of validated project specifications, provenance hashes, and manifest.",
    },
]

UNSUPPORTED_FORMATS_NOTE = (
    "PDF export is intentionally not enabled in Phase 17 so WebForge never emits a fake .pdf containing raw HTML/Markdown; "
    "use the Markdown Bundle (.zip) or Consolidated Markdown (.md) with a dedicated PDF typesetter."
)


def _safe_project_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "project").lower()).strip("-")
    return (slug[:48] or "project")


def _all_exports(db: Session, project_id: str) -> list[DocumentationExport]:
    return list(
        db.scalars(
            select(DocumentationExport)
            .where(DocumentationExport.project_id == project_id)
            .order_by(DocumentationExport.version.desc())
        )
    )


def _latest_official_export(db: Session, project_id: str) -> DocumentationExport | None:
    rows = _all_exports(db, project_id)
    return next((r for r in rows if r.export_mode == "official" and r.status == "completed"), None)


def verify_export_record_integrity(
    exp: DocumentationExport,
    current_snapshot_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Recompute MANIFEST.json and ZIP bundle SHA-256 digests and verify source snapshot alignment."""
    import hashlib
    import json

    manifest_json = json.dumps(exp.manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    recomputed_manifest_sha = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    try:
        _, recomputed_bundle_sha = doc_exp.build_deterministic_zip_bytes(exp.documents or {}, manifest_json)
    except Exception:
        recomputed_bundle_sha = ""

    manifest_ok = bool(exp.manifest_sha256 and exp.manifest_sha256 == recomputed_manifest_sha)
    bundle_ok = bool(exp.bundle_sha256 and exp.bundle_sha256 == recomputed_bundle_sha)
    stored_fp = (exp.source_snapshot or {}).get("snapshot_fingerprint")
    matches_current = bool(
        current_snapshot_fingerprint is None
        or (stored_fp and stored_fp == current_snapshot_fingerprint)
    )
    return {
        "verified": manifest_ok and bundle_ok,
        "manifest_hash_match": manifest_ok,
        "bundle_hash_match": bundle_ok,
        "matches_current_sources": matches_current,
        "stored_snapshot_fingerprint": stored_fp,
        "current_snapshot_fingerprint": current_snapshot_fingerprint,
        "manifest_sha256": exp.manifest_sha256,
        "recomputed_manifest_sha256": recomputed_manifest_sha,
        "bundle_sha256": exp.bundle_sha256,
        "recomputed_bundle_sha256": recomputed_bundle_sha,
    }


def _serialize_export_summary(
    exp: DocumentationExport,
    current_fp: str | None = None,
) -> dict[str, Any]:
    integ = verify_export_record_integrity(exp, current_fp)
    return {
        "id": exp.id,
        "project_id": exp.project_id,
        "version": exp.version,
        "export_mode": exp.export_mode,
        "status": exp.status,
        "manifest_sha256": exp.manifest_sha256,
        "bundle_sha256": exp.bundle_sha256,
        "document_count": len(exp.documents or {}),
        "document_filenames": list((exp.documents or {}).keys()) + ["MANIFEST.json"],
        "included_sections": (exp.manifest or {}).get("included_documents", []),
        "omitted_sections": (exp.manifest or {}).get("omitted_sections", []),
        "validation_summary": exp.validation_summary or {},
        "export_note": exp.export_note,
        "brain_revision": exp.brain_revision,
        "created_by": exp.created_by,
        "created_at": as_utc(exp.created_at).isoformat(),
        "updated_at": as_utc(exp.updated_at).isoformat(),
        "integrity": integ,
    }


def documentation_stage_completion_check(
    db: Session,
    project_id: str,
    precomputed: tuple[dict[str, Any], dict[str, str], list[dict[str, str]], list[dict[str, str]], dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    """Verify whether the final `documentation` lifecycle stage meets all Phase 17 completion criteria."""
    reasons: list[str] = []

    if precomputed is not None:
        snap, docs, inc, omit, val = precomputed
    else:
        snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=False)
        docs, inc, omit = doc_exp.generate_markdown_documents(snap, mode="official")
        val = doc_exp.validate_project_export(snap, docs, mode="official")

    st = snap["stage_statuses"]
    unmet = unmet_deps("documentation", st)
    if unmet:
        reasons.append(f"Unmet lifecycle stage dependencies for documentation: {', '.join(unmet)}.")

    if not val["ready_for_official_export"] or val["blocking_error_count"] > 0:
        first_err = next(
            (f["title"] + " — " + f["message"] for f in val["findings"] if f["severity"] == "blocking_error"),
            "Blocking export validation errors exist.",
        )
        reasons.append(f"Blocking export validation error: {first_err}")

    if omit:
        reasons.append(
            f"Required documentation sections are omitted or unavailable: {', '.join(o['filename'] for o in omit)}."
        )

    latest_official = _latest_official_export(db, project_id)
    if latest_official is None:
        reasons.append(
            "No official documentation bundle has been generated yet (previews alone do not complete the documentation stage)."
        )
    else:
        integ = verify_export_record_integrity(latest_official, snap["snapshot_fingerprint"])
        if not integ["verified"]:
            reasons.append("Latest official documentation export failed manifest or ZIP bundle SHA-256 integrity verification.")
        if not integ["matches_current_sources"]:
            reasons.append(
                f"Latest official documentation export (v{latest_official.version}) is stale because upstream project artifacts changed after export."
            )

    return len(reasons) == 0, reasons


def sync_documentation_stage(db: Session, project_id: str) -> None:
    """Synchronize the `documentation` lifecycle stage status based on official export state and upstream changes."""
    stage_row = db.scalar(
        select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.stage == "documentation")
    )
    if stage_row is None:
        return

    exports = _all_exports(db, project_id)
    if not exports:
        if stage_row.status == "complete":
            stage_row.status = "needs_review"
            stage_row.updated_at = now()
        return

    ok, _ = documentation_stage_completion_check(db, project_id)
    if ok:
        if stage_row.status != "complete":
            stage_row.status = "complete"
            stage_row.updated_at = now()
        return

    # If documentation was previously complete (or an official export exists that is now stale), mark needs_review
    has_official = any(e.export_mode == "official" for e in exports)
    if stage_row.status == "complete" or has_official:
        if stage_row.status != "needs_review":
            stage_row.status = "needs_review"
            stage_row.updated_at = now()
    elif exports and stage_row.status == "not_started":
        stage_row.status = "in_progress"
        stage_row.updated_at = now()


def _build_workspace_state(db: Session, project_id: str) -> dict[str, Any]:
    snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=False)
    docs, inc, omit = doc_exp.generate_markdown_documents(snap, mode="official")
    val = doc_exp.validate_project_export(snap, docs, mode="official")
    ok, reasons = documentation_stage_completion_check(
        db, project_id, precomputed=(snap, docs, inc, omit, val)
    )
    stage_row = db.scalar(
        select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.stage == "documentation")
    )
    exports = _all_exports(db, project_id)
    if stage_row is not None:
        if ok:
            stage_row.status = "complete"
        elif stage_row.status == "complete" or any(e.export_mode == "official" for e in exports):
            stage_row.status = "needs_review"
        elif exports and stage_row.status == "not_started":
            stage_row.status = "in_progress"
        db.commit()
        snap["stage_statuses"]["documentation"] = stage_row.status

    manifest, manifest_json, manifest_sha = doc_exp.build_export_manifest(
        snap, docs, inc, omit, val, mode="official"
    )
    _, bundle_sha = doc_exp.build_deterministic_zip_bytes(docs, manifest_json)

    st = snap["stage_statuses"]
    latest_off = _latest_official_export(db, project_id)

    return {
        "project": snap["project"],
        "stage_key": "documentation",
        "stage_status": st.get("documentation", "not_started"),
        "depends_on": STAGE_DEPS["documentation"],
        "unmet_dependencies": unmet_deps("documentation", st),
        "completion_check": {
            "complete": ok,
            "blocking_reasons": reasons,
        },
        "snapshot_fingerprint": snap["snapshot_fingerprint"],
        "brain_version": snap["brain_version"],
        "artifact_inventory": snap["inventory"],
        "included_sections": inc,
        "omitted_sections": omit,
        "validation_summary": val,
        "preview_manifest_sha256": manifest_sha,
        "preview_bundle_sha256": bundle_sha,
        "current_official_export": _serialize_export_summary(latest_off, snap["snapshot_fingerprint"]) if latest_off else None,
        "export_history": [_serialize_export_summary(e, snap["snapshot_fingerprint"]) for e in exports],
        "supported_formats": SUPPORTED_EXPORT_FORMATS,
        "unsupported_formats_note": UNSUPPORTED_FORMATS_NOTE,
    }


@router.get("")
def get_documentation_workspace(
    project_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    return _build_workspace_state(db, project_id)


@router.post("/preview")
def preview_documentation_bundle(
    project_id: str,
    body: PreviewIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate a read-only preview of the documentation bundle, manifest, and validation findings without mutating state."""
    owned(project_id, u, db)
    mode: doc_exp.ExportMode = "preview" if body.include_drafts_or_stale else "official"
    snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=body.include_drafts_or_stale)
    docs, inc, omit = doc_exp.generate_markdown_documents(snap, mode=mode)
    val = doc_exp.validate_project_export(snap, docs, mode=mode)
    manifest, manifest_json, manifest_sha = doc_exp.build_export_manifest(
        snap, docs, inc, omit, val, mode=mode
    )
    zip_bytes, bundle_sha = doc_exp.build_deterministic_zip_bytes(docs, manifest_json)
    is_official_eligible = bool(val["ready_for_official_export"] and not body.include_drafts_or_stale)

    return {
        "export_mode": mode,
        "include_drafts_or_stale": body.include_drafts_or_stale,
        "official_eligible": is_official_eligible,
        "official_approved_bundle": is_official_eligible,
        "snapshot_fingerprint": snap["snapshot_fingerprint"],
        "brain_version": snap["brain_version"],
        "artifact_inventory": snap["inventory"],
        "manifest_sha256": manifest_sha,
        "bundle_sha256": bundle_sha,
        "bundle_size_bytes": len(zip_bytes),
        "included_sections": inc,
        "omitted_sections": omit,
        "validation_summary": val,
        "manifest": manifest,
        "documents": docs,
    }


@router.post("/generate")
def generate_documentation_bundle(
    project_id: str,
    body: GenerateExportIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate and persist a versioned DocumentationExport bundle (official or preview)."""
    p = owned(project_id, u, db)

    if body.mode == "official" and body.include_drafts_or_stale:
        raise HTTPException(
            status_code=422,
            detail="Official documentation exports cannot set include_drafts_or_stale=true; use mode='preview' to inspect draft or stale artifacts.",
        )

    snap_initial = doc_exp.collect_export_snapshot(
        db, project_id, include_drafts_or_stale=(body.mode == "preview" and body.include_drafts_or_stale)
    )
    if body.expected_snapshot_fingerprint and body.expected_snapshot_fingerprint != snap_initial["snapshot_fingerprint"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Project source artifacts changed while export was being prepared "
                f"(expected {body.expected_snapshot_fingerprint[:16]}..., got {snap_initial['snapshot_fingerprint'][:16]}...). "
                "Refresh and verify before generating."
            ),
        )

    docs, inc, omit = doc_exp.generate_markdown_documents(snap_initial, mode=body.mode)
    val = doc_exp.validate_project_export(snap_initial, docs, mode=body.mode)

    # Even in preview mode, never persist an export that contains detected secrets
    secret_errors = [f for f in val["findings"] if f["code"] == "SECRET_DETECTED_IN_EXPORT"]
    if secret_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Export blocked because sensitive credentials or internal paths were detected.",
                "findings": secret_errors,
            },
        )

    if body.mode == "official" and not val["ready_for_official_export"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot generate an official documentation bundle while blocking validation errors exist.",
                "blocking_error_count": val["blocking_error_count"],
                "findings": [f for f in val["findings"] if f["severity"] == "blocking_error"],
            },
        )

    # Re-verify snapshot consistency before persisting
    snap_check = doc_exp.collect_export_snapshot(
        db, project_id, include_drafts_or_stale=(body.mode == "preview" and body.include_drafts_or_stale)
    )
    if snap_check["snapshot_fingerprint"] != snap_initial["snapshot_fingerprint"]:
        raise HTTPException(
            status_code=409,
            detail="Concurrent modification detected on source artifacts during export generation; please retry.",
        )

    existing = _all_exports(db, project_id)
    next_version = (existing[0].version + 1) if existing else 1

    manifest, manifest_json, manifest_sha = doc_exp.build_export_manifest(
        snap_initial,
        docs,
        inc,
        omit,
        val,
        mode=body.mode,
        export_version=next_version,
    )
    _, bundle_sha = doc_exp.build_deterministic_zip_bytes(docs, manifest_json)

    source_versions = {
        e["artifact_key"]: {
            "version": e["selected_version"],
            "status": e["selected_status"],
            "content_hash": e["content_hash"],
            "stale": e["stale"],
        }
        for e in snap_initial["inventory"]
        if e["present"]
    }

    if body.mode == "official":
        for prev in existing:
            if prev.export_mode == "official" and prev.status == "completed":
                prev.status = "superseded"
                prev.updated_at = now()
        db.flush()

    exp_row = DocumentationExport(
        project_id=project_id,
        version=next_version,
        export_mode=body.mode,
        status="completed",
        source_snapshot={
            "snapshot_fingerprint": snap_initial["snapshot_fingerprint"],
            "brain_version": snap_initial["brain_version"],
            "source_versions": source_versions,
        },
        manifest=manifest,
        documents=docs,
        validation_summary=val,
        manifest_sha256=manifest_sha,
        bundle_sha256=bundle_sha,
        created_by=u.id,
        export_note=body.export_note,
        row_version=1,
    )
    db.add(exp_row)
    db.flush()

    if body.mode == "official":
        doc_brain = DocumentationBrain(
            approved_version=next_version,
            export_id=exp_row.id,
            manifest_sha256=manifest_sha,
            bundle_sha256=bundle_sha,
            exported_at=as_utc(exp_row.created_at).isoformat(),
            included_section_count=len(inc),
            source_versions={k: v["version"] for k, v in source_versions.items() if v.get("version") is not None},
        )
        rev = commit_brain(
            db,
            p,
            {"documentation_spec": doc_brain.model_dump()},
            "documentation_exported",
            u.id,
            commit=False,
        )
        exp_row.brain_revision = rev.version

    sync_documentation_stage(db, project_id)
    db.commit()

    exp_detail = _serialize_export_summary(exp_row, snap_initial["snapshot_fingerprint"])
    exp_detail["manifest"] = exp_row.manifest
    exp_detail["documents"] = exp_row.documents
    exp_detail["source_snapshot"] = exp_row.source_snapshot
    return {
        "export": exp_detail,
        "workspace": _build_workspace_state(db, project_id),
    }


@router.get("/exports")
def list_documentation_exports(
    project_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=False)
    exports = _all_exports(db, project_id)
    return {
        "exports": [_serialize_export_summary(e, snap["snapshot_fingerprint"]) for e in exports],
    }


@router.get("/exports/{export_id}")
def get_documentation_export_detail(
    project_id: str,
    export_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    exp = db.scalar(
        select(DocumentationExport).where(
            DocumentationExport.id == export_id,
            DocumentationExport.project_id == project_id,
        )
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Documentation export not found.")
    snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=False)
    summary = _serialize_export_summary(exp, snap["snapshot_fingerprint"])
    summary["manifest"] = exp.manifest
    summary["documents"] = exp.documents
    return summary


@router.post("/exports/{export_id}/verify")
def verify_documentation_export_endpoint(
    project_id: str,
    export_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    exp = db.scalar(
        select(DocumentationExport).where(
            DocumentationExport.id == export_id,
            DocumentationExport.project_id == project_id,
        )
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Documentation export not found.")
    snap = doc_exp.collect_export_snapshot(db, project_id, include_drafts_or_stale=False)
    integ = verify_export_record_integrity(exp, snap["snapshot_fingerprint"])
    return {
        **integ,
        "export_id": exp.id,
        "version": exp.version,
        "export_mode": exp.export_mode,
        "status": exp.status,
        "integrity": integ,
    }


@router.get("/exports/{export_id}/download")
def download_documentation_export(
    project_id: str,
    export_id: str,
    format: str = Query("zip"),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    p = owned(project_id, u, db)
    if format not in ("zip", "markdown", "json"):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported export format '{format}'. Supported formats: zip, markdown, json. {UNSUPPORTED_FORMATS_NOTE}",
        )
    exp = db.scalar(
        select(DocumentationExport).where(
            DocumentationExport.id == export_id,
            DocumentationExport.project_id == project_id,
        )
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Documentation export not found.")

    integ = verify_export_record_integrity(exp)
    if not integ["verified"]:
        raise HTTPException(
            status_code=409,
            detail="Stored documentation export failed cryptographic integrity verification and cannot be downloaded.",
        )

    slug = _safe_project_slug(p.name)
    mode_tag = "official" if exp.export_mode == "official" else "preview"

    if format == "zip":
        import json

        manifest_json = json.dumps(exp.manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        zip_bytes, bundle_sha = doc_exp.build_deterministic_zip_bytes(exp.documents or {}, manifest_json)
        fname = f"{slug}-docs-v{exp.version}-{mode_tag}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
                "X-Bundle-SHA256": bundle_sha,
                "X-Export-SHA256": bundle_sha,
                "X-Export-Mode": exp.export_mode,
            },
        )

    if format == "markdown":
        md_text = doc_exp.build_consolidated_markdown(exp.documents or {}, exp.manifest or {})
        fname = f"{slug}-docs-v{exp.version}-{mode_tag}.md"
        return Response(
            content=md_text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
                "X-Export-Mode": exp.export_mode,
            },
        )

    # format == "json"
    snap = doc_exp.collect_export_snapshot(
        db, project_id, include_drafts_or_stale=(exp.export_mode == "preview")
    )
    json_text = doc_exp.build_validated_json_export(snap, exp.manifest or {})
    fname = f"{slug}-spec-v{exp.version}-{mode_tag}.json"
    return Response(
        content=json_text.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "X-Export-Mode": exp.export_mode,
        },
    )


@router.get("/exports/{export_id}/files/{filename:path}")
def download_individual_export_file(
    project_id: str,
    export_id: str,
    filename: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    owned(project_id, u, db)
    try:
        safe_name = doc_exp.validate_safe_archive_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    exp = db.scalar(
        select(DocumentationExport).where(
            DocumentationExport.id == export_id,
            DocumentationExport.project_id == project_id,
        )
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Documentation export not found.")

    if safe_name == "MANIFEST.json":
        import json

        manifest_json = json.dumps(exp.manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        return Response(
            content=manifest_json.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="MANIFEST.json"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    docs = exp.documents or {}
    if safe_name not in docs:
        raise HTTPException(status_code=404, detail=f"Document '{safe_name}' is not present in export v{exp.version}.")

    return Response(
        content=docs[safe_name].encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )

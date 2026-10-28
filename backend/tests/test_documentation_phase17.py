"""Phase 17 tests: Documentation & Specification Export bundle generation,
deterministic Markdown & MANIFEST.json assembly, ZIP archive creation & extraction,
safe archive path validation, secret scanning, provenance & content-hash verification,
draft/stale preview vs. official export separation, snapshot consistency checks,
authentication & cross-project ownership isolation, and `documentation` lifecycle stage
completion & upstream invalidation."""
import hashlib
import io
import json
import zipfile
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.documentation_export import (
    build_deterministic_zip_bytes,
    scan_export_for_secrets,
    validate_safe_archive_path,
)
from app.models import ResearchReport
from tests.test_optimization_phase16 import _setup_project_with_approved_phase13
from tests.test_strategy_prd import auth


def _setup_project_with_approved_phase16(client, monkeypatch, email="phase17-owner@example.com"):
    h, pid, stub, _, _, _ = _setup_project_with_approved_phase13(client, monkeypatch, email=email)

    # Complete frontend, database, backend stages so seo/analytics stage dependencies are met
    for stg in ("frontend", "database", "backend"):
        res = client.put(f"/api/projects/{pid}/stages/{stg}", json={"status": "complete"}, headers=h)
        assert res.status_code == 200

    # Initialize, submit, and approve SEO, Analytics, and Performance specifications
    for area in ("seo", "analytics", "performance"):
        init_res = client.post(f"/api/projects/{pid}/optimization/{area}/initialize", json={}, headers=h)
        assert init_res.status_code == 200
        ch = init_res.json()["current_draft"]["content_hash"]
        sub_res = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/1/submit",
            json={"base_hash": ch},
            headers=h,
        )
        assert sub_res.status_code == 200
        app_res = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/1/approve",
            json={"content_hash": ch, "acknowledge_unverified": True, "note": f"Approve {area} v1"},
            headers=h,
        )
        assert app_res.status_code == 200

    return h, pid, stub


def test_archive_path_safety_and_secret_scanning():
    # 1. Valid relative documentation paths pass
    assert validate_safe_archive_path("README.md") == "README.md"
    assert validate_safe_archive_path("06-architecture.md") == "06-architecture.md"
    assert validate_safe_archive_path("MANIFEST.json") == "MANIFEST.json"

    # 2. Unsafe paths, traversal, absolute paths, backslashes, dotfiles, and sensitive filenames are rejected
    unsafe_paths = [
        "",
        "../etc/passwd",
        "docs/../../secret.md",
        "/etc/passwd",
        "\\windows\\system32\\cmd.exe",
        "subdir\\file.md",
        ".env",
        ".env.production",
        "id_rsa",
        "cert.pem",
        "backup.sql",
        "webforge.db",
        "script.sh",
        "file\x00name.md",
    ]
    for bad in unsafe_paths:
        with pytest.raises(ValueError):
            validate_safe_archive_path(bad)

    # 3. Deterministic ZIP archive produces identical SHA-256 across calls
    docs = {
        "README.md": "# Test Bundle\n\nDeterministic UTF-8 — café ✓\n",
        "01-research.md": "# Research\n\nVerified findings.\n",
    }
    manifest_str = json.dumps({"schema_version": "v1", "files": list(docs.keys())}, sort_keys=True, indent=2) + "\n"
    zip1, sha1 = build_deterministic_zip_bytes(docs, manifest_str)
    zip2, sha2 = build_deterministic_zip_bytes(docs, manifest_str)
    assert zip1 == zip2
    assert sha1 == sha2

    # 4. Secret scanning detects credentials, private keys, database passwords, and internal paths
    clean_hits = scan_export_for_secrets(docs, manifest_str)
    assert clean_hits == []

    dirty_docs = {
        "06-architecture.md": (
            "OPENAI_API_KEY = sk-proj-1234567890abcdefghijklmnopqrstuvwxyz\n"
            "DATABASE_URL = postgresql://admin:SuperSecretPass123@db.internal:5432/prod\n"
            "Path: /working_dir/c_ef4e83f8c9952d79/workspace/webforge\n"
            + ("-----BEGIN RSA " + "PRIVATE KEY-----\n")
        )
    }
    hits = scan_export_for_secrets(dirty_docs, manifest_str)
    codes = {h["code"] for h in hits}
    assert "SECRET_OPENAI_KEY" in codes
    assert "SECRET_DB_URL_PASSWORD" in codes
    assert "INTERNAL_FILESYSTEM_PATH" in codes
    assert "SECRET_PRIVATE_KEY" in codes


def test_documentation_export_generation_manifest_and_stage_completion(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase16(
        client, monkeypatch, email="phase17-complete@example.com"
    )

    # 1. Attempting to mark `documentation` complete manually before generating an official export returns 409
    premature = client.put(f"/api/projects/{pid}/stages/documentation", json={"status": "complete"}, headers=h)
    assert premature.status_code == 409
    assert "No official documentation bundle has been generated yet" in premature.json()["detail"]

    # 2. GET /documentation workspace state shows all 14 required artifacts approved, current, and hash-verified
    ws_res = client.get(f"/api/projects/{pid}/documentation", headers=h)
    assert ws_res.status_code == 200
    ws = ws_res.json()
    assert ws["stage_key"] == "documentation"
    assert ws["stage_status"] == "not_started"
    assert ws["validation_summary"]["ready_for_official_export"] is True
    assert ws["validation_summary"]["blocking_error_count"] == 0
    assert len(ws["artifact_inventory"]) == 14
    assert all(item["present"] and item["selected_status"] == "approved" and item["hash_verified"] and not item["stale"] for item in ws["artifact_inventory"])
    assert len(ws["included_sections"]) == 13
    assert len(ws["omitted_sections"]) == 0
    fp = ws["snapshot_fingerprint"]

    # 3. POST /preview generates deterministic documents and manifest without completing the stage
    prev_res = client.post(
        f"/api/projects/{pid}/documentation/preview",
        json={"include_drafts_or_stale": False},
        headers=h,
    )
    assert prev_res.status_code == 200
    prev = prev_res.json()
    assert prev["official_approved_bundle"] is True
    assert prev["snapshot_fingerprint"] == fp
    expected_doc_files = [
        "README.md",
        "01-research.md",
        "02-strategy-and-prd.md",
        "03-ux-specification.md",
        "04-design-system.md",
        "05-prototype.md",
        "06-architecture.md",
        "07-testing-and-security.md",
        "08-infrastructure-and-deployment.md",
        "09-seo.md",
        "10-analytics.md",
        "11-performance.md",
        "12-traceability.md",
    ]
    assert list(prev["documents"].keys()) == expected_doc_files

    # 4. Generating a PREVIEW export (mode="preview") persists v1 as preview, and does NOT complete `documentation`
    gen_prev = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={
            "mode": "preview",
            "include_drafts_or_stale": True,
            "export_note": "Preview check",
        },
        headers=h,
    )
    assert gen_prev.status_code == 200
    assert gen_prev.json()["export"]["version"] == 1
    assert gen_prev.json()["export"]["export_mode"] == "preview"
    assert gen_prev.json()["workspace"]["stage_status"] == "in_progress"

    still_blocked = client.put(f"/api/projects/{pid}/stages/documentation", json={"status": "complete"}, headers=h)
    assert still_blocked.status_code == 409

    # 5. Snapshot consistency guard: mismatched expected_snapshot_fingerprint returns 409
    bad_fp = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={
            "mode": "official",
            "expected_snapshot_fingerprint": "0" * 64,
        },
        headers=h,
    )
    assert bad_fp.status_code == 409
    assert "changed while export was being prepared" in bad_fp.json()["detail"]

    # 6. Generate OFFICIAL export (mode="official") -> persists v2, updates ProjectBrain.documentation_spec, completes stage!
    gen_off = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={
            "mode": "official",
            "include_drafts_or_stale": False,
            "export_note": "Official Phase 17 release bundle",
            "expected_snapshot_fingerprint": fp,
        },
        headers=h,
    )
    assert gen_off.status_code == 200
    off_data = gen_off.json()
    exp = off_data["export"]
    assert exp["version"] == 2
    assert exp["export_mode"] == "official"
    assert exp["status"] == "completed"
    assert off_data["workspace"]["stage_status"] == "complete"
    assert off_data["workspace"]["completion_check"]["complete"] is True
    export_id = exp["id"]

    # Check ProjectBrain pointer
    brain_res = client.get(f"/api/projects/{pid}/brain", headers=h)
    assert brain_res.status_code == 200
    doc_brain = brain_res.json()["brain"]["documentation_spec"]
    assert doc_brain["approved_version"] == 2
    assert doc_brain["export_id"] == export_id
    assert doc_brain["bundle_sha256"] == exp["bundle_sha256"]
    assert doc_brain["manifest_sha256"] == exp["manifest_sha256"]

    # 7. Verify export integrity endpoint
    ver_res = client.post(f"/api/projects/{pid}/documentation/exports/{export_id}/verify", json={}, headers=h)
    assert ver_res.status_code == 200
    integ = ver_res.json()["integrity"]
    assert integ["verified"] is True
    assert integ["manifest_hash_match"] is True
    assert integ["bundle_hash_match"] is True
    assert integ["matches_current_sources"] is True

    # 8. Download ZIP bundle, verify headers, SHA-256 digest, and extract all files
    dl_zip = client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download?format=zip", headers=h)
    assert dl_zip.status_code == 200
    assert dl_zip.headers["content-type"] == "application/zip"
    assert "attachment; filename=" in dl_zip.headers["content-disposition"]
    assert dl_zip.headers["x-content-type-options"] == "nosniff"
    assert dl_zip.headers["cache-control"] == "no-store"
    assert dl_zip.headers["x-export-sha256"] == exp["bundle_sha256"]
    assert hashlib.sha256(dl_zip.content).hexdigest() == exp["bundle_sha256"]

    with zipfile.ZipFile(io.BytesIO(dl_zip.content), "r") as zf:
        names = zf.namelist()
        assert names == [*expected_doc_files, "MANIFEST.json"]
        manifest_from_zip = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
        assert manifest_from_zip["official_approved_bundle"] is True
        for doc_name in expected_doc_files:
            raw_bytes = zf.read(doc_name)
            text = raw_bytes.decode("utf-8")
            assert "OFFICIAL APPROVED SPECIFICATION" in text
            assert hashlib.sha256(raw_bytes).hexdigest() == manifest_from_zip["files"][doc_name]["sha256"]

    # 9. Download consolidated Markdown and JSON specification formats + individual file
    dl_md = client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download?format=markdown", headers=h)
    assert dl_md.status_code == 200
    assert "<!-- BEGIN FILE: 06-architecture.md -->" in dl_md.text

    dl_json = client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download?format=json", headers=h)
    assert dl_json.status_code == 200
    parsed_json = dl_json.json()
    assert parsed_json["schema_version"] == "webforge.project_specification_json.v1"
    assert "architecture" in parsed_json["artifacts"]

    dl_file = client.get(
        f"/api/projects/{pid}/documentation/exports/{export_id}/files/12-traceability.md",
        headers=h,
    )
    assert dl_file.status_code == 200
    assert "End-to-End Requirement Traceability Matrix" in dl_file.text


def test_documentation_upstream_invalidation_and_staleness_handling(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase16(
        client, monkeypatch, email="phase17-invalidation@example.com"
    )

    ws = client.get(f"/api/projects/{pid}/documentation", headers=h).json()
    gen_off = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={"mode": "official", "expected_snapshot_fingerprint": ws["snapshot_fingerprint"]},
        headers=h,
    )
    assert gen_off.status_code == 200
    export_id = gen_off.json()["export"]["id"]
    assert gen_off.json()["workspace"]["stage_status"] == "complete"

    # Now mutate an upstream artifact (copy-on-write edit on approved SEO v1 -> creates draft v2)
    seo_v1 = client.get(f"/api/projects/{pid}/optimization/seo/versions/1", headers=h).json()
    new_strategy = dict(seo_v1["content"]["seo_strategy"])
    new_strategy["primary_search_intent"] = "Updated B2B agency scope baseline search intent triggering Phase 17 invalidation."
    patch_res = client.patch(
        f"/api/projects/{pid}/optimization/seo/versions/1/section",
        json={
            "base_hash": seo_v1["content_hash"],
            "section": "seo_strategy",
            "value": new_strategy,
        },
        headers=h,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["edited_version"] == 2
    assert patch_res.json()["state"]["current_draft"]["version"] == 2

    # 1. `documentation` lifecycle stage must automatically transition from `complete` -> `needs_review`
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    doc_stage = next(s for s in ov["stages"] if s["stage"] == "documentation")
    assert doc_stage["status"] == "needs_review"

    # 2. Verify endpoint on the previous official export now reports `matches_current_sources == False`
    ver_res = client.post(f"/api/projects/{pid}/documentation/exports/{export_id}/verify", json={}, headers=h)
    assert ver_res.status_code == 200
    assert ver_res.json()["integrity"]["verified"] is True
    assert ver_res.json()["integrity"]["matches_current_sources"] is False

    # 3. Attempting to generate a new OFFICIAL export while SEO v2 is an unapproved draft is blocked (409)
    blocked_off = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={"mode": "official"},
        headers=h,
    )
    assert blocked_off.status_code == 409
    assert "OPEN_DRAFT_EXISTS" in str(blocked_off.json()["detail"])

    # 4. Preview with include_drafts_or_stale=True succeeds and labels the bundle as PREVIEW / NON-OFFICIAL
    prev_draft = client.post(
        f"/api/projects/{pid}/documentation/preview",
        json={"include_drafts_or_stale": True},
        headers=h,
    )
    assert prev_draft.status_code == 200
    assert prev_draft.json()["official_approved_bundle"] is False
    assert "PREVIEW / NON-OFFICIAL EXPORT" in prev_draft.json()["documents"]["09-seo.md"]


def test_documentation_missing_artifacts_and_tamper_detection(client, monkeypatch):
    h = auth(client, "phase17-missing@example.com")
    proj = client.post("/api/projects", json={"name": "Incomplete Project", "description": "Missing downstream specs"}, headers=h).json()
    pid = proj["id"]

    # 1. With no artifacts created, workspace reports missing required artifacts and omitted sections
    ws_res = client.get(f"/api/projects/{pid}/documentation", headers=h)
    assert ws_res.status_code == 200
    ws = ws_res.json()
    assert ws["validation_summary"]["ready_for_official_export"] is False
    assert ws["validation_summary"]["blocking_error_count"] >= 14
    codes = {f["code"] for f in ws["validation_summary"]["findings"]}
    assert "MISSING_REQUIRED_ARTIFACT" in codes
    assert len(ws["omitted_sections"]) >= 10

    # 2. Official export is rejected with 409
    gen_fail = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={"mode": "official"},
        headers=h,
    )
    assert gen_fail.status_code == 409

    # 3. Tamper detection: if an approved artifact's content is modified in DB without updating content_hash,
    # pre-export validation catches ARTIFACT_HASH_MISMATCH
    h2, pid2, _ = _setup_project_with_approved_phase16(client, monkeypatch, email="phase17-tamper@example.com")
    with SessionLocal() as db:
        rep = db.scalar(select(ResearchReport).where(ResearchReport.project_id == pid2, ResearchReport.status == "approved"))
        tampered = dict(rep.content)
        tampered["unresolved_questions"] = [{"id": "q-tamper", "question": "Tampered question?"}]
        rep.content = tampered
        db.commit()

    ws_tampered = client.get(f"/api/projects/{pid2}/documentation", headers=h2).json()
    assert ws_tampered["validation_summary"]["ready_for_official_export"] is False
    tamper_codes = {f["code"] for f in ws_tampered["validation_summary"]["findings"]}
    assert "ARTIFACT_HASH_MISMATCH" in tamper_codes


def test_documentation_auth_and_cross_project_isolation(client, monkeypatch):
    h_owner, pid, _ = _setup_project_with_approved_phase16(client, monkeypatch, email="phase17-iso-owner@example.com")
    gen = client.post(f"/api/projects/{pid}/documentation/generate", json={"mode": "official"}, headers=h_owner)
    assert gen.status_code == 200
    export_id = gen.json()["export"]["id"]

    # 1. Unauthenticated requests return 401
    owner_cookies = dict(client.cookies)
    client.cookies.clear()
    csrf = {"X-Requested-With": "WebForge"}
    assert client.get(f"/api/projects/{pid}/documentation").status_code == 401
    assert client.post(f"/api/projects/{pid}/documentation/preview", json={}, headers=csrf).status_code == 401
    assert client.post(f"/api/projects/{pid}/documentation/generate", json={"mode": "official"}, headers=csrf).status_code == 401
    assert client.get(f"/api/projects/{pid}/documentation/exports").status_code == 401
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}").status_code == 401
    assert client.post(f"/api/projects/{pid}/documentation/exports/{export_id}/verify", json={}, headers=csrf).status_code == 401
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download").status_code == 401
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/files/README.md").status_code == 401

    # 2. Cross-project non-owner requests return 404 (no existence leak)
    h_intruder = auth(client, "phase17-intruder@example.com")
    assert client.get(f"/api/projects/{pid}/documentation", headers=h_intruder).status_code == 404
    assert client.post(f"/api/projects/{pid}/documentation/preview", json={}, headers=h_intruder).status_code == 404
    assert client.post(f"/api/projects/{pid}/documentation/generate", json={"mode": "official"}, headers=h_intruder).status_code == 404
    assert client.get(f"/api/projects/{pid}/documentation/exports", headers=h_intruder).status_code == 404
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}", headers=h_intruder).status_code == 404
    assert client.post(f"/api/projects/{pid}/documentation/exports/{export_id}/verify", json={}, headers=h_intruder).status_code == 404
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download", headers=h_intruder).status_code == 404
    assert client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/files/README.md", headers=h_intruder).status_code == 404

    # 3. Path traversal / unsafe filename on individual file download returns 400
    client.cookies.clear()
    for k, v in owner_cookies.items():
        client.cookies.set(k, v)
    bad_file = client.get(
        f"/api/projects/{pid}/documentation/exports/{export_id}/files/.env",
        headers=h_owner,
    )
    assert bad_file.status_code == 400

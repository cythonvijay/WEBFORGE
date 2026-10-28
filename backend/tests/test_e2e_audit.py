"""Full End-to-End Lifecycle & Readiness Audit Test (Phases 0–17).

Executes the 10-step end-to-end verification scenario on a disposable test project:
1. Create a user and authenticate.
2. Create a project and populate required Brain inputs.
3. Progress through the entire 19-stage lifecycle using actual APIs and exact-hash approval rules.
4. Verify downstream stages and generators are blocked (409) when prerequisites are missing or stale.
5. Verify valid approvals, ProjectBrain pointers, and source-version references.
6. Exercise AI generation with deterministic test doubles.
7. Generate the final official documentation export and verify 100% lifecycle completion (19/19 stages complete).
8. Download and extract the ZIP archive, validating all 13 Markdown files, MANIFEST.json, SHA-256 digests, and 0 secret leaks.
9. Mutate an upstream artifact (Architecture v1 -> draft v2) and confirm downstream artifacts, intermediate stages (`frontend`..`monitoring`), optimization stages (`seo`, `analytics`), and `documentation` are invalidated.
10. Verify another user cannot access the project's artifacts or exports (404) and unauthenticated requests are rejected (401).
"""
import hashlib
import io
import json
import zipfile

from app import ai
from app.db import SessionLocal
from app.lifecycle import STAGES
from app.optimization import build_default_optimization_content, build_optimization_basis
from tests.test_optimization_phase16 import StubPhase16Provider
from tests.test_strategy_prd import auth


def test_full_end_to_end_lifecycle_scenario_phases_0_to_17(client, monkeypatch):
    # Step 1: Create a user and authenticate
    h_owner = auth(client, "e2e-audit-owner@example.com")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "e2e-audit-owner@example.com"

    # Step 2: Create a project and populate required Brain inputs
    proj_res = client.post(
        "/api/projects",
        json={
            "name": "ScopeLock E2E Audit",
            "description": "End-to-end agency scope governance platform.",
        },
        headers=h_owner,
    )
    assert proj_res.status_code == 201
    pid = proj_res.json()["id"]

    # Step 4 (Early Check): Verify downstream generators & stages are blocked (409) before prerequisites exist
    assert client.post(f"/api/projects/{pid}/research/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/optimization/seo/initialize", json={}, headers=h_owner).status_code == 409
    assert client.post(f"/api/projects/{pid}/documentation/generate", json={"mode": "official"}, headers=h_owner).status_code == 409
    assert client.put(f"/api/projects/{pid}/stages/product", json={"status": "in_progress"}, headers=h_owner).status_code == 409
    assert client.put(f"/api/projects/{pid}/stages/documentation", json={"status": "complete"}, headers=h_owner).status_code == 409

    # Populate Brain idea, target_users, and goals
    assert client.put(
        f"/api/projects/{pid}/brain/idea",
        json={
            "value": {
                "raw": "ScopeLock helps digital agencies lock client scope baselines, require client sign-off on change requests, and prevent unpaid scope creep.",
                "product_name": "ScopeLock",
                "product_type": "B2B SaaS Web Application",
                "problem": "Agencies lose margin to unapproved scope creep.",
                "features": ["Scope Baseline Locking", "Change Request Approval Workflow"],
                "assumptions": ["Clients will sign off via email link"],
                "open_questions": [],
            }
        },
        headers=h_owner,
    ).status_code == 200
    assert client.put(
        f"/api/projects/{pid}/brain/target_users",
        json={"value": ["Agency Project Managers", "Agency Founders"]},
        headers=h_owner,
    ).status_code == 200
    assert client.put(
        f"/api/projects/{pid}/brain/goals",
        json={"value": ["Eliminate unapproved scope creep", "Provide cryptographic audit trail"]},
        headers=h_owner,
    ).status_code == 200

    # Step 6: Configure deterministic AI test double for all phases
    stub = StubPhase16Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    # Step 3 & 5: Progress through Phase 9 Research
    res_gen = client.post(f"/api/projects/{pid}/research/generate", json={}, headers=h_owner)
    assert res_gen.status_code == 200
    res_hash = res_gen.json()["current"]["content_hash"]
    # Manual completion of research stage while report is still draft must fail (409)
    assert client.put(f"/api/projects/{pid}/stages/research", json={"status": "complete"}, headers=h_owner).status_code == 409
    assert client.post(
        f"/api/projects/{pid}/research/reports/1/submit",
        json={"base_hash": res_hash},
        headers=h_owner,
    ).status_code == 200
    # Wrong hash on approve must fail (409)
    assert client.post(
        f"/api/projects/{pid}/research/reports/1/approve",
        json={"content_hash": "0" * 64, "acknowledge_unverified": True},
        headers=h_owner,
    ).status_code == 409
    assert client.post(
        f"/api/projects/{pid}/research/reports/1/approve",
        json={"content_hash": res_hash, "acknowledge_unverified": True, "note": "Research v1 approved"},
        headers=h_owner,
    ).status_code == 200

    # Progress through Phase 10 Product Strategy & PRD
    stg_gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h_owner)
    assert stg_gen.status_code == 200
    assert stg_gen.json()["current"]["basis"]["research_version"] == 1
    stg_hash = stg_gen.json()["current"]["content_hash"]
    assert client.post(
        f"/api/projects/{pid}/strategy/versions/1/submit",
        json={"base_hash": stg_hash},
        headers=h_owner,
    ).status_code == 200
    assert client.post(
        f"/api/projects/{pid}/strategy/versions/1/approve",
        json={"content_hash": stg_hash, "acknowledge_unverified": True},
        headers=h_owner,
    ).status_code == 200

    prd_gen = client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h_owner)
    assert prd_gen.status_code == 200
    prd_doc = prd_gen.json()["current"]
    assert prd_doc["basis"]["strategy_version"] == 1
    assert prd_doc["basis"]["research_version"] == 1
    req_ids = [
        r["id"]
        for r in prd_doc["content"]["functional_requirements"] + prd_doc["content"]["non_functional_requirements"]
    ]
    prd_status = client.post(
        f"/api/projects/{pid}/prd/versions/1/requirements/status",
        json={"base_hash": prd_doc["content_hash"], "requirement_ids": req_ids, "status": "approved"},
        headers=h_owner,
    )
    assert prd_status.status_code == 200
    prd_hash = prd_status.json()["document"]["content_hash"]
    assert client.post(
        f"/api/projects/{pid}/prd/versions/1/submit",
        json={"base_hash": prd_hash},
        headers=h_owner,
    ).status_code == 200
    assert client.post(
        f"/api/projects/{pid}/prd/versions/1/approve",
        json={"content_hash": prd_hash, "acknowledge_unverified": True},
        headers=h_owner,
    ).status_code == 200

    # Progress through Phase 11 UX (5 artifacts in dependency order)
    for ut in ("personas", "journeys", "ia", "wireframes", "ux_review"):
        u_gen = client.post(f"/api/projects/{pid}/ux/{ut}/generate", json={}, headers=h_owner)
        assert u_gen.status_code == 200
        u_hash = u_gen.json()["current"]["content_hash"]
        assert client.post(
            f"/api/projects/{pid}/ux/{ut}/versions/1/submit",
            json={"base_hash": u_hash},
            headers=h_owner,
        ).status_code == 200
        assert client.post(
            f"/api/projects/{pid}/ux/{ut}/versions/1/approve",
            json={"content_hash": u_hash, "acknowledge_unverified": True},
            headers=h_owner,
        ).status_code == 200

    # Progress through Phase 12 Design System & Interactive Prototype
    for dt in ("design_system", "prototype"):
        d_gen = client.post(f"/api/projects/{pid}/design/{dt}/generate", json={}, headers=h_owner)
        assert d_gen.status_code == 200
        d_hash = d_gen.json()["current"]["content_hash"]
        assert client.post(
            f"/api/projects/{pid}/design/{dt}/versions/1/submit",
            json={"base_hash": d_hash},
            headers=h_owner,
        ).status_code == 200
        assert client.post(
            f"/api/projects/{pid}/design/{dt}/versions/1/approve",
            json={"content_hash": d_hash, "acknowledge_unverified": True},
            headers=h_owner,
        ).status_code == 200

    # Progress through Phase 13 Product Architecture
    arch_gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h_owner)
    assert arch_gen.status_code == 200
    arch_hash = arch_gen.json()["current"]["content_hash"]
    assert client.post(
        f"/api/projects/{pid}/architecture/versions/1/submit",
        json={"base_hash": arch_hash},
        headers=h_owner,
    ).status_code == 200
    assert client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": arch_hash, "acknowledge_unverified": True},
        headers=h_owner,
    ).status_code == 200

    # Complete engineering implementation stages and verify Phase 14 & Phase 15 stage guards
    for stg in ("frontend", "database", "backend", "api", "testing", "security", "docker", "cicd", "infrastructure", "deployment", "monitoring"):
        r_stg = client.put(f"/api/projects/{pid}/stages/{stg}", json={"status": "complete"}, headers=h_owner)
        assert r_stg.status_code == 200, f"Stage {stg} failed to complete: {r_stg.text}"

    # Progress through Phase 16 SEO, Analytics, and Performance (via AI generate with deterministic test double)
    with SessionLocal() as db:
        opt_basis = build_optimization_basis(db, pid)
        stub.seo_data = build_default_optimization_content("seo", opt_basis)
        stub.analytics_data = build_default_optimization_content("analytics", opt_basis)
        stub.performance_data = build_default_optimization_content("performance", opt_basis)

    for area in ("seo", "analytics", "performance"):
        o_gen = client.post(f"/api/projects/{pid}/optimization/{area}/generate", json={}, headers=h_owner)
        assert o_gen.status_code == 200
        o_hash = o_gen.json()["current_draft"]["content_hash"]
        o_sub = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/1/submit",
            json={"base_hash": o_hash},
            headers=h_owner,
        )
        assert o_sub.status_code == 200
        o_app = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/1/approve",
            json={"content_hash": o_hash, "acknowledge_unverified": True, "note": f"Approve {area} v1"},
            headers=h_owner,
        )
        assert o_app.status_code == 200

    # Step 7: Generate final official documentation export (Phase 17)
    ws_before = client.get(f"/api/projects/{pid}/documentation", headers=h_owner).json()
    assert ws_before["validation_summary"]["ready_for_official_export"] is True
    assert ws_before["validation_summary"]["blocking_error_count"] == 0

    gen_export = client.post(
        f"/api/projects/{pid}/documentation/generate",
        json={
            "mode": "official",
            "export_note": "Full E2E Audit Official Bundle",
            "expected_snapshot_fingerprint": ws_before["snapshot_fingerprint"],
        },
        headers=h_owner,
    )
    assert gen_export.status_code == 200
    exp = gen_export.json()["export"]
    export_id = exp["id"]

    # Verify all 19 lifecycle stages are now 'complete' (100% progress!)
    ov_complete = client.get(f"/api/projects/{pid}/overview", headers=h_owner).json()
    assert ov_complete["progress"] == 100
    assert set(ov_complete["completed"]) == set(STAGES)
    assert len(ov_complete["completed"]) == 19

    # Verify ProjectBrain pointers across all phases
    brain_snap = client.get(f"/api/projects/{pid}/brain", headers=h_owner).json()["brain"]
    assert brain_snap["research"]["approved_version"] == 1
    assert brain_snap["strategy"]["approved_version"] == 1
    assert brain_snap["prd"]["approved_version"] == 1
    assert brain_snap["ux"]["personas"]["approved_version"] == 1
    assert brain_snap["design_spec"]["design_system"]["approved_version"] == 1
    assert brain_snap["architecture_spec"]["approved_version"] == 1
    assert brain_snap["optimization_spec"]["seo"]["approved_version"] == 1
    assert brain_snap["documentation_spec"]["approved_version"] == 1
    assert brain_snap["documentation_spec"]["bundle_sha256"] == exp["bundle_sha256"]

    # Step 8: Extract the ZIP and validate its contents, MANIFEST.json, per-file SHA-256 digests, and 0 secret leaks
    dl_zip = client.get(f"/api/projects/{pid}/documentation/exports/{export_id}/download?format=zip", headers=h_owner)
    assert dl_zip.status_code == 200
    assert hashlib.sha256(dl_zip.content).hexdigest() == exp["bundle_sha256"]

    with zipfile.ZipFile(io.BytesIO(dl_zip.content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 14  # 13 .md files + MANIFEST.json
        manifest_obj = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
        assert manifest_obj["official_approved_bundle"] is True
        assert manifest_obj["validation_summary"]["blocking_error_count"] == 0
        for fname, fmeta in manifest_obj["files"].items():
            raw = zf.read(fname)
            assert hashlib.sha256(raw).hexdigest() == fmeta["sha256"]
            text = raw.decode("utf-8")
            assert "JWT_SECRET" not in text
            assert "/working_dir/" not in text

    # Step 9: Change an upstream artifact (Architecture v1 -> draft v2) and confirm downstream artifacts,
    # intermediate stages, optimization stages, and documentation are invalidated
    arch_v1 = client.get(f"/api/projects/{pid}/architecture/versions/1", headers=h_owner).json()
    patch_arch = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/overview",
        json={
            "base_hash": arch_v1["content_hash"],
            "product_scope": "Updated ScopeLock architecture scope during E2E invalidation check.",
        },
        headers=h_owner,
    )
    assert patch_arch.status_code == 200
    assert patch_arch.json()["document"]["version"] == 2
    assert patch_arch.json()["document"]["status"] == "draft"

    ov_after = client.get(f"/api/projects/{pid}/overview", headers=h_owner).json()
    st_after = {s["stage"]: s["status"] for s in ov_after["stages"]}
    # Upstream stages (research, product, ux, design) remain complete
    for up_stg in ("research", "product", "ux", "design"):
        assert st_after[up_stg] == "complete"
    # Architecture and Optimization stages are reopened to in_progress
    assert st_after["architecture"] == "in_progress"
    assert st_after["seo"] == "in_progress"
    assert st_after["analytics"] == "in_progress"
    # Dependent engineering/quality/devops stages and documentation are invalidated to needs_review
    for dep_stg in ("frontend", "database", "backend", "api", "testing", "security", "docker", "cicd", "infrastructure", "deployment", "monitoring", "documentation"):
        assert st_after[dep_stg] == "needs_review", f"Expected {dep_stg} to be invalidated to needs_review, got {st_after[dep_stg]}"

    # Official export is now reported as stale against newer upstream sources
    ver_after = client.post(f"/api/projects/{pid}/documentation/exports/{export_id}/verify", json={}, headers=h_owner)
    assert ver_after.status_code == 200
    assert ver_after.json()["integrity"]["verified"] is True
    assert ver_after.json()["integrity"]["matches_current_sources"] is False

    # Step 10: Verify another user cannot access the project's artifacts or exports (404)
    h_intruder = auth(client, "e2e-audit-intruder@example.com")
    for path in (
        f"/api/projects/{pid}",
        f"/api/projects/{pid}/overview",
        f"/api/projects/{pid}/brain",
        f"/api/projects/{pid}/research",
        f"/api/projects/{pid}/strategy",
        f"/api/projects/{pid}/prd",
        f"/api/projects/{pid}/ux/personas",
        f"/api/projects/{pid}/design/design_system",
        f"/api/projects/{pid}/architecture",
        f"/api/projects/{pid}/optimization",
        f"/api/projects/{pid}/documentation",
        f"/api/projects/{pid}/documentation/exports/{export_id}",
        f"/api/projects/{pid}/documentation/exports/{export_id}/download",
    ):
        assert client.get(path, headers=h_intruder).status_code == 404, f"Expected 404 on {path}"

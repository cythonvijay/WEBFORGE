"""Phase 16 tests: SEO, Analytics & Performance specifications, schema validation,
privacy & indexability guards, honest measurement policy, cross-artifact traceability,
copy-on-write versioning, exact-hash approval, Project Brain updates, upstream invalidation,
stage completion guards, cross-project isolation, and HTML/sitemap/robots verification."""
import copy
import pytest
from pydantic import BaseModel, ValidationError

from app import ai
from app.db import SessionLocal
from app.optimization import (
    AnalyticsContent,
    GeneratedAnalytics,
    GeneratedPerformance,
    GeneratedSeo,
    PerformanceContent,
    SeoContent,
    build_default_optimization_content,
    build_optimization_basis,
    inspect_html_document,
)
from tests.test_architecture import StubPhase13Provider, _setup_project_with_approved_phase12
from tests.test_strategy_prd import auth


class StubPhase16Provider(StubPhase13Provider):
    def __init__(self, seo_data=None, analytics_data=None, performance_data=None, fail: Exception | None = None):
        super().__init__(fail=fail)
        self.seo_data = copy.deepcopy(seo_data)
        self.analytics_data = copy.deepcopy(analytics_data)
        self.performance_data = copy.deepcopy(performance_data)

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        if schema is GeneratedSeo:
            return schema.model_validate(self.seo_data)
        if schema is GeneratedAnalytics:
            return schema.model_validate(self.analytics_data)
        if schema is GeneratedPerformance:
            return schema.model_validate(self.performance_data)
        return await super().generate_structured(prompt, schema)


def _setup_project_with_approved_phase13(client, monkeypatch, email="phase16-owner@example.com"):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email=email)
    gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h)
    assert gen.status_code == 200
    arch_hash = gen.json()["current"]["content_hash"]
    sub = client.post(
        f"/api/projects/{pid}/architecture/versions/1/submit",
        json={"base_hash": arch_hash},
        headers=h,
    )
    assert sub.status_code == 200
    app_res = client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": arch_hash, "acknowledge_unverified": True},
        headers=h,
    )
    assert app_res.status_code == 200

    # Prepare default deterministic payloads for StubPhase16Provider from actual basis
    with SessionLocal() as db:
        basis = build_optimization_basis(db, pid)
        seo_default = build_default_optimization_content("seo", basis)
        analytics_default = build_default_optimization_content("analytics", basis)
        perf_default = build_default_optimization_content("performance", basis)

    stub = StubPhase16Provider(
        seo_data=seo_default,
        analytics_data=analytics_default,
        performance_data=perf_default,
    )
    monkeypatch.setattr(ai, "get_provider", lambda: stub)
    return h, pid, stub, seo_default, analytics_default, perf_default


def test_seo_schema_rejects_private_route_indexing_and_fabricated_canonical_domains(client, monkeypatch):
    _, _, _, seo_default, _, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="seo-schema@example.com"
    )
    valid = SeoContent.model_validate(seo_default)
    assert len(valid.page_metadata) >= 2

    # 1. Private/authenticated route cannot use index or include_in_sitemap=True
    bad_private = copy.deepcopy(seo_default)
    bad_private["page_metadata"][0]["visibility"] = "authenticated"
    bad_private["page_metadata"][0]["robots_index"] = "index"
    with pytest.raises(ValidationError) as exc_info:
        SeoContent.model_validate(bad_private)
    assert "must use robots_index='noindex'" in str(exc_info.value)

    # 2. Fabricated live canonical URL is rejected
    bad_canonical = copy.deepcopy(seo_default)
    bad_canonical["page_metadata"][0]["canonical_path"] = "https://scopelock.io/projects"
    with pytest.raises(ValidationError) as exc_info2:
        SeoContent.model_validate(bad_canonical)
    assert "must not fabricate a live production domain" in str(exc_info2.value)

    # 3. Broken internal link to undefined route is rejected
    bad_link = copy.deepcopy(seo_default)
    bad_link["page_metadata"][0]["internal_links_to"] = ["/non-existent-route"]
    with pytest.raises(ValidationError) as exc_info3:
        SeoContent.model_validate(bad_link)
    assert "not defined in page_metadata" in str(exc_info3.value)


def test_analytics_schema_rejects_sensitive_fields_and_unconsented_tracking(client, monkeypatch):
    _, _, _, _, analytics_default, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="analytics-schema@example.com"
    )
    valid = AnalyticsContent.model_validate(analytics_default)
    assert len(valid.events) >= 2

    # 1. Prohibited sensitive property name (e.g., password, access_token, raw_email) is rejected
    bad_prop = copy.deepcopy(analytics_default)
    bad_prop["events"][0]["properties"].append(
        {
            "name": "user_access_token",
            "data_type": "string",
            "required": True,
            "pii_classification": "none",
            "description": "Leaked bearer token",
        }
    )
    with pytest.raises(ValidationError) as exc_info:
        AnalyticsContent.model_validate(bad_prop)
    assert "prohibited for privacy/security" in str(exc_info.value)

    # 2. Non-essential event without requires_opt_in=True is rejected
    bad_consent = copy.deepcopy(analytics_default)
    bad_consent["events"][0]["consent_category"] = "analytics"
    bad_consent["events"][0]["requires_opt_in"] = False
    with pytest.raises(ValidationError) as exc_info2:
        AnalyticsContent.model_validate(bad_consent)
    assert "must set requires_opt_in=True" in str(exc_info2.value)

    # 3. Third-party transmission enabled is rejected
    bad_3p = copy.deepcopy(analytics_default)
    bad_3p["consent_and_privacy"]["third_party_transmission_enabled"] = True
    with pytest.raises(ValidationError) as exc_info3:
        AnalyticsContent.model_validate(bad_3p)
    assert "third_party_transmission_enabled must be False" in str(exc_info3.value)


def test_performance_schema_distinguishes_targets_from_measured_evidence(client, monkeypatch):
    _, _, _, _, _, perf_default = _setup_project_with_approved_phase13(
        client, monkeypatch, email="perf-schema@example.com"
    )
    valid = PerformanceContent.model_validate(perf_default)
    assert valid.core_web_vitals.measurement_status == "target_budget_only"

    # 1. Claiming measured_observation without measured_pass/measured_warn evidence is rejected
    bad_claim = copy.deepcopy(perf_default)
    bad_claim["core_web_vitals"]["measurement_status"] = "measured_observation"
    with pytest.raises(ValidationError) as exc_info:
        PerformanceContent.model_validate(bad_claim)
    assert "requires at least one measurement_evidence entry" in str(exc_info.value)

    # 2. Claiming a measured_value on an unmeasured_target environment is rejected
    bad_ev = copy.deepcopy(perf_default)
    bad_ev["measurement_evidence"][0]["measured_value"] = "98"
    bad_ev["measurement_evidence"][0]["environment"] = "unmeasured_target"
    with pytest.raises(ValidationError) as exc_info2:
        PerformanceContent.model_validate(bad_ev)
    assert "cannot record a measured_value when environment is 'unmeasured_target'" in str(exc_info2.value)


def test_phase16_prerequisite_gates_block_when_architecture_missing_or_open_draft(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="prereq-p16@example.com")

    # Architecture is not approved yet -> SEO, Analytics, Performance report prerequisites.ready == False
    seo_state = client.get(f"/api/projects/{pid}/optimization/seo", headers=h).json()
    assert seo_state["prerequisites"]["ready"] is False
    workspaces = [r["workspace"] for r in seo_state["prerequisites"]["remediation_links"]]
    assert "architecture" in workspaces

    blocked = client.post(f"/api/projects/{pid}/optimization/seo/generate", json={}, headers=h)
    assert blocked.status_code == 409


def test_phase16_end_to_end_lifecycle_brain_and_stage_guards(client, monkeypatch):
    h, pid, _, _, _, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="e2e-p16@example.com"
    )

    # 1. Complete prerequisite engineering stages (frontend, database, backend) so seo/analytics stage guards are reached directly
    for stg in ("frontend", "database", "backend"):
        r_stg = client.put(f"/api/projects/{pid}/stages/{stg}", json={"status": "complete"}, headers=h)
        assert r_stg.status_code == 200, r_stg.text

    # Manual stage completion is blocked before approval
    manual_seo = client.put(
        f"/api/projects/{pid}/stages/seo",
        json={"status": "complete"},
        headers=h,
    )
    assert manual_seo.status_code == 409
    assert "must be approved" in manual_seo.json()["detail"]

    manual_analytics = client.put(
        f"/api/projects/{pid}/stages/analytics",
        json={"status": "complete"},
        headers=h,
    )
    assert manual_analytics.status_code == 409

    # 2. Generate, submit, and approve SEO, Analytics, and Performance
    for area in ("seo", "analytics", "performance"):
        gen = client.post(f"/api/projects/{pid}/optimization/{area}/generate", json={}, headers=h)
        assert gen.status_code == 200, gen.text
        st = gen.json()
        v = st["current_draft"]["version"]
        hsh = st["current_draft"]["content_hash"]

        # Stale hash on submit is rejected with 409
        bad_sub = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/{v}/submit",
            json={"base_hash": "0" * 64},
            headers=h,
        )
        assert bad_sub.status_code == 409

        sub = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/{v}/submit",
            json={"base_hash": hsh},
            headers=h,
        )
        assert sub.status_code == 200
        hsh_after_sub = sub.json()["current_draft"]["content_hash"]

        # Approve with acknowledge_unverified=False fails because generated items start as "proposed"
        no_ack = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/{v}/approve",
            json={"content_hash": hsh_after_sub, "acknowledge_unverified": False},
            headers=h,
        )
        assert no_ack.status_code == 409

        # Approve with acknowledge_unverified=True succeeds and promotes items to confirmed
        app_res = client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/{v}/approve",
            json={"content_hash": hsh_after_sub, "acknowledge_unverified": True, "note": f"Approve {area} v1"},
            headers=h,
        )
        assert app_res.status_code == 200
        approved_state = app_res.json()
        assert approved_state["current_approved"]["version"] == 1
        assert approved_state["current_draft"] is None

    # 3. Verify stages and Project Brain pointers
    overview = client.get(f"/api/projects/{pid}/optimization", headers=h).json()
    assert overview["seo_stage_status"] == "complete"
    assert overview["analytics_stage_status"] == "complete"
    assert overview["verification"]["overall_status"] == "passed"

    brain_res = client.get(f"/api/projects/{pid}/brain", headers=h).json()
    opt_brain = brain_res["brain"]["optimization_spec"]
    assert opt_brain["seo"]["approved_version"] == 1
    assert opt_brain["analytics"]["approved_version"] == 1
    assert opt_brain["performance"]["approved_version"] == 1

    # 4. Copy-on-write: editing approved SEO v1 creates draft v2 while v1 remains immutable
    seo_v1 = client.get(f"/api/projects/{pid}/optimization/seo/versions/1", headers=h).json()
    new_strategy = copy.deepcopy(seo_v1["content"]["seo_strategy"])
    new_strategy["primary_search_intent"] = "Updated B2B agency scope baseline search intent with copy-on-write."
    edit_res = client.patch(
        f"/api/projects/{pid}/optimization/seo/versions/1/section",
        json={"base_hash": seo_v1["content_hash"], "section": "seo_strategy", "value": new_strategy},
        headers=h,
    )
    assert edit_res.status_code == 200
    ed = edit_res.json()
    assert ed["copied_from_approved"] == 1
    assert ed["edited_version"] == 2
    assert ed["state"]["current_approved"]["version"] == 1
    assert ed["state"]["current_draft"]["version"] == 2
    assert ed["state"]["stage_status"] == "in_progress"

    # Manual completion of SEO stage is now blocked because open draft v2 exists
    manual_seo_blocked = client.put(
        f"/api/projects/{pid}/stages/seo",
        json={"status": "complete"},
        headers=h,
    )
    assert manual_seo_blocked.status_code == 409
    assert "open draft" in manual_seo_blocked.json()["detail"]


def test_upstream_architecture_change_marks_phase16_stale_and_reopens_stages(client, monkeypatch):
    h, pid, _, _, _, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="invalidation-p16@example.com"
    )
    for area in ("seo", "analytics", "performance"):
        gen = client.post(f"/api/projects/{pid}/optimization/{area}/initialize", json={}, headers=h).json()
        hsh = gen["current_draft"]["content_hash"]
        client.post(f"/api/projects/{pid}/optimization/{area}/versions/1/submit", json={"base_hash": hsh}, headers=h)
        client.post(
            f"/api/projects/{pid}/optimization/{area}/versions/1/approve",
            json={"content_hash": hsh, "acknowledge_unverified": True},
            headers=h,
        )

    ov_before = client.get(f"/api/projects/{pid}/optimization", headers=h).json()
    assert ov_before["seo_stage_status"] == "complete"
    assert ov_before["analytics_stage_status"] == "complete"

    # Now create an open draft on upstream Architecture (v2)
    arch_v1 = client.get(f"/api/projects/{pid}/architecture/versions/1", headers=h).json()
    patch_arch = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/overview",
        json={
            "base_hash": arch_v1["content_hash"],
            "product_scope": "Updated ScopeLock architecture scope triggering downstream invalidation.",
        },
        headers=h,
    )
    assert patch_arch.status_code == 200

    # Both seo and analytics stages must automatically reopen to in_progress and emit upstream warnings
    ov_after = client.get(f"/api/projects/{pid}/optimization", headers=h).json()
    assert ov_after["seo_stage_status"] == "in_progress"
    assert ov_after["analytics_stage_status"] == "in_progress"
    assert len(ov_after["areas"]["seo"]["warnings"]) > 0
    assert any(w["artifact"] == "architecture" for w in ov_after["areas"]["seo"]["warnings"])


def test_html_verifier_and_cross_project_isolation_and_platform_metrics(client, monkeypatch):
    h_owner, pid, _, _, _, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="owner-iso-p16@example.com"
    )

    # Initialize SEO for owner (while logged in as owner)
    init_res = client.post(f"/api/projects/{pid}/optimization/seo/initialize", json={}, headers=h_owner)
    assert init_res.status_code == 200
    seo_doc = init_res.json()["current_draft"]
    first_page = seo_doc["content"]["page_metadata"][0]

    # Switch session to another user -> cross-user access is strictly rejected with 404
    h_other = auth(client, "other-user-p16@example.com")
    assert client.get(f"/api/projects/{pid}/optimization", headers=h_other).status_code == 404
    assert client.get(f"/api/projects/{pid}/optimization/seo", headers=h_other).status_code == 404
    assert client.post(f"/api/projects/{pid}/optimization/seo/initialize", json={}, headers=h_other).status_code == 404
    assert (
        client.post(
            f"/api/projects/{pid}/optimization/verify-html",
            json={"route_path": "/", "html_content": "<html></html>"},
            headers=h_other,
        ).status_code
        == 404
    )

    # Switch back to owner
    auth(client, "owner-iso-p16@example.com")

    # HTML verifier detects invalid HTML (missing title, meta description, H1, main)
    bad_html = client.post(
        f"/api/projects/{pid}/optimization/verify-html",
        json={"route_path": first_page["route_path"], "html_content": "<html><body><h2>No H1</h2></body></html>"},
        headers=h_owner,
    )
    assert bad_html.status_code == 200
    assert bad_html.json()["status"] == "failed"
    codes = {f["code"] for f in bad_html.json()["findings"]}
    assert "HTML_TITLE_MISSING" in codes
    assert "HTML_H1_COUNT_INVALID" in codes
    assert "HTML_MAIN_LANDMARK_MISSING" in codes

    # HTML verifier passes compliant HTML
    good_html_str = (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'/>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'/>"
        f"<title>{first_page['title_template']}</title>"
        f"<meta name='description' content='{first_page['meta_description']}'/>"
        f"<meta name='robots' content='{first_page['robots_index']},{first_page['robots_follow']}'/>"
        f"<link rel='canonical' href='{first_page['canonical_path']}'/></head>"
        f"<body><main><h1>{first_page['h1_heading']}</h1></main></body></html>"
    )
    good_html = client.post(
        f"/api/projects/{pid}/optimization/verify-html",
        json={"route_path": first_page["route_path"], "html_content": good_html_str},
        headers=h_owner,
    )
    assert good_html.status_code == 200
    assert good_html.json()["status"] == "passed"

    # WebForge platform observability is separated from product analytics
    metrics = client.get("/api/health/live", headers=h_owner).json()["metrics"]
    assert metrics["scope"] == "webforge_platform_operational_only"
    assert "duration_buckets_ms" in metrics
    assert "avg_duration_ms" in metrics
    assert "error_rate" in metrics


def test_provider_failures_and_not_applicable_coverage_in_phase16(client, monkeypatch):
    h, pid, _, seo_default, _, _ = _setup_project_with_approved_phase13(
        client, monkeypatch, email="fail-na-p16@example.com"
    )

    # 1. Provider not configured -> 503 and no draft created
    monkeypatch.setattr(ai, "get_provider", lambda: (_ for _ in ()).throw(ai.ProviderNotConfigured("AI provider not configured.")))
    res_503 = client.post(f"/api/projects/{pid}/optimization/seo/generate", json={}, headers=h)
    assert res_503.status_code == 503
    st_after_503 = client.get(f"/api/projects/{pid}/optimization/seo", headers=h).json()
    assert st_after_503["current_draft"] is None

    # 2. Provider returns unknown screen_id -> 502 and no draft created
    bad_seo = copy.deepcopy(seo_default)
    bad_seo["page_metadata"][0]["screen_id"] = "SCR-NON-EXISTENT"
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase16Provider(seo_data=bad_seo))
    res_502 = client.post(f"/api/projects/{pid}/optimization/seo/generate", json={}, headers=h)
    assert res_502.status_code == 502
    assert "unknown Prototype/Wireframe screen" in res_502.json()["detail"]

    # 3. Initialize valid SEO draft, remove FR-2 from page_metadata linked_requirement_ids, and justify FR-2 as not_applicable
    init_res = client.post(f"/api/projects/{pid}/optimization/seo/initialize", json={}, headers=h).json()
    v = init_res["current_draft"]["version"]
    hsh = init_res["current_draft"]["content_hash"]
    content = copy.deepcopy(init_res["current_draft"]["content"])

    # Remove FR-2 from page items and remove FR-2 from requirement_coverage -> uncovered requirement blocks submit (422)
    for p in content["page_metadata"]:
        p["linked_requirement_ids"] = ["FR-1"]
    content["seo_strategy"]["requirement_coverage"] = [
        rc for rc in content["seo_strategy"]["requirement_coverage"] if rc["requirement_id"] == "FR-1"
    ]
    put_uncovered = client.put(
        f"/api/projects/{pid}/optimization/seo/versions/{v}",
        json={"base_hash": hsh, "content": content},
        headers=h,
    )
    assert put_uncovered.status_code == 200
    hsh2 = put_uncovered.json()["state"]["current_draft"]["content_hash"]
    sub_blocked = client.post(
        f"/api/projects/{pid}/optimization/seo/versions/{v}/submit",
        json={"base_hash": hsh2},
        headers=h,
    )
    assert sub_blocked.status_code == 422
    assert "FR-2" in sub_blocked.json()["detail"]["uncovered_requirement_ids"]

    # Now add explicit not_applicable justification for FR-2 and NFR-1 -> submit succeeds!
    for req_id in ("FR-2", "NFR-1"):
        content["seo_strategy"]["requirement_coverage"].append(
            {
                "requirement_id": req_id,
                "requirement_title": f"Requirement {req_id}",
                "coverage_status": "not_applicable",
                "justification": f"{req_id} operates purely inside authenticated backend state and has no search indexability surface.",
            }
        )
    put_just = client.put(
        f"/api/projects/{pid}/optimization/seo/versions/{v}",
        json={"base_hash": hsh2, "content": content},
        headers=h,
    )
    assert put_just.status_code == 200
    hsh3 = put_just.json()["state"]["current_draft"]["content_hash"]
    sub_ok = client.post(
        f"/api/projects/{pid}/optimization/seo/versions/{v}/submit",
        json={"base_hash": hsh3},
        headers=h,
    )
    assert sub_ok.status_code == 200

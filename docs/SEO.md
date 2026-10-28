# Phase 16 — Search Engine Optimization (SEO) Specification & Verification

## 1. Scope Separation

WebForge enforces a strict separation between two distinct SEO scopes:

1. **Generated Product SEO Specification (`backend/app/optimization.py`, `backend/app/optimization_api.py`)**:
   - Defines, validates, versions, and approves the search metadata, canonical URL rules, heading hierarchy, structured data (JSON-LD), XML sitemap, and `robots.txt` directives for the **user's product** based on its approved Research, Product Strategy, PRD, UX (Personas, Journeys, IA, Wireframes, UX Review), Design System, Interactive Prototype, and Product Architecture artifacts.
   - Persisted in PostgreSQL (`optimization_artifacts` where `area = 'seo'`) with immutable approved versions, exact-hash approval, copy-on-write editing, and Project Brain pointers (`optimization_spec.seo`).
2. **WebForge Platform Metadata (`frontend/index.html`, `frontend/nginx.conf`)**:
   - WebForge itself is an authenticated engineering workbench. Its HTML shell (`frontend/index.html`) declares `<meta name="robots" content="noindex,nofollow" />` so project workspaces and private product specifications are never indexed by search engines.

---

## 2. Upstream Prerequisites & Lifecycle Gate

Before generating, initializing, editing, submitting, or approving a Phase 16 SEO specification:
- `evaluate_optimization_prerequisites(db, project_id)` verifies that all upstream artifacts are approved, current, and free of open drafts:
  - Phase 9: `Research` (`research` stage complete, approved report, no open draft)
  - Phase 10: `Product Strategy` and `PRD` (`product` stage complete, approved versions, no open drafts)
  - Phase 11: `Personas`, `User Journeys`, `Information Architecture`, `Wireframes`, and `UX Review` (`ux` stage complete, 0 open critical UX findings, no open drafts)
  - Phase 12: `Design System` and `Interactive Prototype` (`design` stage complete, approved versions, no open drafts)
  - Phase 13: `Product Architecture` (`architecture` stage complete, approved version, no open draft)
- If any upstream prerequisite is missing, stale, or has an open draft, generation and approval return `409 Conflict` with structured `blocking_reasons` and `remediation_links` pointing to the exact workspace (`/projects/:id/research`, `/projects/:id/prd`, `/projects/:id/ia`, `/projects/:id/prototype`, `/projects/:id/architecture`, etc.).
- Manual completion of the `seo` lifecycle stage via `PUT /api/projects/{project_id}/stages/seo` is guarded by `seo_stage_completion_check(db, project_id)` and rejected with `409 Conflict` unless a current, non-stale approved SEO specification exists and all Phase 16 product verification checks pass.

---

## 3. SEO Domain Model & Validation Rules (`SeoContent`)

### 3.1 `SeoStrategySummary`
- `primary_search_intent`, `target_audience_summary`, `canonical_domain_strategy`, `url_structure_conventions`, `crawl_and_indexing_policy`, `locale_and_language_strategy`.
- `requirement_coverage`: list of `RequirementCoverageEntry` items (`requirement_id`, `requirement_title`, `coverage_status` in `{"covered", "not_applicable"}`, `justification`). If a PRD requirement has no direct SEO surface (for example, an internal background job or authenticated settings mutation), it must be explicitly marked `"not_applicable"` with a concrete justification (`>= 10` characters).

### 3.2 `PageSeoMetadataSpec` (`SEO-PAGE-1..N`)
Each route/screen entry links to an approved Prototype/Wireframe `screen_id` (`SCR-N` / `WF-N`) and PRD requirements (`linked_requirement_ids`) and specifies:
- `route_path` (normalized leading `/`) and `canonical_path`
- `visibility`: `"public" | "authenticated" | "private_user_data" | "transactional" | "admin"`
- `robots_index`: `"index" | "noindex"` and `robots_follow`: `"follow" | "nofollow"`
- `include_in_sitemap`: `bool`
- `title_template` (`10..70` chars), `meta_description` (`50..160` chars)
- `h1_heading` and `heading_hierarchy` (must begin with `H1:` and must not skip heading levels, e.g., `H1 -> H3` without `H2` is rejected)
- Open Graph (`og_title`, `og_description`, `og_type`) and Twitter Card (`twitter_card`)
- `structured_data_type` (`"None" | "WebSite" | "SoftwareApplication" | "Organization" | "FAQPage" | "BreadcrumbList" | "Article" | "Product"`) and `structured_data_justification` (required whenever `structured_data_type != "None"`)
- `internal_links_to`: validated against defined `route_path` entries in `page_metadata`

### 3.3 Hard Indexability & Canonical Honesty Guards
- **Private Route Protection**: Any page with `visibility != "public"` (`authenticated`, `private_user_data`, `transactional`, `admin`) **must** set `robots_index = "noindex"` and `include_in_sitemap = False`. Attempting to index or include a non-public route in `/sitemap.xml` raises a Pydantic validation error (`422`).
- **No Fabricated Live Domains**: `canonical_path` must be a relative route path starting with `/` (combined at runtime with environment-configured `PUBLIC_BASE_URL`), never a hardcoded or fabricated `http://` / `https://` production URL.
- **Sitemap & Robots Consistency**: `SitemapSpec.included_routes` may only contain public, indexable routes from `page_metadata`; all non-public routes must appear in `SitemapSpec.excluded_routes` or `RobotsTxtSpec.disallow_paths`.

---

## 4. Deterministic Previews & HTML Verification

- **XML Sitemap & `robots.txt` Previews**:
  - `generate_sitemap_xml_preview(seo_content)` and `generate_robots_txt_preview(seo_content)` deterministically render `/sitemap.xml` and `/robots.txt` using `${PUBLIC_BASE_URL}` placeholders and excluding all private/authenticated/API routes.
- **HTML Semantic & Metadata Inspector (`POST /api/projects/{project_id}/optimization/verify-html`)**:
  - Parses real HTML markup using Python's `html.parser.HTMLParser` (`inspect_html_document`) and verifies:
    - `<html lang="...">` attribute presence
    - Non-empty `<title>` (`10..70` characters)
    - `<meta name="description">` (`50..160` characters)
    - `<meta name="viewport">`
    - `<link rel="canonical">`
    - `<meta name="robots">` consistency with route visibility (`noindex` enforced on private/authenticated routes)
    - Single `<h1>` heading and non-skipped heading hierarchy (`<h1>`..`<h6>`)
    - Semantic landmarks (`<main>`, `<nav>`, `<header>`)
    - `<img alt="...">` attributes on all images

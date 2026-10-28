import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const HASH_S1 = "1".repeat(64);

const sampleSeoState = {
  area: "seo",
  stage_key: "seo",
  stage_status: "in_progress",
  prerequisites: {
    ready: true,
    blocking_reasons: [],
    remediation_links: [],
    artifacts: [],
  },
  current_approved: null,
  current_draft: {
    id: "seo-doc-1",
    project_id: "p1",
    area: "seo",
    version: 1,
    status: "draft",
    supersedes_version: null,
    generation_source: "ai",
    ai_metadata: {},
    content: {
      seo_strategy: {
        primary_search_intent: "B2B agency scope baseline search intent.",
        target_audience_summary: "Agency founders and project leads.",
        canonical_domain_strategy: "PUBLIC_BASE_URL + canonical_path",
        url_structure_conventions: ["Lowercase hyphenated paths"],
        crawl_and_indexing_policy: "Public routes indexable; private routes noindex.",
        locale_and_language_strategy: "en-US UTF-8",
        requirement_coverage: [
          {
            requirement_id: "FR-1",
            requirement_title: "Scope baseline locking",
            coverage_status: "covered",
            justification: "Covered by SEO-PAGE-1",
          },
        ],
        open_questions: [],
      },
      page_metadata: [
        {
          id: "SEO-PAGE-1",
          screen_id: "SCR-1",
          route_path: "/",
          visibility: "public",
          robots_index: "index",
          robots_follow: "follow",
          include_in_sitemap: true,
          canonical_path: "/",
          title_template: "ScopeLock | Agency Baseline Governance",
          meta_description: "Manage agency scope baselines with provenance and client sign-off.",
          h1_heading: "Agency Scope Baseline Governance",
          heading_hierarchy: ["H1: Agency Scope Baseline Governance", "H2: Core Capabilities"],
          og_title: "ScopeLock Workspace",
          og_description: "Traceable agency scope baselines.",
          og_type: "website",
          twitter_card: "summary_large_image",
          structured_data_type: "SoftwareApplication",
          structured_data_justification: "Public entry route describes the SaaS offering.",
          internal_links_to: ["/projects"],
          linked_requirement_ids: ["FR-1"],
          status: "confirmed",
          notes: "Public landing route.",
        },
        {
          id: "SEO-PAGE-2",
          screen_id: "SCR-2",
          route_path: "/projects",
          visibility: "authenticated",
          robots_index: "noindex",
          robots_follow: "nofollow",
          include_in_sitemap: false,
          canonical_path: "/projects",
          title_template: "Projects | ScopeLock",
          meta_description: "Authenticated workspace for managing agency projects and scope baselines.",
          h1_heading: "Your Agency Projects",
          heading_hierarchy: ["H1: Your Agency Projects"],
          og_title: "Projects Workspace",
          og_description: "Private project dashboard.",
          og_type: "website",
          twitter_card: "summary",
          structured_data_type: "None",
          structured_data_justification: null,
          internal_links_to: [],
          linked_requirement_ids: ["FR-1"],
          status: "confirmed",
          notes: "Authenticated workspace route.",
        },
      ],
      sitemap_spec: {
        sitemap_path: "/sitemap.xml",
        changefreq_policy: "Weekly for public routes.",
        included_routes: ["/"],
        excluded_routes: ["/projects"],
        exclusion_rationale: "Authenticated routes excluded from public XML sitemap.",
      },
      robots_spec: {
        user_agent: "*",
        allow_paths: ["/"],
        disallow_paths: ["/projects", "/api/"],
        sitemap_reference: "${PUBLIC_BASE_URL}/sitemap.xml",
        rationale: "Block authenticated and API paths.",
      },
      technical_checklist: [
        {
          id: "SEO-CHK-1",
          category: "semantics",
          title: "Single H1 per screen",
          verification_rule: "Verify single H1 and main landmark.",
          linked_screen_ids: ["SCR-1", "SCR-2"],
          status: "confirmed",
        },
        {
          id: "SEO-CHK-2",
          category: "crawlability",
          title: "Private route noindex guard",
          verification_rule: "Verify noindex on authenticated routes.",
          linked_screen_ids: ["SCR-2"],
          status: "confirmed",
        },
      ],
    },
    basis_summary: {},
    content_hash: HASH_S1,
    approval_note: null,
    approved_at: null,
    approved_by: null,
    created_at: "2026-10-28T00:00:00Z",
    updated_at: "2026-10-28T00:00:00Z",
  },
  versions: [
    {
      version: 1,
      status: "draft",
      supersedes_version: null,
      generation_source: "ai",
      content_hash: HASH_S1,
      created_at: "2026-10-28T00:00:00Z",
      updated_at: "2026-10-28T00:00:00Z",
      approved_at: null,
    },
  ],
  completeness: {
    ready_for_submission: true,
    ready_for_approval: true,
    missing_fields: [],
    unresolved_constraint_errors: [],
    unverified_items: [],
    requires_review_items: [],
    uncovered_requirement_ids: [],
    item_count: 4,
  },
  traceability: {
    area: "seo",
    complete: true,
    total_requirements: 1,
    covered_requirements: 1,
    requirement_coverage: [
      {
        requirement_id: "FR-1",
        title: "Scope baseline locking",
        priority: "must",
        covered: true,
        coverage_status: "covered",
        justification: null,
        mapped_item_ids: ["SEO-PAGE-1", "SEO-PAGE-2"],
      },
    ],
    valid_screen_ids: ["SCR-1", "SCR-2"],
    valid_route_paths: ["/", "/projects"],
    valid_endpoint_ids: ["API-1"],
    findings: [],
  },
  warnings: [],
  sitemap_xml_preview: "<urlset><url><loc>https://example.invalid/</loc></url></urlset>",
  robots_txt_preview: "User-agent: *\nAllow: /\nDisallow: /projects",
};

describe("Phase 16 Optimization Workspaces (SEO, Analytics & Performance)", () => {
  it("renders SEO workspace with public/private route indexability, sitemap preview, and HTML verifier", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/optimization/seo": { body: sampleSeoState },
    });

    renderApp(["/projects/p1/seo"]);

    expect(await screen.findByText("SEO & Search Discoverability")).toBeInTheDocument();
    expect(screen.getByText("SEO-PAGE-1")).toBeInTheDocument();
    expect(screen.getByText("Excluded from Sitemap")).toBeInTheDocument();
    expect(screen.getByTestId("requirement-coverage-table")).toBeInTheDocument();
  });

  it("blocks generation and displays remediation links when upstream Architecture is missing", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/optimization/seo": {
        body: {
          ...sampleSeoState,
          current_draft: null,
          versions: [],
          prerequisites: {
            ready: false,
            blocking_reasons: ["Product Architecture has no approved version yet."],
            remediation_links: [
              {
                label: "Product Architecture",
                workspace: "architecture",
                reason: "Product Architecture has no approved version yet.",
              },
            ],
            artifacts: [],
          },
        },
      },
    });

    renderApp(["/projects/p1/seo"]);

    expect(await screen.findByText(/Product Architecture has no approved version yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Go to Product Architecture/i })).toHaveAttribute(
      "href",
      "/projects/p1/architecture"
    );
  });

  it("supports submitting and approving an SEO draft with exact content_hash", async () => {
    const user = userEvent.setup();
    mockApi({
      ...base,
      "GET /projects/:id/optimization/seo": { body: sampleSeoState },
      "POST /projects/:id/optimization/seo/versions/1/submit": {
        body: {
          ...sampleSeoState,
          current_draft: { ...sampleSeoState.current_draft, status: "in_review" },
        },
      },
      "POST /projects/:id/optimization/seo/versions/1/approve": {
        body: {
          ...sampleSeoState,
          stage_status: "complete",
          current_draft: null,
          current_approved: { ...sampleSeoState.current_draft, status: "approved" },
        },
      },
    });

    renderApp(["/projects/p1/seo"]);

    const submitBtn = await screen.findByRole("button", { name: /Submit for Review/i });
    await user.click(submitBtn);
    expect(await screen.findByText(/v1 submitted for review/i)).toBeInTheDocument();

    const approveBtn = screen.getByRole("button", { name: /Approve v1/i });
    await user.click(approveBtn);
    const confirmBtn = await screen.findByRole("button", { name: /Confirm Approval/i });
    await user.click(confirmBtn);
    expect(await screen.findByText(/Project Brain updated/i)).toBeInTheDocument();
  });
});

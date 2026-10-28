import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const PATH = "/projects/p1/research";
const H = "a".repeat(64), H2 = "b".repeat(64), iso = new Date().toISOString();
const base = { ...authed, "GET /projects/:id": { body: project() } };
const finding = (o: Record<string, unknown> = {}) => ({ id: "f-1", topic: "user_needs", statement: "Customers probably struggle to compare photographers.", detail: null, evidence: "hypothesis", citations: [], follow_up: false, follow_up_note: null, origin: "ai", edited_by_user: false, note: null, ...o });
const brief = { product_summary: "Snapbook - marketplace", problem: { text: "Hard to compare photographers", status: "ai_suggested", question_id: null }, target_users: [{ text: "Wedding photographers", status: "user_confirmed", question_id: "q1" }],
  business_goals: [], confirmed_requirements: [], constraints: [], unknowns: ["Who pays the fee?"], missing_inputs: ["Discovery is not completed (status: not started)."], objectives: ["Understand how customers choose"],
  research_questions: ["What makes customers trust a photographer?"], scope_in: ["Local portraits"], scope_out: [] };
const content = (o: Record<string, unknown> = {}) => ({ brief, findings: [finding(), finding({ id: "f-2", topic: "risks", statement: "Photographers may resist booking fees.", evidence: "ai_suggestion" }),
  finding({ id: "f-3", topic: "competitors_alternatives", statement: "Customers likely rely on social media today.", evidence: "unsupported", follow_up: true })], sources: [], unresolved_questions: [{ id: "q-1", question: "Which cities first?" }], limitations: [], ...o });
const counts = { verified_source: 0, user_provided: 0, hypothesis: 1, ai_suggestion: 1, unsupported: 1 };
const report = (o: Record<string, unknown> = {}) => ({ version: 1, status: "draft", created_via: "generated", parent_version: null, created_at: iso, updated_at: iso, submitted_at: null, approved_at: null, content_hash: H,
  finding_count: 3, source_count: 0, error: null, id: "r1", mode: "preliminary", content: content(), basis: {}, approval_note: null, acknowledged_unverified: false, brain_revision: null, evidence_counts: counts,
  unverified_count: 3, editable: true, warnings: [{ code: "no_sources", message: "No sources are attached. Every finding is a hypothesis, suggestion or unsupported claim." }], ...o });
const summary = (o: Record<string, unknown> = {}) => ({ version: 1, status: "draft", created_via: "generated", parent_version: null, created_at: iso, updated_at: iso, submitted_at: null, approved_at: null, content_hash: H, finding_count: 3, source_count: 0, error: null, ...o });
const LIMIT = "No web research was performed. Findings are model-generated suggestions and hypotheses unless you attach a source you have examined.";
const rstate = (o: Record<string, unknown> = {}) => ({ status: "draft", idea_ready: true, mode: "preliminary", current: report(), approved_version: null, history: [summary()], last_error: null, brief_preview: null, discovery_status: "not_started",
  lifecycle: { stage: "research", status: "not_started" }, next_step: { key: "review_and_submit", label: "Review" }, can_generate: true, needs_supersede: true, can_submit: true, can_approve: false, limitations: [LIMIT], ...o });
const empty = rstate({ status: "not_started", current: null, history: [], brief_preview: brief, needs_supersede: false, can_submit: false, next_step: { key: "start_research", label: "Start" } });
const withState = (state: unknown, extra: Record<string, unknown> = {}) => ({ ...base, "GET /projects/:id/research": { body: state }, ...extra });
const header = () => within(screen.getByLabelText("Research status"));
const edited = (o: Record<string, unknown> = {}, st: Record<string, unknown> = {}) => ({ body: { report: report({ content_hash: H2, ...o }), state: rstate({ current: report({ content_hash: H2, ...o }), ...st }) } });

describe("empty and failure states", () => {
  it("shows a useful empty state with the real brief, missing inputs and no fabricated research", async () => {
    mockApi(withState(empty));
    renderApp(PATH);
    expect(await screen.findByText("No research report yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start preliminary research" })).toBeEnabled();
    expect(screen.getByText("Preliminary research: no web research was performed")).toBeInTheDocument();
    const missing = within(screen.getByText("Missing or unconfirmed inputs").closest("[role=status]") as HTMLElement);
    expect(missing.getByText(/Discovery is not completed/)).toBeInTheDocument();
    expect(screen.getByText("AI-proposed, unconfirmed")).toBeInTheDocument();
    expect(screen.getByText("Confirmed by you")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Findings" })).not.toBeInTheDocument();
    expect(screen.getByText(/No versions yet/)).toBeInTheDocument();
  });

  it("asks for an idea first when none exists", async () => {
    mockApi(withState({ ...empty, idea_ready: false, can_generate: false }));
    renderApp(PATH);
    expect(await screen.findByText("Describe your idea first")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start preliminary research" })).not.toBeInTheDocument();
  });

  it("explains an unconfigured provider and does not retry on its own (503)", async () => {
    const api = mockApi(withState(empty, { "POST /projects/:id/research/generate": { status: 503, body: { detail: "AI provider not configured. Nothing was changed." } } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Start preliminary research" }));
    expect(await screen.findByText("AI analysis is not configured yet.")).toBeInTheDocument();
    expect(screen.getByText("No research report yet")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/research/generate")).toBe(1);
  });

  it("shows the specific safe reason when the AI output is rejected (502) and offers a retry", async () => {
    let failed = true, attempted = false;
    const api = mockApi(withState(empty, { "POST /projects/:id/research/generate": () => (attempted = true, failed ? { status: 502, body: { detail: "The AI response could not be used. Nothing was changed." } } : { body: rstate() }),
      "GET /projects/:id/research": () => ({ body: !attempted ? empty : failed ? rstate({ status: "failed", current: null, history: [], brief_preview: brief, needs_supersede: false, last_error: "The AI response could not be used.", next_step: { key: "retry_generation", label: "Retry" } }) : rstate() }) }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Start preliminary research" }));
    expect(await screen.findByText("WebForge couldn't produce a valid research report.")).toBeInTheDocument();
    expect(screen.getByText(/The AI response could not be used\./)).toBeInTheDocument();
    failed = false;
    await userEvent.click(await screen.findByRole("button", { name: "Retry generating the report" }));
    expect(await screen.findByRole("heading", { name: "Findings" })).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/research/generate")).toBe(2);
  });

  it("shows a loading label and sends one request on a double click", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const api = mockApi(withState(empty, { "POST /projects/:id/research/generate": async () => { await gate; return { body: rstate() }; } }));
    renderApp(PATH);
    await userEvent.dblClick(await screen.findByRole("button", { name: "Start preliminary research" }));
    expect(await screen.findByRole("button", { name: "Generating…" })).toBeDisabled();
    release();
    await screen.findByRole("heading", { name: "Findings" });
    expect(api.count("POST", "/projects/p1/research/generate")).toBe(1);
  });
});

describe("report: evidence labels, citations and edits", () => {
  it("groups findings by topic and labels every finding's evidence and origin", async () => {
    mockApi(withState(rstate()));
    renderApp(PATH);
    expect(await screen.findByRole("heading", { level: 3, name: "User needs and pain points" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Risks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Competitors and alternatives" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3, name: "Market context" })).not.toBeInTheDocument(); // empty topics are not filled in
    const f1 = within(screen.getByRole("listitem", { name: "Finding f-1" }));
    expect(f1.getByText("Hypothesis")).toBeInTheDocument();
    expect(f1.getByText("AI-generated")).toBeInTheDocument();
    expect(f1.getByText("No source attached.")).toBeInTheDocument();
    expect(within(screen.getByRole("listitem", { name: "Finding f-2" })).getByText("AI suggestion")).toBeInTheDocument();
    const f3 = within(screen.getByRole("listitem", { name: "Finding f-3" }));
    expect(f3.getByText("Unsupported claim")).toBeInTheDocument();
    expect(f3.getByText("Needs follow-up")).toBeInTheDocument();
    expect(screen.getByText("What remains unverified")).toBeInTheDocument();
    expect(screen.getByText(/No sources attached\. Nothing in this report is backed by a source yet/)).toBeInTheDocument();
    expect(header().getByText("Version 1")).toBeInTheDocument();
    expect(screen.getByText("Research stage: not started")).toBeInTheDocument();  // taken from the backend, not computed here
    expect(document.querySelectorAll("a[href^='http']").length).toBe(0);  // no source links exist, so none are shown
  });

  it("shows source links beside the claim they support, and says whether the source was examined", async () => {
    const src = (o = {}) => ({ id: "src-1", title: "Industry report", url: "https://example.com/report", publisher: "Example Org", accessed_on: "2026-10-01", examined: true, examined_by: "user", note: null, ...o });
    const c = content({ sources: [src(), src({ id: "src-2", title: "Blog post", url: "https://example.org/post", examined: false, examined_by: null, accessed_on: null, publisher: null })],
      findings: [finding({ evidence: "verified_source", citations: [{ source_id: "src-1", claim: "Customers compare photographers mainly on price." }] }),
                 finding({ id: "f-2", evidence: "hypothesis", citations: [{ source_id: "src-2", claim: "Some customers prefer phone booking." }] })] });
    mockApi(withState(rstate({ current: report({ content: c }) })));
    renderApp(PATH);
    const f1 = within(await screen.findByRole("listitem", { name: "Finding f-1" }));
    expect(f1.getByText("Source examined by you")).toBeInTheDocument();
    const link = f1.getByRole("link", { name: "Industry report" });
    expect(link).toHaveAttribute("href", "https://example.com/report");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(f1.getByText("Customers compare photographers mainly on price.")).toBeInTheDocument();
    expect(f1.getByText(/Examined by you on 2026-10-01/)).toBeInTheDocument();
    const f2 = within(screen.getByRole("listitem", { name: "Finding f-2" }));
    expect(f2.getByText("Hypothesis")).toBeInTheDocument();  // a cited but unexamined source never upgrades the label
    expect(f2.getByText("Not examined")).toBeInTheDocument();
  });

  it("edits a finding with the current content hash and shows server validation messages inside the dialog", async () => {
    let calls = 0;
    const api = mockApi(withState(rstate(), { "PATCH /projects/:id/research/reports/:v/findings/:fid": ({ body }: { body: any }) => {
      calls++;
      return calls === 1 ? { status: 422, body: { detail: [{ loc: ["body"], msg: "finding f-1: verified_source needs a citation to a source marked as examined" }] } }
        : edited({ content: content({ findings: [finding({ statement: body.statement, edited_by_user: true }), ...content().findings.slice(1)] }) }); } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Edit finding f-1" }));
    const dlg = within(screen.getByRole("dialog"));
    const stmt = dlg.getByLabelText("Finding");
    await userEvent.clear(stmt); await userEvent.type(stmt, "Customers struggle to compare photographers on price.");
    await userEvent.selectOptions(dlg.getByLabelText("Evidence"), "verified_source");
    await userEvent.click(dlg.getByRole("button", { name: "Save finding" }));
    expect(await dlg.findByText(/verified_source needs a citation/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(dlg.getByLabelText("Finding")).toHaveValue("Customers struggle to compare photographers on price.");  // input is not lost
    await userEvent.selectOptions(dlg.getByLabelText("Evidence"), "hypothesis");
    await userEvent.click(dlg.getByRole("button", { name: "Save finding" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Customers struggle to compare photographers on price.")).toBeInTheDocument();
    expect(within(screen.getByRole("listitem", { name: "Finding f-1" })).getByText("Edited by you")).toBeInTheDocument();
    expect(api.calls.filter((c) => c.method === "PATCH").map((c) => c.body.base_hash)).toEqual([H, H]);
    expect(api.last("PATCH", "/projects/p1/research/reports/1/findings/f-1")?.body).toMatchObject({ evidence: "hypothesis", statement: "Customers struggle to compare photographers on price." });
  });

  it("adds a source (format only) and surfaces a rejected URL", async () => {
    let n = 0;
    const api = mockApi(withState(rstate(), { "POST /projects/:id/research/reports/:v/sources": () => (++n === 1
      ? { status: 422, body: { detail: [{ loc: ["body", "url"], msg: "URL must start with http:// or https:// and include a host" }] } }
      : edited({ source_count: 1, content: content({ sources: [{ id: "src-1", title: "Industry report", url: "https://example.com/report", publisher: null, accessed_on: "2026-10-01", examined: true, examined_by: "user", note: null }] }) })) }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Add source" }));
    const dlg = within(screen.getByRole("dialog"));
    await userEvent.type(dlg.getByLabelText("Title"), "Industry report");
    await userEvent.type(dlg.getByLabelText("URL"), "javascript:alert(1)");
    await userEvent.click(dlg.getByRole("button", { name: "Add source" }));
    expect(await dlg.findByText(/must start with http/)).toBeInTheDocument();
    const url = dlg.getByLabelText("URL");
    await userEvent.clear(url); await userEvent.type(url, "https://example.com/report");
    await userEvent.type(dlg.getByLabelText("Date you accessed it"), "2026-10-01");
    await userEvent.click(dlg.getByRole("checkbox", { name: /I examined this source myself/ }));
    await userEvent.click(dlg.getByRole("button", { name: "Add source" }));
    expect(await screen.findByRole("link", { name: "Industry report" })).toHaveAttribute("href", "https://example.com/report");
    expect(api.last("POST", "/projects/p1/research/reports/1/sources")?.body).toEqual({ base_hash: H, title: "Industry report", url: "https://example.com/report", publisher: null, accessed_on: "2026-10-01", examined: true, note: null });
  });

  it("flags follow-up through the API (unsupported claims are always flagged and cannot be cleared)", async () => {
    const api = mockApi(withState(rstate(), { "POST /projects/:id/research/reports/:v/follow-up": edited({ content: content({ findings: [finding({ follow_up: true }), ...content().findings.slice(1)] }) }) }));
    renderApp(PATH);
    expect(await screen.findByRole("button", { name: "Clear follow-up on finding f-3" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Flag for follow-up: finding f-1" }));
    await waitFor(() => expect(within(screen.getByRole("listitem", { name: "Finding f-1" })).getByText("Needs follow-up")).toBeInTheDocument());
    expect(api.last("POST", "/projects/p1/research/reports/1/follow-up")?.body).toEqual({ base_hash: H, finding_ids: ["f-1"], follow_up: true });
  });

  it("deletes a finding only after confirmation", async () => {
    const api = mockApi(withState(rstate(), { "DELETE /projects/:id/research/reports/:v/findings/:fid": edited({ content: content({ findings: content().findings.slice(1) }) }) }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Delete finding f-1" }));
    expect(api.count("DELETE", "/projects/p1/research/reports/1/findings/f-1")).toBe(0);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete finding" }));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Finding f-1" })).not.toBeInTheDocument());
    expect(api.last("DELETE", "/projects/p1/research/reports/1/findings/f-1")?.query).toBe(`?base_hash=${H}`);
  });

  it("tells the user to reload when the report changed underneath them, and reloads", async () => {
    let gets = 0;
    mockApi(withState(rstate(), { "GET /projects/:id/research": () => ({ body: (gets++, rstate()) }),
      "POST /projects/:id/research/reports/:v/follow-up": { status: 409, body: { detail: "This report changed since you loaded it. Reload and try again." } } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Flag for follow-up: finding f-1" }));
    expect(await screen.findByText(/changed since you loaded it/)).toBeInTheDocument();
    await waitFor(() => expect(gets).toBe(2));
  });
});

describe("review, approval, versions and history", () => {
  it("submits for review using the content hash", async () => {
    const inReview = rstate({ status: "in_review", current: report({ status: "in_review" }), can_submit: false, can_approve: true, lifecycle: { stage: "research", status: "needs_review" } });
    const api = mockApi(withState(rstate(), { "POST /projects/:id/research/reports/:v/submit": { body: inReview } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Submit for review" }));
    expect(await screen.findByRole("button", { name: "Approve version 1" })).toBeEnabled();
    expect(screen.getByText("Research stage: needs review")).toBeInTheDocument();
    expect(api.last("POST", "/projects/p1/research/reports/1/submit")?.body).toEqual({ base_hash: H });
    expect(screen.queryByRole("button", { name: "Submit for review" })).not.toBeInTheDocument();
  });

  it("approval names the exact version, needs acknowledgement of unverified findings, and reflects the backend's lifecycle", async () => {
    const inReview = rstate({ status: "in_review", current: report({ status: "in_review" }), can_submit: false, can_approve: true });
    const approved = rstate({ status: "approved", current: report({ status: "approved", approved_at: iso, acknowledged_unverified: true, approval_note: "Reviewed with the team", editable: false }), approved_version: 1,
      history: [summary({ status: "approved", approved_at: iso })], lifecycle: { stage: "research", status: "complete" }, can_approve: false, can_submit: false, needs_supersede: false });
    const api = mockApi(withState(inReview, { "POST /projects/:id/research/reports/:v/approve": { body: approved } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Approve version 1" }));
    const dlg = within(screen.getByRole("dialog"));
    const confirm = dlg.getByRole("button", { name: "Approve version" });
    expect(confirm).toBeDisabled();
    await userEvent.click(dlg.getByRole("checkbox", { name: /3 findings are not backed by a source I examined/ }));
    await userEvent.type(dlg.getByLabelText("Approval note (optional)"), "Reviewed with the team");
    await userEvent.click(confirm);
    expect(await screen.findByText(/Version 1 approved on/)).toBeInTheDocument();
    expect(screen.getByText("Reviewed with the team", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Research stage: complete")).toBeInTheDocument();
    expect(screen.getByText("Approved version: 1")).toBeInTheDocument();
    expect(api.last("POST", "/projects/p1/research/reports/1/approve")?.body).toEqual({ content_hash: H, acknowledge_unverified: true, note: "Reviewed with the team" });
    expect(screen.queryByRole("button", { name: "Submit for review" })).not.toBeInTheDocument();
  });

  it("shows a backend rejection of an approval (stale version) without pretending it succeeded", async () => {
    const inReview = rstate({ status: "in_review", current: report({ status: "in_review" }), can_submit: false, can_approve: true });
    mockApi(withState(inReview, { "POST /projects/:id/research/reports/:v/approve": { status: 409, body: { detail: "This report changed after you opened it. Reload and review the current version." } } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Approve version 1" }));
    const dlg = within(screen.getByRole("dialog"));
    await userEvent.click(dlg.getByRole("checkbox"));
    await userEvent.click(dlg.getByRole("button", { name: "Approve version" }));
    expect(await dlg.findByText(/changed after you opened it/)).toBeInTheDocument();
    expect(screen.queryByText(/approved on/)).not.toBeInTheDocument();
  });

  it("editing an approved version tells the user a new draft was created and keeps the approval visible", async () => {
    const approved = rstate({ status: "approved", current: report({ status: "approved", approved_at: iso, editable: false }), approved_version: 1, history: [summary({ status: "approved", approved_at: iso })], needs_supersede: false, can_submit: false,
      lifecycle: { stage: "research", status: "complete" } });
    const draft2 = report({ version: 2, parent_version: 1, created_via: "copy_of_approved", content_hash: H2 });
    mockApi(withState(approved, { "POST /projects/:id/research/reports/:v/follow-up": { body: { report: draft2, state: rstate({ current: draft2, approved_version: 1, lifecycle: { stage: "research", status: "in_progress" },
      history: [summary({ version: 2, parent_version: 1, content_hash: H2 }), summary({ status: "approved", approved_at: iso })] }) } } }));
    renderApp(PATH);
    expect(await screen.findByText(/This version is approved and cannot change/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Flag for follow-up: finding f-1" }));
    expect(await screen.findByText("Saved as a new draft, version 2.")).toBeInTheDocument();
    expect(screen.getByText("Approved version: 1")).toBeInTheDocument();
    expect(screen.getByText("Research stage: in progress")).toBeInTheDocument();
    expect(header().getByText("Version 2")).toBeInTheDocument();
  });

  it("regenerating over an open draft asks first, then sends supersede", async () => {
    const api = mockApi(withState(rstate(), { "POST /projects/:id/research/generate": { body: rstate({ current: report({ version: 2, content_hash: H2 }), history: [summary({ version: 2 }), summary({ status: "superseded" })] }) } }));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Regenerate report" }));
    expect(screen.getByText(/stays in the history as superseded/)).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/research/generate")).toBe(0);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(header().getByText("Version 2")).toBeInTheDocument());
    expect(api.last("POST", "/projects/p1/research/generate")?.body).toEqual({ supersede: true });
  });

  it("lists history and opens an earlier version read-only", async () => {
    const old = report({ status: "approved", version: 1, approved_at: iso, editable: false, content: content({ findings: [finding({ statement: "An earlier approved finding about booking." })] }) });
    const cur = report({ version: 2, content_hash: H2 });
    mockApi(withState(rstate({ current: cur, history: [summary({ version: 2 }), summary({ status: "approved", approved_at: iso })], approved_version: 1 }),
      { "GET /projects/:id/research/reports/:v": { body: old } }));
    renderApp(PATH);
    await screen.findByRole("heading", { name: "Findings" });
    expect(header().getByText("Version 2")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Report history" })).getByText("Version 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "View version 1" }));
    expect(await screen.findByText("Viewing version 1 (read-only)")).toBeInTheDocument();
    expect(screen.getByText("An earlier approved finding about booking.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit finding/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Regenerate report" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back to the current report" }));
    await waitFor(() => expect(screen.queryByText(/read-only/)).not.toBeInTheDocument());
  });
});

describe("navigation", () => {
  it("Research is a real page; competitors stay marked as not implemented", async () => {
    mockApi(withState(empty));
    renderApp(PATH);
    await screen.findByText("No research report yet");
    const nav = within(screen.getByRole("navigation", { name: "Primary" }));
    expect(nav.getByRole("link", { name: "Research" })).not.toHaveTextContent("Phase");
    expect(nav.getByRole("link", { name: /Competitors/ })).toHaveTextContent("Phase 10");
  });
});

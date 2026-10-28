import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, dq, dstate, emptyBrain, filledBrain, notStarted, overview, project, renderApp, summary } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() } };
const PATH = "/projects/p1/discovery";
const FIVE = [
  dq({ id: "q1", prompt: "Who will use the product first?", required: true }),
  dq({ id: "q2", prompt: "Which feature must the first release include?", target: "mvp_scope", qtype: "single_choice", required: true, options: [{ id: "booking", label: "Online booking" }, { id: "payments", label: "Payments" }] }),
  dq({ id: "q3", prompt: "Which systems must it connect to?", target: "integrations", qtype: "multiple_choice", required: false, options: [{ id: "stripe", label: "Stripe" }, { id: "email", label: "Email" }] }),
  dq({ id: "q4", prompt: "Will you store customers' personal data?", target: "security_privacy", qtype: "confirmation", required: false }),
];
const counts = (o = 0, a = 0, s = 0, d = 0) => ({ open: o, answered: a, skipped: s, deferred: d, total: o + a + s + d });
const open4 = dstate({ questions: FIVE, counts: counts(4), outstanding_questions: ["q1", "q2", "q3", "q4"] });
const answered = (q: ReturnType<typeof dq>, answer: unknown) => ({ ...q, status: "answered", answer });

describe("rendering and answering", () => {
  it("renders the questions the API returned, with rationale and real counts but no percentages", async () => {
    mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 } });
    renderApp(PATH);
    expect(await screen.findByRole("heading", { name: "Discovery" })).toBeInTheDocument();
    expect(screen.getByLabelText("Who will use the product first?")).toBeInstanceOf(HTMLTextAreaElement);
    expect(within(screen.getByRole("group", { name: /Which feature must/ })).getAllByRole("radio")).toHaveLength(2);
    expect(within(screen.getByRole("group", { name: /Which systems must/ })).getAllByRole("checkbox")).toHaveLength(2);
    expect(within(screen.getByRole("group", { name: /personal data/ })).getByRole("radio", { name: "Yes" })).toBeInTheDocument();
    expect(screen.getAllByText(/Why we ask:/)).toHaveLength(4);
    expect(screen.getByLabelText("Discovery progress")).toHaveTextContent("Round 1 of 3 · 0 answered · 0 skipped · 0 deferred · 4 open");
    expect(document.body.textContent).not.toMatch(/\d+\s?%/);
  });

  it("sends each question type in the shape the API expects, then shows the saved state", async () => {
    let state = open4;
    const api = mockApi({ ...base, "GET /projects/:id/discovery": () => ({ body: state }),
      "POST /projects/:id/discovery/answers": ({ body }) => {
        expect(body.answers).toHaveLength(4);
        state = dstate({ questions: [answered(FIVE[0], { text: "Photographers" }), answered(FIVE[1], { choice: "booking" }), answered(FIVE[2], { choices: ["stripe", "email"] }), answered(FIVE[3], { confirmed: true })],
          counts: counts(0, 4), outstanding_questions: [], can_review: true, can_generate_next_round: true });
        return { body: state };
      } });
    renderApp(PATH);
    await userEvent.type(await screen.findByLabelText("Who will use the product first?"), "  Photographers ");
    await userEvent.click(screen.getByRole("radio", { name: "Online booking" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Stripe" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Email" }));
    await userEvent.click(within(screen.getByRole("group", { name: /personal data/ })).getByRole("radio", { name: "Yes" }));
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    await waitFor(() => expect(screen.getByLabelText("Discovery progress")).toHaveTextContent("4 answered"));
    expect(api.last("POST", "/projects/p1/discovery/answers")?.body).toEqual({ answers: [
      { question_id: "q1", value: "Photographers" }, { question_id: "q2", value: "booking" },
      { question_id: "q3", value: ["stripe", "email"] }, { question_id: "q4", value: true }] });
    expect(screen.getByRole("button", { name: "Save answers" })).toBeDisabled(); // nothing left to save
    expect(screen.getByRole("button", { name: "Review summary" })).toBeEnabled();
  });

  it("validates locally without calling the API", async () => {
    const api = mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 } });
    renderApp(PATH);
    await userEvent.type(await screen.findByLabelText("Who will use the product first?"), "   ");
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(await screen.findByText("Answer can't be empty.")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/discovery/answers")).toBe(0);
  });

  it("shows the server's per-question validation errors and keeps what was typed", async () => {
    mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 },
      "POST /projects/:id/discovery/answers": { status: 422, body: { detail: [{ loc: ["body", "answers", "q2"], msg: "Choose one of the listed options." }] } } });
    renderApp(PATH);
    await userEvent.type(await screen.findByLabelText("Who will use the product first?"), "Photographers");
    await userEvent.click(screen.getByRole("radio", { name: "Payments" }));
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    const group = await screen.findByRole("group", { name: /Which feature must/ });
    expect(within(group).getByText("Choose one of the listed options.")).toBeInTheDocument();
    expect(screen.getByLabelText("Who will use the product first?")).toHaveValue("Photographers");
    expect(screen.getByRole("radio", { name: "Payments" })).toBeChecked();
  });

  it("keeps typed answers when the request fails, and sends only one request on a double click", async () => {
    let calls = 0, release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 },
      "POST /projects/:id/discovery/answers": async () => { calls++; await gate; return { status: 502, body: { detail: "x" } }; } });
    renderApp(PATH);
    await userEvent.type(await screen.findByLabelText("Who will use the product first?"), "Photographers");
    const save = screen.getByRole("button", { name: "Save answers" });
    await userEvent.dblClick(save);
    expect(calls).toBe(1);
    release();
    expect(await screen.findByText("WebForge couldn't use the AI response.")).toBeInTheDocument();
    expect(screen.getByLabelText("Who will use the product first?")).toHaveValue("Photographers");
    expect(screen.getByRole("button", { name: "Save answers" })).toBeEnabled();
  });

  it("offers skip only for optional questions and answer-later for all, via the API", async () => {
    let state = open4;
    const api = mockApi({ ...base, "GET /projects/:id/discovery": () => ({ body: state }),
      "POST /projects/:id/discovery/questions/:qid/skip": ({ params }) => (state = dstate({ questions: FIVE.map((q) => (q.id === params.qid ? { ...q, status: "skipped" } : q)), counts: counts(3, 0, 1) }), { body: state }),
      "POST /projects/:id/discovery/questions/:qid/defer": ({ params }) => (state = dstate({ questions: FIVE.map((q) => (q.id === params.qid ? { ...q, status: "deferred" } : q)), counts: counts(3, 0, 0, 1) }), { body: state }) });
    renderApp(PATH);
    await screen.findByRole("heading", { name: "Discovery" });
    expect(screen.queryByRole("button", { name: /^Skip: Who will use/ })).not.toBeInTheDocument(); // required
    expect(screen.getByRole("button", { name: /^Answer later: Who will use/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^Skip: Which systems/ }));
    await waitFor(() => expect(screen.getByLabelText("Discovery progress")).toHaveTextContent("1 skipped"));
    expect(api.count("POST", "/projects/p1/discovery/questions/q3/skip")).toBe(1);
    await userEvent.click(screen.getByRole("button", { name: /^Answer later: Which feature/ }));
    await waitFor(() => expect(screen.getByLabelText("Discovery progress")).toHaveTextContent("1 deferred"));
  });

  it("resumes a saved session: answers are pre-filled and nothing is pending", async () => {
    const saved = dstate({ questions: [answered(FIVE[0], { text: "Photographers" }), answered(FIVE[1], { choice: "payments" }), answered(FIVE[2], { choices: ["email"] }), answered(FIVE[3], { confirmed: false })], counts: counts(0, 4) });
    mockApi({ ...base, "GET /projects/:id/discovery": { body: saved } });
    renderApp(PATH);
    expect(await screen.findByLabelText("Who will use the product first?")).toHaveValue("Photographers");
    expect(screen.getByRole("radio", { name: "Payments" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Email" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Stripe" })).not.toBeChecked();
    expect(within(screen.getByRole("group", { name: /personal data/ })).getByRole("radio", { name: "No" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Save answers" })).toBeDisabled();
  });

  it("'Save and finish later' stores the answers and returns to the overview", async () => {
    const api = mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 }, "POST /projects/:id/discovery/answers": { body: open4 },
      "GET /projects/:id/overview": { body: overview() }, "GET /projects/:id/brain": { body: emptyBrain } });
    const router = renderApp(PATH);
    await userEvent.type(await screen.findByLabelText("Who will use the product first?"), "Photographers");
    await userEvent.click(screen.getByRole("button", { name: "Save and finish later" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p1/overview"));
    expect(api.count("POST", "/projects/p1/discovery/answers")).toBe(1);
  });
});

describe("starting, failure and retry", () => {
  it("asks for an idea first when none exists, without offering to start", async () => {
    mockApi({ ...base, "GET /projects/:id/discovery": { body: { ...notStarted, idea_ready: false } } });
    renderApp(PATH);
    expect(await screen.findByText("Describe your idea first")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start discovery" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Overview" })).toHaveAttribute("href", "/projects/p1/overview");
  });

  it("explains an unconfigured provider, does not retry on its own, and recovers when retried by the user", async () => {
    let attempt = 0, state: ReturnType<typeof dstate> = notStarted as never;
    const api = mockApi({ ...base, "GET /projects/:id/discovery": () => ({ body: state }),
      "POST /projects/:id/discovery": () => (++attempt === 1
        ? ((state = dstate({ status: "failed", round: 0, questions: [], counts: counts(), can_review: false, last_error: "AI provider not configured." })), { status: 503, body: { detail: "AI provider not configured: GOOGLE_AI_API_KEY is not set" } })
        : ((state = open4), { body: open4 })) });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Start discovery" }));
    expect(await screen.findByText("AI analysis is not configured yet.")).toBeInTheDocument();
    expect(screen.getByText(/saved answers are safe/)).toBeInTheDocument();
    expect(screen.queryByText(/GOOGLE_AI_API_KEY/)).not.toBeInTheDocument();
    expect(await screen.findByText("Questions couldn't be generated")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/discovery")).toBe(1); // no silent retry
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Who will use the product first?")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/discovery")).toBe(2);
  });

  it("explains an unusable AI response (502) and shows a loading label while generating", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockApi({ ...base, "GET /projects/:id/discovery": { body: notStarted }, "POST /projects/:id/discovery": async () => { await gate; return { status: 502, body: { detail: "The AI response could not be used." } }; } });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Start discovery" }));
    expect(await screen.findByRole("button", { name: "Preparing questions…" })).toBeDisabled();
    release();
    expect(await screen.findByText("WebForge couldn't use the AI response.")).toBeInTheDocument();
  });

  it("shows the provider's specific safe reason (for example an unavailable model) on a 502", async () => {
    mockApi({ ...base, "GET /projects/:id/discovery": { body: notStarted }, "POST /projects/:id/discovery": { status: 502, body: { detail: "The configured AI model is not available to this key." } } });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Start discovery" }));
    expect(await screen.findByText(/The configured AI model is not available to this key\./)).toBeInTheDocument();
    expect(screen.getByText(/saved answers are safe/)).toBeInTheDocument();
  });

  it("generates another round on request and keeps earlier questions", async () => {
    const r1 = dstate({ questions: [answered(FIVE[0], { text: "Photographers" })], counts: counts(0, 1), outstanding_questions: [], can_generate_next_round: true });
    const r2 = dstate({ round: 2, questions: [answered(FIVE[0], { text: "Photographers" }), dq({ id: "q9", round: 2, prompt: "What must a customer do in one visit?", target: "core_workflows" })], counts: counts(1, 1), outstanding_questions: ["q9"] });
    let state = r1;
    const api = mockApi({ ...base, "GET /projects/:id/discovery": () => ({ body: state }), "POST /projects/:id/discovery/next-round": () => ((state = r2), { body: r2 }) });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Generate more questions" }));
    expect(await screen.findByLabelText("What must a customer do in one visit?")).toBeInTheDocument();
    expect(screen.getByLabelText("Who will use the product first?")).toHaveValue("Photographers");
    expect(screen.getByText("Round 2")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/discovery/next-round")).toBe(1);
  });
});

describe("review and completion", () => {
  const sm = summary({
    confirmed: [{ question_id: "q1", question: "Who will use the product first?", target: "target_users", answer: "Photographers" }],
    proposed: [{ label: "Features", target: null, items: ["Package comparison"] }],
    assumptions: [{ id: "idea:0", text: "Customers book online", source: "ai_suggested", status: "unverified" }],
    unanswered: [{ id: "q3", question: "Which systems must it connect to?", required: false }],
    deferred: [{ id: "q2", question: "Which feature must the first release include?", required: true }],
  });
  const review = dstate({ status: "ready_for_review", summary: sm, questions: [answered(FIVE[0], { text: "Photographers" })], counts: counts(1, 1, 0, 1),
    outstanding_questions: ["q2", "q3"], can_review: false, can_complete: true, next_step: { key: "complete_discovery", label: "Confirm" } });

  it("moves to review and separates confirmed, proposed, assumptions, unanswered and deferred", async () => {
    const api = mockApi({ ...base, "GET /projects/:id/discovery": { body: open4 }, "POST /projects/:id/discovery/review": { body: review } });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Review summary" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Confirmed by you" })).toBeInTheDocument(); // h1 -> h2, no skipped level
    const confirmed = within(await screen.findByRole("region", { name: "Confirmed by you" }));
    expect(confirmed.getByText("Photographers")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /Proposed by AI/ })).getByText("Package comparison")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Unresolved assumptions" })).getByText(/Customers book online/)).toHaveTextContent("AI-suggested");
    expect(within(screen.getByRole("region", { name: "Unanswered questions" })).getByText("Which systems must it connect to?")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Deferred for later" })).getByText(/Which feature must/)).toBeInTheDocument();
    expect(screen.getByText(/not market validation or research/)).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/discovery/review")).toBe(1);
  });

  it("requires explicit acceptance of unresolved items before completing, then shows a read-only summary", async () => {
    let state = review;
    const done = dstate({ status: "completed", summary: sm, questions: [], counts: counts(), outstanding_questions: [], can_review: false, can_complete: false,
      next_step: { key: "return_to_overview", label: "Return", note: "Discovery clarifies your idea only. Research and PRD generation are not available yet." } });
    const api = mockApi({ ...base, "GET /projects/:id/discovery": () => ({ body: state }), "POST /projects/:id/discovery/complete": () => ((state = done), { body: done }) });
    renderApp(PATH);
    const complete = await screen.findByRole("button", { name: "Complete discovery" });
    expect(complete).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Complete with documented assumptions/ }));
    expect(complete).toBeEnabled();
    await userEvent.click(complete);
    expect(await screen.findByText("Discovery completed.")).toBeInTheDocument();
    expect(api.last("POST", "/projects/p1/discovery/complete")?.body).toEqual({ accept_assumptions: true });
    expect(screen.getByText(/Research and PRD generation are not available yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to project overview" })).toHaveAttribute("href", "/projects/p1/overview");
    expect(screen.queryByRole("button", { name: "Save answers" })).not.toBeInTheDocument();
  });

  it("completes without the assumptions box when nothing is outstanding", async () => {
    const clean = { ...review, outstanding_questions: [], summary: summary(), counts: counts(0, 1) };
    const api = mockApi({ ...base, "GET /projects/:id/discovery": { body: clean }, "POST /projects/:id/discovery/complete": { body: { ...clean, status: "completed" } } });
    renderApp(PATH);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Complete discovery" }));
    await screen.findByText("Discovery completed.");
    expect(api.last("POST", "/projects/p1/discovery/complete")?.body).toEqual({ accept_assumptions: false });
  });

  it("lets the user correct an answer during review before confirming", async () => {
    const api = mockApi({ ...base, "GET /projects/:id/discovery": { body: review }, "POST /projects/:id/discovery/answers": { body: review } });
    renderApp(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Edit answers" }));
    const field = screen.getByLabelText("Who will use the product first?");
    await userEvent.clear(field); await userEvent.type(field, "Wedding photographers");
    expect(screen.getByRole("button", { name: "Complete discovery" })).toBeDisabled(); // unsaved edit blocks completion
    await userEvent.click(screen.getAllByRole("button", { name: "Save answers" })[0]);
    await waitFor(() => expect(api.count("POST", "/projects/p1/discovery/answers")).toBe(1));
    expect(api.last("POST", "/projects/p1/discovery/answers")?.body).toEqual({ answers: [{ question_id: "q1", value: "Wedding photographers" }] });
  });
});

describe("overview callout", () => {
  const ov = { "GET /projects/:id/overview": { body: overview() }, "GET /projects/:id/brain": { body: filledBrain() } };
  it("reflects the backend's discovery state and links to it", async () => {
    mockApi({ ...base, ...ov, "GET /projects/:id/discovery": { body: dstate({ counts: counts(3) }) } });
    renderApp("/projects/p1/overview");
    const region = within(await screen.findByRole("region", { name: "Discovery" }));
    expect(region.getByText("3 questions waiting for your answer.")).toBeInTheDocument();
    expect(region.getByRole("link", { name: "Continue discovery" })).toHaveAttribute("href", "/projects/p1/discovery");
  });

  it("is not shown before an idea exists, and never breaks the overview if discovery fails to load", async () => {
    const api = mockApi({ ...base, "GET /projects/:id/overview": { body: overview() }, "GET /projects/:id/brain": { body: emptyBrain } });
    renderApp("/projects/p1/overview");
    await screen.findByText("What are you building?");
    expect(screen.queryByRole("region", { name: "Discovery" })).not.toBeInTheDocument();
    expect(api.count("GET", "/projects/p1/discovery")).toBe(0);
  });

  it("stays quiet when the discovery request fails", async () => {
    mockApi({ ...base, ...ov, "GET /projects/:id/discovery": { status: 500, body: { detail: "boom" } } });
    renderApp("/projects/p1/overview");
    expect(await screen.findByRole("region", { name: "Lifecycle" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Discovery" })).not.toBeInTheDocument();
  });
});

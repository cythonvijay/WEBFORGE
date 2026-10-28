import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, emptyBrain, filledBrain, notStarted, overview, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = { ...authed, "GET /projects/:id": { body: project() }, "GET /projects/:id/discovery": { body: notStarted } };
const now = new Date().toISOString();

describe("overview data", () => {
  it("shows exactly what the backend returned (progress is not recomputed)", async () => {
    // progress=37 deliberately disagrees with 1/19 stages: the UI must display the backend's number.
    mockApi({ ...base, "GET /projects/:id/brain": { body: filledBrain(3) },
      "GET /projects/:id/overview": { body: overview({ research: "complete", product: "in_progress" }, { progress: 37, next_action: "product",
        recent_changes: [{ version: 3, change_type: "ai_intake", created_at: now }, { version: 1, change_type: "created", created_at: now }] }) } });
    renderApp("/projects/p1/overview");
    expect(await screen.findByRole("progressbar", { name: "Project progress" })).toHaveAttribute("aria-valuenow", "37");
    expect(screen.getByText("1 of 19 stages complete")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Next action" })).getByText("Continue Product")).toBeInTheDocument();
    const recent = within(screen.getByRole("region", { name: "Recent changes" }));
    expect(recent.getByText(/AI intake analysis saved/)).toBeInTheDocument();
    expect(recent.getByText(/Project created/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "System state" })).getByText("v3")).toBeInTheDocument();
    expect(screen.getByText(/Build, deployment and monitoring are not connected/)).toBeInTheDocument();
  });

  it("words the next action by the stage's state (a stage awaiting review is reviewed, not started)", async () => {
    mockApi({ ...base, "GET /projects/:id/brain": { body: filledBrain() },
      "GET /projects/:id/overview": { body: overview({ research: "complete", product: "complete", ux: "needs_review" }, { next_action: "ux" }) } });
    renderApp("/projects/p1/overview");
    expect(await within(await screen.findByRole("region", { name: "Next action" })).findByText("Review UX")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Current work" })).getByText("Needs review")).toBeInTheDocument();
  });

  it("explains dependency blocking from backend data and shows empty change history honestly", async () => {
    mockApi({ ...base, "GET /projects/:id/brain": { body: filledBrain() },
      "GET /projects/:id/overview": { body: overview({ research: "complete", product: "complete", ux: "complete", design: "complete" }, { recent_changes: [] }) } });
    renderApp("/projects/p1/overview");
    expect(await screen.findByText("Complete Architecture before starting Frontend.")).toBeInTheDocument();
    expect(screen.getByText("Complete Backend, Database before starting API.")).toBeInTheDocument();
    expect(screen.getByText("No recent changes yet.")).toBeInTheDocument();
  });

  it("surfaces a stage conflict using the backend's dependency data, and reloads on success", async () => {
    let ov = overview({ research: "complete" });
    const api = mockApi({ ...base, "GET /projects/:id/brain": { body: filledBrain() }, "GET /projects/:id/overview": () => ({ body: ov }),
      "PUT /projects/:id/stages/:stage": ({ params }) => params.stage === "frontend"
        ? { status: 409, body: { detail: "Blocked by incomplete stages: architecture" } }
        : (ov = overview({ research: "complete", product: "in_progress" }), { body: { stage: "product", status: "in_progress" } }) });
    renderApp("/projects/p1/overview");
    await userEvent.selectOptions(await screen.findByLabelText("Set status for Frontend"), "in_progress");
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't set Frontend to in progress yet. Complete Architecture first.");
    expect(api.last("PUT", "/projects/p1/stages/frontend")?.body).toEqual({ status: "in_progress" });
    expect(api.count("GET", "/projects/p1/overview")).toBe(1);

    await userEvent.selectOptions(screen.getByLabelText("Set status for Product"), "in_progress");
    expect(await within(screen.getByRole("region", { name: "Current work" })).findByText("Product")).toBeInTheDocument();
    expect(api.count("GET", "/projects/p1/overview")).toBe(2);
  });
});

describe("AI intake", () => {
  const idea = "A marketplace for local photographers";
  const first = { ...base, "GET /projects/:id/overview": { body: overview() } };

  async function submit(text = idea) {
    await userEvent.type(await screen.findByLabelText("Product idea"), text);
    await userEvent.click(screen.getByRole("button", { name: "Analyze idea" }));
  }

  it("blocks submissions that are too short without calling the API", async () => {
    const api = mockApi({ ...first, "GET /projects/:id/brain": { body: emptyBrain } });
    renderApp("/projects/p1/overview");
    await submit("short");
    expect(screen.getByText("Describe your idea in at least 10 characters.")).toBeInTheDocument();
    expect(api.count("POST", "/projects/p1/intake")).toBe(0);
  });

  it("explains an unconfigured AI provider, keeps the text, and changes nothing (503)", async () => {
    const api = mockApi({ ...first, "GET /projects/:id/brain": { body: emptyBrain }, "POST /projects/:id/intake": { status: 503, body: { detail: "AI provider not configured: GOOGLE_AI_API_KEY is not set" } } });
    renderApp("/projects/p1/overview");
    await submit();
    expect(await screen.findByText("AI analysis is not configured yet.")).toBeInTheDocument();
    expect(screen.getByText(/Your project has not been modified/)).toBeInTheDocument();
    expect(screen.queryByText(/GOOGLE_AI_API_KEY/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Product idea")).toHaveValue(idea);
    expect(api.count("GET", "/projects/p1/brain")).toBe(1);
  });

  it("explains an invalid AI response (502)", async () => {
    mockApi({ ...first, "GET /projects/:id/brain": { body: emptyBrain }, "POST /projects/:id/intake": { status: 502, body: { detail: "Model output failed validation: 2 error(s)" } } });
    renderApp("/projects/p1/overview");
    await submit();
    expect(await screen.findByText("WebForge couldn't validate the AI response.")).toBeInTheDocument();
    expect(screen.getByText(/No project data was changed/)).toBeInTheDocument();
  });

  it("shows a loading state, then the structured result that was saved", async () => {
    let saved = false, release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const api = mockApi({ ...first, "GET /projects/:id/brain": () => ({ body: saved ? filledBrain(2) : emptyBrain }),
      "POST /projects/:id/intake": async () => { await gate; saved = true; return { body: { version: 2, result: {} } }; } });
    renderApp("/projects/p1/overview");
    await submit();
    expect(await screen.findByRole("button", { name: "Analyzing your idea…" })).toBeDisabled();
    release();
    expect(await screen.findByText("Analysis saved as Project Brain v2.")).toBeInTheDocument();
    const review = within(await screen.findByRole("region", { name: "Product idea" }));
    expect(review.getByText("Snapbook")).toBeInTheDocument();
    expect(review.getByText("Hard to compare photographers")).toBeInTheDocument();
    for (const t of ["Customers", "Increase bookings", "Package comparison", "Customers book online", "Who pays the fee?"]) expect(review.getByText(t)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze idea" })).not.toBeInTheDocument();
    expect(api.last("POST", "/projects/p1/intake")?.body).toEqual({ idea });
  });

  it("warns before replacing an existing analysis and only submits on request", async () => {
    const api = mockApi({ ...first, "GET /projects/:id/brain": { body: filledBrain() } });
    renderApp("/projects/p1/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Analyze again" }));
    expect(screen.getByText(/replaces the current idea, target users and goals/)).toBeInTheDocument();
    expect(screen.getByLabelText("Product idea")).toHaveValue("A marketplace for local photographers");
    expect(api.count("POST", "/projects/p1/intake")).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Analyze again" })).toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("marks unimplemented sections clearly and shows no fake content", async () => {
    mockApi({ ...base });
    renderApp("/projects/p1/frontend");
    expect(await screen.findByText("This workspace will become available in Phase 13.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Overview" })).toHaveAttribute("href", "/projects/p1/overview");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: /Frontend/ })).toHaveTextContent("Phase 13");
  });

  it("404s unknown sections and collapses the sidebar behind a toggle", async () => {
    mockApi({ ...base });
    renderApp("/projects/p1/not-a-section");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Toggle navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

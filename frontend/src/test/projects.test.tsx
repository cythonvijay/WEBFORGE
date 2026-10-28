import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { authed, emptyBrain, overview, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

describe("projects list", () => {
  it("renders real rows with status and flags archived projects", async () => {
    mockApi({ ...authed, "GET /projects": { body: [project(), project({ id: "p2", name: "Old idea", status: "archived", description: "" })] } });
    renderApp("/projects");
    const rows = await screen.findAllByRole("row");
    expect(within(rows[1]).getByRole("link", { name: "Snapbook" })).toHaveAttribute("href", "/projects/p1");
    expect(within(rows[1]).getByText("Active")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Archived")).toBeInTheDocument();
    expect(within(rows[2]).getByRole("button", { name: "Restore Old idea" })).toBeInTheDocument();
  });

  it("shows a useful empty state", async () => {
    mockApi({ ...authed, "GET /projects": { body: [] } });
    renderApp("/projects");
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByText(/guide it from idea to production/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New project" })).toBeInTheDocument();
  });

  it("shows a friendly error with retry and hides server internals", async () => {
    let fail = true;
    mockApi({ ...authed, "GET /projects": () => (fail ? { status: 500, body: { detail: "Traceback: psycopg.OperationalError" } } : { body: [project()] }) });
    renderApp("/projects");
    expect(await screen.findByText("Something went wrong on our side. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText(/psycopg/)).not.toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Snapbook" })).toBeInTheDocument();
  });
});

describe("project actions", () => {
  it("creates a project and opens its overview", async () => {
    const api = mockApi({
      ...authed, "GET /projects": { body: [] }, "POST /projects": { status: 201, body: project() },
      "GET /projects/:id": { body: project() }, "GET /projects/:id/overview": { body: overview({}, { progress: 0 }) }, "GET /projects/:id/brain": { body: emptyBrain },
    });
    const router = renderApp("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    await userEvent.type(screen.getByLabelText("Project name"), "Snapbook");
    await userEvent.type(screen.getByLabelText("Description"), "Photographer marketplace");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("heading", { name: "Snapbook" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/p1/overview");
    expect(api.last("POST", "/projects")?.body).toEqual({ name: "Snapbook", description: "Photographer marketplace" });
  });

  it("requires a name and reports server failures inside the dialog", async () => {
    const api = mockApi({ ...authed, "GET /projects": { body: [] }, "POST /projects": { status: 500, body: { detail: "boom" } } });
    renderApp("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(screen.getByText("Give the project a name.")).toBeInTheDocument();
    expect(api.count("POST", "/projects")).toBe(0);
    await userEvent.type(screen.getByLabelText("Project name"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renames, archives and deletes through the API, reloading the list each time", async () => {
    let list = [project()];
    const api = mockApi({
      ...authed, "GET /projects": () => ({ body: list }),
      "PATCH /projects/:id": ({ body }) => { list = [{ ...list[0], ...body }]; return { body: list[0] }; },
      "DELETE /projects/:id": () => { list = []; return { status: 204 }; },
    });
    renderApp("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "Rename Snapbook" }));
    const name = screen.getByLabelText("Project name");
    await userEvent.clear(name); await userEvent.type(name, "Snapbook 2");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("link", { name: "Snapbook 2" })).toBeInTheDocument();
    expect(api.last("PATCH", "/projects/p1")?.body).toEqual({ name: "Snapbook 2" });

    await userEvent.click(screen.getByRole("button", { name: "Archive Snapbook 2" }));
    expect(await screen.findByText("Archived")).toBeInTheDocument();
    expect(api.last("PATCH", "/projects/p1")?.body).toEqual({ status: "archived" });

    await userEvent.click(screen.getByRole("button", { name: "Delete Snapbook 2" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("permanently deleted");
    expect(api.count("DELETE", "/projects/p1")).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete project" }));
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(api.count("DELETE", "/projects/p1")).toBe(1);
  });

  it("explains a missing project instead of crashing", async () => {
    mockApi({ ...authed, "GET /projects/:id": { status: 404, body: { detail: "Project not found" } } });
    renderApp("/projects/nope/overview");
    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeInTheDocument();
  });
});

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { anon, authed, emptyBrain, overview, project, renderApp, user as me } from "./helpers";
import { mockApi } from "./mockApi";

describe("dialog focus management", () => {
  it("traps Tab inside the dialog, lands on the safe action first, and restores focus on Escape", async () => {
    mockApi({ ...authed, "GET /projects": { body: [project()] } });
    renderApp("/projects");
    const trigger = await screen.findByRole("button", { name: "Delete Snapbook" });
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    const confirm = within(dialog).getByRole("button", { name: "Delete project" });
    expect(cancel).toHaveFocus();
    await userEvent.tab(); expect(confirm).toHaveFocus();
    await userEvent.tab(); expect(cancel).toHaveFocus();           // wraps instead of escaping to the page behind
    await userEvent.tab({ shift: true }); expect(confirm).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

describe("shell accessibility", () => {
  it("auth pages have a main landmark", async () => {
    mockApi({ ...anon });
    renderApp("/login");
    expect(await screen.findByRole("main")).toBeInTheDocument();
  });

  it("closes the mobile sidebar with Escape (focus returns to the toggle) and via the backdrop", async () => {
    mockApi({ ...authed, "GET /projects/:id": { body: project() }, "GET /projects/:id/overview": { body: overview() }, "GET /projects/:id/brain": { body: emptyBrain } });
    renderApp("/projects/p1/overview");
    const toggle = await screen.findByRole("button", { name: "Toggle navigation" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
    await userEvent.click(toggle);
    await userEvent.click(document.querySelector('[aria-hidden="true"].fixed')!);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});

describe("sign-out behavior", () => {
  it("does not send you back to the page you signed out from (it may belong to another account)", async () => {
    mockApi({ ...authed, "GET /projects/:id": { body: project() }, "GET /projects/:id/overview": { body: overview() }, "GET /projects/:id/brain": { body: emptyBrain },
      "POST /auth/logout": { status: 204 }, "POST /auth/login": { body: me }, "GET /projects": { body: [] } });
    const router = renderApp("/projects/p1/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123{Enter}");
    await screen.findByRole("heading", { name: "Projects" });
    expect(router.state.location.pathname).toBe("/projects");
  });

  it("still returns you to your page after a session simply expired", async () => {
    let meCalls = 0;
    mockApi({ "GET /auth/me": () => (++meCalls === 1 ? { status: 401, body: {} } : { status: 401, body: {} }), "POST /auth/refresh": { status: 401, body: {} },
      "POST /auth/login": { body: me }, "GET /projects": { body: [] }, "GET /settings": { body: {} } });
    const router = renderApp("/settings");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123{Enter}");
    await screen.findByRole("heading", { name: "Settings" });
    expect(router.state.location.pathname).toBe("/settings");
  });
});

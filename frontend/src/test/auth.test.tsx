import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { anon, authed, renderApp, user as me } from "./helpers";
import { mockApi } from "./mockApi";

describe("authenticated routing", () => {
  it("sends anonymous visitors to /login without loading project data", async () => {
    const api = mockApi({ ...anon });
    const router = renderApp("/projects");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(api.count("GET", "/projects")).toBe(0);
  });

  it("restores the session through a refresh when the access token has expired", async () => {
    let meCalls = 0;
    const api = mockApi({
      "GET /auth/me": () => (++meCalls === 1 ? { status: 401, body: { detail: "Not authenticated" } } : { body: me }),
      "POST /auth/refresh": { body: { ok: true } },
      "GET /projects": { body: [] },
    });
    renderApp("/projects");
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(api.count("POST", "/auth/refresh")).toBe(1);
  });

  it("offers a retry when the server can't be reached at startup", async () => {
    mockApi({ "GET /auth/me": { networkError: true } });
    renderApp("/projects");
    expect(await screen.findByText(/Can't reach WebForge/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("signs out through the API and returns to login", async () => {
    const api = mockApi({ ...authed, "GET /projects": { body: [] }, "POST /auth/logout": { status: 204 } });
    renderApp("/projects");
    await screen.findByText("No projects yet.");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(api.count("POST", "/auth/logout")).toBe(1);
  });

  it("redirects signed-in users away from /login", async () => {
    mockApi({ ...authed, "GET /projects": { body: [] } });
    const router = renderApp("/login");
    await screen.findByRole("heading", { name: "Projects" });
    expect(router.state.location.pathname).toBe("/projects");
  });
});

describe("login form", () => {
  it("validates before calling the API", async () => {
    const api = mockApi({ ...anon });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(api.count("POST", "/auth/login")).toBe(0);
  });

  it("shows the server's error and stays on the page", async () => {
    mockApi({ ...anon, "POST /auth/login": { status: 401, body: { detail: "Invalid email or password" } } });
    const router = renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpassword");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("sends credentials, disables submit while pending, and lands on /projects", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const api = mockApi({ ...anon, "POST /auth/login": async () => { await gate; return { body: me }; }, "GET /projects": { body: [] } });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123{Enter}");
    expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
    release();
    await screen.findByRole("heading", { name: "Projects" });
    expect(api.last("POST", "/auth/login")?.body).toEqual({ email: "ada@example.com", password: "password123" });
  });
});

describe("register form", () => {
  it("enforces the 8 character minimum locally", async () => {
    const api = mockApi({ ...anon });
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(api.count("POST", "/auth/register")).toBe(0);
  });

  it("surfaces a duplicate-email conflict", async () => {
    mockApi({ ...anon, "POST /auth/register": { status: 409, body: { detail: "Email already registered" } } });
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email already registered");
  });

  it("creates the account and enters the app", async () => {
    mockApi({ ...anon, "POST /auth/register": { status: 201, body: me }, "GET /projects": { body: [] } });
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument());
  });
});

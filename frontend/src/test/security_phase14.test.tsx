import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { safeHttpUrl } from "../lib/utils";
import { authed, filledBrain, notStarted, overview, project, renderApp } from "./helpers";
import { mockApi } from "./mockApi";

const base = {
  ...authed,
  "GET /projects/:id": { body: project() },
  "GET /projects/:id/discovery": { body: notStarted },
};

describe("Phase 14 Frontend Security & Stage Completion Guards", () => {
  it("sanitizes unsafe URL protocols via safeHttpUrl", () => {
    expect(safeHttpUrl("https://example.com/report")).toBe("https://example.com/report");
    expect(safeHttpUrl("http://example.com/doc")).toBe("http://example.com/doc");
    expect(safeHttpUrl("javascript:alert(1)")).toBe("#");
    expect(safeHttpUrl("JAVASCRIPT:alert(document.cookie)")).toBe("#");
    expect(safeHttpUrl("data:text/html,<script>alert(1)</script>")).toBe("#");
    expect(safeHttpUrl("vbscript:msgbox(1)")).toBe("#");
    expect(safeHttpUrl("")).toBe("#");
    expect(safeHttpUrl(null)).toBe("#");
  });

  it("surfaces backend stage completion guard errors when attempting to mark Testing or Security complete prematurely", async () => {
    mockApi({
      ...base,
      "GET /projects/:id/brain": { body: filledBrain() },
      "GET /projects/:id/overview": {
        body: overview({
          research: "complete",
          product: "complete",
          ux: "complete",
          design: "complete",
          architecture: "complete",
          frontend: "complete",
          backend: "complete",
          database: "complete",
          api: "complete",
        }),
      },
      "PUT /projects/:id/stages/:stage": ({ params }) => ({
        status: 409,
        body: {
          detail:
            params.stage === "testing"
              ? "Testing stage cannot be marked complete yet: Product Architecture has not been approved yet."
              : "Security stage cannot be marked complete yet: Blocked by incomplete upstream stages: testing",
        },
      }),
    });

    renderApp("/projects/p1/overview");
    await userEvent.selectOptions(await screen.findByLabelText("Set status for Testing"), "complete");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Testing stage cannot be marked complete yet|Can't set Testing to complete yet/
    );
  });
});

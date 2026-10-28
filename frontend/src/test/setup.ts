import "@testing-library/jest-dom/vitest";
import { afterEach, expect, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { unhandled } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  const missed = unhandled.splice(0);
  expect(missed, `requests with no mock route: ${missed.join(", ")}`).toEqual([]);
});

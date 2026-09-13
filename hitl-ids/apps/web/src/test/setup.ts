import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { setApiRole } from "../api/client";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  setApiRole(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { setApiToken } from "../api/client";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  setApiToken(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

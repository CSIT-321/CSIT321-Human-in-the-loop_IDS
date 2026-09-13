/**
 * The S16 demo narrative, driven through a real browser against the real API.
 *
 *     npm run e2e
 *
 * Two servers are started for the run and stopped after it: the API over a *disposable copy* of
 * data/demo.db on :8001 (scripts/serve_rehearsal.py — verdicts are permanent, so a rehearsal must
 * never judge the real queue), and the Vite dev server on :5174 proxying /api to it.
 *
 * HITL_PYTHON selects the interpreter (default "python"); the project's suite runs on Python 3.11.
 */

import { defineConfig, devices } from "@playwright/test";

const python = process.env.HITL_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: `"${python}" ../../scripts/serve_rehearsal.py --port 8001`,
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
      // Surface the API's own log in the run output, so a 500 arrives with its traceback.
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { HITL_API_TARGET: "http://127.0.0.1:8001" },
    },
  ],
});

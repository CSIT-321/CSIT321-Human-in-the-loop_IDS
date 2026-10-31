/**
 * The S16 demo narrative, driven through a real browser against the real API.
 *
 *     npm run e2e
 *
 * Two servers are started and stopped for the run: a freshly seeded, disposable synthetic S16
 * database on :8001 (scripts/serve_s16_rehearsal.py), and Vite on :5174. No demo history is copied.
 *
 * HITL_PYTHON selects the interpreter (default "python"); the project's suite runs on Python 3.11.
 */

import { defineConfig, devices } from "@playwright/test";

const python = process.env.HITL_PYTHON ?? "python";
const apiPort = process.env.HITL_E2E_API_PORT ?? "8001";
const webPort = process.env.HITL_E2E_WEB_PORT ?? "5174";

export default defineConfig({
  testDir: "./e2e",
  testMatch: ["demo.spec.ts", "capture-guide.spec.ts"],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: `"${python}" ../../scripts/serve_s16_rehearsal.py --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      // Surface the API's own log in the run output, so a 500 arrives with its traceback.
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { HITL_API_TARGET: `http://127.0.0.1:${apiPort}` },
    },
  ],
});

import base from "./playwright.config";
import path from "node:path";
const python = process.env.HITL_PYTHON ?? "python";
// SOC guide on Packet Replay: a temp copy of data/demo.db; the spec prepares the replay through the Admin UI.
// Needs hitl-ids/data/packet-replay/ (scripts/build_packet_replay.py). The full 160-step replay takes ~3 min.
export default {
  ...base,
  testDir: path.resolve("e2e"),
  testMatch: ["soc-packet.spec.ts"],
  timeout: 900_000,
  outputDir: path.resolve("test-results/soc-packet-artifacts"),
  use: { ...base.use, baseURL: "http://127.0.0.1:5190" },
  webServer: [
    { command: `"${python}" e2e/soc-packet-fixture.py`,
      url: "http://127.0.0.1:8040/api/health", timeout: 120000, reuseExistingServer: false },
    { command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5190 --strictPort`,
      url: "http://127.0.0.1:5190", timeout: 60000, reuseExistingServer: false,
      env: { HITL_API_TARGET: "http://127.0.0.1:8040" } },
  ],
};

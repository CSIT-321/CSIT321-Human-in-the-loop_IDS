import base from "./playwright.config";
import path from "node:path";
const python=process.env.HITL_PYTHON??"python";
export default {
  ...base,
  timeout:180000,
  testDir:path.resolve("e2e"),
  testMatch:["prospective-collection.spec.ts","prospective-override.spec.ts"],
  outputDir:process.env.HITL_E2E_OUTPUT??path.resolve("test-results/prospective-browser-artifacts"),
  use:{...base.use,baseURL:"http://127.0.0.1:5190"},
  webServer:[
    {command:`"${python}" ../../scripts/serve_routing_rehearsal.py --pristine --port 8012 --prospective`,url:"http://127.0.0.1:8012/api/health",timeout:60000,reuseExistingServer:false},
    {command:`"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5190 --strictPort`,url:"http://127.0.0.1:5190",timeout:60000,reuseExistingServer:false,env:{HITL_API_TARGET:"http://127.0.0.1:8012"}},
  ],
};

import base from "./playwright.pre-freeze.config";
const python=process.env.HITL_PYTHON??"python";
const apiPort=process.env.HITL_VERDICT_MEMORY_API_PORT??"8018";
const webPort=process.env.HITL_VERDICT_MEMORY_WEB_PORT??"5188";
export default { ...base,testMatch:["verdict-memory.spec.ts"],outputDir:"test-results/verdict-memory-artifacts",
  use:{...base.use,baseURL:`http://127.0.0.1:${webPort}`},
  webServer:[
    {...base.webServer[0],command:`"${python}" e2e/verdict-memory-fixture.py`,url:`http://127.0.0.1:${apiPort}/api/health`},
    {...base.webServer[1],command:base.webServer[1].command.replace("5187",webPort),url:`http://127.0.0.1:${webPort}`,env:{HITL_API_TARGET:`http://127.0.0.1:${apiPort}`}},
  ],
};

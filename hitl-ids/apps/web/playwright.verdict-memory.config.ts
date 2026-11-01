import base from "./playwright.pre-freeze.config";
const python=process.env.HITL_PYTHON??"python";
export default { ...base,testMatch:["verdict-memory.spec.ts"],outputDir:"test-results/verdict-memory-artifacts",
  use:{...base.use,baseURL:"http://127.0.0.1:5188"},
  webServer:[
    {...base.webServer[0],command:`"${python}" e2e/verdict-memory-fixture.py`,url:"http://127.0.0.1:8018/api/health"},
    {...base.webServer[1],command:base.webServer[1].command.replace("5187","5188"),url:"http://127.0.0.1:5188",env:{HITL_API_TARGET:"http://127.0.0.1:8018"}},
  ],
};

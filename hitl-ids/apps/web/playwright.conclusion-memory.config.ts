import base from "./playwright.reclassification.config";
const python=process.env.HITL_PYTHON??"python";
export default {...base,testMatch:["conclusion-memory.spec.ts"],outputDir:"test-results/conclusion-memory-artifacts",
 use:{...base.use,baseURL:"http://127.0.0.1:5192"},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/conclusion-memory-fixture.py`,url:"http://127.0.0.1:8022/api/health"},
  {...base.webServer[1],command:base.webServer[1].command.replace("5190","5192"),url:"http://127.0.0.1:5192",env:{HITL_API_TARGET:"http://127.0.0.1:8022"}}
 ]};

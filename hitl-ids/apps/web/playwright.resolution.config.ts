import base from "./playwright.reclassification.config";
const python=process.env.HITL_PYTHON??"python";
export default {...base,testMatch:["case-resolution.spec.ts"],outputDir:"test-results/resolution-artifacts",
 use:{...base.use,baseURL:"http://127.0.0.1:5193"},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/pre-freeze-fixture.py --port 8023`,url:"http://127.0.0.1:8023/api/health"},
  {...base.webServer[1],command:base.webServer[1].command.replace("5190","5193"),url:"http://127.0.0.1:5193",env:{HITL_API_TARGET:"http://127.0.0.1:8023"}}
 ]};

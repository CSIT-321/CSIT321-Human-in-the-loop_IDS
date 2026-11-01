import base from "./playwright.pre-freeze.config";
const python=process.env.HITL_PYTHON??"python";
export default {...base,testMatch:["canonical-verdict-review-safety.spec.ts"],outputDir:"test-results/verdict-safety",
 use:{...base.use,baseURL:"http://127.0.0.1:5194"},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/pre-freeze-fixture.py --port 8024`,url:"http://127.0.0.1:8024/api/health"},
  {...base.webServer[1],command:base.webServer[1].command.replace("5187","5194"),url:"http://127.0.0.1:5194",env:{HITL_API_TARGET:"http://127.0.0.1:8024"}}
 ]};

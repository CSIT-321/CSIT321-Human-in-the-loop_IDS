import base from "./playwright.pre-freeze.config";
const python=process.env.HITL_PYTHON??"python";
export default {...base,testMatch:["automatic-learning.spec.ts"],outputDir:"test-results/automatic-learning",
 use:{...base.use,baseURL:"http://127.0.0.1:5195"},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/automatic-learning-fixture.py --port 8025`,url:"http://127.0.0.1:8025/api/health"},
  {...base.webServer[1],command:base.webServer[1].command.replace("5187","5195"),url:"http://127.0.0.1:5195",env:{HITL_API_TARGET:"http://127.0.0.1:8025"}}
 ]};

import base from './playwright.pre-freeze.config';
const apiPort=process.env.HITL_WORK_API_PORT??'8032';
const webPort=process.env.HITL_WORK_WEB_PORT??'5202';
const python=process.env.HITL_PYTHON??'python';
export default {...base,testMatch:['shared-work.spec.ts'],outputDir:'test-results/shared-work',
 use:{...base.use,baseURL:`http://127.0.0.1:${webPort}`},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/shared-work-fixture.py`,url:`http://127.0.0.1:${apiPort}/api/health`},
  {...base.webServer[1],command:base.webServer[1].command.replace('5187',webPort),url:`http://127.0.0.1:${webPort}`,env:{HITL_API_TARGET:`http://127.0.0.1:${apiPort}`}}
 ]};

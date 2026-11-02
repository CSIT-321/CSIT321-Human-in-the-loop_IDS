import base from './playwright.pre-freeze.config';
const python=process.env.HITL_PYTHON??'python';
export default {...base,testMatch:['shared-work.spec.ts'],outputDir:'test-results/shared-work',
 use:{...base.use,baseURL:'http://127.0.0.1:5202'},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/shared-work-fixture.py`,url:'http://127.0.0.1:8032/api/health'},
  {...base.webServer[1],command:base.webServer[1].command.replace('5187','5202'),url:'http://127.0.0.1:5202',env:{HITL_API_TARGET:'http://127.0.0.1:8032'}}
 ]};

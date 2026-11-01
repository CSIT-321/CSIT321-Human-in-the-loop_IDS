import base from './playwright.pre-freeze.config';
const python=process.env.HITL_PYTHON??'python';
export default {...base,testMatch:['final-golden-path.spec.ts'],outputDir:'test-results/final-golden-path',
 use:{...base.use,baseURL:'http://127.0.0.1:5200'},
 webServer:[
  {...base.webServer[0],command:`"${python}" e2e/final-golden-path-fixture.py`,url:'http://127.0.0.1:8030/api/health'},
  {...base.webServer[1],command:base.webServer[1].command.replace('5187','5200'),url:'http://127.0.0.1:5200',env:{HITL_API_TARGET:'http://127.0.0.1:8030'}}
 ]};

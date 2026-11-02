import base from './playwright.routing.config';
const python = process.env.HITL_PYTHON ?? 'python';
const directory = process.env.HITL_REAL_SURICATA_DIR;
if (!directory) throw new Error('HITL_REAL_SURICATA_DIR must name the actual detector validation directory');
export default {
  ...base, testMatch: ['real-suricata.spec.ts'], outputDir: 'test-results/real-suricata',
  use: {...base.use, baseURL: 'http://127.0.0.1:5201'},
  webServer: [
    {...base.webServer[0], command: `"${python}" ../../scripts/validate_real_suricata.py serve --directory "${directory}" --port 8031`, url: 'http://127.0.0.1:8031/api/health'},
    {...base.webServer[1], command: base.webServer[1].command.replace('5175','5201'), url: 'http://127.0.0.1:5201', env: {HITL_API_TARGET: 'http://127.0.0.1:8031'}},
  ],
};

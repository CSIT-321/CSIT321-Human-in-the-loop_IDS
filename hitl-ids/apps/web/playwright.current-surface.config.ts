import base from './playwright.shared-work.config';
export default { ...base, testMatch: ['shared-work.spec.ts', 'current-surface.spec.ts'], outputDir: 'test-results/current-surface' };

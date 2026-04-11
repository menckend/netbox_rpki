const path = require('path');
const { defineConfig, devices } = require('@playwright/test');

const authFile = path.join(__dirname, 'tests/e2e/.auth/admin.json');

module.exports = defineConfig({
  testDir: path.join(__dirname, 'tests/e2e'),
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.NETBOX_E2E_BASE_URL || 'http://127.0.0.1:8000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.js$/,
      use: {
        storageState: undefined,
      },
    },
    {
      name: 'chromium',
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.js$/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: authFile,
      },
    },
  ],
});
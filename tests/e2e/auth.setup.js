const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const { AUTH_STATE_FILE, prepareRuntimeState } = require('./helpers/runtime');

test('prepare fixtures and authenticate the local admin user', async ({ page }) => {
  const runtime = prepareRuntimeState();

  fs.mkdirSync(path.dirname(AUTH_STATE_FILE), { recursive: true });

  await page.goto('/login/');
  await page.locator('input[name="username"]').fill(runtime.username);
  await page.locator('input[name="password"]').fill(runtime.password);
  await page.locator('button[type="submit"]').click();

  await expect(page).toHaveURL(/\/$/);
  await page.context().storageState({ path: AUTH_STATE_FILE });
});
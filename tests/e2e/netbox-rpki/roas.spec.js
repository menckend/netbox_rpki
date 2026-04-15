const { test, expect } = require('@playwright/test');

const {
  PATHS,
  createCertificateFromOrganization,
  createOrganization,
  createRoaObject,
  deleteCurrentObject,
  fillText,
  relativeChildPath,
  submitSave,
} = require('../helpers/netbox-rpki');

test('roa object CRUD works through the plugin web UI', async ({ page }) => {
  const organization = await createOrganization(page);
  await createCertificateFromOrganization(page, organization);
  const roa = await createRoaObject(page, organization);
  const updatedName = `${roa.name} Updated`;

  await expect(page.locator('body')).toContainText('Prefixes Included in this ROA Object');
  await expect(page.locator('.attr-table')).toContainText(/Jan\.? 1, 2026/);
  await expect(page.locator('.attr-table')).toContainText(/Dec\.? 31, 2026/);

  await page.goto(relativeChildPath(roa.detailPath, 'edit/'));
  await fillText(page, 'name', updatedName);
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(updatedName);

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.roaObjects}$`));
  await expect(page.locator('table tbody')).not.toContainText(updatedName);
});

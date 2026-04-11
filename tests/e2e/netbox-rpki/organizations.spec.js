const { test, expect } = require('@playwright/test');

const {
  PATHS,
  createOrganization,
  deleteCurrentObject,
  fillText,
  relativeChildPath,
  submitSave,
} = require('../helpers/netbox-rpki');

test('organization CRUD works through the plugin web UI', async ({ page }) => {
  const organization = await createOrganization(page);
  const updatedName = `${organization.name} Updated`;

  await page.goto(relativeChildPath(organization.detailPath, 'edit/'));
  await fillText(page, 'name', updatedName);
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(updatedName);

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.organizations}$`));
  await expect(page.locator('table tbody')).not.toContainText(updatedName);
});
const { test, expect } = require('@playwright/test');

const {
  PATHS,
  createCertificateFromOrganization,
  createOrganization,
  deleteCurrentObject,
  fillText,
  relativeChildPath,
  submitSave,
} = require('../helpers/netbox-rpki');

test('certificate CRUD works through the plugin web UI', async ({ page }) => {
  const organization = await createOrganization(page);
  const certificate = await createCertificateFromOrganization(page, organization);
  const updatedIssuer = `${certificate.issuer} Updated`;

  await expect(page.locator('body')).toContainText('Attested IP Netblock Resources');
  await expect(page.locator('body')).toContainText('Attested ASN Resource');
  await expect(page.locator('body')).toContainText('ROAs');

  await page.goto(relativeChildPath(certificate.detailPath, 'edit/'));
  await fillText(page, 'issuer', updatedIssuer);
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(updatedIssuer);

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.certificates}$`));
  await expect(page.locator('table tbody')).not.toContainText(certificate.name);
});
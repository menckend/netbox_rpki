const { test, expect } = require('@playwright/test');

const {
  PATHS,
  createCertificateAsnFromCertificate,
  createCertificateFromOrganization,
  createCertificatePrefixFromCertificate,
  createOrganization,
  createRoaFromCertificate,
  createRoaPrefixFromRoa,
  deleteCurrentObject,
  fillText,
  relativeChildPath,
  runtimeFixtures,
  selectValue,
  submitSave,
} = require('../helpers/netbox-rpki');

test('certificate prefix CRUD works through the hidden relation UI', async ({ page }) => {
  const fixtures = runtimeFixtures();
  const organization = await createOrganization(page);
  const certificate = await createCertificateFromOrganization(page, organization);
  const certificatePrefix = await createCertificatePrefixFromCertificate(page, certificate);

  await expect(page.locator('.attr-table')).toContainText(fixtures.prefixes.primary.label);
  await expect(page.locator('.attr-table')).toContainText(certificate.name);

  await page.goto(relativeChildPath(certificatePrefix.detailPath, 'edit/'));
  await selectValue(page, 'prefix', fixtures.prefixes.secondary.id);
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(fixtures.prefixes.secondary.label);

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.certificatePrefixes}$`));
  await expect(page.locator('table tbody')).not.toContainText(fixtures.prefixes.secondary.label);
});

test('certificate ASN CRUD works through the hidden relation UI', async ({ page }) => {
  const fixtures = runtimeFixtures();
  const organization = await createOrganization(page);
  const certificate = await createCertificateFromOrganization(page, organization);
  const certificateAsn = await createCertificateAsnFromCertificate(page, certificate);

  await expect(page.locator('.attr-table')).toContainText(fixtures.asns.primary.label);
  await expect(page.locator('.attr-table')).toContainText(certificate.name);

  await page.goto(relativeChildPath(certificateAsn.detailPath, 'edit/'));
  await selectValue(page, 'asn', fixtures.asns.secondary.id);
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(fixtures.asns.secondary.label);

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.certificateAsns}$`));
  await expect(page.locator('table tbody')).not.toContainText(fixtures.asns.secondary.label);
});

test('roa prefix CRUD works through the hidden relation UI', async ({ page }) => {
  const fixtures = runtimeFixtures();
  const organization = await createOrganization(page);
  const certificate = await createCertificateFromOrganization(page, organization);
  const roa = await createRoaFromCertificate(page, certificate);
  const roaPrefix = await createRoaPrefixFromRoa(page, roa);

  await expect(page.locator('.attr-table')).toContainText(fixtures.prefixes.primary.label);
  await expect(page.locator('.attr-table')).toContainText(roa.name);

  await page.goto(relativeChildPath(roaPrefix.detailPath, 'edit/'));
  await selectValue(page, 'prefix', fixtures.prefixes.secondary.id);
  await fillText(page, 'max_length', '25');
  await submitSave(page);

  await expect(page.locator('.attr-table')).toContainText(fixtures.prefixes.secondary.label);
  await expect(page.locator('.attr-table')).toContainText('25');

  await deleteCurrentObject(page);
  await expect(page).toHaveURL(new RegExp(`${PATHS.roaPrefixes}$`));
  await expect(page.locator('table tbody')).not.toContainText(fixtures.prefixes.secondary.label);
});
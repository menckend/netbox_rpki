const { expect } = require('@playwright/test');

const { readRuntimeState } = require('./runtime');

const PATHS = {
  certificateAsns: '/plugins/netbox_rpki/certificateasns/',
  certificatePrefixes: '/plugins/netbox_rpki/certificateprefixes/',
  certificates: '/plugins/netbox_rpki/certificate/',
  organizations: '/plugins/netbox_rpki/orgs/',
  roaPrefixes: '/plugins/netbox_rpki/roaprefixes/',
  roas: '/plugins/netbox_rpki/roa/',
};

function runtimeFixtures() {
  return readRuntimeState().fixtures;
}

function objectIdFromUrl(page) {
  const match = new URL(page.url()).pathname.match(/\/(\d+)\/$/);
  if (!match) {
    throw new Error(`Unable to parse object ID from URL: ${page.url()}`);
  }
  return match[1];
}

function relativeChildPath(detailPath, childPath) {
  return new URL(childPath, `http://127.0.0.1${detailPath}`).pathname;
}

function uniqueLabel(prefix) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

function e2eComment(label) {
  return `${runtimeFixtures().marker_prefix}: ${label}`;
}

async function fillText(page, name, value) {
  await page.locator(`[name="${name}"]`).fill(value);
}

async function setCheckbox(page, name, checked) {
  const checkbox = page.locator(`input[type="checkbox"][name="${name}"]`);
  if (checked) {
    await checkbox.check();
  } else {
    await checkbox.uncheck();
  }
}

async function selectValue(page, name, value) {
  await page.locator(`select[name="${name}"]`).selectOption(String(value));
}

async function submitCreate(page) {
  await page.getByRole('button', { exact: true, name: 'Create' }).evaluate((button) => {
    button.form.requestSubmit(button);
  });
}

async function submitSave(page) {
  await page.getByRole('button', { exact: true, name: 'Save' }).evaluate((button) => {
    button.form.requestSubmit(button);
  });
}

async function deleteCurrentObject(page) {
  const deletePath = relativeChildPath(new URL(page.url()).pathname, 'delete/');
  await page.goto(deletePath);
  await page.getByRole('button', { exact: true, name: 'Delete' }).evaluate((button) => {
    button.form.requestSubmit(button);
  });
}

async function createOrganization(page, overrides = {}) {
  const token = uniqueLabel('org');
  const organization = {
    comment: e2eComment(`organization ${token}`),
    detailPath: null,
    extUrl: `https://example.invalid/${token}`,
    id: null,
    name: `Playwright Organization ${token}`,
    orgId: `pw-${token}`,
    ...overrides,
  };

  await page.goto(`${PATHS.organizations}add/`);
  await fillText(page, 'org_id', organization.orgId);
  await fillText(page, 'name', organization.name);
  await fillText(page, 'ext_url', organization.extUrl);
  await fillText(page, 'comments', organization.comment);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/orgs\/\d+\/$/);
  organization.id = objectIdFromUrl(page);
  organization.detailPath = new URL(page.url()).pathname;
  await expect(page.locator('.attr-table')).toContainText(organization.name);

  return organization;
}

async function createCertificateFromOrganization(page, organization, overrides = {}) {
  const token = uniqueLabel('cert');
  const certificate = {
    comment: e2eComment(`certificate ${token}`),
    detailPath: null,
    id: null,
    issuer: `Playwright Issuer ${token}`,
    name: `Playwright Certificate ${token}`,
    selfHosted: true,
    serial: `SERIAL-${token}`,
    subject: `CN=${token}`,
    ...overrides,
  };

  await page.goto(organization.detailPath);
  await page.locator(`a[href="${PATHS.certificates}add/?rpki_org=${organization.id}"]`).click();
  await expect(page.locator('select[name="rpki_org"]')).toHaveValue(String(organization.id));

  await fillText(page, 'name', certificate.name);
  await fillText(page, 'issuer', certificate.issuer);
  await fillText(page, 'subject', certificate.subject);
  await fillText(page, 'serial', certificate.serial);
  await fillText(page, 'comments', certificate.comment);
  await setCheckbox(page, 'auto_renews', true);
  await setCheckbox(page, 'self_hosted', certificate.selfHosted);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/certificate\/\d+\/$/);
  certificate.id = objectIdFromUrl(page);
  certificate.detailPath = new URL(page.url()).pathname;
  await expect(page.locator('.attr-table')).toContainText(certificate.name);

  return certificate;
}

async function createRoaFromCertificate(page, certificate, overrides = {}) {
  const fixtures = runtimeFixtures();
  const token = uniqueLabel('roa');
  const roa = {
    comment: e2eComment(`roa ${token}`),
    detailPath: null,
    id: null,
    name: `Playwright ROA ${token}`,
    originAsId: fixtures.asns.primary.id,
    validFrom: '2026-01-01',
    validTo: '2026-12-31',
    ...overrides,
  };

  await page.goto(certificate.detailPath);
  await page.locator(`a[href="${PATHS.roas}add/?signed_by=${certificate.id}"]`).click();
  await expect(page.locator('select[name="signed_by"]')).toHaveValue(String(certificate.id));

  await fillText(page, 'name', roa.name);
  await selectValue(page, 'origin_as', roa.originAsId);
  await fillText(page, 'valid_from', roa.validFrom);
  await fillText(page, 'valid_to', roa.validTo);
  await fillText(page, 'comments', roa.comment);
  await setCheckbox(page, 'auto_renews', true);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/roa\/\d+\/$/);
  roa.id = objectIdFromUrl(page);
  roa.detailPath = new URL(page.url()).pathname;
  await expect(page.locator('.attr-table')).toContainText(roa.name);

  return roa;
}

async function createCertificatePrefixFromCertificate(page, certificate, overrides = {}) {
  const fixtures = runtimeFixtures();
  const certificatePrefix = {
    comment: e2eComment('certificate prefix'),
    detailPath: null,
    id: null,
    prefixId: fixtures.prefixes.primary.id,
    prefixLabel: fixtures.prefixes.primary.label,
    ...overrides,
  };

  await page.goto(certificate.detailPath);
  await page.locator(`a[href="${PATHS.certificatePrefixes}add/?certificate_name=${certificate.id}"]`).click();
  await expect(page.locator('select[name="certificate_name"]')).toHaveValue(String(certificate.id));

  await selectValue(page, 'prefix', certificatePrefix.prefixId);
  await fillText(page, 'comments', certificatePrefix.comment);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/certificateprefixes\/\d+\/$/);
  certificatePrefix.id = objectIdFromUrl(page);
  certificatePrefix.detailPath = new URL(page.url()).pathname;

  return certificatePrefix;
}

async function createCertificateAsnFromCertificate(page, certificate, overrides = {}) {
  const fixtures = runtimeFixtures();
  const certificateAsn = {
    asnId: fixtures.asns.primary.id,
    asnLabel: fixtures.asns.primary.label,
    comment: e2eComment('certificate asn'),
    detailPath: null,
    id: null,
    ...overrides,
  };

  await page.goto(certificate.detailPath);
  await page.locator(`a[href="${PATHS.certificateAsns}add/?certificate_name2=${certificate.id}"]`).click();
  await expect(page.locator('select[name="certificate_name2"]')).toHaveValue(String(certificate.id));

  await selectValue(page, 'asn', certificateAsn.asnId);
  await fillText(page, 'comments', certificateAsn.comment);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/certificateasns\/\d+\/$/);
  certificateAsn.id = objectIdFromUrl(page);
  certificateAsn.detailPath = new URL(page.url()).pathname;

  return certificateAsn;
}

async function createRoaPrefixFromRoa(page, roa, overrides = {}) {
  const fixtures = runtimeFixtures();
  const roaPrefix = {
    comment: e2eComment('roa prefix'),
    detailPath: null,
    id: null,
    maxLength: '24',
    prefixId: fixtures.prefixes.primary.id,
    prefixLabel: fixtures.prefixes.primary.label,
    ...overrides,
  };

  await page.goto(roa.detailPath);
  await page.locator(`a[href="${PATHS.roaPrefixes}add/?roa_name=${roa.id}"]`).click();
  await expect(page.locator('select[name="roa_name"]')).toHaveValue(String(roa.id));

  await selectValue(page, 'prefix', roaPrefix.prefixId);
  await fillText(page, 'max_length', roaPrefix.maxLength);
  await fillText(page, 'comments', roaPrefix.comment);
  await submitCreate(page);

  await expect(page).toHaveURL(/\/plugins\/netbox_rpki\/roaprefixes\/\d+\/$/);
  roaPrefix.id = objectIdFromUrl(page);
  roaPrefix.detailPath = new URL(page.url()).pathname;

  return roaPrefix;
}

module.exports = {
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
};
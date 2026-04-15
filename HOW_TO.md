# NetBox RPKI Task-Sized Use Cases

Prepared: April 15, 2026

## Purpose

This document reframes the prior broad workflow list as task-sized use cases. Each use case is intended to be narrow enough that it can later be documented as a single step-wise procedure with limited branching.

Status labels:

- `Current`: Supported directly by the implemented feature set or clearly aligned with existing workflows.
- `Near-term`: Reasonable extension of implemented models, services, or reporting already present in the repository.
- `Hypothetical`: Product-direction task that fits the architecture but is not clearly implemented today.

## Table Of Contents

### Organization And Certificate Inventory

1. [Create an organization record for a managed RPKI customer](#create-an-organization-record-for-a-managed-rpki-customer)
2. [Record a resource certificate for an organization](#record-a-resource-certificate-for-an-organization)
3. [Attach prefix resources to a resource certificate](#attach-prefix-resources-to-a-resource-certificate)
4. [Attach ASN resources to a resource certificate](#attach-asn-resources-to-a-resource-certificate)
5. [Link a resource certificate to a trust anchor record](#link-a-resource-certificate-to-a-trust-anchor-record)
6. [Record a publication point used by a resource certificate](#record-a-publication-point-used-by-a-resource-certificate)
7. [Review certificates for an organization that are approaching expiry](#review-certificates-for-an-organization-that-are-approaching-expiry)
8. [Record a replacement certificate during rollover preparation](#record-a-replacement-certificate-during-rollover-preparation)

### Local ROA Data Management

9. [Create a local ROA record for a single origin ASN](#create-a-local-roa-record-for-a-single-origin-asn)
10. [Add a prefix authorization to an existing local ROA](#add-a-prefix-authorization-to-an-existing-local-roa)
11. [Edit max length on an existing ROA prefix authorization](#edit-max-length-on-an-existing-roa-prefix-authorization)
12. [Remove a prefix authorization from an existing local ROA](#remove-a-prefix-authorization-from-an-existing-local-roa)
13. [Retire a local ROA that is no longer intended](#retire-a-local-roa-that-is-no-longer-intended)
14. [Import latest ROAs from a managed provider account](#import-latest-roas-from-a-managed-provider-account)
15. [Review imported provider ROAs that are missing local ownership in NetBox](#review-imported-provider-roas-that-are-missing-local-ownership-in-netbox)
16. [Promote an imported provider ROA into a local ROA source-of-truth record](#promote-an-imported-provider-roa-into-a-local-roa-source-of-truth-record)

### Routing Intent Authoring

17. [Create a routing intent profile for one organization](#create-a-routing-intent-profile-for-one-organization)
18. [Add a routing intent rule to include candidate prefixes](#add-a-routing-intent-rule-to-include-candidate-prefixes)
19. [Add a routing intent rule to exclude a prefix from publication](#add-a-routing-intent-rule-to-exclude-a-prefix-from-publication)
20. [Add a ROA intent override for one prefix](#add-a-roa-intent-override-for-one-prefix)
21. [Bind a routing intent template to an organization](#bind-a-routing-intent-template-to-an-organization)
22. [Regenerate derived ROA intent for one organization](#regenerate-derived-roa-intent-for-one-organization)
23. [Preview the output of a template binding before applying it](#preview-the-output-of-a-template-binding-before-applying-it)
24. [Compare derived intent after a policy change against the last run](#compare-derived-intent-after-a-policy-change-against-the-last-run)

### Reconciliation And Exception Handling

25. [Run ROA reconciliation against local ROA records](#run-roa-reconciliation-against-local-roa-records)
26. [Run ROA reconciliation against imported provider state](#run-roa-reconciliation-against-imported-provider-state)
27. [Review intents marked as replacement required in a reconciliation run](#review-intents-marked-as-replacement-required-in-a-reconciliation-run)
28. [Review published ROAs marked as orphaned in a reconciliation run](#review-published-roas-marked-as-orphaned-in-a-reconciliation-run)
29. [Record an external management exception for a prefix managed outside NetBox](#record-an-external-management-exception-for-a-prefix-managed-outside-netbox)
30. [Review external management exceptions that are past their review date](#review-external-management-exceptions-that-are-past-their-review-date)
31. [Clear an external management exception after ownership returns to NetBox](#clear-an-external-management-exception-after-ownership-returns-to-netbox)
32. [Review reconciliation findings for one delegated entity or managed relationship](#review-reconciliation-findings-for-one-delegated-entity-or-managed-relationship)

### ROA Change Planning And Write-Back

33. [Create a draft ROA change plan from a reconciliation run](#create-a-draft-roa-change-plan-from-a-reconciliation-run)
34. [Review provider operations for a draft ROA change plan](#review-provider-operations-for-a-draft-roa-change-plan)
35. [Add approver notes to a ROA change plan before approval](#add-approver-notes-to-a-roa-change-plan-before-approval)
36. [Approve a draft ROA change plan as primary approver](#approve-a-draft-roa-change-plan-as-primary-approver)
37. [Approve a draft ROA change plan as secondary approver](#approve-a-draft-roa-change-plan-as-secondary-approver)
38. [Preview provider write payloads for an approved ROA change plan](#preview-provider-write-payloads-for-an-approved-roa-change-plan)
39. [Apply an approved ROA change plan to a hosted provider account](#apply-an-approved-roa-change-plan-to-a-hosted-provider-account)
40. [Roll back a completed ROA change plan using its rollback bundle](#roll-back-a-completed-roa-change-plan-using-its-rollback-bundle)

### Validation Simulation And Lint

41. [Run validation simulation for a draft ROA change plan](#run-validation-simulation-for-a-draft-roa-change-plan)
42. [Review simulated collateral impact before approving a ROA change plan](#review-simulated-collateral-impact-before-approving-a-roa-change-plan)
43. [Compare two draft ROA change plans by validation risk](#compare-two-draft-roa-change-plans-by-validation-risk)
44. [Run ROA lint for a reconciliation run](#run-roa-lint-for-a-reconciliation-run)
45. [Acknowledge a known ROA lint finding](#acknowledge-a-known-roa-lint-finding)
46. [Suppress a repeating ROA lint finding](#suppress-a-repeating-roa-lint-finding)
47. [Review change plan lint posture before provider write-back](#review-change-plan-lint-posture-before-provider-write-back)
48. [Block approval when a draft change plan increases critical lint findings](#block-approval-when-a-draft-change-plan-increases-critical-lint-findings)

### Provider Sync And Publication Health

49. [Sync a Krill provider account on demand](#sync-a-krill-provider-account-on-demand)
50. [Sync an ARIN provider account on demand](#sync-an-arin-provider-account-on-demand)
51. [Review the latest snapshot imported for a provider account](#review-the-latest-snapshot-imported-for-a-provider-account)
52. [Review the latest snapshot diff for unexpected ROA churn](#review-the-latest-snapshot-diff-for-unexpected-roa-churn)
53. [Review imported ASPA changes between two provider snapshots](#review-imported-aspa-changes-between-two-provider-snapshots)
54. [Review publication linkage gaps reported in provider evidence summaries](#review-publication-linkage-gaps-reported-in-provider-evidence-summaries)
55. [Evaluate lifecycle health for one provider account](#evaluate-lifecycle-health-for-one-provider-account)
56. [Export provider lifecycle or publication summary data for reporting](#export-provider-lifecycle-or-publication-summary-data-for-reporting)

### Validator Import And Overlay Analysis

57. [Import validated payloads from the Routinator live API](#import-validated-payloads-from-the-routinator-live-api)
58. [Import validated payloads from a Routinator snapshot file](#import-validated-payloads-from-a-routinator-snapshot-file)
59. [Review validated ROA payloads that do not map cleanly to local ROAs](#review-validated-roa-payloads-that-do-not-map-cleanly-to-local-roas)
60. [Compare provider-observed ROAs with validator-observed effective state](#compare-provider-observed-roas-with-validator-observed-effective-state)
61. [Review validator observations for one organization after a provider sync](#review-validator-observations-for-one-organization-after-a-provider-sync)
62. [Identify published objects that are missing from validator output](#identify-published-objects-that-are-missing-from-validator-output)
63. [Build a mismatch review queue from overlay reporting outputs](#build-a-mismatch-review-queue-from-overlay-reporting-outputs)
64. [Review validator run history for a single validator instance](#review-validator-run-history-for-a-single-validator-instance)

### Delegated Authorization Workflows

65. [Create a delegated authorization entity](#create-a-delegated-authorization-entity)
66. [Create a managed authorization relationship for a delegated entity](#create-a-managed-authorization-relationship-for-a-delegated-entity)
67. [Create a delegated publication workflow for a managed relationship](#create-a-delegated-publication-workflow-for-a-managed-relationship)
68. [Populate publication endpoint and child CA handle for a delegated workflow](#populate-publication-endpoint-and-child-ca-handle-for-a-delegated-workflow)
69. [Approve a delegated publication workflow that requires approval](#approve-a-delegated-publication-workflow-that-requires-approval)
70. [Review delegated workflows that are missing prerequisites](#review-delegated-workflows-that-are-missing-prerequisites)
71. [Link authored CA relationship data to a delegated publication workflow](#link-authored-ca-relationship-data-to-a-delegated-publication-workflow)
72. [Review delegated workflows awaiting approval for one organization](#review-delegated-workflows-awaiting-approval-for-one-organization)

### ASPA Management Tasks

73. [Create a local ASPA record for a customer ASN](#create-a-local-aspa-record-for-a-customer-asn)
74. [Add provider ASNs to an ASPA record](#add-provider-asns-to-an-aspa-record)
75. [Reconcile ASPA intent against published or imported ASPA state](#reconcile-aspa-intent-against-published-or-imported-aspa-state)
76. [Create a draft ASPA change plan from reconciliation results](#create-a-draft-aspa-change-plan-from-reconciliation-results)
77. [Approve a draft ASPA change plan as primary approver](#approve-a-draft-aspa-change-plan-as-primary-approver)
78. [Approve a draft ASPA change plan as secondary approver](#approve-a-draft-aspa-change-plan-as-secondary-approver)
79. [Apply an approved ASPA change plan to a hosted provider account](#apply-an-approved-aspa-change-plan-to-a-hosted-provider-account)
80. [Roll back a completed ASPA change plan using its rollback bundle](#roll-back-a-completed-aspa-change-plan-using-its-rollback-bundle)

### IRR And BGP Telemetry Tasks

81. [Import an IRR snapshot from a configured source](#import-an-irr-snapshot-from-a-configured-source)
82. [Run IRR coordination for one organization](#run-irr-coordination-for-one-organization)
83. [Review IRR objects that diverge from derived RPKI intent](#review-irr-objects-that-diverge-from-derived-rpki-intent)
84. [Create an IRR change plan from coordination findings](#create-an-irr-change-plan-from-coordination-findings)
85. [Preview the write set for an IRR change plan before execution](#preview-the-write-set-for-an-irr-change-plan-before-execution)
86. [Apply an IRR change plan to the target integration](#apply-an-irr-change-plan-to-the-target-integration)
87. [Import a BGP telemetry snapshot from MRT data](#import-a-bgp-telemetry-snapshot-from-mrt-data)
88. [Review telemetry observations for prefixes affected by a pending ROA change](#review-telemetry-observations-for-prefixes-affected-by-a-pending-roa-change)

### Signed Object And Lifecycle Analysis

89. [Review the signed-object record linked to a local ROA or ASPA](#review-the-signed-object-record-linked-to-a-local-roa-or-aspa)
90. [Review manifest entries associated with a signed object](#review-manifest-entries-associated-with-a-signed-object)
91. [Review revoked certificate references published in a CRL](#review-revoked-certificate-references-published-in-a-crl)
92. [Identify signed objects that share a publication point failure domain](#identify-signed-objects-that-share-a-publication-point-failure-domain)
93. [Review certificates approaching expiry that could affect published objects](#review-certificates-approaching-expiry-that-could-affect-published-objects)
94. [Model the effect of revoking a resource certificate on effective publication policy](#model-the-effect-of-revoking-a-resource-certificate-on-effective-publication-policy)
95. [Model the effect of revoking an EE certificate on dependent signed objects](#model-the-effect-of-revoking-an-ee-certificate-on-dependent-signed-objects)
96. [Review organization governance summary for approvals, rollbacks, and delegated workflows](#review-organization-governance-summary-for-approvals-rollbacks-and-delegated-workflows)

## Task Sections

### Create an organization record for a managed RPKI customer

#### Description

Creates an `Organization` record that represents one managed RPKI customer or other ownership scope inside the plugin.

#### Inputs

- Required: `org_id`, the organization's external or operator-assigned identifier
- Required: `name`, the display name for the organization
- Optional: `parent_rir`, the parent Regional Internet Registry record
- Optional: `ext_url`, an external reference URL for the organization
- Optional: `tenant`, the related NetBox tenant, if used in the deployment
- Optional: `comments`, freeform notes
- Optional: `tags`, NetBox tags

#### Procedures

##### Using Web UI

1. In the plugin navigation, open `Resources` -> `RIR Customer Orgs`.
2. Click `Add`.
3. Enter a value in `Organization ID` (`org_id`).
4. Enter the organization `Name`.
5. Optionally select `Parent Regional Internet Registry`.
6. Optionally enter `External URL`, `Tenant`, `Comments`, or `Tags`.
7. Save the record.

Notes:

- The E2E UI path for the add form is `/plugins/netbox_rpki/orgs/add/`.
- The create form fields are defined as `org_id`, `name`, `parent_rir`, `ext_url`, `tenant`, `comments`, and `tags`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/organization/`

Example request body:

```json
{
	"org_id": "cust-001",
	"name": "Customer 001",
	"ext_url": "https://example.invalid/customers/cust-001"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new organization record is created and stored in the plugin.
- In the GUI flow, the user lands on the organization detail page under the `RIR Customer Orgs` area.
- In the API flow, the response returns the created object, including its `id`, `url`, `org_id`, `name`, `parent_rir`, `ext_url`, and governance roll-up data.
- The new organization becomes available for later tasks such as recording certificates, running organization-scoped bulk intent, or running organization-scoped ASPA reconciliation.

---
### Record a resource certificate for an organization

#### Description

Creates a `Certificate` record for an existing organization and captures the certificate fields the plugin uses for inventory, lifecycle, and signed-object linkage.

#### Inputs

- Required: `name`, the certificate record name
- Required: `rpki_org`, the owning organization
- Required: `auto_renews`, whether the certificate is expected to renew automatically
- Required: `self_hosted`, whether the certificate is self-hosted
- Optional: `issuer`, `subject`, `serial`
- Optional: `valid_from`, `valid_to`
- Optional: `public_key`, `private_key`
- Optional: `publication_url`, `ca_repository`
- Optional: `trust_anchor`, `publication_point`
- Optional: `tenant`, `comments`, `tags`

#### Procedures

##### Using Web UI

1. Open the target organization detail page.
2. Click the `RPKI Certificate` action on that organization.
3. Confirm that the organization field is prefilled.
4. Enter the certificate `Name`.
5. Set `Auto Renews` and `Self Hosted`.
6. Optionally fill the remaining lifecycle, identity, publication, and linkage fields.
7. Save the record.

Notes:

- The add form is available at `/plugins/netbox_rpki/certificate/add/`.
- The organization detail view exposes a prefilled add link of the form `certificate/add/?rpki_org=<organization_id>`.
- The certificate form fields are `name`, `issuer`, `subject`, `serial`, `valid_from`, `valid_to`, `auto_renews`, `public_key`, `private_key`, `publication_url`, `ca_repository`, `rpki_org`, `trust_anchor`, `publication_point`, `self_hosted`, `tenant`, `comments`, and `tags`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/certificate/`

Example request body:

```json
{
	"name": "Customer 001 Certificate A",
	"issuer": "Issuer A",
	"rpki_org": 1,
	"auto_renews": true,
	"self_hosted": false,
	"valid_to": "2026-12-31"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new certificate record is created for the selected organization.
- The certificate appears on the organization detail page under `Certificates`.
- The certificate detail page can now be used for related tasks such as attaching certificate prefixes, attaching certificate ASNs, linking trust anchors, and linking publication points.

---
### Attach prefix resources to a resource certificate

#### Description

Creates a `CertificatePrefix` record that links one existing NetBox prefix to one existing resource certificate.

#### Inputs

- Required: `certificate_name`, the target certificate
- Required: `prefix`, the existing NetBox prefix to attest on the certificate
- Optional: `tenant`, `comments`, `tags`

#### Procedures

##### Using Web UI

1. Open the target certificate detail page.
2. Click the `Prefix` action.
3. Confirm that the certificate field is prefilled.
4. Select the target `Prefix`.
5. Optionally add `Comments` or `Tags`.
6. Save the record.

Notes:

- The add form is available at `/plugins/netbox_rpki/certificateprefixes/add/`.
- The certificate detail view exposes a prefilled add link of the form `certificateprefixes/add/?certificate_name=<certificate_id>`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/certificateprefix/`

Example request body:

```json
{
	"certificate_name": 10,
	"prefix": 25
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new certificate-prefix association is created.
- The prefix appears in the certificate detail page under `Attested IP Netblock Resources`.
- The certificate prefix record is available as its own detail object for later review or editing.

---
### Attach ASN resources to a resource certificate

#### Description

Creates a `CertificateAsn` record that links one existing ASN to one existing resource certificate.

#### Inputs

- Required: `certificate_name2`, the target certificate
- Required: `asn`, the ASN to attach
- Optional: `tenant`, `comments`, `tags`

#### Procedures

##### Using Web UI

1. Open the target certificate detail page.
2. Click the `ASN` action.
3. Confirm that the certificate field is prefilled.
4. Select the target `ASN`.
5. Optionally add `Comments` or `Tags`.
6. Save the record.

Notes:

- The add form is available at `/plugins/netbox_rpki/certificateasns/add/`.
- The certificate detail view exposes a prefilled add link of the form `certificateasns/add/?certificate_name2=<certificate_id>`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/certificateasn/`

Example request body:

```json
{
	"certificate_name2": 10,
	"asn": 44
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new certificate-ASN association is created.
- The ASN appears in the certificate detail page under `Attested ASN Resource`.
- The certificate ASN record is available as its own detail object for later review or editing.

---
### Link a resource certificate to a trust anchor record

#### Description

Updates an existing certificate so it points to an existing `TrustAnchor` record.

#### Inputs

- Required: the target certificate
- Required: the target trust anchor record
- Optional: any other certificate fields being updated during the same edit

#### Procedures

##### Using Web UI

1. Open the target certificate detail page.
2. Click `Edit`.
3. Select the desired `Trust Anchor`.
4. Save the certificate.

Notes:

- If the trust anchor does not yet exist, create it first under `Trust` -> `Trust Anchors`.
- Trust anchor records are exposed on the standard object path `/plugins/netbox_rpki/trustanchors/`.

##### Using REST API

- `PATCH /api/plugins/netbox-rpki/certificate/<certificate_id>/`

Example request body:

```json
{
	"trust_anchor": 2
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The certificate now references the selected trust anchor.
- The certificate detail page shows the trust anchor link instead of `None`.
- Downstream inventory and reporting surfaces can now follow the certificate-to-trust-anchor relationship.

---
### Record a publication point used by a resource certificate

#### Description

Updates an existing certificate so it points to an existing `PublicationPoint` record.

#### Inputs

- Required: the target certificate
- Required: the target publication point record
- Optional: any other certificate fields being updated during the same edit

#### Procedures

##### Using Web UI

1. Open the target certificate detail page.
2. Click `Edit`.
3. Select the desired `Publication Point`.
4. Save the certificate.

Notes:

- If the publication point does not yet exist, create it first under `Resources` -> `Publication Points`.
- Publication point records are exposed on the standard object path `/plugins/netbox_rpki/publicationpoints/`.

##### Using REST API

- `PATCH /api/plugins/netbox-rpki/certificate/<certificate_id>/`

Example request body:

```json
{
	"publication_point": 3
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The certificate now references the selected publication point.
- The certificate detail page shows the publication point link instead of `None`.
- Downstream inventory and reporting surfaces can now follow the certificate-to-publication-point relationship.

---
### Review certificates for an organization that are approaching expiry

#### Description

Reviews certificate records whose `valid_to` date falls within the effective lifecycle warning threshold.

#### Inputs

- Required: view access to certificates and the operations dashboard
- Optional: a target organization to focus the review

#### Procedures

##### Using Web UI

1. Open the Operations Dashboard.
2. Scroll to the `Certificates Nearing Expiry` card.
3. Review each listed certificate's name, organization, issuer, `Valid To` date, and status badge.
4. Open any certificate detail page that needs follow-up.

Notes:

- The dashboard route is `/plugins/netbox_rpki/operations/`.
- The dashboard only includes certificates that are within the effective lifecycle policy threshold for the owning organization.

##### Using REST API

- `GET /api/plugins/netbox-rpki/certificate/`
- Optional organization filter: `GET /api/plugins/netbox-rpki/certificate/?rpki_org=1`

Review the returned `valid_to` values against the lifecycle threshold used by your deployment.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The operator has a concrete list of certificates that need renewal, rollover preparation, or additional review.
- The dashboard or API review identifies which organization each certificate belongs to and when it expires.
- Follow-up tasks such as recording a replacement certificate can be scheduled from that review.

---
### Record a replacement certificate during rollover preparation

#### Description

Creates a second certificate record for the same organization so rollover preparation can be tracked explicitly in inventory.

#### Inputs

- Required: the owning organization
- Required: a new certificate name for the replacement certificate
- Required: `auto_renews` and `self_hosted`
- Optional: issuer, subject, serial, validity dates, trust anchor, publication point, comments, and tags

#### Procedures

##### Using Web UI

1. Open the owning organization detail page.
2. Click `RPKI Certificate`.
3. Enter the replacement certificate's identifying information and validity dates.
4. Set any trust anchor or publication point linkage that is already known.
5. Save the new certificate.

Notes:

- This repository does not expose a dedicated rollover wizard for certificate replacement.
- Rollover preparation is currently recorded by creating another certificate record through the normal certificate create flow.

##### Using REST API

- `POST /api/plugins/netbox-rpki/certificate/`

Example request body:

```json
{
	"name": "Customer 001 Certificate B",
	"rpki_org": 1,
	"valid_from": "2026-10-01",
	"valid_to": "2027-09-30",
	"auto_renews": true,
	"self_hosted": false
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new certificate record exists alongside the current certificate record.
- The organization now shows both certificates in its certificate table.
- Subsequent signed-object or publication tasks can reference the replacement certificate explicitly.

---
### Create a local ROA record for a single origin ASN

#### Description

Creates a `RoaObject` record for one organization and one origin ASN.

#### Inputs

- Required: `name`, the ROA object name
- Required: `organization`, the owning organization
- Required: `origin_as`, the origin ASN
- Optional: `valid_from`, `valid_to`
- Optional: `validation_state`
- Optional: `signed_object`
- Optional: `tenant`, `comments`, `tags`

#### Procedures

##### Using Web UI

1. Open `ROAs` -> `ROA Objects`.
2. Click `Add`.
3. Enter the ROA object `Name`.
4. Select the owning `Organization`.
5. Select the `Origination AS Number`.
6. Optionally enter `Valid From`, `Valid To`, `Validation State`, and `Signed Object`.
7. Save the record.

Notes:

- The add form is available at `/plugins/netbox_rpki/roaobject/add/`.
- The form fields are `name`, `organization`, `origin_as`, `valid_from`, `valid_to`, `validation_state`, `signed_object`, `tenant`, `comments`, and `tags`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roaobject/`

Example request body:

```json
{
	"name": "Customer 001 ROA A",
	"organization": 1,
	"origin_as": 44,
	"validation_state": "unknown"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new ROA object record is created.
- The ROA object appears in the ROA object list and has its own detail page.
- The record is ready for prefix authorizations to be added in later tasks.

---
### Add a prefix authorization to an existing local ROA

#### Description

Creates a `RoaObjectPrefix` record that adds one authorized prefix and max length to an existing ROA object.

#### Inputs

- Required: `roa_object`, the target ROA object
- Required: `prefix`, the target prefix
- Required: `prefix_cidr_text`, the text form of the prefix if the UI or workflow uses it explicitly
- Required: `max_length`
- Optional: `is_current`
- Optional: `tenant`, `comments`, `tags`

#### Procedures

##### Using Web UI

1. Open the target ROA object detail page.
2. Click the `ROA Object Prefix` action.
3. Confirm that the ROA object field is prefilled.
4. Select the target `Prefix`.
5. Enter or confirm `Prefix CIDR`.
6. Enter `Maximum Prefix Length`.
7. Save the record.

Notes:

- The add form is available at `/plugins/netbox_rpki/roaobjectprefixes/add/`.
- The ROA object detail view exposes a prefilled add link of the form `roaobjectprefixes/add/?roa_object=<roa_object_id>`.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roaobjectprefix/`

Example request body:

```json
{
	"roa_object": 20,
	"prefix": 25,
	"prefix_cidr_text": "10.0.10.0/24",
	"max_length": 24,
	"is_current": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new ROA object prefix record is created.
- The prefix appears in the ROA object detail page under `Prefixes Included in this ROA Object`.
- The ROA object now has at least one concrete prefix authorization.

---
### Edit max length on an existing ROA prefix authorization

#### Description

Updates the `max_length` on an existing ROA object prefix record.

#### Inputs

- Required: the target ROA object prefix record
- Required: the new `max_length` value

#### Procedures

##### Using Web UI

1. Open the target ROA object prefix detail page.
2. Click `Edit`.
3. Replace `Maximum Prefix Length` with the new value.
4. Save the record.

Notes:

- ROA object prefix records are exposed at `/plugins/netbox_rpki/roaobjectprefixes/<id>/`.
- The edit view follows the standard path `/plugins/netbox_rpki/roaobjectprefixes/<id>/edit/`.

##### Using REST API

- `PATCH /api/plugins/netbox-rpki/roaobjectprefix/<roa_object_prefix_id>/`

Example request body:

```json
{
	"max_length": 25
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The ROA object prefix record stores the new `max_length` value.
- The ROA object detail page reflects the updated prefix authorization.
- Future reconciliation, validation, and publication tasks use the updated max-length value.

---
### Remove a prefix authorization from an existing local ROA

#### Description

Deletes one `RoaObjectPrefix` record from a local ROA.

#### Inputs

- Required: the target ROA object prefix record
- Required: confirmation that the authorization should be removed

#### Procedures

##### Using Web UI

1. Open the target ROA object prefix detail page.
2. Click `Delete`.
3. Confirm the removal.

##### Using REST API

- `DELETE /api/plugins/netbox-rpki/roaobjectprefix/<roa_object_prefix_id>/`

No request body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The prefix authorization is removed from the ROA object.
- The ROA object detail page no longer lists that authorization.

---
### Retire a local ROA that is no longer intended

#### Description

Deletes a `RoaObject` once its prefix authorizations are no longer needed.

#### Inputs

- Required: the target ROA object
- Required: any remaining prefix authorizations must be removed first

#### Procedures

##### Using Web UI

1. Open the target ROA object detail page.
2. Remove any remaining prefix authorizations.
3. Click `Delete` on the ROA object and confirm.

##### Using REST API

- `DELETE /api/plugins/netbox-rpki/roaobject/<roa_object_id>/`

No request body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The local ROA record is removed.
- Its prefix authorizations are no longer published from NetBox.

---
### Import latest ROAs from a managed provider account

#### Description

Queues a provider sync so NetBox imports the latest ROA snapshot and imported ROA authorizations for one provider account.

#### Inputs

- Required: the provider account
- Required: `sync_enabled` must be true

#### Procedures

##### Using Web UI

1. Open the provider account detail page.
2. Click `Sync`.
3. Confirm the sync request.

##### Using REST API

- `POST /api/plugins/netbox-rpki/rpkiprovideraccount/<provider_account_id>/sync/`

Use an empty request body; the action enqueues the background sync job and returns the provider account payload.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A provider sync job is queued or reused if one is already pending.
- A new provider snapshot is imported when the sync completes.
- The imported ROA authorization table for that snapshot is refreshed.

---
### Review imported provider ROAs that are missing local ownership in NetBox

#### Description

Reviews imported ROA authorization rows that do not yet have a matching local ROA record in NetBox.

This is currently a manual comparison workflow; the UI exposes imported ROA authorizations per provider snapshot, but there is no dedicated one-click missing-ownership queue yet.

#### Inputs

- Required: the provider snapshot or provider account to review
- Required: the imported ROA authorization rows for that snapshot

#### Procedures

##### Using Web UI

1. Open the provider snapshot detail page.
2. Review the `Imported ROA Authorizations` table.
3. Compare each imported prefix and origin ASN against local ROA objects for the same organization.

##### Using REST API

- `GET /api/plugins/netbox-rpki/importedroaauthorization/`

Filter by `provider_snapshot` to isolate one import, then compare `prefix`, `origin_asn`, and `max_length` against local ROA records.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Imported ROA rows with no matching local ROA are identified for follow-up.
- Any gaps can be turned into new local ROA records or tracked as exceptions.

---
### Promote an imported provider ROA into a local ROA source-of-truth record

#### Description

Copies an imported ROA authorization into a local `RoaObject` and `RoaObjectPrefix` pair.

This is currently a manual workflow; the repository does not provide a single promote action from an imported row into a local source-of-truth record.

#### Inputs

- Required: the imported ROA authorization row
- Required: the local organization that should own the ROA
- Required: the target prefix and max length

#### Procedures

##### Using Web UI

1. Open the imported ROA authorization and copy the prefix, origin ASN, and max length.
2. Create a new local ROA object for the owning organization.
3. Add a prefix authorization to that ROA object using the imported values.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roaobject/`
- `POST /api/plugins/netbox-rpki/roaobjectprefix/`

Create the local ROA first, then create the matching prefix authorization with the imported prefix and max length.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A local ROA record exists for the imported authorization.
- Future reconciliation can treat the local record as the source of truth.

---
### Create a routing intent profile for one organization

#### Description

Creates a `RoutingIntentProfile` that defines how one organization derives ROA intent.

#### Inputs

- Required: `name`
- Required: `organization`
- Optional: `status`, `description`, `selector_mode`, `prefix_selector_query`, `asn_selector_query`, `default_max_length_policy`, `context_groups`, `allow_as0`, `enabled`

#### Procedures

##### Using Web UI

1. Open `Intent` -> `Routing Intent Profiles`.
2. Click `Add`.
3. Enter the profile name and organization.
4. Set the selector and policy fields you need.
5. Save the profile.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentprofile/`

Example request body:

```json
{
	"name": "Customer 001 Intent",
	"organization": 1,
	"status": "active",
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A routing intent profile is created for the organization.
- The profile can now own rules, overrides, and reconciliation runs.

---
### Add a routing intent rule to include candidate prefixes

#### Description

Creates a `RoutingIntentRule` with an include action so matching prefixes are brought into the derived intent set.

#### Inputs

- Required: the target intent profile
- Required: `action` set to include
- Required: at least one selector field such as tenant, VRF, site, region, role, tag, custom field, or origin ASN
- Optional: `weight`, `address_family`, `max_length_mode`, `max_length_value`, `enabled`

#### Procedures

##### Using Web UI

1. Open the target routing intent profile.
2. Open its rules table and click `Add`.
3. Set the rule action to `Include`.
4. Fill in the selector fields that define the candidate prefixes.
5. Save the rule.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentrule/`

Example request body:

```json
{
	"name": "Include Customer Prefixes",
	"intent_profile": 1,
	"action": "include",
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The rule appears under the intent profile.
- Matching prefixes are included the next time intent is derived.

---
### Add a routing intent rule to exclude a prefix from publication

#### Description

Creates a `RoutingIntentRule` with an exclude action so a prefix is removed from publication intent.

#### Inputs

- Required: the target intent profile
- Required: `action` set to exclude
- Required: selector fields that identify the prefix or prefix set to suppress
- Optional: `weight`, `address_family`, `enabled`

#### Procedures

##### Using Web UI

1. Open the target routing intent profile.
2. Add a new routing intent rule.
3. Set the rule action to `Exclude`.
4. Narrow the selector to the prefix you want to suppress.
5. Save the rule.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentrule/`

Example request body:

```json
{
	"name": "Exclude Specific Prefix",
	"intent_profile": 1,
	"action": "exclude",
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The exclusion rule is stored on the profile.
- The prefix is omitted from future derived publication intent.

---
### Add a ROA intent override for one prefix

#### Description

Creates a `ROAIntentOverride` that changes the derived intent for one prefix.

#### Inputs

- Required: the owning organization or intent profile scope
- Required: the target prefix
- Required: the override `action`
- Optional: `origin_asn`, `max_length`, `tenant_scope`, `vrf_scope`, `site_scope`, `region_scope`, `reason`, `starts_at`, `ends_at`, `enabled`

#### Procedures

##### Using Web UI

1. Open `Intent` -> `ROA Intent Overrides`.
2. Click `Add`.
3. Select the scope and target prefix.
4. Set the override action and any value overrides.
5. Save the record.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roaintentoverride/`

Example request body:

```json
{
	"name": "Override 10.0.10.0/24",
	"organization": 1,
	"intent_profile": 2,
	"prefix": 25,
	"action": "include",
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The override appears in the intent profile’s override table.
- Future derivation uses the override for that prefix.

---
### Bind a routing intent template to an organization

#### Description

Creates a `RoutingIntentTemplateBinding` that connects a template to an intent profile and organization.

#### Inputs

- Required: `template`
- Required: `intent_profile`
- Optional: `enabled`, `binding_priority`, `binding_label`, `origin_asn_override`, `max_length_mode`, `max_length_value`, `prefix_selector_query`, `asn_selector_query`, `context_groups`

#### Procedures

##### Using Web UI

1. Open `Intent` -> `Routing Intent Template Bindings`.
2. Click `Add`.
3. Choose the template and intent profile for the organization.
4. Set the binding filters and policy options.
5. Save the binding.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintenttemplatebinding/`

Example request body:

```json
{
	"name": "Customer 001 Binding",
	"template": 1,
	"intent_profile": 2,
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The template binding is stored and linked to the selected profile.
- The binding can be previewed or regenerated later.

---
### Regenerate derived ROA intent for one organization

#### Description

Reruns the selected organization’s routing intent profile so NetBox recomputes derived ROA intent and reconciliation results.

#### Inputs

- Required: the routing intent profile for the organization
- Optional: `comparison_scope`
- Optional: `provider_snapshot` when comparing against imported provider state

#### Procedures

##### Using Web UI

1. Open the routing intent profile detail page.
2. Click `Run Profile`.
3. Select the comparison scope and provider snapshot if needed.
4. Confirm the run.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentprofile/<routing_intent_profile_id>/run/`

Example request body:

```json
{
	"comparison_scope": "local_roa_records"
}
```

Use `provider_imported` and include a `provider_snapshot` value when the run should compare against imported provider state.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A new intent derivation run is created.
- A matching ROA reconciliation run is created for the selected comparison scope.

---
### Preview the output of a template binding before applying it

#### Description

Shows the derived intent that a template binding would produce without applying it.

#### Inputs

- Required: the routing intent template binding

#### Procedures

##### Using Web UI

1. Open the template binding detail page.
2. Click `Preview Binding`.
3. Review the derived prefix and ASN selections before regenerating.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintenttemplatebinding/<routing_intent_template_binding_id>/preview/`

No request body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The preview page shows the binding’s current derived intent.
- No derivation or reconciliation records are written by the preview itself.

---
### Compare derived intent after a policy change against the last run

#### Description

Manually compares the latest binding state with the last compiled or reconciled result.

There is no dedicated compare endpoint yet, so this is a review workflow that uses the binding’s current fingerprint, the preview output, and the most recent run summaries.

#### Inputs

- Required: the template binding or routing intent profile being reviewed
- Required: the last derivation or reconciliation run you want to compare against

#### Procedures

##### Using Web UI

1. Open the template binding detail page.
2. Review the `Last Compiled Fingerprint` and the current summary.
3. Open the most recent reconciliation run or preview the binding again.
4. Compare the new output against the previous run summary.

##### Using REST API

- `GET /api/plugins/netbox-rpki/routingintenttemplatebinding/<routing_intent_template_binding_id>/`
- `POST /api/plugins/netbox-rpki/routingintenttemplatebinding/<routing_intent_template_binding_id>/preview/`

Use the detail response together with the preview payload; there is no dedicated compare action.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can tell whether the policy change altered the derived intent.
- The comparison is visible through the changed preview output or fingerprint.

---
### Run ROA reconciliation against local ROA records

#### Description

Creates a ROA reconciliation run that compares derived intent against local ROA records.

#### Inputs

- Required: the routing intent profile
- Optional: `comparison_scope` set to `local_roa_records`

#### Procedures

##### Using Web UI

1. Open the routing intent profile detail page.
2. Click `Run Profile`.
3. Leave the comparison scope on local ROA records.
4. Confirm the run.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentprofile/<routing_intent_profile_id>/run/`

Example request body:

```json
{
	"comparison_scope": "local_roa_records"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A ROA reconciliation run is created for the profile.
- The run produces ROA intent results and published ROA results against local records.

---
### Run ROA reconciliation against imported provider state

#### Description

Creates a ROA reconciliation run that compares derived intent against a provider snapshot imported from a managed provider account.

#### Inputs

- Required: the routing intent profile
- Required: the provider snapshot to compare against
- Required: `comparison_scope` set to `provider_imported`

#### Procedures

##### Using Web UI

1. Open the routing intent profile detail page.
2. Click `Run Profile`.
3. Choose the imported-provider comparison scope.
4. Select the provider snapshot.
5. Confirm the run.

##### Using REST API

- `POST /api/plugins/netbox-rpki/routingintentprofile/<routing_intent_profile_id>/run/`

Example request body:

```json
{
	"comparison_scope": "provider_imported",
	"provider_snapshot": 10
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A ROA reconciliation run is created for the selected provider snapshot.
- The run compares derived intent against the imported provider state.

---
### Review intents marked as replacement required in a reconciliation run

#### Description

Reviews `ROAIntentResult` rows from a reconciliation run where the derived intent needs replacement.

#### Inputs

- Required: the reconciliation run

#### Procedures

##### Using Web UI

1. Open the ROA reconciliation run detail page.
2. Review the `ROA Intent Results` table.
3. Open the rows whose `Result Type` indicates replacement is required.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roaintentresult/?reconciliation_run=<reconciliation_run_id>&result_type=replacement_required`

Use the result list to isolate the affected intents for the run.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The replacement-required intent rows are identified.
- Each row shows the best published ROA and the expected derived intent.

---
### Review published ROAs marked as orphaned in a reconciliation run

#### Description

Reviews `PublishedROAResult` rows where a published ROA does not map cleanly to the current derived intent.

#### Inputs

- Required: the reconciliation run

#### Procedures

##### Using Web UI

1. Open the ROA reconciliation run detail page.
2. Review the `Published ROA Results` table.
3. Open the rows whose `Result Type` indicates an orphaned published ROA.

##### Using REST API

- `GET /api/plugins/netbox-rpki/publishedroaresult/?reconciliation_run=<reconciliation_run_id>&result_type=orphaned`

Use the published-result list to review orphaned ROAs and their imported authorization matches.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The orphaned published ROA rows are identified.
- Each row shows the published ROA, the imported authorization, and the diff details.

---
### Record an external management exception for a prefix managed outside NetBox

#### Description

Creates an `ExternalManagementException` so NetBox can track a prefix that is managed elsewhere.

#### Inputs

- Required: `organization`
- Required: the exception scope, usually a prefix
- Required: `owner` and `reason`
- Optional: `review_at`, `starts_at`, `ends_at`, `enabled`, `origin_asn`, `max_length`, related ROA or imported authorization fields

#### Procedures

##### Using Web UI

1. Open `Reconciliation` -> `External Management Exceptions`.
2. Click `Add`.
3. Enter the prefix, owner, reason, and review date.
4. Save the exception.

##### Using REST API

- `POST /api/plugins/netbox-rpki/externalmanagementexception/`

Example request body:

```json
{
	"name": "External Ownership Exception",
	"organization": 1,
	"scope_type": "roa_prefix",
	"prefix": 25,
	"owner": "External NOC",
	"reason": "Managed in an external system",
	"enabled": true
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The exception is recorded and shown in the exception list.
- The operations dashboard can surface it for later review.

---
### Review external management exceptions that are past their review date

#### Description

Reviews external management exceptions whose review date has passed or is due.

The operations dashboard already surfaces these items, but the list API does not expose a dedicated review-date filter, so review is mostly by dashboard and list inspection.

#### Inputs

- Required: the exception list or operations dashboard

#### Procedures

##### Using Web UI

1. Open the operations dashboard.
2. Review the `External Management Exceptions Requiring Review` card.
3. Open any exception whose review date or expiry date has passed.

##### Using REST API

- `GET /api/plugins/netbox-rpki/externalmanagementexception/`

Inspect the returned `review_at` and `ends_at` values; the current API does not provide a dedicated review-date filter.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Exceptions past their review date are identified for follow-up.
- The exception can be updated, disabled, or removed after review.

---
### Clear an external management exception after ownership returns to NetBox

#### Description

Removes an external management exception once NetBox owns the prefix again.

There is no dedicated clear action today; clearing the exception is done by deleting the record or disabling it if you need to retain history.

#### Inputs

- Required: the target external management exception
- Required: confirmation that the exception is no longer needed

#### Procedures

##### Using Web UI

1. Open the exception detail page.
2. If you need to preserve history, disable the exception instead of deleting it.
3. Otherwise click `Delete` and confirm.

##### Using REST API

- `DELETE /api/plugins/netbox-rpki/externalmanagementexception/<external_management_exception_id>/`

No request body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The exception no longer appears as an active NetBox-managed exception.
- Follow-up review and reconciliation tasks stop treating the prefix as externally managed.

---
### Review reconciliation findings for one delegated entity or managed relationship

#### Description

Reviews the reconciliation posture for a delegated authorization entity or managed relationship from its detail page and related workflow tables. The repository does not yet expose a single aggregated findings screen for this task, so the review is assembled from linked records.

#### Inputs

- A delegated authorization entity or managed relationship
- The related reconciliation or publication workflow records
- Permission to view the underlying objects

#### Procedures

##### Using Web UI

1. Open the delegated authorization entity or managed relationship detail page.
2. Review the summary field and linked workflow tables.
3. Open the related reconciliation or workflow records when you need the underlying findings.

##### Using REST API

- `GET /api/plugins/netbox-rpki/delegatedauthorizationentity/<id>/`
	Review the entity summary and related managed relationships.
- `GET /api/plugins/netbox-rpki/managedauthorizationrelationship/<id>/`
	Review the relationship summary and related publication workflows.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can identify the current posture for the delegated entity or managed relationship.
- Any unresolved issues are traced back to the linked reconciliation or workflow records.

---
### Create a draft ROA change plan from a reconciliation run

#### Description

Creates a draft `ROAChangePlan` from a completed ROA reconciliation run and carries forward the plan items needed for write-back.

#### Inputs

- A completed ROA reconciliation run
- Permission to create a change plan from the run's intent profile

#### Procedures

##### Using Web UI

1. Open the reconciliation run detail page.
2. Click `Create Plan`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roareconciliationrun/<id>/create_plan/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A draft ROA change plan is created and linked to the reconciliation run.
- The new plan includes the provider write items that will be reviewed before approval.

---
### Review provider operations for a draft ROA change plan

#### Description

Reviews the provider-facing operations that a draft change plan will generate before any write-back occurs.

#### Inputs

- A draft ROA change plan
- Permission to view the plan and its related write executions

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Review the `ROA Change Plan Items` table for operation type, payload, and before or after state.
3. Review `Provider Write Executions` if a preview or apply run already exists.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roachangeplan/<id>/`
	Inspect `items`, `summary_json`, and `provider_write_executions` in the plan payload.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can see the outbound operations the plan will send to the provider.
- You can review the plan payload before approval or preview.

---
### Add approver notes to a ROA change plan before approval

#### Description

Records approver notes together with the primary approval so the change record carries governance context.

#### Inputs

- A draft ROA change plan
- Approver notes, if any
- Optional ticket reference, change reference, and maintenance window fields

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Approve`.
3. Fill in `Approval Notes` and any other governance fields.
4. Submit the form.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/approve/`
	Example body:

```json
{
	"approval_notes": "Reviewed with operations"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The approval record stores the notes.
- The plan's governance fields are updated with the submitted approval metadata.

---
### Approve a draft ROA change plan as primary approver

#### Description

Submits the primary approval for a draft ROA change plan after the current lint and simulation checks are satisfied.

#### Inputs

- A draft ROA change plan
- Approval permission on the plan
- Any lint or simulation acknowledgements required by the current posture

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Approve`.
3. Review any required lint or simulation acknowledgements.
4. Submit the form.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/approve/`
	Example body:

```json
{
	"requires_secondary_approval": true,
	"approval_notes": "Primary approval complete"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The plan moves to `approved` or `awaiting_2nd`.
- An approval record is created and the plan keeps the approval metadata.

---
### Approve a draft ROA change plan as secondary approver

#### Description

Completes the second approval step for a plan that was marked as requiring secondary approval.

#### Inputs

- A plan in `awaiting_2nd`
- A secondary approver who is different from the primary approver

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Secondary Approval`.
3. Enter any optional approval notes.
4. Submit the form.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/approve_secondary/`
	Example body:

```json
{
	"approval_notes": "Secondary review complete"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The plan status returns to `approved`.
- The secondary approver and timestamp are recorded on the plan.

---
### Preview provider write payloads for an approved ROA change plan

#### Description

Records a provider preview execution and shows the exact outbound ROA delta without applying it to the provider.

#### Inputs

- A change plan that is eligible for preview
- Permission to execute write actions on the plan

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Preview`.
3. Confirm the action to record the preview execution.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/preview/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A preview execution is recorded.
- The returned payload includes the outbound delta and does not change provider state.

---
### Apply an approved ROA change plan to a hosted provider account

#### Description

Applies the ROA delta to the configured provider account and starts the follow-up provider sync that captures the resulting snapshot.

#### Inputs

- An approved ROA change plan
- A provider account that supports ROA write-back

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Apply`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/apply/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The plan moves to `applied` when the provider write succeeds.
- A provider write execution is recorded, a rollback bundle is created, and a follow-up sync is attempted.

---
### Roll back a completed ROA change plan using its rollback bundle

#### Description

Uses the rollback bundle generated from an applied change plan to reverse the provider write.

#### Inputs

- A completed plan with an associated rollback bundle
- Approval permission on the rollback bundle

#### Procedures

##### Using Web UI

1. Open the rollback bundle from the change plan detail page.
2. Click `Approve` if the bundle is not yet approved.
3. Click `Apply` and confirm the rollback.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplanrollbackbundle/<id>/approve/`
- `POST /api/plugins/netbox-rpki/roachangeplanrollbackbundle/<id>/apply/`
	Approve first, then apply.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The rollback bundle records the reversal delta and apply result.
- The follow-up sync outcome is stored on the bundle detail page.

---
### Run validation simulation for a draft ROA change plan

#### Description

Runs the ROA validation simulation workflow for a draft plan and records the latest simulation run on that plan.

#### Inputs

- A draft ROA change plan

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Simulate`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/simulate/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A ROA validation simulation run is created and linked to the plan.
- The plan detail page shows the latest simulation posture and summary.

---
### Review simulated collateral impact before approving a ROA change plan

#### Description

Reviews the latest simulation posture, including whether the plan is informational, acknowledgement-required, or blocking.

#### Inputs

- A draft plan with a completed simulation run

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Review `Latest Simulation Posture`, `Latest Simulation Partially Constrained`, and the linked simulation run.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roachangeplan/<id>/`
- `GET /api/plugins/netbox-rpki/roavalidationsimulationrun/<id>/`
	The plan payload includes `latest_simulation_posture` and `latest_simulation_summary`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can tell whether approval is blocked or requires acknowledgements.
- The simulation run and plan posture agree on the current plan state.

---
### Compare two draft ROA change plans by validation risk

#### Description

Compares two draft plans manually by their latest simulation posture and summary. The repository does not provide a dedicated plan-to-plan comparison view or API action yet.

#### Inputs

- Two draft ROA change plans
- Completed simulation runs for both plans

#### Procedures

##### Using Web UI

1. Open each plan detail page.
2. Compare the latest simulation posture, partial-constraint flag, and simulation summary.
3. Use the linked simulation run detail pages if you need per-result analysis.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roachangeplan/<id>/`
	Review the returned simulation posture fields for each plan; there is no comparison endpoint.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can rank the plans by blocking findings, acknowledgement requirements, and constrained scenarios.
- Any comparison remains a manual review across the two plan payloads.

---
### Run ROA lint for a reconciliation run

#### Description

ROA lint is executed by the reconciliation pipeline and again when a change plan is created from that reconciliation run. There is no standalone lint-run trigger in the UI.

#### Inputs

- A completed ROA reconciliation run
- Optionally, a draft ROA change plan derived from that run

#### Procedures

##### Using Web UI

1. Open the reconciliation run or change plan detail page.
2. Review the linked `ROA Lint Runs` table.
3. Open the latest lint run to inspect the findings.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roareconciliationrun/<id>/`
- `GET /api/plugins/netbox-rpki/roachangeplan/<id>/`
	The lint run is returned as related data; the run itself is produced by the pipeline or service layer.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A ROA lint run exists and is linked to the reconciliation run or change plan.
- The lint run contains findings, counts, and posture data for review.

---
### Acknowledge a known ROA lint finding

#### Description

Records acknowledgement for current lint findings on the draft change plan without approving the plan yet.

#### Inputs

- A draft ROA change plan
- The current lint findings to acknowledge

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Click `Acknowledge Lint`.
3. Select the findings to acknowledge and submit the form.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/acknowledge_findings/`
	Example body:

```json
{
	"acknowledged_finding_ids": [1, 2],
	"lint_acknowledgement_notes": "Reviewed and accepted"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The selected lint findings are acknowledged against the plan.
- The plan's lint posture is refreshed after the acknowledgements are recorded.

---
### Suppress a repeating ROA lint finding

#### Description

Creates a suppression for a lint finding so repeated matches with the same fact context can be silenced within the configured scope.

#### Inputs

- A ROA lint finding
- A suppression scope, reason, and optional expiry

#### Procedures

##### Using Web UI

1. Open the lint finding detail page.
2. Click `Suppress Finding`.
3. Choose the suppression scope, provide a reason, and submit.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roalintfinding/<id>/suppress/`
	Example body:

```json
{
	"scope_type": "org",
	"reason": "Known and accepted during rollout",
	"expires_at": "2026-05-01T12:00:00Z"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A lint suppression record is created.
- Future matching findings can be suppressed by the active scope and fact fingerprint.

---
### Review change plan lint posture before provider write-back

#### Description

Reviews the current lint posture for a change plan before preview, approval, or apply.

#### Inputs

- A draft or approved ROA change plan

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Review `Lint Posture` and the latest ROA lint run.
3. Check the `ROA Lint Acknowledgements` table for any outstanding review work.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roachangeplan/<id>/`
	Inspect `latest_lint_posture`, `latest_lint_run`, and `latest_lint_summary`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can see whether the plan is clear for write-back or still needs lint review.
- The latest posture matches the latest recorded lint run.

---
### Block approval when a draft change plan increases critical lint findings

#### Description

Approval is blocked when the latest lint run still has unresolved blocking findings or missing acknowledgements. This is enforced by the approval service.

#### Inputs

- A draft change plan
- Its latest lint run

#### Procedures

##### Using Web UI

1. Open the change plan detail page.
2. Attempt to approve the plan while blocking findings remain unresolved.
3. Resolve or acknowledge the findings, then retry approval.

##### Using REST API

- `POST /api/plugins/netbox-rpki/roachangeplan/<id>/approve/`
	The request is rejected until unresolved blocking or acknowledgement-required findings are cleared.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The plan remains unapproved until the lint posture is acceptable.
- The API returns an error that identifies the blocking lint condition.

---
### Sync a Krill provider account on demand

#### Description

Triggers an on-demand sync for a Krill-backed provider account, imports a fresh snapshot, and updates the account's sync summary.

#### Inputs

- A Krill provider account
- Sync enabled on the account

#### Procedures

##### Using Web UI

1. Open the provider account detail page.
2. Click `Sync`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/provideraccount/<id>/sync/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A provider sync run and provider snapshot are recorded.
- Krill-backed ROA and related repository data are available from the latest snapshot.

---
### Sync an ARIN provider account on demand

#### Description

Triggers an on-demand sync for an ARIN-backed provider account. The current implementation imports ARIN-hosted ROA authorizations only.

#### Inputs

- An ARIN provider account
- Sync enabled on the account

#### Procedures

##### Using Web UI

1. Open the provider account detail page.
2. Click `Sync`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/provideraccount/<id>/sync/`
	No body is required.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A provider sync run and provider snapshot are recorded.
- The imported data reflects the ARIN ROA-only synchronization scope.

---
### Review the latest snapshot imported for a provider account

#### Description

Reviews the latest imported provider snapshot from the provider account detail page and then opens the snapshot detail page for the imported data itself.

#### Inputs

- A provider account with at least one completed sync

#### Procedures

##### Using Web UI

1. Open the provider account detail page.
2. Inspect `Last Sync Summary` to find the latest snapshot.
3. Open the newest entry in the `Provider Snapshots` table.

##### Using REST API

- `GET /api/plugins/netbox-rpki/provideraccount/<id>/`
	Follow `last_sync_summary_json.latest_snapshot_id` to the snapshot record.
- `GET /api/plugins/netbox-rpki/providersnapshot/<snapshot_id>/`
	Review the imported snapshot detail.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can identify the latest imported snapshot for the account.
- The snapshot detail page shows the imported ROA, ASPA, publication, and observation summaries.

---
### Review the latest snapshot diff for unexpected ROA churn

#### Description

Reviews the newest provider snapshot diff for ROA churn, using the diff summary and item table to spot unexpected adds, removals, or changes.

#### Inputs

- A provider account with at least two completed snapshots
- The comparison snapshot you want to review

#### Procedures

##### Using Web UI

1. Open the provider snapshot detail page.
2. Review `Latest Diff Summary` or open the newest row in `Snapshot Comparison Diffs`.
3. Inspect diff items where the object family is ROA authorizations.

##### Using REST API

- `POST /api/plugins/netbox-rpki/providersnapshot/<id>/compare/`
	Supply `base_snapshot` when you want a specific pair; omit it to compare against the latest earlier snapshot.
- `GET /api/plugins/netbox-rpki/providersnapshotdiff/<id>/`
	Review `summary_json` and the related diff items.

##### Using GraphQL API

- `provider_snapshot_latest_diff(snapshot_id: ID)`
- `provider_snapshot_diff(base_snapshot_id: ID, comparison_snapshot_id: ID)`

#### Expected Results

- The diff shows whether ROA churn is expected or anomalous.
- The diff detail page exposes the change counts and item-level before/after state.

---
### Review imported ASPA changes between two provider snapshots

#### Description

Compares two provider snapshots and reviews imported ASPA additions, removals, and updates between them.

#### Inputs

- A base provider snapshot
- A later comparison snapshot

#### Procedures

##### Using Web UI

1. Open the later provider snapshot detail page.
2. Click the compare action or open the related provider snapshot diff.
3. Review the ASPA family rows in the diff item table.

##### Using REST API

- `POST /api/plugins/netbox-rpki/providersnapshot/<id>/compare/`
	Example body: `{"base_snapshot": <snapshot_id>}`.
- `GET /api/plugins/netbox-rpki/providersnapshotdiff/<id>/`
	Inspect the ASPA-related diff items and summary counts.

##### Using GraphQL API

- `provider_snapshot_diff(base_snapshot_id: ID, comparison_snapshot_id: ID)`

#### Expected Results

- ASPA deltas are grouped by change type and family.
- The diff summary matches the snapshot pair you selected.

---
### Review publication linkage gaps reported in provider evidence summaries

#### Description

Reviews provider snapshot evidence for publication points, signed objects, and certificate observations when linkage is incomplete or ambiguous.

#### Inputs

- A provider snapshot with imported evidence payloads

#### Procedures

##### Using Web UI

1. Open the provider snapshot detail page.
2. Review `Imported Publication Points`, `Imported Signed Objects`, and `Imported Certificate Observations`.
3. Open the relevant record and inspect its evidence summary and linkage fields.

##### Using REST API

- `GET /api/plugins/netbox-rpki/providersnapshot/<id>/`
	Inspect the imported evidence collections and the snapshot summary.
- `GET /api/plugins/netbox-rpki/importedpublicationpoint/?provider_snapshot=<id>`
	Review `payload_json.evidence_summary` for linkage status.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Linkage gaps are visible on the imported evidence records.
- The snapshot summary reflects publication-oriented evidence coverage.

---
### Evaluate lifecycle health for one provider account

#### Description

Reviews the overall sync and publication health for one provider account, including its latest snapshot and timeline posture.

#### Inputs

- A provider account with sync history

#### Procedures

##### Using Web UI

1. Open the provider account detail page.
2. Review `Last Sync Summary`, `Lifecycle Health Timeline`, and `Publication Diff Timeline`.
3. Open the latest snapshot or diff if the summary shows attention items.

##### Using REST API

- `GET /api/plugins/netbox-rpki/provideraccount/<id>/`
	Review `last_sync_summary_json` and the linked rollup fields.
- `GET /api/plugins/netbox-rpki/provideraccount/<id>/export/lifecycle/?format=json`
	Export the lifecycle summary for reporting.

##### Using GraphQL API

- `netbox_rpki_provideraccount(id: ID) { lifecycle_health_summary publication_health health_timeline publication_diff_timeline }`

#### Expected Results

- The account’s sync, publication, and diff posture are consistent.
- Any stale or attention-requiring state is visible in the rollup.

---
### Export provider lifecycle or publication summary data for reporting

#### Description

Exports provider lifecycle or publication reporting data for a single provider account or for all visible accounts.

#### Inputs

- One provider account, or a view of all provider accounts
- A preferred export format: JSON or CSV

#### Procedures

##### Using Web UI

1. Open the provider account detail page or the provider account summary page.
2. Click one of the export actions.
3. Download the JSON or CSV response.

##### Using REST API

- `GET /api/plugins/netbox-rpki/provideraccount/<id>/export/lifecycle/?format=json`
- `GET /api/plugins/netbox-rpki/provideraccount/<id>/export/timeline/?format=csv`
- `GET /api/plugins/netbox-rpki/provideraccount/summary/?format=json`
	Use the collection summary endpoint when you want all visible accounts.

##### Using GraphQL API

- `provider_account_summary`
- `provider_snapshot_summary`

#### Expected Results

- The exported payload includes the documented schema version and requested rows.
- CSV exports include the expected report columns.

---
### Import validated payloads from the Routinator live API

#### Description

Imports validated ROA and ASPA payloads from a Routinator instance using its live JSONext API.

#### Inputs

- A validator instance with a live base URL
- Access to the Routinator JSONext endpoint

#### Procedures

##### Using Web UI

1. Open the validator instance detail page to confirm the target validator.
2. Run the validator import command or enqueue the background job that targets the instance.

##### Using REST API

Not applicable.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A validation run is created with fetch mode `live_api`.
- Validated ROA and ASPA payload rows are stored with the run.

---
### Import validated payloads from a Routinator snapshot file

#### Description

Imports validated payloads from a Routinator JSONext snapshot file instead of the live API.

#### Inputs

- A validator instance
- A Routinator JSONext snapshot file

#### Procedures

##### Using Web UI

1. Open the validator instance detail page to confirm the target validator.
2. Run the validator import command or enqueue the background job with the snapshot file path.

##### Using REST API

Not applicable.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The snapshot file is normalized through the same Routinator import pipeline.
- The stored validation run records fetch mode `snapshot_import`.

---
### Review validated ROA payloads that do not map cleanly to local ROAs

#### Description

Reviews validated ROA payloads whose matched local ROA or object validation result is missing, ambiguous, or only partially resolved.

#### Inputs

- A completed validation run
- The validated ROA payload rows from that run

#### Procedures

##### Using Web UI

1. Open the validation run detail page.
2. Open the linked validated ROA payload rows.
3. Filter for rows whose linked object validation result shows an `unmatched`, `payload_level`, or ambiguous match state.

##### Using REST API

- `GET /api/plugins/netbox-rpki/validatedroapayload/?validation_run=<id>`
- `GET /api/plugins/netbox-rpki/objectvalidationresult/?validation_run=<id>`
	Review `match_status`, `external_object_key`, and `details_json`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- You can isolate payloads that need manual review.
- The linked object-validation rows explain why each payload did not map cleanly.

---
### Compare provider-observed ROAs with validator-observed effective state

#### Description

Compares local ROA intent or provider-observed ROAs against what the validator reports as effective state.

#### Inputs

- A ROA record or provider snapshot
- A completed validation run or validated payload set

#### Procedures

##### Using Web UI

1. Open the ROA detail page or the imported validated payload detail page.
2. Review the external overlay summary for validator posture and telemetry posture.
3. Compare the local ROA fields with the validator-evidence fields.

##### Using REST API

- `GET /api/plugins/netbox-rpki/roaobject/<id>/`
	Inspect the overlay summary for validator-observed state.
- `GET /api/plugins/netbox-rpki/validatedroapayload/?validation_run=<id>`
	Review the matching validated payloads.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Mismatches between local ROA state and validator state are visible.
- The overlay summary points to the effective-state posture that should be reviewed.

---
### Review validator observations for one organization after a provider sync

#### Description

Reviews validator observations for one organization after a provider sync so that imported evidence and validator output can be checked together.

#### Inputs

- An organization with recent provider sync data
- A validator instance with at least one completed run

#### Procedures

##### Using Web UI

1. Open the organization’s provider account or snapshot pages.
2. Open the validator instance detail page and review its run history summary.
3. Compare the imported evidence records with the latest validator run.

##### Using REST API

- `GET /api/plugins/netbox-rpki/validatorinstance/<id>/history-summary/`
	Review the most recent runs and the comparison summary.
- `GET /api/plugins/netbox-rpki/validationrun/<id>/`
	Inspect the matching validation-run summary and payload counts.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The latest validator run is easy to compare with the newest provider snapshot.
- Imported evidence and validator observations can be reviewed side by side.

---
### Identify published objects that are missing from validator output

#### Description

Checks published objects that appear in provider evidence but not in validator output, usually by reviewing imported object and observation summaries together.

#### Inputs

- A provider snapshot with imported publication evidence
- A validator run or validated payload set for the same time window

#### Procedures

##### Using Web UI

1. Open the provider snapshot detail page.
2. Review the imported signed objects and certificate observations.
3. Identify rows whose overlay summaries show missing validator linkage or no matching validator posture.

##### Using REST API

- `GET /api/plugins/netbox-rpki/importedsignedobject/?provider_snapshot=<id>`
- `GET /api/plugins/netbox-rpki/importedcertificateobservation/?provider_snapshot=<id>`
	Review the payload summaries for unmatched or missing validator output.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Missing validator coverage is visible from the imported evidence summaries.
- The review identifies objects that need follow-up against validator output.

---
### Build a mismatch review queue from overlay reporting outputs

#### Description

Builds a manual review queue from overlay summaries when provider, publication, and validator evidence disagree.

#### Inputs

- One provider snapshot or validation run
- Imported object rows with overlay summaries

#### Procedures

##### Using Web UI

1. Open the relevant provider snapshot or imported object detail pages.
2. Sort by the overlay summary fields that report mismatch categories.
3. Copy the rows that need follow-up into your local review list.

##### Using REST API

- `GET /api/plugins/netbox-rpki/importedsignedobject/?provider_snapshot=<id>`
- `GET /api/plugins/netbox-rpki/importedcertificateobservation/?provider_snapshot=<id>`
	Use the overlay summary payloads to seed the queue.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The queue contains only objects with meaningful mismatch signals.
- The repository does not create a dedicated queue object, so the workflow remains manual.

---
### Review validator run history for a single validator instance

#### Description

Reviews the most recent validation runs for one validator instance, including freshness and field-level changes between runs.

#### Inputs

- A validator instance with completed runs

#### Procedures

##### Using Web UI

1. Open the validator instance detail page.
2. Click or open `History Summary`.
3. Review the run timeline and the latest comparison block.

##### Using REST API

- `GET /api/plugins/netbox-rpki/validatorinstance/<id>/history-summary/`
	Review the run count, latest comparison, and timeline.

##### Using GraphQL API

- `netbox_rpki_validatorinstance(id: ID) { run_history_summary }`

#### Expected Results

- The latest runs and their freshness state are visible.
- Changes between the current and previous runs are summarized clearly.

---
### Create a delegated authorization entity

#### Description

Creates a delegated authorization entity for a downstream customer, partner, or other delegated subject.

#### Inputs

- An organization that owns the delegated relationship
- Entity name and optional contact details

#### Procedures

##### Using Web UI

1. Open Delegated Authorization Entities.
2. Click `Add`.
3. Enter the entity details and save.

##### Using REST API

- `POST /api/plugins/netbox-rpki/delegatedauthorizationentity/`
	Example body: `{"name": "Downstream Entity", "organization": <id>, "kind": "customer"}`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The entity is created under the selected organization.
- It appears in delegated-authorization lists and detail views.

---
### Create a managed authorization relationship for a delegated entity

#### Description

Creates the managed relationship that links an organization to a delegated entity and records the operational role and status.

#### Inputs

- An existing delegated authorization entity
- The organization that manages the relationship

#### Procedures

##### Using Web UI

1. Open Managed Authorization Relationships.
2. Click `Add`.
3. Select the organization and delegated entity, then save.

##### Using REST API

- `POST /api/plugins/netbox-rpki/managedauthorizationrelationship/`
	Example body: `{"name": "Managed Relationship", "organization": <id>, "delegated_entity": <id>}`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The relationship is created for the same organization as the delegated entity.
- The relationship detail page shows the linked workflow summary.

---
### Create a delegated publication workflow for a managed relationship

#### Description

Creates a delegated publication workflow that tracks publication provisioning for a managed relationship.

#### Inputs

- A managed authorization relationship
- A workflow name and initial status

#### Procedures

##### Using Web UI

1. Open Delegated Publication Workflows.
2. Click `Add`.
3. Select the managed relationship and save the draft workflow.

##### Using REST API

- `POST /api/plugins/netbox-rpki/delegatedpublicationworkflow/`
	Example body: `{"name": "Delegated Publication Workflow", "organization": <id>, "managed_relationship": <id>}`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The workflow is created in draft or active state.
- The detail page shows the managed relationship and summary fields.

---
### Populate publication endpoint and child CA handle for a delegated workflow

#### Description

Populates the publication server URI and CA handles needed for a delegated publication workflow.

#### Inputs

- A delegated publication workflow
- The parent CA handle, child CA handle, and publication server URI

#### Procedures

##### Using Web UI

1. Open the delegated publication workflow detail page.
2. Click `Edit`.
3. Fill in the CA handle and publication endpoint fields, then save.

##### Using REST API

- `PATCH /api/plugins/netbox-rpki/delegatedpublicationworkflow/<id>/`
	Update `parent_ca_handle`, `child_ca_handle`, and `publication_server_uri`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The workflow summary no longer reports missing endpoint or child-handle prerequisites.
- The workflow detail page shows the populated publication values.

---
### Approve a delegated publication workflow that requires approval

#### Description

Approves a delegated publication workflow that is waiting for explicit approval.

#### Inputs

- A workflow with `requires_approval` enabled
- A user with change permission on the workflow

#### Procedures

##### Using Web UI

1. Open the workflow detail page.
2. Click `Approve Workflow`.
3. Confirm the action.

##### Using REST API

- `POST /api/plugins/netbox-rpki/delegatedpublicationworkflow/<id>/approve/`
	Example body: `{"approved_by": "alice"}`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- `approved_at` and `approved_by` are set on the workflow.
- The detail page no longer shows the workflow as awaiting approval.

---
### Review delegated workflows that are missing prerequisites

#### Description

Reviews delegated publication workflows whose summaries report missing prerequisites such as an inactive relationship, a disabled entity, or missing publication data.

#### Inputs

- One or more delegated publication workflows

#### Procedures

##### Using Web UI

1. Open Delegated Publication Workflows.
2. Filter to the organization or relationship you want to review.
3. Open each workflow detail page and inspect `Workflow Summary`.

##### Using REST API

- `GET /api/plugins/netbox-rpki/delegatedpublicationworkflow/?organization=<id>`
	Review the workflow summary payload for `missing_prerequisites`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Missing prerequisites are listed explicitly.
- The workflow summary makes it clear what must be filled in before publication can proceed.

---
### Link authored CA relationship data to a delegated publication workflow

#### Description

Links authored CA relationship data to the managed relationship and delegated workflow that represent the same delegated publication path.

#### Inputs

- An authored CA relationship
- A managed authorization relationship
- A delegated publication workflow

#### Procedures

##### Using Web UI

1. Open the authored CA relationship detail page.
2. Review the linked delegated workflow summary and bottom table.
3. If the workflow is not linked, adjust the managed relationship or workflow fields so the linkage resolves.

##### Using REST API

- `GET /api/plugins/netbox-rpki/authoredcarelationship/<id>/`
	Review the delegated linkage summary on the authored CA relationship record.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The authored CA relationship and delegated workflow resolve to the same managed path.
- The detail summary shows the linkage as connected instead of partial or unlinked.

---
### Review delegated workflows awaiting approval for one organization

#### Description

Reviews delegated publication workflows for one organization where approval is still pending.

#### Inputs

- An organization with delegated publication workflows

#### Procedures

##### Using Web UI

1. Open Delegated Publication Workflows.
2. Filter by organization and review workflows with approval required.
3. Open each workflow detail page and confirm whether approval is still pending.

##### Using REST API

- `GET /api/plugins/netbox-rpki/delegatedpublicationworkflow/?organization=<id>&requires_approval=true`
	Use the detail payload to confirm whether `approved_at` is empty.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The workflows waiting on approval are easy to isolate.
- The organization-level review shows which workflows still need a decision.

---
### Create a local ASPA record for a customer ASN

#### Description

Creates a local `ASPA` record for one customer ASN in the owning organization. This is the authored ASPA inventory record used by reconciliation and provider write-back.

#### Inputs

- Required: `organization`, the owning organization
- Required: `customer_as`, the customer ASN for the ASPA
- Optional: `signed_object`, `valid_from`, `valid_to`, `validation_state`, `comments`, `tenant`, `tags`

#### Procedures

##### Using Web UI

1. Open `Objects` -> `ASPAs`.
2. Click `Add`.
3. Select the organization and customer ASN.
4. Optionally set the signed object and validity fields.
5. Save the record.

Notes:

- The add form is exposed through the standard registry-driven detail and list views.
- ASPA records are validated against the owning organization and the selected customer ASN.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspa/`

Example request body:

```json
{
	"name": "Customer 64500 ASPA",
	"organization": 1,
	"customer_as": 64500,
	"valid_from": "2026-04-15",
	"validation_state": "unknown"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A local ASPA record exists for the selected customer ASN.
- The ASPA detail page shows the record and its authorized provider table.
- The record can be used as input for ASPA reconciliation and provider-backed change plans.

---
### Add provider ASNs to an ASPA record

#### Description

Adds one or more provider authorization rows to an existing ASPA record. Each row represents a provider ASN allowed for the customer ASN on that ASPA.

#### Inputs

- Required: the target ASPA record
- Required: one or more provider ASNs
- Optional: `is_current`, `comments`, `tenant`, `tags`

#### Procedures

##### Using Web UI

1. Open the ASPA detail page.
2. Review the `Authorized Provider ASNs` table.
3. Add or edit provider rows through the child-table surface if your deployment exposes inline actions for that table.
4. Save the updated provider set.

Notes:

- This is a row-level child object workflow; there is no dedicated REST create endpoint for provider rows in the plugin.
- If inline editing is not exposed in your deployment, this remains a manual or admin-path task.

##### Using REST API

- No dedicated REST endpoint is registered for ASPA provider rows in this plugin.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The ASPA record lists the selected provider ASNs.
- Reconciliation and overlay summaries use the updated provider set.
- The ASPA detail page reflects the current authorization set.

---
### Reconcile ASPA intent against published or imported ASPA state

#### Description

Runs ASPA reconciliation for one organization and compares derived intent against local authored ASPA records or imported provider state.

#### Inputs

- Required: the target organization
- Required: `comparison_scope` (`local_aspa_records` or `provider_imported`)
- Optional: `provider_snapshot` when reconciling against imported state

#### Procedures

##### Using Web UI

1. Open the organization detail page.
2. Use `Run ASPA Reconciliation`.
3. Select the comparison scope and, when needed, the provider snapshot.

Notes:

- The reconciliation is organization-scoped.
- Imported-state reconciliation depends on a provider snapshot for the selected organization.

##### Using REST API

- `POST /api/plugins/netbox-rpki/organization/<organization_id>/run-aspa-reconciliation/`

Example request body:

```json
{
	"comparison_scope": "provider_imported",
	"provider_snapshot": 12
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- A completed `ASPAReconciliationRun` is queued or created.
- The run exposes intent and published-result summaries for follow-up planning.
- Reconciliation findings are available for draft plan generation and review.

---
### Create a draft ASPA change plan from reconciliation results

#### Description

Creates a draft `ASPAChangePlan` from a completed reconciliation run. This is the planning step before approval and provider write-back.

#### Inputs

- Required: a completed ASPA reconciliation run
- Optional: a plan name

#### Procedures

##### Using Web UI

1. Open the reconciliation run detail page.
2. Click `Create Plan`.
3. Review the generated draft change plan and its items.

Notes:

- The plan is derived from the reconciliation findings, not entered manually.
- The current implementation treats this as a command or action-driven workflow, not a free-form authoring screen.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspareconciliationrun/<run_id>/create_plan/`

Use an empty request body; the action returns the new plan payload and item count.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A draft ASPA change plan is created with items derived from the reconciliation findings.
- The plan summary records provider add and remove counts when provider-backed data is present.
- The plan remains in draft status until approval actions are taken.

---
### Approve a draft ASPA change plan as primary approver

#### Description

Records the primary approval for a draft `ASPAChangePlan` and captures governance metadata, including change references and maintenance-window context.

#### Inputs

- Required: a draft ASPA change plan
- Optional: `requires_secondary_approval`, `ticket_reference`, `change_reference`, `maintenance_window_start`, `maintenance_window_end`, `approval_notes`

#### Procedures

##### Using Web UI

1. Open the ASPA change plan detail page.
2. Click `Approve`.
3. Enter the approval metadata and submit.

Notes:

- If secondary approval is required, the plan moves to the awaiting-secondary state after the first approval.
- The approval action creates governance history records, not just a status flip.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspachangeplan/<plan_id>/approve/`

Example request body:

```json
{
	"requires_secondary_approval": true,
	"ticket_reference": "CHG-1001",
	"change_reference": "ASPA-2026-04",
	"approval_notes": "Reviewed by primary approver"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The plan status moves out of draft and records the primary approver.
- The approval record appears on the plan detail page.
- The plan becomes eligible for secondary approval or apply, depending on its governance settings.

---
### Approve a draft ASPA change plan as secondary approver

#### Description

Records the secondary approval for an ASPA change plan that requires two approvers. The secondary approver must be different from the primary approver.

#### Inputs

- Required: an already primary-approved ASPA change plan
- Optional: `approval_notes`

#### Procedures

##### Using Web UI

1. Open the ASPA change plan detail page.
2. Click `Secondary Approval`.
3. Add any notes and submit.

Notes:

- This action is only available while the plan is awaiting secondary approval.
- The system records a distinct approval event for auditability.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspachangeplan/<plan_id>/approve_secondary/`

Example request body:

```json
{
	"approval_notes": "Secondary approver confirmed the final state"
}
```

##### Using GraphQL API

Not applicable.

#### Expected Results

- The change plan records the secondary approver and approval timestamp.
- The plan becomes eligible for apply when its other prerequisites are met.
- The plan status returns to approved after secondary approval completes.

---
### Apply an approved ASPA change plan to a hosted provider account

#### Description

Applies an approved, provider-backed ASPA change plan to the configured provider account. In the current implementation this is Krill-backed provider write-back.

#### Inputs

- Required: an approved ASPA change plan
- Required: a provider-backed plan with a configured provider account

#### Procedures

##### Using Web UI

1. Open the ASPA change plan detail page.
2. Click `Apply`.
3. Confirm the apply request.

Notes:

- The plan must already be approved and tied to a provider account that supports ASPA writes.
- After apply, the service captures provider execution metadata and typically refreshes provider-sync evidence.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspachangeplan/<plan_id>/apply/`

Use an empty request body; the response includes the provider write execution and delta summary.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The provider write is executed and recorded as a `ProviderWriteExecution`.
- The plan status and apply timestamps update after the write completes.
- Any follow-up sync or snapshot evidence is recorded when the provider write path supports it.

---
### Roll back a completed ASPA change plan using its rollback bundle

#### Description

Applies the rollback bundle that was generated from a completed ASPA change plan. The rollback bundle is the inverse delta captured from the original apply.

#### Inputs

- Required: an ASPA rollback bundle derived from the completed plan
- Required: approval before apply, when the bundle workflow requires it

#### Procedures

##### Using Web UI

1. Open the ASPA change plan detail page.
2. Open the related rollback bundle from the `Rollback Bundles` table.
3. Approve the bundle if needed, then click `Apply`.

Notes:

- Rollback bundles are first-class records with their own approval and apply path.
- The source plan stays available for audit and traceability after rollback.

##### Using REST API

- `POST /api/plugins/netbox-rpki/aspachangeplanrollbackbundle/<bundle_id>/apply/`

If the bundle has not yet been approved, call the matching `approve` action first.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The rollback bundle is applied and its status changes to the completed state.
- The source plan remains available for audit and rollback traceability.
- Provider-sync follow-up evidence is recorded when the adapter completes the rollback flow.

---
### Import an IRR snapshot from a configured source

#### Description

Imports an IRR snapshot from a configured IRR source. The implemented path is command-driven, with optional background-job execution.

#### Inputs

- Required: an `IrrSource`
- Required for snapshot import: a snapshot file path
- Optional: `--enqueue` to run it as a NetBox job

#### Procedures

##### Using Web UI

1. Open the IRR source detail page.
2. Review the source configuration and last sync state.
3. Run the import through the management command or queued job path; there is no dedicated import button in the plugin UI.

Notes:

- This task is currently operationally command-driven, not a pure browser action.
- The UI is useful for confirming source configuration and reviewing the resulting snapshot.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irrsource/`

Use the source endpoint to review configuration; the import itself is command-driven through `sync_irr_source`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A completed `IrrSnapshot` is created for the source.
- Imported route, AS-set, and maintainer objects are available for coordination.
- The snapshot can feed coordination and change-plan workflows.

---
### Run IRR coordination for one organization

#### Description

Compares NetBox route policy with imported IRR state for one organization and produces an `IrrCoordinationRun`.

#### Inputs

- Required: the organization to coordinate
- Required: at least one enabled IRR source for that organization

#### Procedures

##### Using Web UI

1. Open the IRR source and organization detail pages to confirm the configured inputs.
2. Run `run_irr_coordination` from the management command or a queued job.
3. Review the resulting coordination run in the IRR tables.

Notes:

- Coordination is driven by imported IRR data plus organization intent.
- The current flow is service or command driven; the UI is primarily for review.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irr_coordination_run/`

The coordination itself is command-driven; use the list endpoint to review completed runs.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A completed IRR coordination run exists for the organization.
- The run contains result rows for matched, missing, extra, and conflict cases.
- The findings can be converted into source-specific change plans.

---
### Review IRR objects that diverge from derived RPKI intent

#### Description

Reviews coordination results that do not match derived intent, such as missing, extra, or conflicting imported objects. This is a review workflow, not a write action.

#### Inputs

- Required: a completed `IrrCoordinationRun`
- Optional: the source or family filter you want to inspect

#### Procedures

##### Using Web UI

1. Open the IRR coordination run detail page.
2. Review the `IRR Coordination Results` table.
3. Filter for `missing_in_source`, `extra_in_source`, or `source_conflict` rows.

Notes:

- The review is read-only and is intended to surface divergence for operator action.
- Exact remediation depends on the source adapter and the organization’s routing policy.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irrcoordinationrun/<run_id>/`

Use the run payload and related result list endpoints to inspect the divergence details.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The divergent IRR objects are visible with their stable keys and source summaries.
- Coordination findings can be used to draft a source-specific change plan.
- Operators can trace each divergence back to a source snapshot and object family.

---
### Create an IRR change plan from coordination findings

#### Description

Creates source-specific IRR change plans from a completed coordination run. This is the planning step that turns coordination findings into actionable write sets.

#### Inputs

- Required: a completed IRR coordination run
- Optional: queued job execution instead of synchronous execution

#### Procedures

##### Using Web UI

1. Review the completed coordination run.
2. Generate change plans with the `create_irr_change_plans` command or its background-job form.
3. Open the resulting plan(s) and inspect the items.

Notes:

- The current implementation treats this as command-driven plan generation.
- Plan creation is source-specific when multiple IRR sources participate in the same run.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irr_change_plan/`

Change-plan drafting is command-driven in the current implementation; the list endpoint is for review after the plan is created.

##### Using GraphQL API

Not applicable.

#### Expected Results

- One or more `IrrChangePlan` records are created for the coordination run.
- Each plan records item counts, write-support mode, and capability warnings.
- The plans can be previewed before any execution is attempted.

---
### Preview the write set for an IRR change plan before execution

#### Description

Builds a preview execution for one IRR change plan so the operator can review the write set before applying it. This is a dry-run path.

#### Inputs

- Required: an `IrrChangePlan`
- Optional: preview mode via the command path

#### Procedures

##### Using Web UI

1. Open the IRR change plan detail page.
2. Review the plan items and request payloads.
3. Run the preview through the command-driven execution path; there is no dedicated preview button in the plugin UI.

Notes:

- Preview does not mutate the target integration.
- The write set shown here should match what the apply step would submit for the same plan state.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irr_change_plan/<plan_id>/`

Preview execution is command-driven through `execute_irr_change_plan --mode preview`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The preview execution records the write set and response summary without changing the target integration.
- The plan detail page can show the stored execution record after the run.
- Operators can inspect the execution payload before deciding whether to apply.

---
### Apply an IRR change plan to the target integration

#### Description

Applies an IRR change plan to its target integration adapter. This is the execution step after preview and review.

#### Inputs

- Required: an `IrrChangePlan`
- Required: a target source that supports apply mode

#### Procedures

##### Using Web UI

1. Open the IRR change plan detail page.
2. Review the plan items and plan summary.
3. Run the apply path through the command or queued job; the plugin does not expose a dedicated apply button.

Notes:

- Only adapters that support apply mode should receive the plan.
- The current implementation expects execution to be initiated by command or job, not a bespoke UI control.

##### Using REST API

- `GET /api/plugins/netbox-rpki/irr_change_plan/<plan_id>/`

The apply step is command-driven through `execute_irr_change_plan --mode apply`.

##### Using GraphQL API

Not applicable.

#### Expected Results

- An `IrrWriteExecution` is recorded for the apply run.
- The target integration reflects the executed write set when the adapter supports apply mode.
- The execution record preserves the write payload and outcome for audit.

---
### Import a BGP telemetry snapshot from MRT data

#### Description

Imports BGP telemetry observations from a normalized snapshot derived from MRT data. This is the current telemetry ingest path.

#### Inputs

- Required: a `TelemetrySource`
- Required: a snapshot file path
- Optional: `--enqueue` to run as a background job

#### Procedures

##### Using Web UI

1. Open the telemetry source detail page.
2. Review the source configuration and run history summary.
3. Run `sync_telemetry_source` with the snapshot file; there is no dedicated UI import action in the plugin.

Notes:

- Telemetry import is command-driven in the current implementation.
- The detail page is used to confirm source setup and inspect the resulting run history.

##### Using REST API

- `GET /api/plugins/netbox-rpki/telemetrysource/`

Use the source endpoint to review configuration; the import itself is command-driven.

##### Using GraphQL API

Not applicable.

#### Expected Results

- A completed `TelemetryRun` is created for the source.
- The run stores imported `BgpPathObservation` rows and summary counts.
- The imported observations become available for overlay and change-review workflows.

---
### Review telemetry observations for prefixes affected by a pending ROA change

#### Description

Reviews BGP telemetry observations that relate to prefixes affected by a pending ROA change. This is a manual correlation workflow in the current implementation.

#### Inputs

- Required: the pending ROA change plan or ROA object under review
- Required: one or more completed telemetry runs

#### Procedures

##### Using Web UI

1. Open the ROA change plan or ROA object detail page.
2. Review the simulation or overlay summary for affected prefixes.
3. Open the relevant telemetry run and inspect matching `BgpPathObservation` rows.

Notes:

- The plugin exposes the evidence needed for this review, but it does not automate the correlation as a dedicated action.
- This is intentionally a review step before approval or apply.

##### Using REST API

- `GET /api/plugins/netbox-rpki/telemetryrun/`

The plugin exposes telemetry runs and observations for review; there is no dedicated pending-change correlation action.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Telemetry observations for the affected prefixes are identified for operator review.
- Any mismatch between pending ROA intent and observed paths is visible in the run summaries.
- The operator can use the telemetry evidence to decide whether the change is safe to continue.

---
### Review the signed-object record linked to a local ROA or ASPA

#### Description

Reviews the signed-object record that backs a local ROA or ASPA object. This is a read-only detail workflow.

#### Inputs

- Required: the signed object, or the linked ROA/ASPA object

#### Procedures

##### Using Web UI

1. Open the signed object detail page.
2. Follow the `ROA Object` or `ASPA` link to the linked extension record.
3. Review the publication, validation, and relationship fields on the detail page.

Notes:

- The detail view exposes linked ROA and ASPA extension records directly.
- The signed-object record is the primary place to review validity and publication state together.

##### Using REST API

- `GET /api/plugins/netbox-rpki/signedobject/<signed_object_id>/`

The detail payload exposes the ROA or ASPA extension when the signed object is retrieved in detail form.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The signed object and its linked ROA or ASPA extension are visible together.
- The operator can confirm publication and validation state from one record.
- The linked extension can be used to navigate back to the authored object if needed.

---
### Review manifest entries associated with a signed object

#### Description

Reviews manifest evidence associated with a signed object. In the current implementation, this is primarily done through the signed-object and manifest detail records rather than a dedicated review workflow.

#### Inputs

- Required: the signed object or its manifest record

#### Procedures

##### Using Web UI

1. Open the signed object detail page.
2. Follow the `Current Manifest` link when present.
3. Review the manifest record and its related signed-object reference.

Notes:

- This is a read-only inspection flow.
- The manifest link is the normal place to inspect entry-level evidence when the deployment exposes it.

##### Using REST API

- `GET /api/plugins/netbox-rpki/manifest/`

Use the manifest record to review the signed-object relationship and any entry evidence exposed by your deployment.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The manifest linked to the signed object can be inspected from the related detail page.
- Entry-level evidence is available for audit or follow-up review.
- The operator can see how the manifest relates to the signed object in the object graph.

---
### Review revoked certificate references published in a CRL

#### Description

Reviews revoked-certificate references published in a certificate revocation list and the related signed-object evidence.

#### Inputs

- Required: the CRL record or its linked signed object

#### Procedures

##### Using Web UI

1. Open the CRL detail page.
2. Review the linked signed object and issuance certificate.
3. Inspect any revoked-certificate rows associated with the CRL in the related detail surface if exposed.

Notes:

- The current UI is detail-oriented; there is no separate CRL review workflow.
- Some revocation evidence may appear through the signed-object detail path depending on the deployed tables.

##### Using REST API

- `GET /api/plugins/netbox-rpki/certificaterevocationlist/`

Use the CRL detail payload to identify the issuing certificate, manifest linkage, and any revoked-certificate references present in the data model.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The CRL and its revocation references are available for inspection.
- Operators can trace revoked certificate data back to the issuing certificate and signed object.
- The CRL relationship can be used to follow the affected publication chain.

---
### Identify signed objects that share a publication point failure domain

#### Description

Identifies signed objects that depend on the same publication point or publication infrastructure. This is a near-term analysis task that builds on existing signed-object and publication-point detail data.

#### Inputs

- Required: one or more publication points or signed objects to compare

#### Procedures

##### Using Web UI

1. Open the publication point detail page.
2. Review linked signed objects and imported evidence on the related tables.
3. Compare objects that point at the same repository or publication URI.

Notes:

- The current implementation exposes the underlying data, but not a dedicated failure-domain analysis tool.
- This task is therefore a manual or near-term review workflow.

##### Using REST API

- `GET /api/plugins/netbox-rpki/publicationpoint/`

Use the publication-point records and linked signed objects to group objects by shared failure domain.

##### Using GraphQL API

Not applicable.

#### Expected Results

- Signed objects that share a publication point can be grouped for impact analysis.
- A publication-point outage scope can be estimated from the related detail records.
- The grouping can inform certificate, manifest, and signed-object impact reviews.

---
### Review certificates approaching expiry that could affect published objects

#### Description

Reviews resource certificates whose `valid_to` date is close enough to affect published end-entity certificates or other signed objects. This is a current read-only review flow backed by the operations dashboard and certificate detail pages.

#### Inputs

- Required: view access to the operations dashboard and resource certificates
- Optional: a target organization to narrow the review

#### Procedures

##### Using Web UI

1. Open the Operations Dashboard.
2. Review the `Certificates Nearing Expiry` card.
3. Open any certificate that needs follow-up.
4. Review the certificate detail page for the linked organization, trust anchor, publication point, issued end-entity certificates, signed objects, and ROA objects.

Notes:

- The dashboard route is `/plugins/netbox_rpki/operations/`.
- The dashboard uses the effective lifecycle policy threshold for the owning organization.
- The certificate detail page is the best place to inspect which published objects still depend on the certificate.

##### Using REST API

- `GET /api/plugins/netbox-rpki/certificate/`
- Optional organization filter: `GET /api/plugins/netbox-rpki/certificate/?rpki_org=1`

Review the returned `valid_to` values against the effective lifecycle policy threshold used by your deployment.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The operator gets a concrete list of certificates that need renewal review before published objects become risky.
- The certificate detail page shows the certificate's ownership and downstream linkage.
- Follow-up work such as replacement certificate recording can be planned from the review.

---
### Model the effect of revoking a resource certificate on effective publication policy

#### Description

Reviews the downstream effect of revoking a resource certificate on the effective publication posture for the objects it supports. This is a near-term manual analysis task: the plugin models the relationships, but it does not provide a dedicated revocation simulation workflow.

#### Inputs

- Required: a resource certificate and its owning organization
- Optional: the linked publication point, trust anchor, and downstream end-entity certificates or signed objects

#### Procedures

##### Using Web UI

1. Open the resource certificate detail page.
2. Review the linked organization, trust anchor, and publication point.
3. Review the `Issued End-Entity Certificates`, `Signed Objects`, and `ROA Objects` tables.
4. Open the linked records that would need republishing or replacement after revocation.

Notes:

- The current UI exposes the dependency graph, not a revocation modeling action.
- This review is manual and evidence-based.

##### Using REST API

- `GET /api/plugins/netbox-rpki/certificate/<id>/`
- `GET /api/plugins/netbox-rpki/endentitycertificate/?resource_certificate=<id>`
- `GET /api/plugins/netbox-rpki/signedobject/?resource_certificate=<id>`

Use the certificate and related object payloads to enumerate dependent records and estimate which published objects lose their issuing-certificate context.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The operator can list the dependent end-entity certificates and signed objects.
- The publication-policy impact of revocation is made explicit for manual review.
- No automated revoke-and-recompute workflow is performed by the current implementation.

---
### Model the effect of revoking an EE certificate on dependent signed objects

#### Description

Reviews the downstream effect of revoking an end-entity certificate on the signed objects that depend on it. This is hypothetical in the product today: the dependency graph exists, but there is no dedicated EE revocation impact simulator or workflow action.

#### Inputs

- Required: an end-entity certificate
- Optional: the linked signed objects, manifests, and CRL records

#### Procedures

##### Using Web UI

1. Open the end-entity certificate detail page.
2. Review the linked resource certificate and publication point.
3. Review the `Signed Objects` table.
4. Open each signed object detail page and inspect the manifest and certificate revocation list links when present.

Notes:

- The current UI exposes the dependency graph, not a revocation modeling workflow.
- Any revocation review is manual and evidence-based.

##### Using REST API

- `GET /api/plugins/netbox-rpki/endentitycertificate/<id>/`
- `GET /api/plugins/netbox-rpki/signedobject/?ee_certificate=<id>`
- `GET /api/plugins/netbox-rpki/certificaterevocationlist/?signed_object=<signed_object_id>`

Use the EE certificate and signed-object payloads to trace which published objects would be affected if the EE certificate were revoked.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The operator can trace all signed objects that rely on the EE certificate.
- Any linked manifest or CRL evidence remains available through the detail graph.
- No automated revocation simulation or write-back occurs.

---
### Review organization governance summary for approvals, rollbacks, and delegated workflows

#### Description

Reviews the organization-level governance roll-up for approvals, rollback posture, bulk intent runs, and delegated-workflow attention. This is current and backed by the organization detail page, REST serializer, and the governance roll-up service.

#### Inputs

- Required: an organization record
- Optional: access to the underlying change plans, rollback bundles, bulk intent runs, and routing-intent exceptions for drill-down

#### Procedures

##### Using Web UI

1. Open the organization detail page.
2. Review the `Governance Roll-up` field.
3. Open the linked workflow records when you need the concrete change plan, rollback bundle, or delegated-workflow details.
4. Use the Operations Dashboard when you need a broader attention view across the organization.

Notes:

- The organization detail page renders `build_organization_governance_rollup()`.
- The roll-up aggregates change plans, rollback bundles, bulk intent runs, and routing-intent exceptions.
- Delegated workflow review still happens record by record; the roll-up is an overview, not a replacement for the detail pages.

##### Using REST API

- `GET /api/plugins/netbox-rpki/organization/<id>/`
- `GET /api/plugins/netbox-rpki/roachangeplan/?organization=<id>`
- `GET /api/plugins/netbox-rpki/aspachangeplan/?organization=<id>`
- `GET /api/plugins/netbox-rpki/roachangeplanrollbackbundle/?organization=<id>`
- `GET /api/plugins/netbox-rpki/aspachangeplanrollbackbundle/?organization=<id>`
- `GET /api/plugins/netbox-rpki/bulkintentrun/?organization=<id>`
- `GET /api/plugins/netbox-rpki/routingintentexception/?organization=<id>`

Use the organization detail payload for the roll-up counts, then drill into the underlying objects when you need the concrete records.

##### Using GraphQL API

Not applicable.

#### Expected Results

- The operator gets a single summary of approval, rollback, and delegated-workflow posture for the organization.
- The summary highlights items awaiting approval, approved but not yet applied, failed, or rollback-eligible.
- Follow-up work still happens on the underlying objects.

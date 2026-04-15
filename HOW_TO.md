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

Endpoint:

- `POST /api/plugins/netbox-rpki/organization/`

Minimal request body:

```json
{
	"org_id": "cust-001",
	"name": "Customer 001"
}
```

Example request body with optional fields:

```json
{
	"org_id": "cust-001",
	"name": "Customer 001",
	"parent_rir": 1,
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

Endpoint:

- `POST /api/plugins/netbox-rpki/certificate/`

Minimal request body:

```json
{
	"name": "Customer 001 Certificate A",
	"rpki_org": 1,
	"auto_renews": true,
	"self_hosted": false
}
```

Example request body with additional fields:

```json
{
	"name": "Customer 001 Certificate A",
	"issuer": "Issuer A",
	"subject": "CN=Customer 001 Certificate A",
	"serial": "SERIAL-001-A",
	"valid_from": "2026-01-01",
	"valid_to": "2026-12-31",
	"auto_renews": true,
	"self_hosted": false,
	"rpki_org": 1,
	"trust_anchor": 2,
	"publication_point": 3
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

Endpoint:

- `POST /api/plugins/netbox-rpki/certificateprefix/`

Minimal request body:

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

Endpoint:

- `POST /api/plugins/netbox-rpki/certificateasn/`

Minimal request body:

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

Endpoint:

- `PATCH /api/plugins/netbox-rpki/certificate/<certificate_id>/`

Minimal request body:

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

Endpoint:

- `PATCH /api/plugins/netbox-rpki/certificate/<certificate_id>/`

Minimal request body:

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

Endpoint:

- `GET /api/plugins/netbox-rpki/certificate/`

Typical usage:

1. Request the certificate list, optionally filtered by organization.
2. Review the returned `valid_to` values.
3. Compare those dates against the lifecycle threshold used by your deployment.

Example:

- `GET /api/plugins/netbox-rpki/certificate/?rpki_org=1`

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

Endpoint:

- `POST /api/plugins/netbox-rpki/certificate/`

Example request body:

```json
{
	"name": "Customer 001 Certificate B",
	"rpki_org": 1,
	"valid_from": "2026-10-01",
	"valid_to": "2027-09-30",
	"auto_renews": true,
	"self_hosted": false,
	"trust_anchor": 2,
	"publication_point": 3
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

Endpoint:

- `POST /api/plugins/netbox-rpki/roaobject/`

Minimal request body:

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

Endpoint:

- `POST /api/plugins/netbox-rpki/roaobjectprefix/`

Minimal request body:

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

Endpoint:

- `PATCH /api/plugins/netbox-rpki/roaobjectprefix/<roa_object_prefix_id>/`

Minimal request body:

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

Status: `Current`


---
### Retire a local ROA that is no longer intended

Status: `Current`


---
### Import latest ROAs from a managed provider account

Status: `Current`


---
### Review imported provider ROAs that are missing local ownership in NetBox

Status: `Near-term`


---
### Promote an imported provider ROA into a local ROA source-of-truth record

Status: `Near-term`


---
### Create a routing intent profile for one organization

Status: `Current`


---
### Add a routing intent rule to include candidate prefixes

Status: `Current`


---
### Add a routing intent rule to exclude a prefix from publication

Status: `Current`


---
### Add a ROA intent override for one prefix

Status: `Current`


---
### Bind a routing intent template to an organization

Status: `Current`


---
### Regenerate derived ROA intent for one organization

Status: `Current`


---
### Preview the output of a template binding before applying it

Status: `Near-term`


---
### Compare derived intent after a policy change against the last run

Status: `Near-term`


---
### Run ROA reconciliation against local ROA records

Status: `Current`


---
### Run ROA reconciliation against imported provider state

Status: `Current`


---
### Review intents marked as replacement required in a reconciliation run

Status: `Current`


---
### Review published ROAs marked as orphaned in a reconciliation run

Status: `Current`


---
### Record an external management exception for a prefix managed outside NetBox

Status: `Current`


---
### Review external management exceptions that are past their review date

Status: `Near-term`


---
### Clear an external management exception after ownership returns to NetBox

Status: `Current`


---
### Review reconciliation findings for one delegated entity or managed relationship

Status: `Near-term`


---
### Create a draft ROA change plan from a reconciliation run

Status: `Current`


---
### Review provider operations for a draft ROA change plan

Status: `Current`


---
### Add approver notes to a ROA change plan before approval

Status: `Current`


---
### Approve a draft ROA change plan as primary approver

Status: `Current`


---
### Approve a draft ROA change plan as secondary approver

Status: `Current`


---
### Preview provider write payloads for an approved ROA change plan

Status: `Current`


---
### Apply an approved ROA change plan to a hosted provider account

Status: `Current`


---
### Roll back a completed ROA change plan using its rollback bundle

Status: `Current`


---
### Run validation simulation for a draft ROA change plan

Status: `Current`


---
### Review simulated collateral impact before approving a ROA change plan

Status: `Current`


---
### Compare two draft ROA change plans by validation risk

Status: `Near-term`


---
### Run ROA lint for a reconciliation run

Status: `Current`


---
### Acknowledge a known ROA lint finding

Status: `Current`


---
### Suppress a repeating ROA lint finding

Status: `Current`


---
### Review change plan lint posture before provider write-back

Status: `Current`


---
### Block approval when a draft change plan increases critical lint findings

Status: `Hypothetical`


---
### Sync a Krill provider account on demand

Status: `Current`


---
### Sync an ARIN provider account on demand

Status: `Current`


---
### Review the latest snapshot imported for a provider account

Status: `Current`


---
### Review the latest snapshot diff for unexpected ROA churn

Status: `Current`


---
### Review imported ASPA changes between two provider snapshots

Status: `Current`


---
### Review publication linkage gaps reported in provider evidence summaries

Status: `Current`


---
### Evaluate lifecycle health for one provider account

Status: `Current`


---
### Export provider lifecycle or publication summary data for reporting

Status: `Current`


---
### Import validated payloads from the Routinator live API

Status: `Current`


---
### Import validated payloads from a Routinator snapshot file

Status: `Current`


---
### Review validated ROA payloads that do not map cleanly to local ROAs

Status: `Near-term`


---
### Compare provider-observed ROAs with validator-observed effective state

Status: `Current`


---
### Review validator observations for one organization after a provider sync

Status: `Near-term`


---
### Identify published objects that are missing from validator output

Status: `Hypothetical`


---
### Build a mismatch review queue from overlay reporting outputs

Status: `Near-term`


---
### Review validator run history for a single validator instance

Status: `Current`


---
### Create a delegated authorization entity

Status: `Current`


---
### Create a managed authorization relationship for a delegated entity

Status: `Current`


---
### Create a delegated publication workflow for a managed relationship

Status: `Current`


---
### Populate publication endpoint and child CA handle for a delegated workflow

Status: `Current`


---
### Approve a delegated publication workflow that requires approval

Status: `Current`


---
### Review delegated workflows that are missing prerequisites

Status: `Current`


---
### Link authored CA relationship data to a delegated publication workflow

Status: `Near-term`


---
### Review delegated workflows awaiting approval for one organization

Status: `Near-term`


---
### Create a local ASPA record for a customer ASN

Status: `Current`


---
### Add provider ASNs to an ASPA record

Status: `Current`


---
### Reconcile ASPA intent against published or imported ASPA state

Status: `Current`


---
### Create a draft ASPA change plan from reconciliation results

Status: `Current`


---
### Approve a draft ASPA change plan as primary approver

Status: `Current`


---
### Approve a draft ASPA change plan as secondary approver

Status: `Current`


---
### Apply an approved ASPA change plan to a hosted provider account

Status: `Current`


---
### Roll back a completed ASPA change plan using its rollback bundle

Status: `Current`


---
### Import an IRR snapshot from a configured source

Status: `Current`


---
### Run IRR coordination for one organization

Status: `Current`


---
### Review IRR objects that diverge from derived RPKI intent

Status: `Current`


---
### Create an IRR change plan from coordination findings

Status: `Current`


---
### Preview the write set for an IRR change plan before execution

Status: `Current`


---
### Apply an IRR change plan to the target integration

Status: `Current`


---
### Import a BGP telemetry snapshot from MRT data

Status: `Current`


---
### Review telemetry observations for prefixes affected by a pending ROA change

Status: `Near-term`


---
### Review the signed-object record linked to a local ROA or ASPA

Status: `Current`


---
### Review manifest entries associated with a signed object

Status: `Current`


---
### Review revoked certificate references published in a CRL

Status: `Current`


---
### Identify signed objects that share a publication point failure domain

Status: `Hypothetical`


---
### Review certificates approaching expiry that could affect published objects

Status: `Current`


---
### Model the effect of revoking a resource certificate on effective publication policy

Status: `Near-term`


---
### Model the effect of revoking an EE certificate on dependent signed objects

Status: `Hypothetical`


---
### Review organization governance summary for approvals, rollbacks, and delegated workflows

Status: `Current`

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone
from django.utils.text import slugify
from netaddr import IPNetwork

from dcim.models import Region, Site
from ipam.models import ASN, Prefix, RIR, VRF
from tenancy.models import Tenant

from netbox_rpki import models as rpki_models


DEFAULT_SEED_COUNT = 12
DEV_SEED_MARKER = "Managed by devrun/seed-data.sh"


SEED_TARGET_MODELS = (
    RIR,
    Tenant,
    Region,
    Site,
    VRF,
    ASN,
    Prefix,
    rpki_models.Organization,
    rpki_models.Repository,
    rpki_models.PublicationPoint,
    rpki_models.TrustAnchor,
    rpki_models.TrustAnchorLocator,
    rpki_models.Certificate,
    rpki_models.EndEntityCertificate,
    rpki_models.SignedObject,
    rpki_models.CertificateRevocationList,
    rpki_models.RevokedCertificate,
    rpki_models.Manifest,
    rpki_models.ManifestEntry,
    rpki_models.TrustAnchorKey,
    rpki_models.RoaObject,
    rpki_models.RoaObjectPrefix,
    rpki_models.CertificatePrefix,
    rpki_models.CertificateAsn,
    rpki_models.ASPA,
    rpki_models.ASPAProvider,
    rpki_models.ASPAIntent,
    rpki_models.ASPAIntentMatch,
    rpki_models.ASPAReconciliationRun,
    rpki_models.ASPAIntentResult,
    rpki_models.PublishedASPAResult,
    rpki_models.RSC,
    rpki_models.RSCFileHash,
    rpki_models.RouterCertificate,
    rpki_models.ValidatorInstance,
    rpki_models.ValidationRun,
    rpki_models.ObjectValidationResult,
    rpki_models.ValidatedRoaPayload,
    rpki_models.ValidatedAspaPayload,
    rpki_models.RoutingIntentProfile,
    rpki_models.RoutingIntentRule,
    rpki_models.ROAIntentOverride,
    rpki_models.IntentDerivationRun,
    rpki_models.ROAIntent,
    rpki_models.ROAIntentMatch,
    rpki_models.ROAReconciliationRun,
    rpki_models.ROAIntentResult,
    rpki_models.PublishedROAResult,
)


def _seeded_queryset(model, marker: str):
    field_names = {field.name for field in model._meta.concrete_fields}
    if "comments" in field_names:
        return model.objects.filter(comments=marker)
    if "description" in field_names:
        return model.objects.filter(description=marker)
    raise ValueError(f"{model.__name__} cannot be filtered by the seed marker")


def _seeded_text_kwargs(model, marker: str) -> dict[str, str]:
    field_names = {field.name for field in model._meta.concrete_fields}
    kwargs: dict[str, str] = {}
    if "description" in field_names:
        kwargs["description"] = marker
    if "comments" in field_names:
        kwargs["comments"] = marker
    return kwargs


def clear_seed_sample_data(marker: str) -> None:
    for model in reversed(SEED_TARGET_MODELS):
        _seeded_queryset(model, marker).delete()


def count_seed_sample_data(marker: str) -> dict[str, int]:
    return {model.__name__: _seeded_queryset(model, marker).count() for model in SEED_TARGET_MODELS}


def seed_sample_data(
    *,
    item_count: int = DEFAULT_SEED_COUNT,
    label_prefix: str = "Seed",
    marker: str = DEV_SEED_MARKER,
    cleanup: bool = False,
) -> dict[str, list[object]]:
    if item_count < 12:
        raise ValueError("item_count must be at least 12")

    if cleanup:
        clear_seed_sample_data(marker)

    now = timezone.now()
    slug_prefix = slugify(label_prefix) or "seed"

    rirs = []
    tenants = []
    regions = []
    sites = []
    vrfs = []
    customer_asns = []
    provider_asns = []
    prefixes_v4 = []
    prefixes_v6 = []

    for index in range(item_count):
        suffix = f"{index + 1:02d}"

        rir = RIR.objects.create(
            name=f"{label_prefix} RIR {suffix}",
            slug=f"{slug_prefix}-rir-{suffix}",
            is_private=True,
            **_seeded_text_kwargs(RIR, marker),
        )
        tenant = Tenant.objects.create(
            name=f"{label_prefix} Tenant {suffix}",
            slug=f"{slug_prefix}-tenant-{suffix}",
            **_seeded_text_kwargs(Tenant, marker),
        )
        region = Region.objects.create(
            name=f"{label_prefix} Region {suffix}",
            slug=f"{slug_prefix}-region-{suffix}",
            **_seeded_text_kwargs(Region, marker),
        )
        site = Site.objects.create(
            name=f"{label_prefix} Site {suffix}",
            slug=f"{slug_prefix}-site-{suffix}",
            region=region,
            tenant=tenant,
            **_seeded_text_kwargs(Site, marker),
        )
        vrf = VRF.objects.create(
            name=f"{label_prefix} VRF {suffix}",
            rd=f"64512:{index + 1}",
            tenant=tenant,
            **_seeded_text_kwargs(VRF, marker),
        )
        customer_asn = ASN.objects.create(
            asn=4250000000 + index,
            rir=rir,
            tenant=tenant,
            **_seeded_text_kwargs(ASN, marker),
        )
        provider_asn = ASN.objects.create(
            asn=4250001000 + index,
            rir=rir,
            tenant=tenant,
            **_seeded_text_kwargs(ASN, marker),
        )
        prefix_v4 = Prefix.objects.create(
            prefix=IPNetwork(f"10.250.{index}.0/24"),
            vrf=vrf,
            tenant=tenant,
            **_seeded_text_kwargs(Prefix, marker),
        )
        prefix_v6 = Prefix.objects.create(
            prefix=IPNetwork(f"2001:db8:250:{index}::/48"),
            vrf=vrf,
            tenant=tenant,
            **_seeded_text_kwargs(Prefix, marker),
        )

        rirs.append(rir)
        tenants.append(tenant)
        regions.append(region)
        sites.append(site)
        vrfs.append(vrf)
        customer_asns.append(customer_asn)
        provider_asns.append(provider_asn)
        prefixes_v4.append(prefix_v4)
        prefixes_v6.append(prefix_v6)

    organizations = []
    repositories = []
    publication_points = []
    trust_anchors = []
    trust_anchor_locators = []
    certificates = []
    ee_certificates = []
    generic_signed_objects = []
    roa_signed_objects = []
    manifest_signed_objects = []
    aspa_signed_objects = []
    rsc_signed_objects = []
    tak_signed_objects = []
    revocation_lists = []
    manifests = []
    trust_anchor_keys = []
    roas = []
    roa_prefixes = []
    certificate_prefixes = []
    certificate_asns = []
    aspas = []
    aspa_providers = []
    aspa_intents = []
    aspa_intent_matches = []
    aspa_reconciliation_runs = []
    aspa_intent_results = []
    published_aspa_results = []
    rscs = []
    rsc_file_hashes = []
    router_certificates = []
    validator_instances = []
    validation_runs = []
    object_validation_results = []
    validated_roa_payloads = []
    validated_aspa_payloads = []
    routing_intent_profiles = []
    routing_intent_rules = []
    roa_intent_overrides = []
    intent_derivation_runs = []
    roa_intents = []
    roa_intent_matches = []
    reconciliation_runs = []
    roa_intent_results = []
    published_roa_results = []
    revoked_certificates = []
    manifest_entries = []

    for index in range(item_count):
        suffix = f"{index + 1:02d}"
        marker_kwargs = _seeded_text_kwargs(rpki_models.Organization, marker)
        valid_from = date(2025, 1, 1) + timedelta(days=index)
        valid_to = date(2026, 1, 1) + timedelta(days=index)
        started_at = now - timedelta(hours=(index + 1))
        completed_at = started_at + timedelta(minutes=5)

        organization = rpki_models.Organization.objects.create(
            org_id=f"{slug_prefix}-org-{suffix}",
            name=f"{label_prefix} Organization {suffix}",
            parent_rir=rirs[index],
            tenant=tenants[index],
            ext_url=f"https://example.invalid/{slug_prefix}/org-{suffix}",
            **marker_kwargs,
        )
        repository = rpki_models.Repository.objects.create(
            name=f"{label_prefix} Repository {suffix}",
            organization=organization,
            repository_type=rpki_models.RepositoryType.MIXED,
            rsync_base_uri=f"rsync://repo.example.invalid/{slug_prefix}/{suffix}/",
            rrdp_notify_uri=f"https://rrdp.example.invalid/{slug_prefix}/{suffix}/notification.xml",
            status=rpki_models.ValidationState.UNKNOWN,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.Repository, marker),
        )
        publication_point = rpki_models.PublicationPoint.objects.create(
            name=f"{label_prefix} Publication Point {suffix}",
            organization=organization,
            repository=repository,
            publication_uri=f"rsync://repo.example.invalid/{slug_prefix}/{suffix}/objects/",
            rsync_base_uri=repository.rsync_base_uri,
            rrdp_notify_uri=repository.rrdp_notify_uri,
            retrieval_state=rpki_models.RetrievalState.DISCOVERED,
            validation_state=rpki_models.ValidationState.UNKNOWN,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.PublicationPoint, marker),
        )
        trust_anchor = rpki_models.TrustAnchor.objects.create(
            name=f"{label_prefix} Trust Anchor {suffix}",
            organization=organization,
            subject=f"CN={label_prefix} Trust Anchor {suffix}",
            subject_key_identifier=f"ta-ski-{suffix}",
            rsync_uri=f"rsync://ta.example.invalid/{slug_prefix}/{suffix}.cer",
            rrdp_notify_uri=f"https://ta.example.invalid/{slug_prefix}/{suffix}.xml",
            status=rpki_models.ValidationState.VALID,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.TrustAnchor, marker),
        )
        trust_anchor_locator = rpki_models.TrustAnchorLocator.objects.create(
            name=f"{label_prefix} Trust Anchor Locator {suffix}",
            trust_anchor=trust_anchor,
            rsync_uri=trust_anchor.rsync_uri,
            https_uri=f"https://ta.example.invalid/{slug_prefix}/{suffix}.tal",
            public_key_info=f"public-key-info-{suffix}",
            is_active=True,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.TrustAnchorLocator, marker),
        )
        certificate = rpki_models.Certificate.objects.create(
            name=f"{label_prefix} Certificate {suffix}",
            rpki_org=organization,
            trust_anchor=trust_anchor,
            publication_point=publication_point,
            issuer=f"{label_prefix} Issuer {suffix}",
            subject=f"CN={label_prefix} Certificate {suffix}",
            serial=f"{slug_prefix}-cert-{suffix}",
            valid_from=valid_from,
            valid_to=valid_to,
            auto_renews=index % 2 == 0,
            public_key=f"public-key-{suffix}",
            private_key=f"private-key-{suffix}",
            publication_url=publication_point.publication_uri,
            ca_repository=repository.rsync_base_uri,
            self_hosted=index % 2 == 1,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.Certificate, marker),
        )
        ee_certificate = rpki_models.EndEntityCertificate.objects.create(
            name=f"{label_prefix} End Entity Certificate {suffix}",
            organization=organization,
            resource_certificate=certificate,
            publication_point=publication_point,
            subject=f"CN={label_prefix} EE Certificate {suffix}",
            issuer=certificate.subject,
            serial=f"{slug_prefix}-ee-{suffix}",
            ski=f"ski-{suffix}",
            aki=f"aki-{suffix}",
            valid_from=valid_from,
            valid_to=valid_to,
            public_key=f"ee-public-key-{suffix}",
            status=rpki_models.ValidationState.VALID,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.EndEntityCertificate, marker),
        )

        def create_signed_object(name_suffix: str, object_type: str):
            return rpki_models.SignedObject.objects.create(
                name=f"{label_prefix} {name_suffix} {suffix}",
                organization=organization,
                object_type=object_type,
                display_label=f"{label_prefix} {name_suffix} {suffix}",
                resource_certificate=certificate,
                ee_certificate=ee_certificate,
                publication_point=publication_point,
                filename=f"{slug_prefix}-{slugify(name_suffix)}-{suffix}.sig",
                object_uri=f"{publication_point.publication_uri}{slugify(name_suffix)}-{suffix}.sig",
                repository_uri=repository.rsync_base_uri,
                content_hash=f"hash-{slugify(name_suffix)}-{suffix}",
                serial_or_version=f"v{index + 1}",
                cms_digest_algorithm="sha256",
                cms_signature_algorithm="rsa-sha256",
                publication_status=rpki_models.PublicationStatus.PUBLISHED,
                validation_state=rpki_models.ValidationState.VALID,
                valid_from=valid_from,
                valid_to=valid_to,
                raw_payload_reference=f"payload://{slug_prefix}/{slugify(name_suffix)}/{suffix}",
                tenant=tenants[index],
                **_seeded_text_kwargs(rpki_models.SignedObject, marker),
            )

        generic_signed_object = create_signed_object("Signed Object", rpki_models.SignedObjectType.OTHER)
        roa_signed_object = create_signed_object("ROA Signed Object", rpki_models.SignedObjectType.ROA)
        manifest_signed_object = create_signed_object("Manifest Signed Object", rpki_models.SignedObjectType.MANIFEST)
        aspa_signed_object = create_signed_object("ASPA Signed Object", rpki_models.SignedObjectType.ASPA)
        rsc_signed_object = create_signed_object("RSC Signed Object", rpki_models.SignedObjectType.RSC)
        tak_signed_object = create_signed_object("TAK Signed Object", rpki_models.SignedObjectType.TAK)

        revocation_list = rpki_models.CertificateRevocationList.objects.create(
            name=f"{label_prefix} CRL {suffix}",
            organization=organization,
            issuing_certificate=certificate,
            publication_point=publication_point,
            crl_number=f"crl-{suffix}",
            this_update=started_at,
            next_update=completed_at + timedelta(days=7),
            publication_uri=f"{publication_point.publication_uri}crl-{suffix}.crl",
            retrieval_state=rpki_models.RetrievalState.FETCHED,
            validation_state=rpki_models.ValidationState.VALID,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.CertificateRevocationList, marker),
        )
        manifest = rpki_models.Manifest.objects.create(
            name=f"{label_prefix} Manifest {suffix}",
            signed_object=manifest_signed_object,
            manifest_number=f"mft-{suffix}",
            this_update=started_at,
            next_update=completed_at + timedelta(days=1),
            current_crl=revocation_list,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.Manifest, marker),
        )
        revocation_list.manifest = manifest
        revocation_list.save(update_fields=["manifest"])

        trust_anchor_key = rpki_models.TrustAnchorKey.objects.create(
            name=f"{label_prefix} Trust Anchor Key {suffix}",
            trust_anchor=trust_anchor,
            signed_object=tak_signed_object,
            current_public_key=f"current-public-key-{suffix}",
            next_public_key=f"next-public-key-{suffix}",
            valid_from=valid_from,
            valid_to=valid_to,
            publication_uri=f"{publication_point.publication_uri}tak-{suffix}.cer",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.TrustAnchorKey, marker),
        )
        roa = rpki_models.RoaObject.objects.create(
            name=f"{label_prefix} ROA Object {suffix}",
            organization=certificate.rpki_org,
            origin_as=customer_asns[index],
            signed_object=roa_signed_object,
            valid_from=valid_from,
            valid_to=valid_to,
            validation_state=roa_signed_object.validation_state,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RoaObject, marker),
        )
        roa_prefix = rpki_models.RoaObjectPrefix.objects.create(
            roa_object=roa,
            prefix=prefixes_v4[index],
            prefix_cidr_text=str(prefixes_v4[index].prefix),
            max_length=24,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RoaObjectPrefix, marker),
        )
        certificate_prefix = rpki_models.CertificatePrefix.objects.create(
            prefix=prefixes_v6[index],
            certificate_name=certificate,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.CertificatePrefix, marker),
        )
        certificate_asn = rpki_models.CertificateAsn.objects.create(
            asn=provider_asns[index],
            certificate_name2=certificate,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.CertificateAsn, marker),
        )
        aspa = rpki_models.ASPA.objects.create(
            name=f"{label_prefix} ASPA {suffix}",
            organization=organization,
            signed_object=aspa_signed_object,
            customer_as=customer_asns[index],
            valid_from=valid_from,
            valid_to=valid_to,
            validation_state=rpki_models.ValidationState.VALID,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPA, marker),
        )
        aspa_provider = rpki_models.ASPAProvider.objects.create(
            aspa=aspa,
            provider_as=provider_asns[index],
            is_current=True,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPAProvider, marker),
        )
        aspa_intent_key = rpki_models.ASPAIntent.build_intent_key(
            customer_asn_value=customer_asns[index].asn,
            provider_asn_value=provider_asns[index].asn,
        )
        aspa_intent = rpki_models.ASPAIntent.objects.create(
            name=f"{label_prefix} ASPA Intent {suffix}",
            organization=organization,
            intent_key=aspa_intent_key,
            customer_as=customer_asns[index],
            provider_as=provider_asns[index],
            explanation=f"seed intent {suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPAIntent, marker),
        )
        aspa_intent_match = rpki_models.ASPAIntentMatch.objects.create(
            name=f"{label_prefix} ASPA Intent Match {suffix}",
            aspa_intent=aspa_intent,
            aspa=aspa,
            match_kind=rpki_models.ASPAIntentMatchKind.EXACT,
            is_best_match=True,
            details_json={"seed_suffix": suffix},
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPAIntentMatch, marker),
        )
        aspa_reconciliation_run = rpki_models.ASPAReconciliationRun.objects.create(
            name=f"{label_prefix} ASPA Reconciliation Run {suffix}",
            organization=organization,
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            intent_count=1,
            published_aspa_count=1,
            result_summary_json={"matches": 1},
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPAReconciliationRun, marker),
        )
        aspa_intent_result = rpki_models.ASPAIntentResult.objects.create(
            name=f"{label_prefix} ASPA Intent Result {suffix}",
            reconciliation_run=aspa_reconciliation_run,
            aspa_intent=aspa_intent,
            result_type=rpki_models.ASPAIntentResultType.MATCH,
            severity=rpki_models.ReconciliationSeverity.INFO,
            best_aspa=aspa,
            match_count=1,
            details_json={"seed_suffix": suffix},
            computed_at=completed_at,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ASPAIntentResult, marker),
        )
        published_aspa_result = rpki_models.PublishedASPAResult.objects.create(
            name=f"{label_prefix} Published ASPA Result {suffix}",
            reconciliation_run=aspa_reconciliation_run,
            aspa=aspa,
            result_type=rpki_models.PublishedASPAResultType.MATCHED,
            severity=rpki_models.ReconciliationSeverity.INFO,
            matched_intent_count=1,
            details_json={"seed_suffix": suffix},
            computed_at=completed_at,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.PublishedASPAResult, marker),
        )
        rsc = rpki_models.RSC.objects.create(
            name=f"{label_prefix} RSC {suffix}",
            organization=organization,
            signed_object=rsc_signed_object,
            version=f"1.{index}",
            digest_algorithm="sha256",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RSC, marker),
        )
        rsc_file_hash = rpki_models.RSCFileHash.objects.create(
            rsc=rsc,
            filename=f"artifact-{suffix}.bin",
            hash_algorithm="sha256",
            hash_value=f"hash-value-{suffix}",
            artifact_reference=f"artifact://{slug_prefix}/{suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RSCFileHash, marker),
        )
        router_certificate = rpki_models.RouterCertificate.objects.create(
            name=f"{label_prefix} Router Certificate {suffix}",
            organization=organization,
            resource_certificate=certificate,
            publication_point=publication_point,
            asn=provider_asns[index],
            subject=f"CN={label_prefix} Router Certificate {suffix}",
            issuer=certificate.subject,
            serial=f"router-cert-{suffix}",
            ski=f"router-ski-{suffix}",
            router_public_key=f"router-public-key-{suffix}",
            valid_from=valid_from,
            valid_to=valid_to,
            status=rpki_models.ValidationState.VALID,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RouterCertificate, marker),
        )
        validator_instance = rpki_models.ValidatorInstance.objects.create(
            name=f"{label_prefix} Validator {suffix}",
            organization=organization,
            software_name="Routinator",
            software_version="1.0",
            base_url=f"https://validator.example.invalid/{slug_prefix}/{suffix}/",
            status=rpki_models.ValidationRunStatus.COMPLETED,
            last_run_at=completed_at,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ValidatorInstance, marker),
        )
        validation_run = rpki_models.ValidationRun.objects.create(
            name=f"{label_prefix} Validation Run {suffix}",
            validator=validator_instance,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            repository_serial=f"repo-serial-{suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ValidationRun, marker),
        )
        object_validation_result = rpki_models.ObjectValidationResult.objects.create(
            name=f"{label_prefix} Object Validation Result {suffix}",
            validation_run=validation_run,
            signed_object=generic_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            observed_at=completed_at,
            reason=f"seed validation result {suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ObjectValidationResult, marker),
        )
        roa_object_validation_result = rpki_models.ObjectValidationResult.objects.create(
            name=f"{label_prefix} ROA Object Validation Result {suffix}",
            validation_run=validation_run,
            signed_object=roa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            observed_at=completed_at,
            reason=f"seed roa validation result {suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ObjectValidationResult, marker),
        )
        aspa_object_validation_result = rpki_models.ObjectValidationResult.objects.create(
            name=f"{label_prefix} ASPA Object Validation Result {suffix}",
            validation_run=validation_run,
            signed_object=aspa_signed_object,
            validation_state=rpki_models.ValidationState.VALID,
            disposition=rpki_models.ValidationDisposition.ACCEPTED,
            observed_at=completed_at,
            reason=f"seed aspa validation result {suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ObjectValidationResult, marker),
        )
        validated_roa_payload = rpki_models.ValidatedRoaPayload.objects.create(
            name=f"{label_prefix} Validated ROA Payload {suffix}",
            validation_run=validation_run,
            roa_object=roa,
            object_validation_result=roa_object_validation_result,
            prefix=prefixes_v4[index],
            origin_as=customer_asns[index],
            max_length=24,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ValidatedRoaPayload, marker),
        )
        validated_aspa_payload = rpki_models.ValidatedAspaPayload.objects.create(
            name=f"{label_prefix} Validated ASPA Payload {suffix}",
            validation_run=validation_run,
            aspa=aspa,
            object_validation_result=aspa_object_validation_result,
            customer_as=customer_asns[index],
            provider_as=provider_asns[index],
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ValidatedAspaPayload, marker),
        )
        routing_intent_profile = rpki_models.RoutingIntentProfile.objects.create(
            name=f"{label_prefix} Routing Intent Profile {suffix}",
            organization=organization,
            is_default=index == 0,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            description=f"{marker} profile {suffix}",
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f"tenant={tenants[index].slug}",
            asn_selector_query=f"asn={customer_asns[index].asn}",
            default_max_length_policy=rpki_models.DefaultMaxLengthPolicy.EXACT,
            allow_as0=False,
            enabled=True,
            tenant=tenants[index],
            comments=marker,
        )
        routing_intent_rule = rpki_models.RoutingIntentRule.objects.create(
            name=f"{label_prefix} Routing Intent Rule {suffix}",
            intent_profile=routing_intent_profile,
            weight=index + 1,
            action=rpki_models.RoutingIntentRuleAction.INCLUDE,
            address_family=rpki_models.AddressFamily.IPV4,
            match_tenant=tenants[index],
            match_vrf=vrfs[index],
            match_site=sites[index],
            match_region=regions[index],
            match_role="edge",
            match_tag="export",
            match_custom_field=f"seed-policy-{suffix}",
            origin_asn=customer_asns[index],
            max_length_mode=rpki_models.RoutingIntentRuleMaxLengthMode.EXACT,
            max_length_value=24,
            enabled=True,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RoutingIntentRule, marker),
        )
        roa_intent_override = rpki_models.ROAIntentOverride.objects.create(
            name=f"{label_prefix} ROA Intent Override {suffix}",
            organization=organization,
            intent_profile=routing_intent_profile,
            action=rpki_models.ROAIntentOverrideAction.FORCE_INCLUDE,
            prefix=prefixes_v4[index],
            prefix_cidr_text=str(prefixes_v4[index].prefix),
            origin_asn=customer_asns[index],
            origin_asn_value=customer_asns[index].asn,
            max_length=24,
            tenant_scope=tenants[index],
            vrf_scope=vrfs[index],
            site_scope=sites[index],
            region_scope=regions[index],
            reason=f"seed override {suffix}",
            starts_at=started_at,
            ends_at=completed_at + timedelta(days=30),
            enabled=True,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ROAIntentOverride, marker),
        )
        intent_derivation_run = rpki_models.IntentDerivationRun.objects.create(
            name=f"{label_prefix} Intent Derivation Run {suffix}",
            organization=organization,
            intent_profile=routing_intent_profile,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            trigger_mode=rpki_models.IntentRunTriggerMode.MANUAL,
            started_at=started_at,
            completed_at=completed_at,
            input_fingerprint=f"fingerprint-{suffix}",
            prefix_count_scanned=2,
            intent_count_emitted=1,
            warning_count=0,
            error_summary="",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.IntentDerivationRun, marker),
        )
        intent_key = rpki_models.ROAIntent.build_intent_key(
            prefix_cidr_text=str(prefixes_v4[index].prefix),
            address_family=rpki_models.AddressFamily.IPV4,
            origin_asn_value=customer_asns[index].asn,
            max_length=24,
            tenant_id=tenants[index].pk,
            vrf_id=vrfs[index].pk,
            site_id=sites[index].pk,
            region_id=regions[index].pk,
        )
        roa_intent = rpki_models.ROAIntent.objects.create(
            name=f"{label_prefix} ROA Intent {suffix}",
            derivation_run=intent_derivation_run,
            organization=organization,
            intent_profile=routing_intent_profile,
            intent_key=intent_key,
            prefix=prefixes_v4[index],
            prefix_cidr_text=str(prefixes_v4[index].prefix),
            address_family=rpki_models.AddressFamily.IPV4,
            origin_asn=customer_asns[index],
            origin_asn_value=customer_asns[index].asn,
            is_as0=False,
            max_length=24,
            scope_tenant=tenants[index],
            scope_vrf=vrfs[index],
            scope_site=sites[index],
            scope_region=regions[index],
            source_rule=routing_intent_rule,
            applied_override=roa_intent_override,
            derived_state=rpki_models.ROAIntentDerivedState.ACTIVE,
            exposure_state=rpki_models.ROAIntentExposureState.ADVERTISED,
            explanation=f"seed intent {suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ROAIntent, marker),
        )
        roa_intent_match = rpki_models.ROAIntentMatch.objects.create(
            name=f"{label_prefix} ROA Intent Match {suffix}",
            roa_intent=roa_intent,
            roa_object=roa,
            match_kind=rpki_models.ROAIntentMatchKind.EXACT,
            is_best_match=True,
            details_json={"seed_suffix": suffix},
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ROAIntentMatch, marker),
        )
        reconciliation_run = rpki_models.ROAReconciliationRun.objects.create(
            name=f"{label_prefix} ROA Reconciliation Run {suffix}",
            organization=organization,
            intent_profile=routing_intent_profile,
            basis_derivation_run=intent_derivation_run,
            comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            published_roa_count=1,
            intent_count=1,
            result_summary_json={"matches": 1},
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ROAReconciliationRun, marker),
        )
        roa_intent_result = rpki_models.ROAIntentResult.objects.create(
            name=f"{label_prefix} ROA Intent Result {suffix}",
            reconciliation_run=reconciliation_run,
            roa_intent=roa_intent,
            result_type=rpki_models.ROAIntentResultType.MATCH,
            severity=rpki_models.ReconciliationSeverity.INFO,
            best_roa_object=roa,
            match_count=1,
            details_json={"seed_suffix": suffix},
            computed_at=completed_at,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ROAIntentResult, marker),
        )
        published_roa_result = rpki_models.PublishedROAResult.objects.create(
            name=f"{label_prefix} Published ROA Result {suffix}",
            reconciliation_run=reconciliation_run,
            roa_object=roa,
            result_type=rpki_models.PublishedROAResultType.MATCHED,
            severity=rpki_models.ReconciliationSeverity.INFO,
            matched_intent_count=1,
            details_json={"seed_suffix": suffix},
            computed_at=completed_at,
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.PublishedROAResult, marker),
        )
        revoked_certificate = rpki_models.RevokedCertificate.objects.create(
            revocation_list=revocation_list,
            certificate=certificate,
            ee_certificate=ee_certificate,
            serial=f"revoked-{suffix}",
            revoked_at=completed_at,
            revocation_reason="keyCompromise",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.RevokedCertificate, marker),
        )
        manifest_entry = rpki_models.ManifestEntry.objects.create(
            manifest=manifest,
            signed_object=generic_signed_object,
            certificate=certificate,
            ee_certificate=ee_certificate,
            revocation_list=revocation_list,
            filename=f"manifest-entry-{suffix}.roa",
            hash_algorithm="sha256",
            hash_value=f"manifest-hash-{suffix}",
            tenant=tenants[index],
            **_seeded_text_kwargs(rpki_models.ManifestEntry, marker),
        )

        organizations.append(organization)
        repositories.append(repository)
        publication_points.append(publication_point)
        trust_anchors.append(trust_anchor)
        trust_anchor_locators.append(trust_anchor_locator)
        certificates.append(certificate)
        ee_certificates.append(ee_certificate)
        generic_signed_objects.append(generic_signed_object)
        roa_signed_objects.append(roa_signed_object)
        manifest_signed_objects.append(manifest_signed_object)
        aspa_signed_objects.append(aspa_signed_object)
        rsc_signed_objects.append(rsc_signed_object)
        tak_signed_objects.append(tak_signed_object)
        revocation_lists.append(revocation_list)
        manifests.append(manifest)
        trust_anchor_keys.append(trust_anchor_key)
        roas.append(roa)
        roa_prefixes.append(roa_prefix)
        certificate_prefixes.append(certificate_prefix)
        certificate_asns.append(certificate_asn)
        aspas.append(aspa)
        aspa_providers.append(aspa_provider)
        aspa_intents.append(aspa_intent)
        aspa_intent_matches.append(aspa_intent_match)
        aspa_reconciliation_runs.append(aspa_reconciliation_run)
        aspa_intent_results.append(aspa_intent_result)
        published_aspa_results.append(published_aspa_result)
        rscs.append(rsc)
        rsc_file_hashes.append(rsc_file_hash)
        router_certificates.append(router_certificate)
        validator_instances.append(validator_instance)
        validation_runs.append(validation_run)
        object_validation_results.append(object_validation_result)
        object_validation_results.append(roa_object_validation_result)
        object_validation_results.append(aspa_object_validation_result)
        validated_roa_payloads.append(validated_roa_payload)
        validated_aspa_payloads.append(validated_aspa_payload)
        routing_intent_profiles.append(routing_intent_profile)
        routing_intent_rules.append(routing_intent_rule)
        roa_intent_overrides.append(roa_intent_override)
        intent_derivation_runs.append(intent_derivation_run)
        roa_intents.append(roa_intent)
        roa_intent_matches.append(roa_intent_match)
        reconciliation_runs.append(reconciliation_run)
        roa_intent_results.append(roa_intent_result)
        published_roa_results.append(published_roa_result)
        revoked_certificates.append(revoked_certificate)
        manifest_entries.append(manifest_entry)

    return {
        "rirs": rirs,
        "tenants": tenants,
        "regions": regions,
        "sites": sites,
        "vrfs": vrfs,
        "customer_asns": customer_asns,
        "provider_asns": provider_asns,
        "prefixes_v4": prefixes_v4,
        "prefixes_v6": prefixes_v6,
        "organizations": organizations,
        "repositories": repositories,
        "publication_points": publication_points,
        "trust_anchors": trust_anchors,
        "trust_anchor_locators": trust_anchor_locators,
        "certificates": certificates,
        "ee_certificates": ee_certificates,
        "generic_signed_objects": generic_signed_objects,
        "roa_signed_objects": roa_signed_objects,
        "manifest_signed_objects": manifest_signed_objects,
        "aspa_signed_objects": aspa_signed_objects,
        "rsc_signed_objects": rsc_signed_objects,
        "tak_signed_objects": tak_signed_objects,
        "revocation_lists": revocation_lists,
        "manifests": manifests,
        "trust_anchor_keys": trust_anchor_keys,
        "roas": roas,
        "roa_prefixes": roa_prefixes,
        "certificate_prefixes": certificate_prefixes,
        "certificate_asns": certificate_asns,
        "aspas": aspas,
        "aspa_providers": aspa_providers,
        "aspa_intents": aspa_intents,
        "aspa_intent_matches": aspa_intent_matches,
        "aspa_reconciliation_runs": aspa_reconciliation_runs,
        "aspa_intent_results": aspa_intent_results,
        "published_aspa_results": published_aspa_results,
        "rscs": rscs,
        "rsc_file_hashes": rsc_file_hashes,
        "router_certificates": router_certificates,
        "validator_instances": validator_instances,
        "validation_runs": validation_runs,
        "object_validation_results": object_validation_results,
        "validated_roa_payloads": validated_roa_payloads,
        "validated_aspa_payloads": validated_aspa_payloads,
        "routing_intent_profiles": routing_intent_profiles,
        "routing_intent_rules": routing_intent_rules,
        "roa_intent_overrides": roa_intent_overrides,
        "intent_derivation_runs": intent_derivation_runs,
        "roa_intents": roa_intents,
        "roa_intent_matches": roa_intent_matches,
        "reconciliation_runs": reconciliation_runs,
        "roa_intent_results": roa_intent_results,
        "published_roa_results": published_roa_results,
        "revoked_certificates": revoked_certificates,
        "manifest_entries": manifest_entries,
    }

from dataclasses import dataclass
from uuid import uuid4

from django.utils.text import slugify
from netaddr import IPNetwork

from ipam.models import ASN, Prefix, RIR
from tenancy.models import Tenant

from netbox_rpki import models as rpki_models
from netbox_rpki.sample_data import count_seed_sample_data, seed_sample_data


def create_test_rir(name='RIR 1', slug=None, is_private=True):
    return RIR.objects.get_or_create(
        slug=slug or slugify(name),
        defaults={
            'name': name,
            'is_private': is_private,
        },
    )[0]


def create_test_organization(org_id='org-1', name='Organization 1', **kwargs):
    return rpki_models.Organization.objects.create(org_id=org_id, name=name, **kwargs)


def create_test_certificate(
    name='Certificate 1',
    rpki_org=None,
    auto_renews=True,
    self_hosted=False,
    **kwargs,
):
    if rpki_org is None:
        rpki_org = create_test_organization()
    return rpki_models.Certificate.objects.create(
        name=name,
        rpki_org=rpki_org,
        auto_renews=auto_renews,
        self_hosted=self_hosted,
        **kwargs,
    )


def create_test_prefix(prefix='10.0.0.0/24', **kwargs):
    return Prefix.objects.create(prefix=IPNetwork(prefix), **kwargs)


def create_test_asn(asn=65001, rir=None, **kwargs):
    if rir is None:
        rir = create_test_rir(name=f'RIR {asn}', slug=f'rir-{asn}')
    return ASN.objects.get_or_create(
        asn=asn,
        defaults={
            'rir': rir,
            **kwargs,
        },
    )[0]


def create_test_roa(name='ROA 1', signed_by=None, auto_renews=True, signed_object=None, **kwargs):
    if signed_by is None:
        signed_by = create_test_certificate()
    if signed_object is None and kwargs.pop('link_signed_object', False):
        organization = signed_by.rpki_org
        publication_point = create_test_publication_point(organization=organization)
        ee_certificate = create_test_end_entity_certificate(
            organization=organization,
            resource_certificate=signed_by,
            publication_point=publication_point,
            valid_from=kwargs.get('valid_from'),
            valid_to=kwargs.get('valid_to'),
        )
        signed_object = create_test_signed_object(
            name=f'{name} Signed Object',
            organization=organization,
            object_type=rpki_models.SignedObjectType.ROA,
            resource_certificate=signed_by,
            ee_certificate=ee_certificate,
            publication_point=publication_point,
            valid_from=kwargs.get('valid_from'),
            valid_to=kwargs.get('valid_to'),
        )
    return rpki_models.Roa.objects.create(
        name=name,
        signed_by=signed_by,
        signed_object=signed_object,
        auto_renews=auto_renews,
        **kwargs,
    )


def create_test_roa_prefix(prefix=None, roa=None, max_length=24, **kwargs):
    if prefix is None:
        prefix = create_test_prefix()
    if roa is None:
        roa = create_test_roa()
    return roa.RoaToPrefixTable.model.objects.create(
        prefix=prefix,
        roa_name=roa,
        max_length=max_length,
        **kwargs,
    )


def create_test_certificate_prefix(prefix=None, certificate=None, **kwargs):
    if prefix is None:
        prefix = create_test_prefix()
    if certificate is None:
        certificate = create_test_certificate()
    return rpki_models.CertificatePrefix.objects.create(prefix=prefix, certificate_name=certificate, **kwargs)


def create_test_certificate_asn(asn=None, certificate=None, **kwargs):
    if asn is None:
        asn = create_test_asn()
    if certificate is None:
        certificate = create_test_certificate()
    return rpki_models.CertificateAsn.objects.create(asn=asn, certificate_name2=certificate, **kwargs)


def get_rpki_model_class(model_name: str):
    return getattr(rpki_models, model_name)


def create_test_model(model_name: str, **kwargs):
    return get_rpki_model_class(model_name).objects.create(**kwargs)


def create_test_repository(
    name='Repository 1',
    organization=None,
    repository_type=None,
    rsync_base_uri='',
    rrdp_notify_uri='',
    status=None,
    last_observed_at=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.Repository.objects.create(
        name=name,
        organization=organization,
        repository_type=repository_type or rpki_models.RepositoryType.MIXED,
        rsync_base_uri=rsync_base_uri,
        rrdp_notify_uri=rrdp_notify_uri,
        status=status or rpki_models.ValidationState.UNKNOWN,
        last_observed_at=last_observed_at,
        **kwargs,
    )


def create_test_publication_point(
    name='Publication Point 1',
    organization=None,
    repository=None,
    publication_uri='',
    rsync_base_uri='',
    rrdp_notify_uri='',
    retrieval_state=None,
    validation_state=None,
    last_observed_at=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if repository is None:
        repository = create_test_repository(organization=organization)
    return rpki_models.PublicationPoint.objects.create(
        name=name,
        organization=organization,
        repository=repository,
        publication_uri=publication_uri,
        rsync_base_uri=rsync_base_uri,
        rrdp_notify_uri=rrdp_notify_uri,
        retrieval_state=retrieval_state or rpki_models.RetrievalState.UNKNOWN,
        validation_state=validation_state or rpki_models.ValidationState.UNKNOWN,
        last_observed_at=last_observed_at,
        **kwargs,
    )


def create_test_trust_anchor(
    name='Trust Anchor 1',
    organization=None,
    subject='',
    subject_key_identifier='',
    rsync_uri='',
    rrdp_notify_uri='',
    status=None,
    superseded_by=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.TrustAnchor.objects.create(
        name=name,
        organization=organization,
        subject=subject,
        subject_key_identifier=subject_key_identifier,
        rsync_uri=rsync_uri,
        rrdp_notify_uri=rrdp_notify_uri,
        status=status or rpki_models.ValidationState.UNKNOWN,
        superseded_by=superseded_by,
        **kwargs,
    )


def create_test_trust_anchor_locator(
    name='Trust Anchor Locator 1',
    trust_anchor=None,
    rsync_uri='',
    https_uri='',
    public_key_info='',
    is_active=True,
    **kwargs,
):
    if trust_anchor is None:
        trust_anchor = create_test_trust_anchor()
    return rpki_models.TrustAnchorLocator.objects.create(
        name=name,
        trust_anchor=trust_anchor,
        rsync_uri=rsync_uri,
        https_uri=https_uri,
        public_key_info=public_key_info,
        is_active=is_active,
        **kwargs,
    )


def create_test_end_entity_certificate(
    name='End Entity Certificate 1',
    organization=None,
    resource_certificate=None,
    publication_point=None,
    subject='',
    issuer='',
    serial='',
    ski='',
    aki='',
    valid_from=None,
    valid_to=None,
    public_key='',
    status=None,
    **kwargs,
):
    if resource_certificate is None:
        if organization is None:
            organization = create_test_organization()
        resource_certificate = create_test_certificate(rpki_org=organization)
    if organization is None:
        organization = resource_certificate.rpki_org
    if publication_point is None:
        publication_point = resource_certificate.publication_point
        if publication_point is None:
            publication_point = create_test_publication_point(organization=organization)
    return rpki_models.EndEntityCertificate.objects.create(
        name=name,
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
        subject=subject,
        issuer=issuer,
        serial=serial,
        ski=ski,
        aki=aki,
        valid_from=valid_from,
        valid_to=valid_to,
        public_key=public_key,
        status=status or rpki_models.ValidationState.UNKNOWN,
        **kwargs,
    )


def create_test_signed_object(
    name='Signed Object 1',
    organization=None,
    object_type=None,
    display_label='',
    resource_certificate=None,
    ee_certificate=None,
    publication_point=None,
    current_manifest=None,
    filename='',
    object_uri='',
    repository_uri='',
    content_hash='',
    serial_or_version='',
    cms_digest_algorithm='',
    cms_signature_algorithm='',
    publication_status=None,
    validation_state=None,
    valid_from=None,
    valid_to=None,
    raw_payload_reference='',
    **kwargs,
):
    if ee_certificate is not None:
        if organization is None:
            organization = ee_certificate.organization
        if resource_certificate is None:
            resource_certificate = ee_certificate.resource_certificate
        if publication_point is None:
            publication_point = ee_certificate.publication_point
    if organization is None:
        organization = create_test_organization()
    if resource_certificate is None:
        resource_certificate = create_test_certificate(rpki_org=organization)
    if ee_certificate is None:
        ee_certificate = create_test_end_entity_certificate(organization=organization, resource_certificate=resource_certificate)
    if publication_point is None:
        publication_point = ee_certificate.publication_point
        if publication_point is None:
            publication_point = create_test_publication_point(organization=organization)
    return rpki_models.SignedObject.objects.create(
        name=name,
        organization=organization,
        object_type=object_type or rpki_models.SignedObjectType.OTHER,
        display_label=display_label,
        resource_certificate=resource_certificate,
        ee_certificate=ee_certificate,
        publication_point=publication_point,
        current_manifest=current_manifest,
        filename=filename,
        object_uri=object_uri,
        repository_uri=repository_uri,
        content_hash=content_hash,
        serial_or_version=serial_or_version,
        cms_digest_algorithm=cms_digest_algorithm,
        cms_signature_algorithm=cms_signature_algorithm,
        publication_status=publication_status or rpki_models.PublicationStatus.DRAFT,
        validation_state=validation_state or rpki_models.ValidationState.UNKNOWN,
        valid_from=valid_from,
        valid_to=valid_to,
        raw_payload_reference=raw_payload_reference,
        **kwargs,
    )


def create_test_certificate_revocation_list(
    name='Certificate Revocation List 1',
    organization=None,
    issuing_certificate=None,
    signed_object=None,
    publication_point=None,
    manifest=None,
    crl_number='',
    this_update=None,
    next_update=None,
    publication_uri='',
    retrieval_state=None,
    validation_state=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if issuing_certificate is None:
        issuing_certificate = create_test_certificate(rpki_org=organization)
    if publication_point is None:
        publication_point = create_test_publication_point(organization=organization)
    return rpki_models.CertificateRevocationList.objects.create(
        name=name,
        organization=organization,
        issuing_certificate=issuing_certificate,
        signed_object=signed_object,
        publication_point=publication_point,
        manifest=manifest,
        crl_number=crl_number,
        this_update=this_update,
        next_update=next_update,
        publication_uri=publication_uri,
        retrieval_state=retrieval_state or rpki_models.RetrievalState.UNKNOWN,
        validation_state=validation_state or rpki_models.ValidationState.UNKNOWN,
        **kwargs,
    )


def create_test_revoked_certificate(
    revocation_list=None,
    certificate=None,
    ee_certificate=None,
    serial='',
    revoked_at=None,
    revocation_reason='',
    **kwargs,
):
    if revocation_list is None:
        revocation_list = create_test_certificate_revocation_list()
    if certificate is None:
        certificate = create_test_certificate()
    if ee_certificate is None:
        ee_certificate = create_test_end_entity_certificate()
    return rpki_models.RevokedCertificate.objects.create(
        revocation_list=revocation_list,
        certificate=certificate,
        ee_certificate=ee_certificate,
        serial=serial,
        revoked_at=revoked_at,
        revocation_reason=revocation_reason,
        **kwargs,
    )


def create_test_manifest(
    name='Manifest 1',
    signed_object=None,
    manifest_number='',
    this_update=None,
    next_update=None,
    current_crl=None,
    **kwargs,
):
    if signed_object is None:
        signed_object = create_test_signed_object()
    return rpki_models.Manifest.objects.create(
        name=name,
        signed_object=signed_object,
        manifest_number=manifest_number,
        this_update=this_update,
        next_update=next_update,
        current_crl=current_crl,
        **kwargs,
    )


def create_test_manifest_entry(
    manifest=None,
    signed_object=None,
    certificate=None,
    ee_certificate=None,
    revocation_list=None,
    filename='manifest-entry',
    hash_algorithm='',
    hash_value='',
    **kwargs,
):
    if manifest is None:
        manifest = create_test_manifest()
    return rpki_models.ManifestEntry.objects.create(
        manifest=manifest,
        signed_object=signed_object,
        certificate=certificate,
        ee_certificate=ee_certificate,
        revocation_list=revocation_list,
        filename=filename,
        hash_algorithm=hash_algorithm,
        hash_value=hash_value,
        **kwargs,
    )


def create_test_trust_anchor_key(
    name='Trust Anchor Key 1',
    trust_anchor=None,
    signed_object=None,
    current_public_key='',
    next_public_key='',
    valid_from=None,
    valid_to=None,
    publication_uri='',
    supersedes=None,
    **kwargs,
):
    if trust_anchor is None:
        trust_anchor = create_test_trust_anchor()
    if signed_object is None:
        signed_object = create_test_signed_object()
    return rpki_models.TrustAnchorKey.objects.create(
        name=name,
        trust_anchor=trust_anchor,
        signed_object=signed_object,
        current_public_key=current_public_key,
        next_public_key=next_public_key,
        valid_from=valid_from,
        valid_to=valid_to,
        publication_uri=publication_uri,
        supersedes=supersedes,
        **kwargs,
    )


def create_test_aspa(
    name='ASPA 1',
    organization=None,
    signed_object=None,
    customer_as=None,
    valid_from=None,
    valid_to=None,
    validation_state=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if customer_as is None:
        customer_as = create_test_asn()
    if signed_object is None:
        signed_object = create_test_signed_object(organization=organization)
    return rpki_models.ASPA.objects.create(
        name=name,
        organization=organization,
        signed_object=signed_object,
        customer_as=customer_as,
        valid_from=valid_from,
        valid_to=valid_to,
        validation_state=validation_state or rpki_models.ValidationState.UNKNOWN,
        **kwargs,
    )


def create_test_aspa_provider(aspa=None, provider_as=None, is_current=True, **kwargs):
    if aspa is None:
        aspa = create_test_aspa()
    if provider_as is None:
        provider_as = create_test_asn()
    return rpki_models.ASPAProvider.objects.create(
        aspa=aspa,
        provider_as=provider_as,
        is_current=is_current,
        **kwargs,
    )


def create_test_aspa_intent(
    name='ASPA Intent 1',
    organization=None,
    intent_key='',
    customer_as=None,
    provider_as=None,
    explanation='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if customer_as is None:
        customer_as = create_test_asn()
    if provider_as is None:
        provider_as = create_test_asn(customer_as.asn + 1)
    if not intent_key:
        intent_key = rpki_models.ASPAIntent.build_intent_key(
            customer_asn_value=customer_as.asn,
            provider_asn_value=provider_as.asn,
        )
    return rpki_models.ASPAIntent.objects.create(
        name=name,
        organization=organization,
        intent_key=intent_key,
        customer_as=customer_as,
        provider_as=provider_as,
        explanation=explanation,
        **kwargs,
    )


def create_test_rsc(
    name='RSC 1',
    organization=None,
    signed_object=None,
    version='',
    digest_algorithm='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if signed_object is None:
        signed_object = create_test_signed_object(organization=organization)
    return rpki_models.RSC.objects.create(
        name=name,
        organization=organization,
        signed_object=signed_object,
        version=version,
        digest_algorithm=digest_algorithm,
        **kwargs,
    )


def create_test_rsc_file_hash(
    rsc=None,
    filename='rsc-file',
    hash_algorithm='',
    hash_value='',
    artifact_reference='',
    **kwargs,
):
    if rsc is None:
        rsc = create_test_rsc()
    return rpki_models.RSCFileHash.objects.create(
        rsc=rsc,
        filename=filename,
        hash_algorithm=hash_algorithm,
        hash_value=hash_value,
        artifact_reference=artifact_reference,
        **kwargs,
    )


def create_test_router_certificate(
    name='Router Certificate 1',
    organization=None,
    resource_certificate=None,
    publication_point=None,
    ee_certificate=None,
    asn=None,
    subject='',
    issuer='',
    serial='',
    ski='',
    router_public_key='',
    valid_from=None,
    valid_to=None,
    status=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if resource_certificate is None:
        resource_certificate = create_test_certificate(rpki_org=organization)
    if publication_point is None:
        publication_point = create_test_publication_point(organization=organization)
    if ee_certificate is None and kwargs.pop('link_ee_certificate', False):
        ee_certificate = create_test_end_entity_certificate(
            organization=organization,
            resource_certificate=resource_certificate,
            publication_point=publication_point,
            subject=subject,
            issuer=issuer,
            serial=serial,
            ski=ski,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    if asn is None:
        asn = create_test_asn()
    return rpki_models.RouterCertificate.objects.create(
        name=name,
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
        ee_certificate=ee_certificate,
        asn=asn,
        subject=subject,
        issuer=issuer,
        serial=serial,
        ski=ski,
        router_public_key=router_public_key,
        valid_from=valid_from,
        valid_to=valid_to,
        status=status or rpki_models.ValidationState.UNKNOWN,
        **kwargs,
    )


def create_test_validator_instance(
    name='Validator Instance 1',
    organization=None,
    software_name='',
    software_version='',
    base_url='',
    status=None,
    last_run_at=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.ValidatorInstance.objects.create(
        name=name,
        organization=organization,
        software_name=software_name,
        software_version=software_version,
        base_url=base_url,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        last_run_at=last_run_at,
        **kwargs,
    )


def create_test_validation_run(
    name='Validation Run 1',
    validator=None,
    status=None,
    started_at=None,
    completed_at=None,
    repository_serial='',
    **kwargs,
):
    if validator is None:
        validator = create_test_validator_instance()
    return rpki_models.ValidationRun.objects.create(
        name=name,
        validator=validator,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        started_at=started_at,
        completed_at=completed_at,
        repository_serial=repository_serial,
        **kwargs,
    )


def create_test_object_validation_result(
    name='Object Validation Result 1',
    validation_run=None,
    signed_object=None,
    validation_state=None,
    disposition=None,
    observed_at=None,
    reason='',
    **kwargs,
):
    if validation_run is None:
        validation_run = create_test_validation_run()
    return rpki_models.ObjectValidationResult.objects.create(
        name=name,
        validation_run=validation_run,
        signed_object=signed_object,
        validation_state=validation_state or rpki_models.ValidationState.UNKNOWN,
        disposition=disposition or rpki_models.ValidationDisposition.NOTED,
        observed_at=observed_at,
        reason=reason,
        **kwargs,
    )


def create_test_validated_roa_payload(
    name='Validated ROA Payload 1',
    validation_run=None,
    roa=None,
    object_validation_result=None,
    prefix=None,
    origin_as=None,
    max_length=None,
    **kwargs,
):
    if validation_run is None:
        validation_run = create_test_validation_run()
    if roa is None:
        roa = create_test_roa()
    if prefix is None:
        prefix = create_test_prefix()
    if origin_as is None:
        origin_as = create_test_asn()
    return rpki_models.ValidatedRoaPayload.objects.create(
        name=name,
        validation_run=validation_run,
        roa=roa,
        object_validation_result=object_validation_result,
        prefix=prefix,
        origin_as=origin_as,
        max_length=max_length,
        **kwargs,
    )


def create_test_validated_aspa_payload(
    name='Validated ASPA Payload 1',
    validation_run=None,
    aspa=None,
    object_validation_result=None,
    customer_as=None,
    provider_as=None,
    **kwargs,
):
    if validation_run is None:
        validation_run = create_test_validation_run()
    if aspa is None:
        aspa = create_test_aspa()
    if customer_as is None:
        customer_as = create_test_asn()
    if provider_as is None:
        provider_as = create_test_asn()
    return rpki_models.ValidatedAspaPayload.objects.create(
        name=name,
        validation_run=validation_run,
        aspa=aspa,
        object_validation_result=object_validation_result,
        customer_as=customer_as,
        provider_as=provider_as,
        **kwargs,
    )


def create_test_routing_intent_profile(
    name='Routing Intent Profile 1',
    organization=None,
    is_default=False,
    status=None,
    description='',
    selector_mode=None,
    prefix_selector_query='',
    asn_selector_query='',
    default_max_length_policy=None,
    allow_as0=False,
    enabled=True,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.RoutingIntentProfile.objects.create(
        name=name,
        organization=organization,
        is_default=is_default,
        status=status or rpki_models.RoutingIntentProfileStatus.DRAFT,
        description=description,
        selector_mode=selector_mode or rpki_models.RoutingIntentSelectorMode.FILTERED,
        prefix_selector_query=prefix_selector_query,
        asn_selector_query=asn_selector_query,
        default_max_length_policy=default_max_length_policy or rpki_models.DefaultMaxLengthPolicy.EXACT,
        allow_as0=allow_as0,
        enabled=enabled,
        **kwargs,
    )


def create_test_routing_intent_rule(
    name='Routing Intent Rule 1',
    intent_profile=None,
    weight=100,
    action=None,
    address_family='',
    match_tenant=None,
    match_vrf=None,
    match_site=None,
    match_region=None,
    match_role='',
    match_tag='',
    match_custom_field='',
    origin_asn=None,
    max_length_mode=None,
    max_length_value=None,
    enabled=True,
    **kwargs,
):
    if intent_profile is None:
        intent_profile = create_test_routing_intent_profile()
    return rpki_models.RoutingIntentRule.objects.create(
        name=name,
        intent_profile=intent_profile,
        weight=weight,
        action=action or rpki_models.RoutingIntentRuleAction.INCLUDE,
        address_family=address_family,
        match_tenant=match_tenant,
        match_vrf=match_vrf,
        match_site=match_site,
        match_region=match_region,
        match_role=match_role,
        match_tag=match_tag,
        match_custom_field=match_custom_field,
        origin_asn=origin_asn,
        max_length_mode=max_length_mode or rpki_models.RoutingIntentRuleMaxLengthMode.INHERIT,
        max_length_value=max_length_value,
        enabled=enabled,
        **kwargs,
    )


def create_test_roa_intent_override(
    name='ROA Intent Override 1',
    organization=None,
    intent_profile=None,
    action=None,
    prefix=None,
    prefix_cidr_text='',
    origin_asn=None,
    origin_asn_value=None,
    max_length=None,
    tenant_scope=None,
    vrf_scope=None,
    site_scope=None,
    region_scope=None,
    reason='',
    starts_at=None,
    ends_at=None,
    enabled=True,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.ROAIntentOverride.objects.create(
        name=name,
        organization=organization,
        intent_profile=intent_profile,
        action=action or rpki_models.ROAIntentOverrideAction.FORCE_INCLUDE,
        prefix=prefix,
        prefix_cidr_text=prefix_cidr_text,
        origin_asn=origin_asn,
        origin_asn_value=origin_asn_value,
        max_length=max_length,
        tenant_scope=tenant_scope,
        vrf_scope=vrf_scope,
        site_scope=site_scope,
        region_scope=region_scope,
        reason=reason,
        starts_at=starts_at,
        ends_at=ends_at,
        enabled=enabled,
        **kwargs,
    )


def create_test_routing_intent_template(
    name='Routing Intent Template 1',
    organization=None,
    status=None,
    description='',
    enabled=True,
    template_version=1,
    template_fingerprint='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.RoutingIntentTemplate.objects.create(
        name=name,
        organization=organization,
        status=status or rpki_models.RoutingIntentTemplateStatus.DRAFT,
        description=description,
        enabled=enabled,
        template_version=template_version,
        template_fingerprint=template_fingerprint,
        **kwargs,
    )


def create_test_routing_intent_template_rule(
    name='Routing Intent Template Rule 1',
    template=None,
    weight=100,
    action=None,
    address_family='',
    match_tenant=None,
    match_vrf=None,
    match_site=None,
    match_region=None,
    match_role='',
    match_tag='',
    match_custom_field='',
    origin_asn=None,
    max_length_mode=None,
    max_length_value=None,
    enabled=True,
    **kwargs,
):
    if template is None:
        template = create_test_routing_intent_template()
    return rpki_models.RoutingIntentTemplateRule.objects.create(
        name=name,
        template=template,
        weight=weight,
        action=action or rpki_models.RoutingIntentRuleAction.INCLUDE,
        address_family=address_family,
        match_tenant=match_tenant,
        match_vrf=match_vrf,
        match_site=match_site,
        match_region=match_region,
        match_role=match_role,
        match_tag=match_tag,
        match_custom_field=match_custom_field,
        origin_asn=origin_asn,
        max_length_mode=max_length_mode or rpki_models.RoutingIntentRuleMaxLengthMode.INHERIT,
        max_length_value=max_length_value,
        enabled=enabled,
        **kwargs,
    )


def create_test_routing_intent_template_binding(
    name='Routing Intent Template Binding 1',
    template=None,
    intent_profile=None,
    enabled=True,
    binding_priority=100,
    binding_label='',
    origin_asn_override=None,
    max_length_mode=None,
    max_length_value=None,
    prefix_selector_query='',
    asn_selector_query='',
    state=None,
    last_compiled_fingerprint='',
    summary_json=None,
    **kwargs,
):
    if template is None and intent_profile is None:
        organization = create_test_organization()
        template = create_test_routing_intent_template(organization=organization)
        intent_profile = create_test_routing_intent_profile(organization=organization)
    elif template is None:
        template = create_test_routing_intent_template(organization=intent_profile.organization)
    elif intent_profile is None:
        intent_profile = create_test_routing_intent_profile(organization=template.organization)
    return rpki_models.RoutingIntentTemplateBinding.objects.create(
        name=name,
        template=template,
        intent_profile=intent_profile,
        enabled=enabled,
        binding_priority=binding_priority,
        binding_label=binding_label,
        origin_asn_override=origin_asn_override,
        max_length_mode=max_length_mode or rpki_models.RoutingIntentRuleMaxLengthMode.INHERIT,
        max_length_value=max_length_value,
        prefix_selector_query=prefix_selector_query,
        asn_selector_query=asn_selector_query,
        state=state or rpki_models.RoutingIntentTemplateBindingState.PENDING,
        last_compiled_fingerprint=last_compiled_fingerprint,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_routing_intent_exception(
    name='Routing Intent Exception 1',
    organization=None,
    intent_profile=None,
    template_binding=None,
    exception_type=None,
    effect_mode=None,
    prefix=None,
    prefix_cidr_text='',
    origin_asn=None,
    origin_asn_value=None,
    max_length=None,
    tenant_scope=None,
    vrf_scope=None,
    site_scope=None,
    region_scope=None,
    starts_at=None,
    ends_at=None,
    reason='',
    approved_by='',
    approved_at=None,
    enabled=True,
    summary_json=None,
    **kwargs,
):
    if organization is None:
        if template_binding is not None:
            organization = template_binding.intent_profile.organization
        elif intent_profile is not None:
            organization = intent_profile.organization
        else:
            organization = create_test_organization()
    if intent_profile is None and template_binding is not None:
        intent_profile = template_binding.intent_profile
    elif intent_profile is None and template_binding is None:
        intent_profile = create_test_routing_intent_profile(organization=organization)
    return rpki_models.RoutingIntentException.objects.create(
        name=name,
        organization=organization,
        intent_profile=intent_profile,
        template_binding=template_binding,
        exception_type=exception_type or rpki_models.RoutingIntentExceptionType.TRAFFIC_ENGINEERING,
        effect_mode=effect_mode or rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS,
        prefix=prefix,
        prefix_cidr_text=prefix_cidr_text,
        origin_asn=origin_asn,
        origin_asn_value=origin_asn_value,
        max_length=max_length,
        tenant_scope=tenant_scope,
        vrf_scope=vrf_scope,
        site_scope=site_scope,
        region_scope=region_scope,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
        approved_by=approved_by,
        approved_at=approved_at,
        enabled=enabled,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_bulk_intent_run(
    name='Bulk Intent Run 1',
    organization=None,
    status=None,
    trigger_mode=None,
    target_mode=None,
    baseline_fingerprint='',
    resulting_fingerprint='',
    started_at=None,
    completed_at=None,
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.BulkIntentRun.objects.create(
        name=name,
        organization=organization,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        trigger_mode=trigger_mode or rpki_models.IntentRunTriggerMode.MANUAL,
        target_mode=target_mode or rpki_models.BulkIntentTargetMode.BINDINGS,
        baseline_fingerprint=baseline_fingerprint,
        resulting_fingerprint=resulting_fingerprint,
        started_at=started_at,
        completed_at=completed_at,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_bulk_intent_run_scope_result(
    name='Bulk Intent Run Scope Result 1',
    bulk_run=None,
    intent_profile=None,
    template_binding=None,
    status=None,
    scope_kind='',
    scope_key='scope-1',
    derivation_run=None,
    reconciliation_run=None,
    change_plan=None,
    prefix_count_scanned=0,
    intent_count_emitted=0,
    plan_item_count=0,
    summary_json=None,
    **kwargs,
):
    if bulk_run is None and intent_profile is None and template_binding is None:
        organization = create_test_organization()
        bulk_run = create_test_bulk_intent_run(organization=organization)
        intent_profile = create_test_routing_intent_profile(organization=organization)
    elif bulk_run is None:
        if template_binding is not None:
            organization = template_binding.intent_profile.organization
        else:
            organization = intent_profile.organization
        bulk_run = create_test_bulk_intent_run(organization=organization)
    if intent_profile is None and template_binding is not None:
        intent_profile = template_binding.intent_profile
    elif intent_profile is None:
        intent_profile = create_test_routing_intent_profile(organization=bulk_run.organization)
    return rpki_models.BulkIntentRunScopeResult.objects.create(
        name=name,
        bulk_run=bulk_run,
        intent_profile=intent_profile,
        template_binding=template_binding,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        scope_kind=scope_kind,
        scope_key=scope_key,
        derivation_run=derivation_run,
        reconciliation_run=reconciliation_run,
        change_plan=change_plan,
        prefix_count_scanned=prefix_count_scanned,
        intent_count_emitted=intent_count_emitted,
        plan_item_count=plan_item_count,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_intent_derivation_run(
    name='Intent Derivation Run 1',
    organization=None,
    intent_profile=None,
    status=None,
    trigger_mode=None,
    started_at=None,
    completed_at=None,
    input_fingerprint='',
    prefix_count_scanned=0,
    intent_count_emitted=0,
    warning_count=0,
    error_summary='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if intent_profile is None:
        intent_profile = create_test_routing_intent_profile(organization=organization)
    return rpki_models.IntentDerivationRun.objects.create(
        name=name,
        organization=organization,
        intent_profile=intent_profile,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        trigger_mode=trigger_mode or rpki_models.IntentRunTriggerMode.MANUAL,
        started_at=started_at,
        completed_at=completed_at,
        input_fingerprint=input_fingerprint,
        prefix_count_scanned=prefix_count_scanned,
        intent_count_emitted=intent_count_emitted,
        warning_count=warning_count,
        error_summary=error_summary,
        **kwargs,
    )


def create_test_roa_intent(
    name='ROA Intent 1',
    derivation_run=None,
    organization=None,
    intent_profile=None,
    intent_key='',
    prefix=None,
    prefix_cidr_text='',
    address_family=None,
    origin_asn=None,
    origin_asn_value=None,
    is_as0=False,
    max_length=None,
    scope_tenant=None,
    scope_vrf=None,
    scope_site=None,
    scope_region=None,
    source_rule=None,
    applied_override=None,
    derived_state=None,
    exposure_state=None,
    explanation='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if intent_profile is None:
        intent_profile = create_test_routing_intent_profile(organization=organization)
    if derivation_run is None:
        derivation_run = create_test_intent_derivation_run(organization=organization, intent_profile=intent_profile)
    if prefix is None and not prefix_cidr_text:
        prefix = create_test_prefix()
    resolved_prefix_text = prefix_cidr_text or (str(prefix.prefix) if prefix is not None else '')
    if not intent_key:
        intent_key = rpki_models.ROAIntent.build_intent_key(
            prefix_cidr_text=resolved_prefix_text,
            address_family=address_family or rpki_models.AddressFamily.IPV4,
            origin_asn_value=origin_asn_value if origin_asn_value is not None else getattr(origin_asn, 'asn', None),
            max_length=max_length,
            tenant_id=getattr(scope_tenant, 'pk', None),
            vrf_id=getattr(scope_vrf, 'pk', None),
            site_id=getattr(scope_site, 'pk', None),
            region_id=getattr(scope_region, 'pk', None),
        )
    return rpki_models.ROAIntent.objects.create(
        name=name,
        derivation_run=derivation_run,
        organization=organization,
        intent_profile=intent_profile,
        intent_key=intent_key,
        prefix=prefix,
        prefix_cidr_text=resolved_prefix_text,
        address_family=address_family or rpki_models.AddressFamily.IPV4,
        origin_asn=origin_asn,
        origin_asn_value=origin_asn_value,
        is_as0=is_as0,
        max_length=max_length,
        scope_tenant=scope_tenant,
        scope_vrf=scope_vrf,
        scope_site=scope_site,
        scope_region=scope_region,
        source_rule=source_rule,
        applied_override=applied_override,
        derived_state=derived_state or rpki_models.ROAIntentDerivedState.ACTIVE,
        exposure_state=exposure_state or rpki_models.ROAIntentExposureState.ELIGIBLE_NOT_ADVERTISED,
        explanation=explanation,
        **kwargs,
    )


def create_test_provider_snapshot(
    name='Provider Snapshot 1',
    provider_account=None,
    organization=None,
    provider_name='ARIN',
    status=None,
    fetched_at=None,
    completed_at=None,
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.ProviderSnapshot.objects.create(
        name=name,
        provider_account=provider_account,
        organization=organization,
        provider_name=provider_name,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        fetched_at=fetched_at,
        completed_at=completed_at,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_imported_signed_object(
    name='Imported Signed Object 1',
    provider_snapshot=None,
    organization=None,
    publication_point=None,
    authored_signed_object=None,
    signed_object_key='',
    signed_object_type=None,
    publication_uri='rsync://example.invalid/repo/',
    signed_object_uri='rsync://example.invalid/repo/object.mft',
    object_hash='',
    body_base64='ZHVtbXk=',
    external_object_id='',
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if publication_point is None:
        publication_point = create_test_imported_publication_point(
            organization=organization,
            provider_snapshot=provider_snapshot,
            publication_uri=publication_uri,
        )
    if not signed_object_key:
        signed_object_key = rpki_models.ImportedSignedObject.build_signed_object_key(
            publication_uri=publication_uri,
            signed_object_uri=signed_object_uri,
            object_hash=object_hash,
        )
    return rpki_models.ImportedSignedObject.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        publication_point=publication_point,
        authored_signed_object=authored_signed_object,
        signed_object_key=signed_object_key,
        signed_object_type=signed_object_type or rpki_models.SignedObjectType.MANIFEST,
        publication_uri=publication_uri,
        signed_object_uri=signed_object_uri,
        object_hash=object_hash,
        body_base64=body_base64,
        external_object_id=external_object_id,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_provider_account(
    name='Provider Account 1',
    organization=None,
    provider_type=None,
    transport=None,
    org_handle='ORG-TEST',
    ca_handle='',
    api_key='test-api-key',
    api_base_url='https://reg.arin.net',
    sync_enabled=True,
    sync_interval=None,
    last_successful_sync=None,
    last_sync_status=None,
    last_sync_summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    return rpki_models.RpkiProviderAccount.objects.create(
        name=name,
        organization=organization,
        provider_type=provider_type or rpki_models.ProviderType.ARIN,
        transport=transport or rpki_models.ProviderSyncTransport.PRODUCTION,
        org_handle=org_handle,
        ca_handle=ca_handle,
        api_key=api_key,
        api_base_url=api_base_url,
        sync_enabled=sync_enabled,
        sync_interval=sync_interval,
        last_successful_sync=last_successful_sync,
        last_sync_status=last_sync_status or rpki_models.ValidationRunStatus.PENDING,
        last_sync_summary_json=last_sync_summary_json or {},
        **kwargs,
    )


def create_test_provider_sync_run(
    name='Provider Sync Run 1',
    organization=None,
    provider_account=None,
    provider_snapshot=None,
    status=None,
    started_at=None,
    completed_at=None,
    records_fetched=0,
    records_imported=0,
    error='',
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_account is None:
        provider_account = create_test_provider_account(organization=organization)
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization, provider_account=provider_account)
    return rpki_models.ProviderSyncRun.objects.create(
        name=name,
        organization=organization,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        records_fetched=records_fetched,
        records_imported=records_imported,
        error=error,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_provider_snapshot_diff(
    name='Provider Snapshot Diff 1',
    organization=None,
    provider_account=None,
    base_snapshot=None,
    comparison_snapshot=None,
    status=None,
    compared_at=None,
    error='',
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_account is None:
        provider_account = create_test_provider_account(organization=organization)
    if base_snapshot is None:
        base_snapshot = create_test_provider_snapshot(
            name=f'{name} Base Snapshot',
            organization=organization,
            provider_account=provider_account,
        )
    if comparison_snapshot is None:
        comparison_snapshot = create_test_provider_snapshot(
            name=f'{name} Comparison Snapshot',
            organization=organization,
            provider_account=provider_account,
        )
    return rpki_models.ProviderSnapshotDiff.objects.create(
        name=name,
        organization=organization,
        provider_account=provider_account,
        base_snapshot=base_snapshot,
        comparison_snapshot=comparison_snapshot,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        compared_at=compared_at,
        error=error,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_provider_snapshot_diff_item(
    name='Provider Snapshot Diff Item 1',
    snapshot_diff=None,
    object_family=None,
    change_type=None,
    external_reference=None,
    provider_identity='provider-identity-1',
    external_object_id='external-object-1',
    before_state_json=None,
    after_state_json=None,
    prefix_cidr_text='',
    origin_asn_value=None,
    customer_as_value=None,
    provider_as_value=None,
    related_handle='',
    certificate_identifier='',
    publication_uri='',
    signed_object_uri='',
    is_stale=False,
    **kwargs,
):
    if snapshot_diff is None:
        snapshot_diff = create_test_provider_snapshot_diff()
    return rpki_models.ProviderSnapshotDiffItem.objects.create(
        name=name,
        snapshot_diff=snapshot_diff,
        object_family=object_family or rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
        change_type=change_type or rpki_models.ProviderSnapshotDiffChangeType.CHANGED,
        external_reference=external_reference,
        provider_identity=provider_identity,
        external_object_id=external_object_id,
        before_state_json=before_state_json or {},
        after_state_json=after_state_json or {},
        prefix_cidr_text=prefix_cidr_text,
        origin_asn_value=origin_asn_value,
        customer_as_value=customer_as_value,
        provider_as_value=provider_as_value,
        related_handle=related_handle,
        certificate_identifier=certificate_identifier,
        publication_uri=publication_uri,
        signed_object_uri=signed_object_uri,
        is_stale=is_stale,
        **kwargs,
    )


def create_test_external_object_reference(
    name='External Object Reference 1',
    organization=None,
    provider_account=None,
    object_type=None,
    provider_identity='provider-object-1',
    external_object_id='provider-object-1',
    last_seen_provider_snapshot=None,
    last_seen_imported_authorization=None,
    last_seen_imported_aspa=None,
    last_seen_at=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_account is None:
        provider_account = create_test_provider_account(organization=organization)
    if last_seen_provider_snapshot is None:
        last_seen_provider_snapshot = create_test_provider_snapshot(
            organization=organization,
            provider_account=provider_account,
        )
    return rpki_models.ExternalObjectReference.objects.create(
        name=name,
        organization=organization,
        provider_account=provider_account,
        object_type=object_type or rpki_models.ExternalObjectType.ROA_AUTHORIZATION,
        provider_identity=provider_identity,
        external_object_id=external_object_id,
        last_seen_provider_snapshot=last_seen_provider_snapshot,
        last_seen_imported_authorization=last_seen_imported_authorization,
        last_seen_imported_aspa=last_seen_imported_aspa,
        last_seen_at=last_seen_at,
        **kwargs,
    )


def create_test_imported_roa_authorization(
    name='Imported ROA Authorization 1',
    provider_snapshot=None,
    organization=None,
    authorization_key='',
    prefix=None,
    prefix_cidr_text='',
    address_family=None,
    origin_asn=None,
    origin_asn_value=None,
    max_length=None,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if prefix is None and not prefix_cidr_text:
        prefix = create_test_prefix()
    resolved_prefix_text = prefix_cidr_text or (str(prefix.prefix) if prefix is not None else '')
    resolved_origin_value = origin_asn_value if origin_asn_value is not None else getattr(origin_asn, 'asn', None)
    if not authorization_key:
        authorization_key = rpki_models.ImportedRoaAuthorization.build_authorization_key(
            prefix_cidr_text=resolved_prefix_text,
            address_family=address_family or rpki_models.AddressFamily.IPV4,
            origin_asn_value=resolved_origin_value,
            max_length=max_length,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedRoaAuthorization.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        authorization_key=authorization_key,
        prefix=prefix,
        prefix_cidr_text=resolved_prefix_text,
        address_family=address_family or rpki_models.AddressFamily.IPV4,
        origin_asn=origin_asn,
        origin_asn_value=resolved_origin_value,
        max_length=max_length,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_aspa(
    name='Imported ASPA 1',
    provider_snapshot=None,
    organization=None,
    authorization_key='',
    customer_as=None,
    customer_as_value=None,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    resolved_customer_value = customer_as_value if customer_as_value is not None else getattr(customer_as, 'asn', None)
    if not authorization_key:
        authorization_key = rpki_models.ImportedAspa.build_authorization_key(
            customer_as_value=resolved_customer_value,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedAspa.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        authorization_key=authorization_key,
        customer_as=customer_as,
        customer_as_value=resolved_customer_value,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_aspa_provider(
    imported_aspa=None,
    provider_as=None,
    provider_as_value=None,
    address_family='',
    raw_provider_text='',
    **kwargs,
):
    if imported_aspa is None:
        imported_aspa = create_test_imported_aspa()
    resolved_provider_value = provider_as_value if provider_as_value is not None else getattr(provider_as, 'asn', None)
    if not raw_provider_text and resolved_provider_value is not None:
        raw_provider_text = f'AS{resolved_provider_value}'
        if address_family == rpki_models.AddressFamily.IPV4:
            raw_provider_text += '(v4)'
        elif address_family == rpki_models.AddressFamily.IPV6:
            raw_provider_text += '(v6)'
    return rpki_models.ImportedAspaProvider.objects.create(
        imported_aspa=imported_aspa,
        provider_as=provider_as,
        provider_as_value=resolved_provider_value,
        address_family=address_family,
        raw_provider_text=raw_provider_text,
        **kwargs,
    )


def create_test_imported_ca_metadata(
    name='Imported CA Metadata 1',
    provider_snapshot=None,
    organization=None,
    metadata_key='',
    ca_handle='netbox-rpki-dev',
    id_cert_hash='krill-ca-id-cert-sha256',
    publication_uri='rsync://testbed.krill.cloud/repo/netbox-rpki-dev/',
    rrdp_notification_uri='https://testbed.krill.cloud/rrdp/notification.xml',
    parent_count=1,
    child_count=1,
    suspended_child_count=0,
    resource_class_count=1,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if not metadata_key:
        metadata_key = rpki_models.ImportedCaMetadata.build_metadata_key(
            ca_handle=ca_handle,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedCaMetadata.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        metadata_key=metadata_key,
        ca_handle=ca_handle,
        id_cert_hash=id_cert_hash,
        publication_uri=publication_uri,
        rrdp_notification_uri=rrdp_notification_uri,
        parent_count=parent_count,
        child_count=child_count,
        suspended_child_count=suspended_child_count,
        resource_class_count=resource_class_count,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_parent_link(
    name='Imported Parent Link 1',
    provider_snapshot=None,
    organization=None,
    link_key='',
    parent_handle='testbed',
    relationship_type='rfc6492',
    service_uri='https://testbed.krill.cloud/rfc6492/testbed/',
    last_exchange_at=None,
    last_exchange_result='Success',
    last_success_at=None,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if not link_key:
        link_key = rpki_models.ImportedParentLink.build_link_key(
            parent_handle=parent_handle,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedParentLink.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        link_key=link_key,
        parent_handle=parent_handle,
        relationship_type=relationship_type,
        service_uri=service_uri,
        last_exchange_at=last_exchange_at,
        last_exchange_result=last_exchange_result,
        last_success_at=last_success_at,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_child_link(
    name='Imported Child Link 1',
    provider_snapshot=None,
    organization=None,
    link_key='',
    child_handle='edge-customer-01',
    state='active',
    id_cert_hash='krill-child-id-cert-sha256',
    user_agent='krill/0.16.0',
    last_exchange_at=None,
    last_exchange_result='Success',
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if not link_key:
        link_key = rpki_models.ImportedChildLink.build_link_key(
            child_handle=child_handle,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedChildLink.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        link_key=link_key,
        child_handle=child_handle,
        state=state,
        id_cert_hash=id_cert_hash,
        user_agent=user_agent,
        last_exchange_at=last_exchange_at,
        last_exchange_result=last_exchange_result,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_resource_entitlement(
    name='Imported Resource Entitlement 1',
    provider_snapshot=None,
    organization=None,
    entitlement_key='',
    entitlement_source=None,
    related_handle='',
    class_name='',
    asn_resources='AS65000-AS65010',
    ipv4_resources='10.10.0.0/24',
    ipv6_resources='',
    not_after=None,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    resolved_source = entitlement_source or rpki_models.ImportedResourceEntitlementSource.CA
    if not entitlement_key:
        entitlement_key = rpki_models.ImportedResourceEntitlement.build_entitlement_key(
            entitlement_source=resolved_source,
            related_handle=related_handle,
            class_name=class_name,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedResourceEntitlement.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        entitlement_key=entitlement_key,
        entitlement_source=resolved_source,
        related_handle=related_handle,
        class_name=class_name,
        asn_resources=asn_resources,
        ipv4_resources=ipv4_resources,
        ipv6_resources=ipv6_resources,
        not_after=not_after,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_publication_point(
    name='Imported Publication Point 1',
    provider_snapshot=None,
    organization=None,
    authored_publication_point=None,
    publication_key='',
    service_uri='https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/',
    publication_uri='rsync://testbed.krill.cloud/repo/netbox-rpki-dev/',
    rrdp_notification_uri='https://testbed.krill.cloud/rrdp/notification.xml',
    last_exchange_at=None,
    last_exchange_result='Success',
    next_exchange_before=None,
    published_object_count=2,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if not publication_key:
        publication_key = rpki_models.ImportedPublicationPoint.build_publication_key(
            service_uri=service_uri,
            publication_uri=publication_uri,
            external_object_id=external_object_id,
        )
    return rpki_models.ImportedPublicationPoint.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        authored_publication_point=authored_publication_point,
        publication_key=publication_key,
        service_uri=service_uri,
        publication_uri=publication_uri,
        rrdp_notification_uri=rrdp_notification_uri,
        last_exchange_at=last_exchange_at,
        last_exchange_result=last_exchange_result,
        next_exchange_before=next_exchange_before,
        published_object_count=published_object_count,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_imported_certificate_observation(
    name='Imported Certificate Observation 1',
    provider_snapshot=None,
    organization=None,
    certificate_key='deadbeef',
    observation_source=None,
    publication_point=None,
    signed_object=None,
    certificate_uri='rsync://example.invalid/repo/example.cer',
    publication_uri='rsync://example.invalid/repo/',
    signed_object_uri='',
    related_handle='',
    class_name='',
    subject='CN=Example',
    issuer='CN=Issuer',
    serial_number='1',
    not_before=None,
    not_after=None,
    external_object_id='',
    external_reference=None,
    is_stale=False,
    payload_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    if not external_object_id:
        external_object_id = certificate_key
    return rpki_models.ImportedCertificateObservation.objects.create(
        name=name,
        provider_snapshot=provider_snapshot,
        organization=organization,
        certificate_key=rpki_models.ImportedCertificateObservation.build_certificate_key(
            certificate_key=certificate_key,
        ),
        observation_source=observation_source or rpki_models.CertificateObservationSource.SIGNED_OBJECT_EE,
        publication_point=publication_point,
        signed_object=signed_object,
        certificate_uri=certificate_uri,
        publication_uri=publication_uri,
        signed_object_uri=signed_object_uri,
        related_handle=related_handle,
        class_name=class_name,
        subject=subject,
        issuer=issuer,
        serial_number=serial_number,
        not_before=not_before,
        not_after=not_after,
        external_object_id=external_object_id,
        external_reference=external_reference,
        is_stale=is_stale,
        payload_json=payload_json or {},
        **kwargs,
    )


def create_test_aspa_intent_match(
    name='ASPA Intent Match 1',
    aspa_intent=None,
    aspa=None,
    imported_aspa=None,
    match_kind=None,
    is_best_match=False,
    details_json=None,
    **kwargs,
):
    if aspa_intent is None:
        aspa_intent = create_test_aspa_intent()
    if aspa is None and imported_aspa is None:
        aspa = create_test_aspa(customer_as=aspa_intent.customer_as)
    return rpki_models.ASPAIntentMatch.objects.create(
        name=name,
        aspa_intent=aspa_intent,
        aspa=aspa,
        imported_aspa=imported_aspa,
        match_kind=match_kind or rpki_models.ASPAIntentMatchKind.EXACT,
        is_best_match=is_best_match,
        details_json=details_json or {},
        **kwargs,
    )


def create_test_roa_intent_match(
    name='ROA Intent Match 1',
    roa_intent=None,
    roa=None,
    imported_authorization=None,
    match_kind=None,
    is_best_match=False,
    details_json=None,
    **kwargs,
):
    if roa_intent is None:
        roa_intent = create_test_roa_intent(origin_asn=create_test_asn())
    if roa is None and imported_authorization is None:
        roa = create_test_roa(origin_as=roa_intent.origin_asn, signed_by=create_test_certificate())
    return rpki_models.ROAIntentMatch.objects.create(
        name=name,
        roa_intent=roa_intent,
        roa=roa,
        imported_authorization=imported_authorization,
        match_kind=match_kind or rpki_models.ROAIntentMatchKind.EXACT,
        is_best_match=is_best_match,
        details_json=details_json or {},
        **kwargs,
    )


def create_test_roa_reconciliation_run(
    name='ROA Reconciliation Run 1',
    organization=None,
    intent_profile=None,
    basis_derivation_run=None,
    provider_snapshot=None,
    comparison_scope=None,
    status=None,
    started_at=None,
    completed_at=None,
    published_roa_count=0,
    intent_count=0,
    result_summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if intent_profile is None:
        intent_profile = create_test_routing_intent_profile(organization=organization)
    if basis_derivation_run is None:
        basis_derivation_run = create_test_intent_derivation_run(organization=organization, intent_profile=intent_profile)
    return rpki_models.ROAReconciliationRun.objects.create(
        name=name,
        organization=organization,
        intent_profile=intent_profile,
        basis_derivation_run=basis_derivation_run,
        provider_snapshot=provider_snapshot,
        comparison_scope=comparison_scope or rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        started_at=started_at,
        completed_at=completed_at,
        published_roa_count=published_roa_count,
        intent_count=intent_count,
        result_summary_json=result_summary_json or {},
        **kwargs,
    )


def create_test_roa_lint_run(
    name='ROA Lint Run 1',
    reconciliation_run=None,
    change_plan=None,
    status=None,
    started_at=None,
    completed_at=None,
    finding_count=0,
    info_count=0,
    warning_count=0,
    error_count=0,
    critical_count=0,
    summary_json=None,
    **kwargs,
):
    if reconciliation_run is None:
        reconciliation_run = create_test_roa_reconciliation_run()
    return rpki_models.ROALintRun.objects.create(
        name=name,
        reconciliation_run=reconciliation_run,
        change_plan=change_plan,
        tenant=reconciliation_run.tenant,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        finding_count=finding_count,
        info_count=info_count,
        warning_count=warning_count,
        error_count=error_count,
        critical_count=critical_count,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_aspa_reconciliation_run(
    name='ASPA Reconciliation Run 1',
    organization=None,
    provider_snapshot=None,
    comparison_scope=None,
    status=None,
    started_at=None,
    completed_at=None,
    intent_count=0,
    published_aspa_count=0,
    result_summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    resolved_scope = comparison_scope or rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS
    if provider_snapshot is None and resolved_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
        provider_snapshot = create_test_provider_snapshot(organization=organization)
    return rpki_models.ASPAReconciliationRun.objects.create(
        name=name,
        organization=organization,
        provider_snapshot=provider_snapshot,
        comparison_scope=resolved_scope,
        status=status or rpki_models.ValidationRunStatus.PENDING,
        started_at=started_at,
        completed_at=completed_at,
        intent_count=intent_count,
        published_aspa_count=published_aspa_count,
        result_summary_json=result_summary_json or {},
        **kwargs,
    )


def create_test_aspa_intent_result(
    name='ASPA Intent Result 1',
    reconciliation_run=None,
    aspa_intent=None,
    result_type=None,
    severity=None,
    best_aspa=None,
    best_imported_aspa=None,
    match_count=0,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if aspa_intent is None:
        aspa_intent = create_test_aspa_intent()
    if reconciliation_run is None:
        run_scope = rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS
        provider_snapshot = None
        if best_imported_aspa is not None and best_aspa is None:
            run_scope = rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED
            provider_snapshot = best_imported_aspa.provider_snapshot
        reconciliation_run = create_test_aspa_reconciliation_run(
            organization=aspa_intent.organization,
            provider_snapshot=provider_snapshot,
            comparison_scope=run_scope,
        )
    return rpki_models.ASPAIntentResult.objects.create(
        name=name,
        reconciliation_run=reconciliation_run,
        aspa_intent=aspa_intent,
        result_type=result_type or rpki_models.ASPAIntentResultType.MATCH,
        severity=severity or rpki_models.ReconciliationSeverity.INFO,
        best_aspa=best_aspa,
        best_imported_aspa=best_imported_aspa,
        match_count=match_count,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_published_aspa_result(
    name='Published ASPA Result 1',
    reconciliation_run=None,
    aspa=None,
    imported_aspa=None,
    result_type=None,
    severity=None,
    matched_intent_count=0,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if aspa is None and imported_aspa is None:
        aspa = create_test_aspa()
    if reconciliation_run is None:
        run_scope = rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS
        provider_snapshot = None
        if imported_aspa is not None and aspa is None:
            run_scope = rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED
            provider_snapshot = imported_aspa.provider_snapshot
        reconciliation_run = create_test_aspa_reconciliation_run(
            organization=getattr(aspa, 'organization', None) or getattr(imported_aspa, 'organization', None),
            provider_snapshot=provider_snapshot,
            comparison_scope=run_scope,
        )
    return rpki_models.PublishedASPAResult.objects.create(
        name=name,
        reconciliation_run=reconciliation_run,
        aspa=aspa,
        imported_aspa=imported_aspa,
        result_type=result_type or rpki_models.PublishedASPAResultType.MATCHED,
        severity=severity or rpki_models.ReconciliationSeverity.INFO,
        matched_intent_count=matched_intent_count,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_roa_intent_result(
    name='ROA Intent Result 1',
    reconciliation_run=None,
    roa_intent=None,
    result_type=None,
    severity=None,
    best_roa=None,
    best_imported_authorization=None,
    match_count=0,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if roa_intent is None:
        roa_intent = create_test_roa_intent(origin_asn=create_test_asn())
    if reconciliation_run is None:
        reconciliation_run = create_test_roa_reconciliation_run(
            organization=roa_intent.organization,
            intent_profile=roa_intent.intent_profile,
            basis_derivation_run=roa_intent.derivation_run,
        )
    return rpki_models.ROAIntentResult.objects.create(
        name=name,
        reconciliation_run=reconciliation_run,
        roa_intent=roa_intent,
        result_type=result_type or rpki_models.ROAIntentResultType.MATCH,
        severity=severity or rpki_models.ReconciliationSeverity.INFO,
        best_roa=best_roa,
        best_imported_authorization=best_imported_authorization,
        match_count=match_count,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_published_roa_result(
    name='Published ROA Result 1',
    reconciliation_run=None,
    roa=None,
    imported_authorization=None,
    result_type=None,
    severity=None,
    matched_intent_count=0,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if roa is None and imported_authorization is None:
        roa = create_test_roa()
    if reconciliation_run is None:
        organization = create_test_organization()
        intent_profile = create_test_routing_intent_profile(organization=organization)
        basis_derivation_run = create_test_intent_derivation_run(organization=organization, intent_profile=intent_profile)
        reconciliation_run = create_test_roa_reconciliation_run(
            organization=organization,
            intent_profile=intent_profile,
            basis_derivation_run=basis_derivation_run,
        )
    return rpki_models.PublishedROAResult.objects.create(
        name=name,
        reconciliation_run=reconciliation_run,
        roa=roa,
        imported_authorization=imported_authorization,
        result_type=result_type or rpki_models.PublishedROAResultType.MATCHED,
        severity=severity or rpki_models.ReconciliationSeverity.INFO,
        matched_intent_count=matched_intent_count,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_roa_lint_finding(
    name='ROA Lint Finding 1',
    lint_run=None,
    roa_intent_result=None,
    published_roa_result=None,
    change_plan_item=None,
    finding_code='replacement_required',
    severity=None,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if lint_run is None:
        lint_run = create_test_roa_lint_run()
    return rpki_models.ROALintFinding.objects.create(
        name=name,
        lint_run=lint_run,
        tenant=lint_run.tenant,
        roa_intent_result=roa_intent_result,
        published_roa_result=published_roa_result,
        change_plan_item=change_plan_item,
        finding_code=finding_code,
        severity=severity or rpki_models.ReconciliationSeverity.WARNING,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_roa_lint_acknowledgement(
    name='ROA Lint Acknowledgement 1',
    organization=None,
    change_plan=None,
    lint_run=None,
    finding=None,
    acknowledged_by='',
    acknowledged_at=None,
    ticket_reference='',
    change_reference='',
    notes='',
    **kwargs,
):
    if finding is None:
        finding = create_test_roa_lint_finding()
    if lint_run is None:
        lint_run = finding.lint_run
    if change_plan is None:
        change_plan = lint_run.change_plan or create_test_roa_change_plan(
            organization=finding.lint_run.reconciliation_run.organization,
            source_reconciliation_run=finding.lint_run.reconciliation_run,
        )
    if organization is None:
        organization = change_plan.organization
    return rpki_models.ROALintAcknowledgement.objects.create(
        name=name,
        organization=organization,
        change_plan=change_plan,
        lint_run=lint_run,
        finding=finding,
        tenant=change_plan.tenant,
        acknowledged_by=acknowledged_by,
        acknowledged_at=acknowledged_at,
        ticket_reference=ticket_reference,
        change_reference=change_reference,
        notes=notes,
        **kwargs,
    )


def create_test_roa_lint_suppression(
    name='ROA Lint Suppression 1',
    organization=None,
    finding_code='replacement_required',
    scope_type=None,
    intent_profile=None,
    roa_intent=None,
    reason='Suppressed for testing.',
    notes='',
    fact_fingerprint='test-fact-fingerprint',
    fact_context_json=None,
    created_by='',
    created_at=None,
    expires_at=None,
    last_matched_at=None,
    match_count=0,
    lifted_by='',
    lifted_at=None,
    lift_reason='',
    **kwargs,
):
    if roa_intent is None and intent_profile is None:
        roa_intent = create_test_roa_intent(origin_asn=create_test_asn())
    if organization is None:
        organization = getattr(roa_intent, 'organization', None) or getattr(intent_profile, 'organization', None) or create_test_organization()
    if scope_type is None:
        scope_type = (
            rpki_models.ROALintSuppressionScope.INTENT
            if roa_intent is not None
            else rpki_models.ROALintSuppressionScope.PROFILE
        )
    if scope_type == rpki_models.ROALintSuppressionScope.PROFILE and intent_profile is None and roa_intent is not None:
        intent_profile = roa_intent.intent_profile
        roa_intent = None
    return rpki_models.ROALintSuppression.objects.create(
        name=name,
        organization=organization,
        tenant=getattr(roa_intent, 'tenant', None),
        finding_code=finding_code,
        scope_type=scope_type,
        intent_profile=intent_profile,
        roa_intent=roa_intent,
        reason=reason,
        notes=notes,
        fact_fingerprint=fact_fingerprint,
        fact_context_json=fact_context_json or {'finding_code': finding_code, 'details': {}},
        created_by=created_by,
        created_at=created_at,
        expires_at=expires_at,
        last_matched_at=last_matched_at,
        match_count=match_count,
        lifted_by=lifted_by,
        lifted_at=lifted_at,
        lift_reason=lift_reason,
        **kwargs,
    )


def create_test_roa_change_plan(
    name='ROA Change Plan 1',
    organization=None,
    source_reconciliation_run=None,
    provider_account=None,
    provider_snapshot=None,
    status=None,
    ticket_reference='',
    change_reference='',
    maintenance_window_start=None,
    maintenance_window_end=None,
    approved_at=None,
    approved_by='',
    apply_started_at=None,
    apply_requested_by='',
    applied_at=None,
    failed_at=None,
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if source_reconciliation_run is None:
        profile = create_test_routing_intent_profile(organization=organization)
        derivation_run = create_test_intent_derivation_run(organization=organization, intent_profile=profile)
        source_reconciliation_run = create_test_roa_reconciliation_run(
            organization=organization,
            intent_profile=profile,
            basis_derivation_run=derivation_run,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
    return rpki_models.ROAChangePlan.objects.create(
        name=name,
        organization=organization,
        source_reconciliation_run=source_reconciliation_run,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        status=status or rpki_models.ROAChangePlanStatus.DRAFT,
        ticket_reference=ticket_reference,
        change_reference=change_reference,
        maintenance_window_start=maintenance_window_start,
        maintenance_window_end=maintenance_window_end,
        approved_at=approved_at,
        approved_by=approved_by,
        apply_started_at=apply_started_at,
        apply_requested_by=apply_requested_by,
        applied_at=applied_at,
        failed_at=failed_at,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_roa_change_plan_item(
    name='ROA Change Plan Item 1',
    change_plan=None,
    action_type=None,
    plan_semantic=None,
    roa_intent=None,
    roa=None,
    imported_authorization=None,
    provider_operation='',
    provider_payload_json=None,
    before_state_json=None,
    after_state_json=None,
    reason='',
    **kwargs,
):
    if change_plan is None:
        change_plan = create_test_roa_change_plan()
    return rpki_models.ROAChangePlanItem.objects.create(
        name=name,
        change_plan=change_plan,
        action_type=action_type or rpki_models.ROAChangePlanAction.CREATE,
        plan_semantic=plan_semantic,
        roa_intent=roa_intent,
        roa=roa,
        imported_authorization=imported_authorization,
        provider_operation=provider_operation,
        provider_payload_json=provider_payload_json or {},
        before_state_json=before_state_json or {},
        after_state_json=after_state_json or {},
        reason=reason,
        **kwargs,
    )


def create_test_roa_validation_simulation_run(
    name='ROA Validation Simulation Run 1',
    change_plan=None,
    status=None,
    started_at=None,
    completed_at=None,
    result_count=0,
    predicted_valid_count=0,
    predicted_invalid_count=0,
    predicted_not_found_count=0,
    summary_json=None,
    **kwargs,
):
    if change_plan is None:
        change_plan = create_test_roa_change_plan()
    return rpki_models.ROAValidationSimulationRun.objects.create(
        name=name,
        change_plan=change_plan,
        tenant=change_plan.tenant,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        result_count=result_count,
        predicted_valid_count=predicted_valid_count,
        predicted_invalid_count=predicted_invalid_count,
        predicted_not_found_count=predicted_not_found_count,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_roa_validation_simulation_result(
    name='ROA Validation Simulation Result 1',
    simulation_run=None,
    change_plan_item=None,
    outcome_type=None,
    details_json=None,
    computed_at=None,
    **kwargs,
):
    if simulation_run is None:
        simulation_run = create_test_roa_validation_simulation_run()
    return rpki_models.ROAValidationSimulationResult.objects.create(
        name=name,
        simulation_run=simulation_run,
        tenant=simulation_run.tenant,
        change_plan_item=change_plan_item,
        outcome_type=outcome_type or rpki_models.ROAValidationSimulationOutcome.NOT_FOUND,
        details_json=details_json or {},
        computed_at=computed_at,
        **kwargs,
    )


def create_test_aspa_change_plan(
    name='ASPA Change Plan 1',
    organization=None,
    source_reconciliation_run=None,
    provider_account=None,
    provider_snapshot=None,
    status=None,
    ticket_reference='',
    change_reference='',
    maintenance_window_start=None,
    maintenance_window_end=None,
    approved_at=None,
    approved_by='',
    apply_started_at=None,
    apply_requested_by='',
    applied_at=None,
    failed_at=None,
    summary_json=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if source_reconciliation_run is None:
        source_reconciliation_run = create_test_aspa_reconciliation_run(
            organization=organization,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )
    return rpki_models.ASPAChangePlan.objects.create(
        name=name,
        organization=organization,
        source_reconciliation_run=source_reconciliation_run,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        status=status or rpki_models.ASPAChangePlanStatus.DRAFT,
        ticket_reference=ticket_reference,
        change_reference=change_reference,
        maintenance_window_start=maintenance_window_start,
        maintenance_window_end=maintenance_window_end,
        approved_at=approved_at,
        approved_by=approved_by,
        apply_started_at=apply_started_at,
        apply_requested_by=apply_requested_by,
        applied_at=applied_at,
        failed_at=failed_at,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_aspa_change_plan_item(
    name='ASPA Change Plan Item 1',
    change_plan=None,
    action_type=None,
    plan_semantic=None,
    aspa_intent=None,
    aspa=None,
    imported_aspa=None,
    provider_operation='',
    provider_payload_json=None,
    before_state_json=None,
    after_state_json=None,
    reason='',
    **kwargs,
):
    if change_plan is None:
        change_plan = create_test_aspa_change_plan()
    return rpki_models.ASPAChangePlanItem.objects.create(
        name=name,
        change_plan=change_plan,
        action_type=action_type or rpki_models.ASPAChangePlanAction.CREATE,
        plan_semantic=plan_semantic,
        aspa_intent=aspa_intent,
        aspa=aspa,
        imported_aspa=imported_aspa,
        provider_operation=provider_operation,
        provider_payload_json=provider_payload_json or {},
        before_state_json=before_state_json or {},
        after_state_json=after_state_json or {},
        reason=reason,
        **kwargs,
    )


@dataclass(frozen=True)
class RoaChangePlanMatrixScenario:
    organization: object
    tenant: object
    intent_profile: object
    derivation_run: object
    local_reconciliation_run: object
    local_plan: object
    provider_account: object
    provider_snapshot: object
    provider_reconciliation_run: object
    provider_plan: object
    selected_prefixes: tuple[object, object]
    orphan_prefix: object
    replacement_roa: object
    orphan_roa: object
    replacement_imported_authorization: object
    orphan_imported_authorization: object


def create_test_roa_change_plan_matrix(
    *,
    organization=None,
    tenant=None,
    intent_profile=None,
    provider_account=None,
    provider_snapshot=None,
    selected_prefix_cidrs=None,
    orphan_prefix_cidr=None,
    active_origin_asn=66110,
    replacement_origin_asn=66111,
    orphan_origin_asn=66112,
    replacement_max_length=26,
    provider_name='Krill',
    name_token=None,
) -> RoaChangePlanMatrixScenario:
    from netbox_rpki.services import create_roa_change_plan, derive_roa_intents, reconcile_roa_intents

    matrix_label = 'ROA Plan Matrix'
    matrix_slug = 'roa-plan-matrix'
    if name_token:
        token_slug = slugify(name_token) or uuid4().hex[:8]
        matrix_label = f'ROA Plan Matrix {name_token}'
        matrix_slug = f'roa-plan-matrix-{token_slug}'

    if selected_prefix_cidrs is None:
        if name_token:
            second_octet = (int(uuid4().hex[:4], 16) % 180) + 20
            third_octet = int(uuid4().hex[4:6], 16) % 250
            selected_prefix_cidrs = (
                f'10.{second_octet}.{third_octet}.0/24',
                f'10.{second_octet}.{(third_octet + 1) % 250}.0/24',
            )
        else:
            selected_prefix_cidrs = ('10.210.1.0/24', '10.210.2.0/24')

    if orphan_prefix_cidr is None:
        if name_token:
            second_octet = int(selected_prefix_cidrs[0].split('.')[1])
            third_octet = (int(selected_prefix_cidrs[0].split('.')[2]) + 99) % 250
            orphan_prefix_cidr = f'10.{second_octet}.{third_octet}.0/24'
        else:
            orphan_prefix_cidr = '10.210.99.0/24'

    if organization is None:
        organization = create_test_organization(org_id=f'{matrix_slug}-org', name=f'{matrix_label} Org')
    if tenant is None:
        tenant_suffix = uuid4().hex[:8]
        tenant = Tenant.objects.create(
            name=f'{matrix_label} Tenant {tenant_suffix}',
            slug=f'{matrix_slug}-tenant-{tenant_suffix}',
        )
    active_asn = create_test_asn(active_origin_asn)
    replacement_asn = create_test_asn(replacement_origin_asn)
    orphan_asn = create_test_asn(orphan_origin_asn)
    if intent_profile is None:
        intent_profile = create_test_routing_intent_profile(
            name=f'{matrix_label} Profile',
            organization=organization,
            status=rpki_models.RoutingIntentProfileStatus.ACTIVE,
            selector_mode=rpki_models.RoutingIntentSelectorMode.FILTERED,
            prefix_selector_query=f'tenant_id={tenant.pk}',
            asn_selector_query=f'id={active_asn.pk}',
        )

    selected_prefixes = tuple(
        create_test_prefix(prefix_cidr, tenant=tenant, status='active')
        for prefix_cidr in selected_prefix_cidrs
    )
    orphan_prefix = create_test_prefix(orphan_prefix_cidr, status='active')

    derivation_run = derive_roa_intents(intent_profile)

    local_certificate = create_test_certificate(name=f'{matrix_label} Local Cert', rpki_org=organization)
    replacement_roa = create_test_roa(name=f'{matrix_label} Replacement ROA', signed_by=local_certificate, origin_as=replacement_asn)
    create_test_roa_prefix(prefix=selected_prefixes[0], roa=replacement_roa, max_length=replacement_max_length)
    orphan_roa = create_test_roa(name=f'{matrix_label} Orphan ROA', signed_by=local_certificate, origin_as=orphan_asn)
    create_test_roa_prefix(prefix=orphan_prefix, roa=orphan_roa, max_length=24)

    local_reconciliation_run = reconcile_roa_intents(derivation_run)
    local_plan = create_roa_change_plan(local_reconciliation_run, name=f'{matrix_label} Local Plan')

    if provider_account is None:
        provider_account = create_test_provider_account(
            name=f'{matrix_label} Provider Account',
            organization=organization,
            provider_type=rpki_models.ProviderType.KRILL,
            org_handle=f'ORG-{matrix_slug.upper()}',
            ca_handle=f'{matrix_slug}-ca',
            api_base_url='https://krill.example.invalid',
        )
    if provider_snapshot is None:
        provider_snapshot = create_test_provider_snapshot(
            name=f'{matrix_label} Provider Snapshot',
            organization=organization,
            provider_account=provider_account,
            provider_name=provider_name,
            status=rpki_models.ValidationRunStatus.COMPLETED,
        )

    replacement_imported_authorization = create_test_imported_roa_authorization(
        name=f'{matrix_label} Replacement Imported Authorization',
        provider_snapshot=provider_snapshot,
        organization=organization,
        prefix=selected_prefixes[0],
        origin_asn=replacement_asn,
        max_length=replacement_max_length,
        payload_json={'comment': 'replacement target'},
    )
    orphan_imported_authorization = create_test_imported_roa_authorization(
        name=f'{matrix_label} Orphan Imported Authorization',
        provider_snapshot=provider_snapshot,
        organization=organization,
        prefix=orphan_prefix,
        origin_asn=orphan_asn,
        max_length=24,
        payload_json={'comment': 'orphaned target'},
    )

    provider_reconciliation_run = reconcile_roa_intents(
        derivation_run,
        comparison_scope=rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED,
        provider_snapshot=provider_snapshot,
    )
    provider_plan = create_roa_change_plan(provider_reconciliation_run, name=f'{matrix_label} Provider Plan')

    return RoaChangePlanMatrixScenario(
        organization=organization,
        tenant=tenant,
        intent_profile=intent_profile,
        derivation_run=derivation_run,
        local_reconciliation_run=local_reconciliation_run,
        local_plan=local_plan,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        provider_reconciliation_run=provider_reconciliation_run,
        provider_plan=provider_plan,
        selected_prefixes=selected_prefixes,
        orphan_prefix=orphan_prefix,
        replacement_roa=replacement_roa,
        orphan_roa=orphan_roa,
        replacement_imported_authorization=replacement_imported_authorization,
        orphan_imported_authorization=orphan_imported_authorization,
    )


def create_test_provider_write_execution(
    name='Provider Write Execution 1',
    organization=None,
    provider_account=None,
    provider_snapshot=None,
    change_plan=None,
    aspa_change_plan=None,
    execution_mode=None,
    status=None,
    requested_by='',
    started_at=None,
    completed_at=None,
    item_count=0,
    request_payload_json=None,
    response_payload_json=None,
    error='',
    followup_sync_run=None,
    followup_provider_snapshot=None,
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if aspa_change_plan is not None and change_plan is not None:
        raise ValueError('Pass either change_plan or aspa_change_plan, not both.')
    if change_plan is not None:
        provider_account = provider_account or change_plan.provider_account or create_test_provider_account(organization=organization)
        provider_snapshot = provider_snapshot or change_plan.provider_snapshot or create_test_provider_snapshot(
            organization=organization,
            provider_account=provider_account,
        )
    elif aspa_change_plan is not None:
        provider_account = (
            provider_account
            or aspa_change_plan.provider_account
            or create_test_provider_account(organization=organization)
        )
        provider_snapshot = provider_snapshot or aspa_change_plan.provider_snapshot or create_test_provider_snapshot(
            organization=organization,
            provider_account=provider_account,
        )
    else:
        provider_account = provider_account or create_test_provider_account(organization=organization)
        provider_snapshot = provider_snapshot or create_test_provider_snapshot(
            organization=organization,
            provider_account=provider_account,
        )
        change_plan = create_test_roa_change_plan(
            organization=organization,
            provider_account=provider_account,
            provider_snapshot=provider_snapshot,
        )
    return rpki_models.ProviderWriteExecution.objects.create(
        name=name,
        organization=organization,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        change_plan=change_plan,
        aspa_change_plan=aspa_change_plan,
        execution_mode=execution_mode or rpki_models.ProviderWriteExecutionMode.PREVIEW,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        requested_by=requested_by,
        started_at=started_at,
        completed_at=completed_at,
        item_count=item_count,
        request_payload_json=request_payload_json or {},
        response_payload_json=response_payload_json or {},
        error=error,
        followup_sync_run=followup_sync_run,
        followup_provider_snapshot=followup_provider_snapshot,
        **kwargs,
    )


def create_test_approval_record(
    name='Approval Record 1',
    organization=None,
    change_plan=None,
    aspa_change_plan=None,
    disposition=None,
    recorded_by='',
    recorded_at=None,
    ticket_reference='',
    change_reference='',
    maintenance_window_start=None,
    maintenance_window_end=None,
    notes='',
    **kwargs,
):
    if organization is None:
        organization = create_test_organization()
    if aspa_change_plan is not None and change_plan is not None:
        raise ValueError('Pass either change_plan or aspa_change_plan, not both.')
    if change_plan is None and aspa_change_plan is None:
        change_plan = create_test_roa_change_plan(organization=organization)
    target_plan = change_plan or aspa_change_plan
    return rpki_models.ApprovalRecord.objects.create(
        name=name,
        organization=organization,
        change_plan=change_plan,
        aspa_change_plan=aspa_change_plan,
        tenant=target_plan.tenant,
        disposition=disposition or rpki_models.ValidationDisposition.ACCEPTED,
        recorded_by=recorded_by,
        recorded_at=recorded_at,
        ticket_reference=ticket_reference,
        change_reference=change_reference,
        maintenance_window_start=maintenance_window_start,
        maintenance_window_end=maintenance_window_end,
        notes=notes,
        **kwargs,
    )


def create_test_sample_dataset(item_count=12, label_prefix='Test Fixture Seed', marker='Managed by netbox_rpki.tests.utils'):
    return seed_sample_data(
        item_count=item_count,
        label_prefix=label_prefix,
        marker=marker,
        cleanup=False,
    )


def count_test_sample_dataset(marker='Managed by netbox_rpki.tests.utils'):
    return count_seed_sample_data(marker)

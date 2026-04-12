from django.utils.text import slugify
from netaddr import IPNetwork

from ipam.models import ASN, Prefix, RIR

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


def create_test_roa(name='ROA 1', signed_by=None, auto_renews=True, **kwargs):
    if signed_by is None:
        signed_by = create_test_certificate()
    return rpki_models.Roa.objects.create(name=name, signed_by=signed_by, auto_renews=auto_renews, **kwargs)


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
    if organization is None:
        organization = create_test_organization()
    if resource_certificate is None:
        resource_certificate = create_test_certificate(rpki_org=organization)
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
    if organization is None:
        organization = create_test_organization()
    if resource_certificate is None:
        resource_certificate = create_test_certificate(rpki_org=organization)
    if ee_certificate is None:
        ee_certificate = create_test_end_entity_certificate(organization=organization, resource_certificate=resource_certificate)
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
    if asn is None:
        asn = create_test_asn()
    return rpki_models.RouterCertificate.objects.create(
        name=name,
        organization=organization,
        resource_certificate=resource_certificate,
        publication_point=publication_point,
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
        prefix=prefix,
        origin_as=origin_as,
        max_length=max_length,
        **kwargs,
    )


def create_test_validated_aspa_payload(
    name='Validated ASPA Payload 1',
    validation_run=None,
    aspa=None,
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
        organization=organization,
        provider_name=provider_name,
        status=status or rpki_models.ValidationRunStatus.COMPLETED,
        fetched_at=fetched_at,
        completed_at=completed_at,
        summary_json=summary_json or {},
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
        is_stale=is_stale,
        payload_json=payload_json or {},
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


def create_test_roa_change_plan(
    name='ROA Change Plan 1',
    organization=None,
    source_reconciliation_run=None,
    status=None,
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
        status=status or rpki_models.ROAChangePlanStatus.DRAFT,
        summary_json=summary_json or {},
        **kwargs,
    )


def create_test_roa_change_plan_item(
    name='ROA Change Plan Item 1',
    change_plan=None,
    action_type=None,
    roa_intent=None,
    roa=None,
    imported_authorization=None,
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
        roa_intent=roa_intent,
        roa=roa,
        imported_authorization=imported_authorization,
        before_state_json=before_state_json or {},
        after_state_json=after_state_json or {},
        reason=reason,
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

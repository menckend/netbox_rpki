from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qsl

from django.http import QueryDict
from django.utils import timezone
from netaddr import IPNetwork

from dcim.models import Location, Region, Site
from ipam.filtersets import ASNFilterSet, PrefixFilterSet
from ipam.models import ASN, Prefix

from netbox_rpki import models as rpki_models


class RoutingIntentExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class PublishedAuthorization:
    source_key: str
    source_name: str
    roa: rpki_models.Roa | None
    roa_prefix: rpki_models.RoaPrefix | None
    imported_authorization: rpki_models.ImportedRoaAuthorization | None
    network: IPNetwork
    prefix_cidr_text: str
    origin_asn_value: int | None
    max_length: int | None
    stale: bool


@dataclass(frozen=True)
class CompiledTemplateBinding:
    binding: rpki_models.RoutingIntentTemplateBinding
    rules: tuple[rpki_models.RoutingIntentTemplateRule, ...]
    prefix_ids: frozenset[int]
    selected_asns: tuple[ASN, ...]
    default_origin_asn: ASN | None
    template_fingerprint: str
    binding_fingerprint: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CompiledRoutingIntentException:
    exception: rpki_models.RoutingIntentException
    fingerprint: str


@dataclass(frozen=True)
class RoutingIntentBindingRegenerationAssessment:
    binding: rpki_models.RoutingIntentTemplateBinding
    state: str
    changed: bool
    previous_fingerprint: str | None
    current_fingerprint: str | None
    reason_codes: tuple[str, ...]
    reason_summary: str


@dataclass(frozen=True)
class CompiledRoutingIntentPolicy:
    profile: rpki_models.RoutingIntentProfile
    prefixes: tuple[Prefix, ...]
    selected_asns: tuple[ASN, ...]
    default_origin_asn: ASN | None
    local_rules: tuple[rpki_models.RoutingIntentRule, ...]
    exceptions: tuple[CompiledRoutingIntentException, ...]
    overrides: tuple[rpki_models.ROAIntentOverride, ...]
    template_bindings: tuple[CompiledTemplateBinding, ...]
    warnings: tuple[str, ...]
    input_fingerprint: str


@dataclass(frozen=True)
class ROAIntentPreviewResult:
    prefix: Prefix
    prefix_cidr_text: str
    origin_asn: ASN | None
    origin_asn_value: int | None
    max_length: int | None
    derived_state: str
    exposure_state: str
    source_rule: rpki_models.RoutingIntentRule | None
    applied_override: rpki_models.ROAIntentOverride | None
    explanation: str


@dataclass(frozen=True)
class RoutingIntentDerivationPreview:
    profile: rpki_models.RoutingIntentProfile
    compiled_policy: CompiledRoutingIntentPolicy
    results: tuple[ROAIntentPreviewResult, ...]
    warnings: tuple[str, ...]


MATCH_SCORES = {
    rpki_models.ROAIntentMatchKind.EXACT: 100,
    rpki_models.ROAIntentMatchKind.LENGTH_NARROWER: 90,
    rpki_models.ROAIntentMatchKind.LENGTH_BROADER: 80,
    rpki_models.ROAIntentMatchKind.ORIGIN_CONFLICT: 70,
    rpki_models.ROAIntentMatchKind.SUBSET: 60,
    rpki_models.ROAIntentMatchKind.SUPERSET: 55,
    rpki_models.ROAIntentMatchKind.PREFIX_CONFLICT: 50,
    rpki_models.ROAIntentMatchKind.STALE_CANDIDATE: 40,
}

REPLACEMENT_REASON_TEXT = {
    'origin_mismatch': 'the published authorization uses the wrong origin ASN',
    'max_length_overbroad': 'the published authorization is broader than the intended maxLength',
    'max_length_too_narrow': 'the published authorization is narrower than the intended maxLength',
    'max_length_mismatch': 'the published authorization uses a different maxLength than intent',
    'origin_and_max_length_overbroad': 'the published authorization uses the wrong origin ASN and an overbroad maxLength',
    'origin_and_max_length_too_narrow': 'the published authorization uses the wrong origin ASN and a too-narrow maxLength',
    'origin_and_max_length_mismatch': 'the published authorization uses the wrong origin ASN and a different maxLength',
}

REPLACEMENT_REASON_PRIORITY = {
    'origin_and_max_length_overbroad': 70,
    'origin_and_max_length_too_narrow': 65,
    'origin_and_max_length_mismatch': 60,
    'origin_mismatch': 50,
    'max_length_overbroad': 40,
    'max_length_too_narrow': 35,
    'max_length_mismatch': 30,
}

INTENT_RESULT_FROM_REPLACEMENT_REASON = {
    'origin_mismatch': (
        rpki_models.ROAIntentResultType.ASN_MISMATCH,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'max_length_overbroad': (
        rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'max_length_too_narrow': (
        rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'max_length_mismatch': (
        rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'origin_and_max_length_overbroad': (
        rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'origin_and_max_length_too_narrow': (
        rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'origin_and_max_length_mismatch': (
        rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_MISMATCH,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
}

PUBLISHED_RESULT_FROM_REPLACEMENT_REASON = {
    'origin_mismatch': (
        rpki_models.PublishedROAResultType.WRONG_ORIGIN,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'max_length_overbroad': (
        rpki_models.PublishedROAResultType.BROADER_THAN_NEEDED,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'max_length_too_narrow': (
        rpki_models.PublishedROAResultType.MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'max_length_mismatch': (
        rpki_models.PublishedROAResultType.MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.WARNING,
    ),
    'origin_and_max_length_overbroad': (
        rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_OVERBROAD,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'origin_and_max_length_too_narrow': (
        rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_TOO_NARROW,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
    'origin_and_max_length_mismatch': (
        rpki_models.PublishedROAResultType.WRONG_ORIGIN_AND_MAX_LENGTH_MISMATCH,
        rpki_models.ReconciliationSeverity.ERROR,
    ),
}

REPLACEMENT_INTENT_RESULT_TYPES = {
    rpki_models.ROAIntentResultType.ASN_MISMATCH,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_OVERBROAD,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_TOO_NARROW,
    rpki_models.ROAIntentResultType.ASN_AND_MAX_LENGTH_MISMATCH,
    rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD,
    rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW,
}


def _build_selector_querydict(raw_query: str) -> QueryDict:
    raw_query = (raw_query or '').strip().lstrip('?')
    querydict = QueryDict('', mutable=True)
    if not raw_query:
        return querydict

    if '=' not in raw_query and '&' not in raw_query:
        querydict.setlist('q', [raw_query])
        return querydict

    for key, value in parse_qsl(raw_query, keep_blank_values=True):
        querydict.appendlist(key, value)

    return querydict


def _apply_selector(filterset_class, queryset, selector_mode: str, raw_query: str):
    if selector_mode == rpki_models.RoutingIntentSelectorMode.EXPLICIT and not (raw_query or '').strip():
        return queryset.none()

    querydict = _build_selector_querydict(raw_query)
    if not querydict:
        return queryset

    filterset = filterset_class(data=querydict, queryset=queryset)
    if not filterset.is_valid():
        error_text = '; '.join(
            f'{field}: {" ".join(errors)}'
            for field, errors in filterset.form.errors.items()
        )
        raise RoutingIntentExecutionError(f'Invalid selector query: {error_text}')

    return filterset.qs


def _resolve_prefix_site(prefix: Prefix):
    site = getattr(prefix, '_site', None)
    if site is not None:
        return site

    scope = getattr(prefix, 'scope', None)
    if isinstance(scope, Site):
        return scope
    if isinstance(scope, Location):
        return scope.site

    return getattr(scope, 'site', None)


def _resolve_prefix_region(prefix: Prefix):
    region = getattr(prefix, '_region', None)
    if region is not None:
        return region

    scope = getattr(prefix, 'scope', None)
    if isinstance(scope, Region):
        return scope

    site = _resolve_prefix_site(prefix)
    return getattr(site, 'region', None)


def _prefix_has_tag(prefix: Prefix, tag_name: str) -> bool:
    normalized = (tag_name or '').strip().lower()
    if not normalized:
        return True

    return prefix.tags.filter(slug=normalized).exists() or prefix.tags.filter(name__iexact=normalized).exists()


def _prefix_matches_custom_field(prefix: Prefix, expression: str) -> bool:
    expression = (expression or '').strip()
    if not expression:
        return True

    custom_field_data = getattr(prefix, 'custom_field_data', {}) or {}
    if '=' not in expression:
        value = custom_field_data.get(expression)
        return value not in (None, '', [], {})

    field_name, expected_value = [part.strip() for part in expression.split('=', 1)]
    return str(custom_field_data.get(field_name, '')) == expected_value


def _prefix_matches_rule(prefix: Prefix, rule: rpki_models.RoutingIntentRule) -> bool:
    if rule.address_family:
        family = rpki_models.AddressFamily.IPV6 if prefix.family == 6 else rpki_models.AddressFamily.IPV4
        if family != rule.address_family:
            return False

    if rule.match_tenant_id and prefix.tenant_id != rule.match_tenant_id:
        return False
    if rule.match_vrf_id and prefix.vrf_id != rule.match_vrf_id:
        return False

    site = _resolve_prefix_site(prefix)
    if rule.match_site_id and getattr(site, 'pk', None) != rule.match_site_id:
        return False

    region = _resolve_prefix_region(prefix)
    if rule.match_region_id and getattr(region, 'pk', None) != rule.match_region_id:
        return False

    if rule.match_role:
        role = getattr(prefix, 'role', None)
        if role is None:
            return False
        role_tokens = {str(role).lower(), getattr(role, 'name', '').lower(), getattr(role, 'slug', '').lower()}
        if rule.match_role.strip().lower() not in role_tokens:
            return False

    if rule.match_tag and not _prefix_has_tag(prefix, rule.match_tag):
        return False

    if rule.match_custom_field and not _prefix_matches_custom_field(prefix, rule.match_custom_field):
        return False

    return True


def _override_matches_prefix(
    prefix: Prefix,
    override: rpki_models.ROAIntentOverride,
    *,
    profile: rpki_models.RoutingIntentProfile,
    now,
) -> bool:
    if override.intent_profile_id and override.intent_profile_id != profile.pk:
        return False

    if override.starts_at and override.starts_at > now:
        return False
    if override.ends_at and override.ends_at < now:
        return False

    if override.prefix_id and override.prefix_id != prefix.pk:
        return False
    if override.prefix_cidr_text and override.prefix_cidr_text != str(prefix.prefix):
        return False

    if override.tenant_scope_id and override.tenant_scope_id != prefix.tenant_id:
        return False
    if override.vrf_scope_id and override.vrf_scope_id != prefix.vrf_id:
        return False

    site = _resolve_prefix_site(prefix)
    if override.site_scope_id and getattr(site, 'pk', None) != override.site_scope_id:
        return False

    region = _resolve_prefix_region(prefix)
    if override.region_scope_id and getattr(region, 'pk', None) != override.region_scope_id:
        return False

    return True


def _override_specificity(override: rpki_models.ROAIntentOverride) -> tuple[int, int, int, int]:
    return (
        1 if override.prefix_id or override.prefix_cidr_text else 0,
        sum(
            1
            for field_name in ('tenant_scope_id', 'vrf_scope_id', 'site_scope_id', 'region_scope_id')
            if getattr(override, field_name)
        ),
        1 if override.intent_profile_id else 0,
        override.pk,
    )


def _exception_matches_prefix(
    prefix: Prefix,
    compiled_exception: CompiledRoutingIntentException,
    *,
    profile: rpki_models.RoutingIntentProfile,
    active_binding_ids: frozenset[int],
    now,
) -> bool:
    exception = compiled_exception.exception
    if exception.intent_profile_id and exception.intent_profile_id != profile.pk:
        return False
    if exception.template_binding_id and exception.template_binding_id not in active_binding_ids:
        return False
    if not exception.approved_at or not exception.approved_by:
        return False

    if exception.starts_at and exception.starts_at > now:
        return False
    if exception.ends_at and exception.ends_at < now:
        return False

    if exception.prefix_id and exception.prefix_id != prefix.pk:
        return False
    if exception.prefix_cidr_text and exception.prefix_cidr_text != str(prefix.prefix):
        return False

    if exception.tenant_scope_id and exception.tenant_scope_id != prefix.tenant_id:
        return False
    if exception.vrf_scope_id and exception.vrf_scope_id != prefix.vrf_id:
        return False

    site = _resolve_prefix_site(prefix)
    if exception.site_scope_id and getattr(site, 'pk', None) != exception.site_scope_id:
        return False

    region = _resolve_prefix_region(prefix)
    if exception.region_scope_id and getattr(region, 'pk', None) != exception.region_scope_id:
        return False

    return True


def _exception_specificity(compiled_exception: CompiledRoutingIntentException) -> tuple[int, int, int, int, int]:
    exception = compiled_exception.exception
    return (
        1 if exception.prefix_id or exception.prefix_cidr_text else 0,
        sum(
            1
            for field_name in ('tenant_scope_id', 'vrf_scope_id', 'site_scope_id', 'region_scope_id')
            if getattr(exception, field_name)
        ),
        1 if exception.template_binding_id else 0,
        1 if exception.intent_profile_id else 0,
        exception.pk,
    )


def _default_max_length(profile: rpki_models.RoutingIntentProfile, prefix: Prefix) -> int:
    return prefix.prefix.prefixlen


def _resolve_default_origin_asn(selected_asns, *, context_label: str = 'profile') -> tuple[ASN | None, list[str]]:
    warnings = []
    if len(selected_asns) == 1:
        return selected_asns[0], warnings
    if not selected_asns:
        warnings.append(f'No ASN matched the {context_label} ASN selector; intents without explicit origin rules will be shadowed.')
    else:
        warnings.append(f'Multiple ASNs matched the {context_label} ASN selector; intents without explicit origin rules will be shadowed.')
    return None, warnings


def _materialize_template_fingerprint(
    template: rpki_models.RoutingIntentTemplate,
    rules: tuple[rpki_models.RoutingIntentTemplateRule, ...],
) -> str:
    payload = '|'.join(
        (
            str(template.organization_id),
            template.name,
            template.status,
            str(template.enabled),
            str(template.template_version),
            *(
                ':'.join(
                    (
                        rule.name,
                        str(rule.weight),
                        rule.action,
                        rule.address_family or '',
                        str(rule.match_tenant_id or ''),
                        str(rule.match_vrf_id or ''),
                        str(rule.match_site_id or ''),
                        str(rule.match_region_id or ''),
                        rule.match_role or '',
                        rule.match_tag or '',
                        rule.match_custom_field or '',
                        str(rule.origin_asn_id or ''),
                        rule.max_length_mode,
                        str(rule.max_length_value or ''),
                        str(rule.enabled),
                    )
                )
                for rule in rules
            ),
        )
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _resolve_binding_default_max_length(
    binding: rpki_models.RoutingIntentTemplateBinding,
    prefix: Prefix,
) -> int | None:
    if binding.max_length_mode == rpki_models.RoutingIntentRuleMaxLengthMode.EXPLICIT and binding.max_length_value is not None:
        return binding.max_length_value
    if binding.max_length_mode in {
        rpki_models.RoutingIntentRuleMaxLengthMode.EXACT,
        rpki_models.RoutingIntentRuleMaxLengthMode.INHERIT,
    }:
        return prefix.prefix.prefixlen
    return None


def _fingerprint_queryset(prefixes, asns, profile, rules, overrides, template_bindings=()) -> str:
    payload = '|'.join(
        [
            str(profile.pk),
            profile.prefix_selector_query or '',
            profile.asn_selector_query or '',
            ','.join(str(prefix.pk) for prefix in prefixes),
            ','.join(str(asn.pk) for asn in asns),
            ','.join(str(rule.pk) for rule in rules),
            ','.join(str(override.pk) for override in overrides),
            ','.join(template_bindings),
        ]
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _materialize_exception_fingerprint(exception: rpki_models.RoutingIntentException) -> str:
    payload = '|'.join(
        (
            str(exception.pk),
            str(exception.organization_id),
            str(exception.intent_profile_id or ''),
            str(exception.template_binding_id or ''),
            exception.exception_type,
            exception.effect_mode,
            str(exception.prefix_id or ''),
            exception.prefix_cidr_text or '',
            str(exception.origin_asn_id or ''),
            str(exception.origin_asn_value or ''),
            str(exception.max_length or ''),
            str(exception.tenant_scope_id or ''),
            str(exception.vrf_scope_id or ''),
            str(exception.site_scope_id or ''),
            str(exception.region_scope_id or ''),
            exception.starts_at.isoformat() if exception.starts_at else '',
            exception.ends_at.isoformat() if exception.ends_at else '',
            str(exception.enabled),
        )
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _resolve_origin_value(origin_asn: ASN | None, origin_asn_value: int | None) -> int | None:
    if origin_asn_value is not None:
        return origin_asn_value
    return getattr(origin_asn, 'asn', None)


def _build_binding_summary_payload(
    binding: rpki_models.RoutingIntentTemplateBinding,
    *,
    template_rules,
    template_fingerprint: str,
    binding_fingerprint: str,
    scoped_prefixes,
    scoped_asns,
    binding_warnings,
):
    return {
        'template_id': binding.template_id,
        'template_version': binding.template.template_version,
        'template_fingerprint': template_fingerprint,
        'binding_fingerprint': binding_fingerprint,
        'scoped_prefix_count': len(scoped_prefixes),
        'scoped_asn_count': len(scoped_asns),
        'active_rule_count': len(template_rules),
        'warning_count': len(binding_warnings),
        'warnings': list(binding_warnings),
    }


def _classify_binding_regeneration(
    binding: rpki_models.RoutingIntentTemplateBinding,
    *,
    binding_fingerprint: str,
    summary_payload: dict,
) -> RoutingIntentBindingRegenerationAssessment:
    previous_fingerprint = binding.last_compiled_fingerprint or None
    previous_summary = dict(binding.summary_json or {})
    reason_codes: list[str] = []

    if previous_fingerprint is None:
        state = rpki_models.RoutingIntentTemplateBindingState.PENDING
        reason_codes.append('never_compiled')
    elif previous_fingerprint == binding_fingerprint:
        state = rpki_models.RoutingIntentTemplateBindingState.CURRENT
    else:
        state = rpki_models.RoutingIntentTemplateBindingState.STALE
        if previous_summary.get('template_fingerprint') != summary_payload['template_fingerprint']:
            reason_codes.append('template_policy_changed')
        if previous_summary.get('template_version') != summary_payload['template_version']:
            reason_codes.append('template_version_changed')
        if previous_summary.get('scoped_prefix_count') != summary_payload['scoped_prefix_count']:
            reason_codes.append('prefix_scope_changed')
        if previous_summary.get('scoped_asn_count') != summary_payload['scoped_asn_count']:
            reason_codes.append('asn_scope_changed')
        if previous_summary.get('warning_count') != summary_payload['warning_count']:
            reason_codes.append('warning_profile_changed')
        if not reason_codes:
            reason_codes.append('binding_parameters_changed')

    reason_summary_map = {
        'never_compiled': 'Binding has not been regenerated yet.',
        'template_policy_changed': 'Template policy fingerprint changed.',
        'template_version_changed': 'Template version changed.',
        'prefix_scope_changed': 'Scoped prefix selection changed.',
        'asn_scope_changed': 'Scoped ASN selection changed.',
        'warning_profile_changed': 'Compilation warnings changed.',
        'binding_parameters_changed': 'Binding inputs changed.',
    }
    if not reason_codes:
        reason_summary = 'No material drift detected.'
    else:
        reason_summary = ' '.join(reason_summary_map[code] for code in reason_codes)

    return RoutingIntentBindingRegenerationAssessment(
        binding=binding,
        state=state,
        changed=state == rpki_models.RoutingIntentTemplateBindingState.STALE,
        previous_fingerprint=previous_fingerprint,
        current_fingerprint=binding_fingerprint,
        reason_codes=tuple(reason_codes),
        reason_summary=reason_summary,
    )


def _build_compiled_template_binding(
    binding: rpki_models.RoutingIntentTemplateBinding,
    *,
    profile_prefixes: tuple[Prefix, ...],
    profile_selected_asns: tuple[ASN, ...],
    persist_state: bool = False,
    commit_current: bool = False,
) -> CompiledTemplateBinding:
    binding_warnings: list[str] = []
    prefix_queryset = Prefix.objects.filter(pk__in=[prefix.pk for prefix in profile_prefixes]).select_related(
        'tenant', 'vrf', 'role', '_site', '_region'
    )
    asn_queryset = ASN.objects.filter(pk__in=[asn.pk for asn in profile_selected_asns]).select_related('tenant')

    try:
        scoped_prefixes = tuple(
            _apply_selector(
                PrefixFilterSet,
                prefix_queryset,
                rpki_models.RoutingIntentSelectorMode.FILTERED,
                binding.prefix_selector_query,
            )
        )
        scoped_asns = tuple(
            _apply_selector(
                ASNFilterSet,
                asn_queryset,
                rpki_models.RoutingIntentSelectorMode.FILTERED,
                binding.asn_selector_query,
            )
        )
    except RoutingIntentExecutionError as exc:
        if persist_state:
            binding.state = rpki_models.RoutingIntentTemplateBindingState.INVALID
            binding.summary_json = {'error': str(exc)}
            binding.save(update_fields=('state', 'summary_json'))
        raise

    template_rules = tuple(
        binding.template.rules.filter(enabled=True)
        .select_related('origin_asn', 'match_tenant', 'match_vrf', 'match_site', 'match_region')
        .order_by('weight', 'name', 'pk')
    )
    template_fingerprint = _materialize_template_fingerprint(binding.template, template_rules)
    binding_default_origin_asn = binding.origin_asn_override
    if binding_default_origin_asn is None:
        binding_default_origin_asn, binding_origin_warnings = _resolve_default_origin_asn(
            scoped_asns,
            context_label=f'binding "{binding.name}"',
        )
        binding_warnings.extend(binding_origin_warnings)

    binding_fingerprint_payload = '|'.join(
        (
            str(binding.pk),
            str(binding.intent_profile_id),
            str(binding.binding_priority),
            str(binding.enabled),
            binding.binding_label or '',
            str(binding.origin_asn_override_id or ''),
            binding.max_length_mode,
            str(binding.max_length_value or ''),
            binding.prefix_selector_query or '',
            binding.asn_selector_query or '',
            str(binding.template.template_version),
            template_fingerprint,
            ','.join(str(prefix.pk) for prefix in scoped_prefixes),
            ','.join(str(asn.pk) for asn in scoped_asns),
            str(getattr(binding_default_origin_asn, 'asn', '')),
        )
    )
    binding_fingerprint = hashlib.sha256(binding_fingerprint_payload.encode('utf-8')).hexdigest()
    summary_payload = _build_binding_summary_payload(
        binding,
        template_rules=template_rules,
        template_fingerprint=template_fingerprint,
        binding_fingerprint=binding_fingerprint,
        scoped_prefixes=scoped_prefixes,
        scoped_asns=scoped_asns,
        binding_warnings=binding_warnings,
    )
    regeneration_assessment = _classify_binding_regeneration(
        binding,
        binding_fingerprint=binding_fingerprint,
        summary_payload=summary_payload,
    )

    if persist_state:
        if binding.template.template_fingerprint != template_fingerprint:
            binding.template.template_fingerprint = template_fingerprint
            binding.template.save(update_fields=('template_fingerprint',))
        binding.state = (
            rpki_models.RoutingIntentTemplateBindingState.CURRENT
            if commit_current
            else regeneration_assessment.state
        )
        if commit_current:
            binding.last_compiled_fingerprint = binding_fingerprint
        binding.summary_json = {
            **summary_payload,
            'previous_binding_fingerprint': regeneration_assessment.previous_fingerprint,
            'regeneration_reason_codes': list(regeneration_assessment.reason_codes),
            'regeneration_reason_summary': regeneration_assessment.reason_summary,
            'candidate_binding_fingerprint': binding_fingerprint,
        }
        update_fields = ['state', 'summary_json']
        if commit_current:
            update_fields.append('last_compiled_fingerprint')
        binding.save(update_fields=tuple(update_fields))

    return CompiledTemplateBinding(
        binding=binding,
        rules=template_rules,
        prefix_ids=frozenset(prefix.pk for prefix in scoped_prefixes),
        selected_asns=scoped_asns,
        default_origin_asn=binding_default_origin_asn,
        template_fingerprint=template_fingerprint,
        binding_fingerprint=binding_fingerprint,
        warnings=tuple(binding_warnings),
    )


def compile_routing_intent_policy(
    profile: rpki_models.RoutingIntentProfile,
    *,
    bindings: tuple[rpki_models.RoutingIntentTemplateBinding, ...] | None = None,
    include_inactive_bindings: bool = False,
    persist_state: bool = False,
    commit_binding_state: bool = False,
) -> CompiledRoutingIntentPolicy:
    if not profile.enabled:
        raise RoutingIntentExecutionError('Routing intent profile is disabled.')

    prefixes = tuple(
        _apply_selector(
            PrefixFilterSet,
            Prefix.objects.all().select_related('tenant', 'vrf', 'role', '_site', '_region'),
            profile.selector_mode,
            profile.prefix_selector_query,
        )
    )
    selected_asns = tuple(
        _apply_selector(
            ASNFilterSet,
            ASN.objects.all().select_related('tenant'),
            profile.selector_mode,
            profile.asn_selector_query,
        )
    )
    local_rules = tuple(
        profile.rules.filter(enabled=True)
        .select_related('origin_asn', 'match_tenant', 'match_vrf', 'match_site', 'match_region')
        .order_by('weight', 'name', 'pk')
    )
    overrides = tuple(
        profile.organization.roa_intent_overrides.filter(enabled=True)
        .select_related('intent_profile', 'prefix', 'origin_asn', 'tenant_scope', 'vrf_scope', 'site_scope', 'region_scope')
    )

    default_origin_asn, warnings = _resolve_default_origin_asn(selected_asns)

    if bindings is None:
        candidate_bindings = tuple(
            profile.template_bindings.select_related('template', 'origin_asn_override')
            .order_by('binding_priority', 'template__name', 'pk')
        )
    else:
        candidate_bindings = tuple(bindings)

    candidate_binding_ids = frozenset(binding.pk for binding in candidate_bindings)
    exception_queryset = (
        profile.organization.routing_intent_exceptions.filter(enabled=True)
        .select_related(
            'intent_profile',
            'template_binding',
            'prefix',
            'origin_asn',
            'tenant_scope',
            'vrf_scope',
            'site_scope',
            'region_scope',
        )
    )
    compiled_exceptions = tuple(
        CompiledRoutingIntentException(
            exception=exception,
            fingerprint=_materialize_exception_fingerprint(exception),
        )
        for exception in exception_queryset
        if (
            exception.intent_profile_id in (None, profile.pk)
            and (exception.template_binding_id is None or exception.template_binding_id in candidate_binding_ids)
            and exception.approved_at
            and exception.approved_by
        )
    )

    compiled_bindings = []
    for binding in candidate_bindings:
        if binding.intent_profile_id != profile.pk:
            raise RoutingIntentExecutionError(
                f'Template binding {binding.pk} does not belong to routing intent profile {profile.pk}.'
            )
        if not include_inactive_bindings:
            if not binding.enabled:
                continue
            if not binding.template.enabled:
                warnings.append(
                    f'Template binding {binding.name} was skipped because template {binding.template.name} is disabled.'
                )
                continue
            if binding.template.status != rpki_models.RoutingIntentTemplateStatus.ACTIVE:
                warnings.append(
                    f'Template binding {binding.name} was skipped because template {binding.template.name} is not active.'
                )
                continue
        compiled_binding = _build_compiled_template_binding(
            binding,
            profile_prefixes=prefixes,
            profile_selected_asns=selected_asns,
            persist_state=persist_state,
            commit_current=commit_binding_state,
        )
        compiled_bindings.append(compiled_binding)
        warnings.extend(compiled_binding.warnings)

    return CompiledRoutingIntentPolicy(
        profile=profile,
        prefixes=prefixes,
        selected_asns=selected_asns,
        default_origin_asn=default_origin_asn,
        local_rules=local_rules,
        exceptions=compiled_exceptions,
        overrides=overrides,
        template_bindings=tuple(compiled_bindings),
        warnings=tuple(warnings),
        input_fingerprint=_fingerprint_queryset(
            prefixes,
            selected_asns,
            profile,
            local_rules,
            overrides,
            template_bindings=tuple(
                (
                    *[binding.binding_fingerprint for binding in compiled_bindings],
                    *[compiled_exception.fingerprint for compiled_exception in compiled_exceptions],
                )
            ),
        ),
    )


def _apply_rule_effect(
    prefix: Prefix,
    rule,
    *,
    included: bool,
    origin_asn: ASN | None,
    origin_asn_value: int | None,
    max_length: int | None,
):
    if not _prefix_matches_rule(prefix, rule):
        return included, origin_asn, origin_asn_value, max_length, False

    if rule.action == rpki_models.RoutingIntentRuleAction.EXCLUDE:
        included = False
    elif rule.action in (
        rpki_models.RoutingIntentRuleAction.INCLUDE,
        rpki_models.RoutingIntentRuleAction.REQUIRE_TAG,
        rpki_models.RoutingIntentRuleAction.REQUIRE_CF,
    ):
        included = True
    elif rule.action == rpki_models.RoutingIntentRuleAction.SET_ORIGIN and rule.origin_asn_id:
        included = True
        origin_asn = rule.origin_asn
        origin_asn_value = rule.origin_asn.asn
    elif rule.action == rpki_models.RoutingIntentRuleAction.SET_MAX_LENGTH:
        included = True
        if rule.max_length_mode == rpki_models.RoutingIntentRuleMaxLengthMode.EXPLICIT and rule.max_length_value is not None:
            max_length = rule.max_length_value
        else:
            max_length = prefix.prefix.prefixlen

    return included, origin_asn, origin_asn_value, max_length, True


def _evaluate_compiled_roa_intents(
    compiled_policy: CompiledRoutingIntentPolicy,
):
    profile = compiled_policy.profile
    now = timezone.now()
    warnings = list(compiled_policy.warnings)
    results = []
    active_binding_ids = frozenset(compiled_binding.binding.pk for compiled_binding in compiled_policy.template_bindings)

    for prefix in compiled_policy.prefixes:
        included = True
        origin_asn = compiled_policy.default_origin_asn
        origin_asn_value = getattr(compiled_policy.default_origin_asn, 'asn', None)
        max_length = _default_max_length(profile, prefix)
        source_rule = None
        applied_override = None
        explanation_parts = [f'Selected prefix {prefix.prefix} from profile query.']
        last_template_binding_name = None

        for compiled_binding in compiled_policy.template_bindings:
            if prefix.pk not in compiled_binding.prefix_ids:
                continue

            before_template_state = (included, origin_asn_value, max_length)
            binding_changed_state = False
            explanation_parts.append(f'Applied template binding {compiled_binding.binding.name}.')

            if compiled_binding.default_origin_asn is not None:
                included = True
                origin_asn = compiled_binding.default_origin_asn
                origin_asn_value = compiled_binding.default_origin_asn.asn
                binding_changed_state = True
                explanation_parts.append(
                    f'Binding {compiled_binding.binding.name} resolved default origin ASN to AS{origin_asn_value}.'
                )

            binding_max_length = _resolve_binding_default_max_length(compiled_binding.binding, prefix)
            if binding_max_length is not None:
                included = True
                max_length = binding_max_length
                binding_changed_state = True
                explanation_parts.append(
                    f'Binding {compiled_binding.binding.name} resolved default maxLength to {binding_max_length}.'
                )

            for template_rule in compiled_binding.rules:
                included, origin_asn, origin_asn_value, max_length, matched = _apply_rule_effect(
                    prefix,
                    template_rule,
                    included=included,
                    origin_asn=origin_asn,
                    origin_asn_value=origin_asn_value,
                    max_length=max_length,
                )
                if matched:
                    binding_changed_state = True
                    explanation_parts.append(
                        f'Applied template rule {template_rule.name} from binding {compiled_binding.binding.name} ({template_rule.action}).'
                    )

            after_template_state = (included, origin_asn_value, max_length)
            if last_template_binding_name and binding_changed_state and after_template_state != before_template_state:
                warnings.append(
                    'Template binding {binding} overrode template-derived policy from binding {prior} for prefix {prefix}.'.format(
                        binding=compiled_binding.binding.name,
                        prior=last_template_binding_name,
                        prefix=prefix.prefix,
                    )
                )
            if binding_changed_state:
                last_template_binding_name = compiled_binding.binding.name

        for rule in compiled_policy.local_rules:
            included, origin_asn, origin_asn_value, max_length, matched = _apply_rule_effect(
                prefix,
                rule,
                included=included,
                origin_asn=origin_asn,
                origin_asn_value=origin_asn_value,
                max_length=max_length,
            )
            if matched:
                source_rule = rule
                explanation_parts.append(f'Applied rule {rule.name} ({rule.action}).')

        matching_exceptions = sorted(
            (
                compiled_exception
                for compiled_exception in compiled_policy.exceptions
                if _exception_matches_prefix(
                    prefix,
                    compiled_exception,
                    profile=profile,
                    active_binding_ids=active_binding_ids,
                    now=now,
                )
            ),
            key=_exception_specificity,
            reverse=True,
        )
        for compiled_exception in matching_exceptions:
            exception = compiled_exception.exception
            explanation_parts.append(
                f'Applied exception {exception.name} ({exception.effect_mode}).'
            )
            if exception.effect_mode == rpki_models.RoutingIntentExceptionEffectMode.SUPPRESS:
                included = False
            else:
                included = True
                exception_origin_value = _resolve_origin_value(exception.origin_asn, exception.origin_asn_value)
                if exception_origin_value is not None:
                    origin_asn = exception.origin_asn
                    origin_asn_value = exception_origin_value
                if exception.effect_mode == rpki_models.RoutingIntentExceptionEffectMode.TEMPORARY_REPLACEMENT:
                    if exception.max_length is not None:
                        max_length = exception.max_length
                elif exception.effect_mode == rpki_models.RoutingIntentExceptionEffectMode.BROADEN:
                    if exception.max_length is not None:
                        max_length = max(max_length, exception.max_length) if max_length is not None else exception.max_length
                elif exception.effect_mode == rpki_models.RoutingIntentExceptionEffectMode.NARROW:
                    if exception.max_length is not None:
                        max_length = min(max_length, exception.max_length) if max_length is not None else exception.max_length

        matching_overrides = sorted(
            (
                override
                for override in compiled_policy.overrides
                if _override_matches_prefix(prefix, override, profile=profile, now=now)
            ),
            key=_override_specificity,
            reverse=True,
        )
        for override in matching_overrides:
            applied_override = override
            explanation_parts.append(f'Applied override {override.name} ({override.action}).')
            if override.action == rpki_models.ROAIntentOverrideAction.SUPPRESS:
                included = False
            elif override.action == rpki_models.ROAIntentOverrideAction.FORCE_INCLUDE:
                included = True
            elif override.action == rpki_models.ROAIntentOverrideAction.REPLACE_ORIGIN:
                included = True
                origin_asn = override.origin_asn
                origin_asn_value = _resolve_origin_value(override.origin_asn, override.origin_asn_value)
            elif override.action == rpki_models.ROAIntentOverrideAction.REPLACE_MAX_LENGTH and override.max_length is not None:
                included = True
                max_length = override.max_length

        is_as0 = origin_asn_value == 0
        if is_as0 and not profile.allow_as0:
            warnings.append(f'Prefix {prefix.prefix} resolved to AS0 but AS0 is disabled on profile {profile.name}.')
            explanation_parts.append('AS0 resolution blocked because the profile does not allow AS0.')
            included = False

        if not included:
            derived_state = rpki_models.ROAIntentDerivedState.SUPPRESSED
        elif origin_asn_value is None and not is_as0:
            derived_state = rpki_models.ROAIntentDerivedState.SHADOWED
            explanation_parts.append('No origin ASN resolved for this prefix.')
        else:
            derived_state = rpki_models.ROAIntentDerivedState.ACTIVE

        exposure_state = (
            rpki_models.ROAIntentExposureState.ADVERTISED
            if prefix.status == 'active'
            else rpki_models.ROAIntentExposureState.ELIGIBLE_NOT_ADVERTISED
        )
        prefix_text = str(prefix.prefix)

        results.append(
            {
                'prefix': prefix,
                'prefix_cidr_text': prefix_text,
                'address_family': rpki_models.AddressFamily.IPV6 if prefix.family == 6 else rpki_models.AddressFamily.IPV4,
                'origin_asn': origin_asn,
                'origin_asn_value': _resolve_origin_value(origin_asn, origin_asn_value),
                'max_length': max_length,
                'derived_state': derived_state,
                'exposure_state': exposure_state,
                'scope_tenant': prefix.tenant,
                'scope_vrf': prefix.vrf,
                'scope_site': _resolve_prefix_site(prefix),
                'scope_region': _resolve_prefix_region(prefix),
                'source_rule': source_rule,
                'applied_override': applied_override,
                'explanation': ' '.join(explanation_parts),
                'is_as0': is_as0,
            }
        )

    return tuple(results), tuple(warnings)


def derive_roa_intents(
    profile: rpki_models.RoutingIntentProfile,
    *,
    trigger_mode: str = rpki_models.IntentRunTriggerMode.MANUAL,
    run_name: str | None = None,
    compiled_policy: CompiledRoutingIntentPolicy | None = None,
) -> rpki_models.IntentDerivationRun:
    compiled_policy = compiled_policy or compile_routing_intent_policy(
        profile,
        persist_state=True,
        commit_binding_state=True,
    )
    if compiled_policy.profile.pk != profile.pk:
        raise RoutingIntentExecutionError('Compiled policy does not belong to the selected routing intent profile.')

    preview_rows, warnings = _evaluate_compiled_roa_intents(compiled_policy)
    now = timezone.now()

    derivation_run = rpki_models.IntentDerivationRun.objects.create(
        name=run_name or f'{profile.name} Derivation {now:%Y-%m-%d %H:%M:%S}',
        organization=profile.organization,
        intent_profile=profile,
        tenant=profile.tenant,
        status=rpki_models.ValidationRunStatus.RUNNING,
        trigger_mode=trigger_mode,
        started_at=now,
        input_fingerprint=compiled_policy.input_fingerprint,
        prefix_count_scanned=len(compiled_policy.prefixes),
        warning_count=len(warnings),
        error_summary='\n'.join(warnings),
    )

    emitted_count = 0
    for row in preview_rows:
        resolved_origin_value = row['origin_asn_value']
        intent_name = f'{row["prefix_cidr_text"]} -> AS{resolved_origin_value if resolved_origin_value is not None else "unresolved"}'

        rpki_models.ROAIntent.objects.create(
            name=intent_name,
            derivation_run=derivation_run,
            organization=profile.organization,
            intent_profile=profile,
            tenant=row['prefix'].tenant or profile.tenant,
            intent_key=rpki_models.ROAIntent.build_intent_key(
                prefix_cidr_text=row['prefix_cidr_text'],
                address_family=row['address_family'],
                origin_asn_value=resolved_origin_value,
                max_length=row['max_length'],
                tenant_id=row['prefix'].tenant_id,
                vrf_id=row['prefix'].vrf_id,
                site_id=getattr(row['scope_site'], 'pk', None),
                region_id=getattr(row['scope_region'], 'pk', None),
            ),
            prefix=row['prefix'],
            prefix_cidr_text=row['prefix_cidr_text'],
            address_family=row['address_family'],
            origin_asn=row['origin_asn'],
            origin_asn_value=resolved_origin_value,
            is_as0=row['is_as0'],
            max_length=row['max_length'],
            scope_tenant=row['scope_tenant'],
            scope_vrf=row['scope_vrf'],
            scope_site=row['scope_site'],
            scope_region=row['scope_region'],
            source_rule=row['source_rule'],
            applied_override=row['applied_override'],
            derived_state=row['derived_state'],
            exposure_state=row['exposure_state'],
            explanation=row['explanation'],
        )
        emitted_count += 1

    derivation_run.status = rpki_models.ValidationRunStatus.COMPLETED
    derivation_run.completed_at = timezone.now()
    derivation_run.intent_count_emitted = emitted_count
    derivation_run.warning_count = len(warnings)
    derivation_run.error_summary = '\n'.join(warnings)
    derivation_run.save(update_fields=(
        'status',
        'completed_at',
        'intent_count_emitted',
        'warning_count',
        'error_summary',
    ))
    return derivation_run


def preview_routing_intent_template_binding(
    binding: rpki_models.RoutingIntentTemplateBinding,
) -> RoutingIntentDerivationPreview:
    compiled_policy = compile_routing_intent_policy(
        binding.intent_profile,
        bindings=(binding,),
        include_inactive_bindings=True,
        persist_state=False,
    )
    preview_rows, warnings = _evaluate_compiled_roa_intents(compiled_policy)
    return RoutingIntentDerivationPreview(
        profile=binding.intent_profile,
        compiled_policy=compiled_policy,
        results=tuple(
            ROAIntentPreviewResult(
                prefix=row['prefix'],
                prefix_cidr_text=row['prefix_cidr_text'],
                origin_asn=row['origin_asn'],
                origin_asn_value=row['origin_asn_value'],
                max_length=row['max_length'],
                derived_state=row['derived_state'],
                exposure_state=row['exposure_state'],
                source_rule=row['source_rule'],
                applied_override=row['applied_override'],
                explanation=row['explanation'],
            )
            for row in preview_rows
        ),
        warnings=warnings,
    )


def refresh_routing_intent_template_binding_state(
    binding: rpki_models.RoutingIntentTemplateBinding,
) -> RoutingIntentBindingRegenerationAssessment:
    compile_routing_intent_policy(
        binding.intent_profile,
        bindings=(binding,),
        include_inactive_bindings=True,
        persist_state=True,
        commit_binding_state=False,
    )
    binding.refresh_from_db()
    summary = dict(binding.summary_json or {})
    return RoutingIntentBindingRegenerationAssessment(
        binding=binding,
        state=binding.state,
        changed=binding.state == rpki_models.RoutingIntentTemplateBindingState.STALE,
        previous_fingerprint=summary.get('previous_binding_fingerprint'),
        current_fingerprint=summary.get('candidate_binding_fingerprint') or binding.last_compiled_fingerprint or None,
        reason_codes=tuple(summary.get('regeneration_reason_codes') or ()),
        reason_summary=summary.get('regeneration_reason_summary') or '',
    )


def run_routing_intent_template_binding_pipeline(
    binding: rpki_models.RoutingIntentTemplateBinding,
    *,
    trigger_mode: str = rpki_models.IntentRunTriggerMode.MANUAL,
    comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
) -> tuple[rpki_models.IntentDerivationRun, rpki_models.ROAReconciliationRun]:
    if not binding.enabled:
        raise RoutingIntentExecutionError('Routing intent template binding is disabled.')
    if not binding.template.enabled:
        raise RoutingIntentExecutionError('Routing intent template is disabled.')
    if binding.template.status != rpki_models.RoutingIntentTemplateStatus.ACTIVE:
        raise RoutingIntentExecutionError('Routing intent template must be active before regeneration.')

    compiled_policy = compile_routing_intent_policy(
        binding.intent_profile,
        bindings=(binding,),
        persist_state=True,
        commit_binding_state=True,
    )
    if not compiled_policy.template_bindings:
        raise RoutingIntentExecutionError('No active compiled policy was produced for this template binding.')

    derivation_run = derive_roa_intents(
        binding.intent_profile,
        trigger_mode=trigger_mode,
        run_name=f'{binding.name} Derivation {timezone.now():%Y-%m-%d %H:%M:%S}',
        compiled_policy=compiled_policy,
    )
    reconciliation_run = reconcile_roa_intents(
        derivation_run,
        comparison_scope=comparison_scope,
        provider_snapshot=provider_snapshot,
    )
    return derivation_run, reconciliation_run


def _network_contains(container: IPNetwork, member: IPNetwork) -> bool:
    return container.version == member.version and container.first <= member.first and container.last >= member.last


def _load_local_published_authorizations() -> dict[str, list[PublishedAuthorization]]:
    by_source = {}
    prefix_rows = rpki_models.RoaPrefix.objects.select_related('roa_name', 'roa_name__origin_as').all()
    today = timezone.now().date()
    for prefix_row in prefix_rows:
        roa = prefix_row.roa_name
        source_key = f'roa:{roa.pk}'
        by_source.setdefault(source_key, []).append(
            PublishedAuthorization(
                source_key=source_key,
                source_name=roa.name,
                roa=roa,
                roa_prefix=prefix_row,
                imported_authorization=None,
                network=IPNetwork(str(prefix_row.prefix.prefix)),
                prefix_cidr_text=str(prefix_row.prefix.prefix),
                origin_asn_value=getattr(roa.origin_as, 'asn', None),
                max_length=prefix_row.max_length,
                stale=bool(roa.valid_to and roa.valid_to < today),
            )
        )
    return by_source


def _resolve_provider_snapshot(
    profile: rpki_models.RoutingIntentProfile,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None,
) -> rpki_models.ProviderSnapshot:
    if isinstance(provider_snapshot, rpki_models.ProviderSnapshot):
        return provider_snapshot
    if provider_snapshot is not None:
        return rpki_models.ProviderSnapshot.objects.get(pk=provider_snapshot, organization=profile.organization)

    snapshot = (
        profile.organization.provider_snapshots
        .filter(status=rpki_models.ValidationRunStatus.COMPLETED)
        .order_by('-completed_at', '-fetched_at', '-pk')
        .first()
    )
    if snapshot is None:
        raise RoutingIntentExecutionError(
            f'No completed provider snapshot is available for organization {profile.organization.name}.'
        )
    return snapshot


def _load_imported_published_authorizations(
    profile: rpki_models.RoutingIntentProfile,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None,
) -> tuple[rpki_models.ProviderSnapshot, dict[str, list[PublishedAuthorization]]]:
    snapshot = _resolve_provider_snapshot(profile, provider_snapshot)
    by_source = {}
    rows = snapshot.imported_roa_authorizations.select_related('origin_asn', 'prefix').all()
    for imported in rows:
        source_key = f'imported:{imported.pk}'
        by_source[source_key] = [
            PublishedAuthorization(
                source_key=source_key,
                source_name=imported.name,
                roa=None,
                roa_prefix=None,
                imported_authorization=imported,
                network=IPNetwork(imported.prefix_cidr_text),
                prefix_cidr_text=imported.prefix_cidr_text,
                origin_asn_value=imported.origin_asn_value,
                max_length=imported.max_length,
                stale=imported.is_stale,
            )
        ]
    return snapshot, by_source


def _published_authorizations(
    profile: rpki_models.RoutingIntentProfile,
    comparison_scope: str,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
) -> tuple[rpki_models.ProviderSnapshot | None, dict[str, list[PublishedAuthorization]]]:
    if comparison_scope == rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS:
        return None, _load_local_published_authorizations()
    if comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
        return _load_imported_published_authorizations(profile, provider_snapshot)
    raise RoutingIntentExecutionError('Mixed reconciliation is not implemented yet.')


def _classify_match(intent: rpki_models.ROAIntent, published: PublishedAuthorization) -> str | None:
    if intent.address_family == rpki_models.AddressFamily.IPV6 and published.network.version != 6:
        return None
    if intent.address_family == rpki_models.AddressFamily.IPV4 and published.network.version != 4:
        return None

    intent_network = IPNetwork(intent.prefix_cidr_text)
    same_prefix = intent_network == published.network
    same_origin = intent.origin_asn_value == published.origin_asn_value

    if published.stale:
        return rpki_models.ROAIntentMatchKind.STALE_CANDIDATE
    if same_prefix and same_origin and intent.max_length == published.max_length:
        return rpki_models.ROAIntentMatchKind.EXACT
    if same_prefix and same_origin and published.max_length is not None and intent.max_length is not None:
        if published.max_length > intent.max_length:
            return rpki_models.ROAIntentMatchKind.LENGTH_BROADER
        if published.max_length < intent.max_length:
            return rpki_models.ROAIntentMatchKind.LENGTH_NARROWER
    if same_prefix and not same_origin:
        return rpki_models.ROAIntentMatchKind.ORIGIN_CONFLICT
    if _network_contains(published.network, intent_network):
        return rpki_models.ROAIntentMatchKind.SUPERSET if same_origin else rpki_models.ROAIntentMatchKind.PREFIX_CONFLICT
    if _network_contains(intent_network, published.network):
        return rpki_models.ROAIntentMatchKind.SUBSET if same_origin else rpki_models.ROAIntentMatchKind.PREFIX_CONFLICT

    return None


def _max_length_relation(intent_max_length: int | None, published_max_length: int | None) -> str:
    if intent_max_length == published_max_length:
        return 'exact'
    if intent_max_length is None or published_max_length is None:
        return 'different'
    if published_max_length > intent_max_length:
        return 'broader'
    if published_max_length < intent_max_length:
        return 'narrower'
    return 'different'


def _replacement_reason_code(*, prefix_relation: str, same_origin: bool, max_length_relation: str) -> str | None:
    if prefix_relation != 'exact':
        return None
    if same_origin:
        if max_length_relation == 'broader':
            return 'max_length_overbroad'
        if max_length_relation == 'narrower':
            return 'max_length_too_narrow'
        if max_length_relation == 'different':
            return 'max_length_mismatch'
        return None

    if max_length_relation == 'exact':
        return 'origin_mismatch'
    if max_length_relation == 'broader':
        return 'origin_and_max_length_overbroad'
    if max_length_relation == 'narrower':
        return 'origin_and_max_length_too_narrow'
    return 'origin_and_max_length_mismatch'


def _build_match_analysis(intent: rpki_models.ROAIntent, published: PublishedAuthorization) -> dict:
    intent_network = IPNetwork(intent.prefix_cidr_text)
    same_prefix = intent_network == published.network
    same_origin = intent.origin_asn_value == published.origin_asn_value
    if same_prefix:
        prefix_relation = 'exact'
    elif _network_contains(published.network, intent_network):
        prefix_relation = 'published_superset'
    elif _network_contains(intent_network, published.network):
        prefix_relation = 'published_subset'
    else:
        prefix_relation = 'disjoint'

    max_length_relation = _max_length_relation(intent.max_length, published.max_length)
    mismatch_axes = []
    if prefix_relation != 'exact':
        mismatch_axes.append('prefix')
    if not same_origin:
        mismatch_axes.append('origin_asn')
    if max_length_relation != 'exact':
        mismatch_axes.append('max_length')

    replacement_reason = _replacement_reason_code(
        prefix_relation=prefix_relation,
        same_origin=same_origin,
        max_length_relation=max_length_relation,
    )
    return {
        'prefix_relation': prefix_relation,
        'same_origin': same_origin,
        'max_length_relation': max_length_relation,
        'mismatch_axes': mismatch_axes,
        'replacement_required': replacement_reason is not None,
        'replacement_reason_code': replacement_reason,
    }


def _serialize_match_source(match: rpki_models.ROAIntentMatch | None) -> dict:
    if match is None:
        return {}
    if match.roa_id is not None:
        return {
            'source': 'local_roa',
            'roa_id': match.roa_id,
            'name': match.roa.name,
        }

    imported = match.imported_authorization
    return {
        'source': 'provider_imported',
        'imported_authorization_id': imported.pk,
        'name': imported.name,
        'external_object_id': imported.external_object_id,
        'payload_json': imported.payload_json,
    }


def _result_from_best_match(
    intent: rpki_models.ROAIntent,
    best_match: rpki_models.ROAIntentMatch | None,
) -> tuple[str, str]:
    if intent.derived_state == rpki_models.ROAIntentDerivedState.SUPPRESSED:
        return rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY, rpki_models.ReconciliationSeverity.INFO
    if intent.derived_state != rpki_models.ROAIntentDerivedState.ACTIVE:
        return rpki_models.ROAIntentResultType.INACTIVE_INTENT, rpki_models.ReconciliationSeverity.WARNING
    if best_match is None:
        return rpki_models.ROAIntentResultType.MISSING, rpki_models.ReconciliationSeverity.ERROR
    best_match_kind = best_match.match_kind
    if best_match_kind == rpki_models.ROAIntentMatchKind.EXACT:
        return rpki_models.ROAIntentResultType.MATCH, rpki_models.ReconciliationSeverity.INFO
    if best_match_kind == rpki_models.ROAIntentMatchKind.STALE_CANDIDATE:
        return rpki_models.ROAIntentResultType.STALE, rpki_models.ReconciliationSeverity.WARNING
    replacement_reason = (best_match.details_json or {}).get('replacement_reason_code')
    if replacement_reason:
        return INTENT_RESULT_FROM_REPLACEMENT_REASON[replacement_reason]
    if best_match_kind == rpki_models.ROAIntentMatchKind.ORIGIN_CONFLICT:
        return rpki_models.ROAIntentResultType.ASN_MISMATCH, rpki_models.ReconciliationSeverity.ERROR
    if best_match_kind == rpki_models.ROAIntentMatchKind.LENGTH_BROADER:
        return rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD, rpki_models.ReconciliationSeverity.WARNING
    if best_match_kind == rpki_models.ROAIntentMatchKind.LENGTH_NARROWER:
        return rpki_models.ROAIntentResultType.MAX_LENGTH_TOO_NARROW, rpki_models.ReconciliationSeverity.WARNING
    return rpki_models.ROAIntentResultType.PREFIX_MISMATCH, rpki_models.ReconciliationSeverity.WARNING


def _match_source_key(match: rpki_models.ROAIntentMatch) -> str:
    if match.roa_id is not None:
        return f'roa:{match.roa_id}'
    return f'imported:{match.imported_authorization_id}'


def _published_result_from_matches(row_matches: list[dict]) -> tuple[str, str, dict]:
    if not row_matches:
        return (
            rpki_models.PublishedROAResultType.ORPHANED,
            rpki_models.ReconciliationSeverity.WARNING,
            {
                'replacement_required': False,
                'matched_intent_result_types': [],
            },
        )

    replacement_matches = [match_info for match_info in row_matches if match_info.get('replacement_required')]
    if replacement_matches:
        selected = max(
            replacement_matches,
            key=lambda match_info: REPLACEMENT_REASON_PRIORITY.get(match_info.get('replacement_reason_code') or '', 0),
        )
        result_type, severity = PUBLISHED_RESULT_FROM_REPLACEMENT_REASON[selected['replacement_reason_code']]
        return (
            result_type,
            severity,
            {
                'replacement_required': True,
                'replacement_reason_code': selected['replacement_reason_code'],
                'matched_intent_ids': [match_info['roa_intent_id'] for match_info in row_matches],
                'matched_intent_result_types': [match_info['result_type'] for match_info in row_matches],
            },
        )

    result_types = {match_info['result_type'] for match_info in row_matches}
    if rpki_models.ROAIntentResultType.STALE in result_types:
        return (
            rpki_models.PublishedROAResultType.STALE,
            rpki_models.ReconciliationSeverity.WARNING,
            {
                'replacement_required': False,
                'matched_intent_ids': [match_info['roa_intent_id'] for match_info in row_matches],
                'matched_intent_result_types': [match_info['result_type'] for match_info in row_matches],
            },
        )

    return (
        rpki_models.PublishedROAResultType.MATCHED,
        rpki_models.ReconciliationSeverity.INFO,
        {
            'replacement_required': False,
            'matched_intent_ids': [match_info['roa_intent_id'] for match_info in row_matches],
            'matched_intent_result_types': [match_info['result_type'] for match_info in row_matches],
        },
    )


def reconcile_roa_intents(
    derivation_run: rpki_models.IntentDerivationRun,
    *,
    comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
    run_name: str | None = None,
) -> rpki_models.ROAReconciliationRun:
    now = timezone.now()
    profile = derivation_run.intent_profile
    resolved_snapshot, published_by_source = _published_authorizations(profile, comparison_scope, provider_snapshot)
    reconciliation_run = rpki_models.ROAReconciliationRun.objects.create(
        name=run_name or f'{profile.name} Reconciliation {now:%Y-%m-%d %H:%M:%S}',
        organization=profile.organization,
        intent_profile=profile,
        basis_derivation_run=derivation_run,
        provider_snapshot=resolved_snapshot,
        tenant=profile.tenant,
        comparison_scope=comparison_scope,
        status=rpki_models.ValidationRunStatus.RUNNING,
        started_at=now,
    )

    published_rows = [row for rows in published_by_source.values() for row in rows]
    intent_result_summary: dict[str, int] = {}
    published_result_summary: dict[str, int] = {}
    best_match_kind_summary: dict[str, int] = {}
    best_results_by_source: dict[str, list[dict]] = {}
    active_intents = 0

    intents = derivation_run.roa_intents.select_related('origin_asn', 'prefix', 'scope_tenant', 'scope_vrf', 'scope_site', 'scope_region').all()
    for intent in intents:
        if intent.derived_state == rpki_models.ROAIntentDerivedState.ACTIVE:
            active_intents += 1

        candidates = []
        for published in published_rows:
            match_kind = _classify_match(intent, published)
            if match_kind is None:
                continue
            match_analysis = _build_match_analysis(intent, published)
            match = rpki_models.ROAIntentMatch.objects.create(
                name=f'{intent.name} vs {published.source_name}',
                roa_intent=intent,
                roa=published.roa,
                imported_authorization=published.imported_authorization,
                tenant=intent.tenant,
                match_kind=match_kind,
                details_json={
                    'intent_prefix': intent.prefix_cidr_text,
                    'published_prefix': published.prefix_cidr_text,
                    'intent_origin_asn': intent.origin_asn_value,
                    'published_origin_asn': published.origin_asn_value,
                    'intent_max_length': intent.max_length,
                    'published_max_length': published.max_length,
                    'stale': published.stale,
                    **match_analysis,
                },
            )
            candidates.append(match)

        best_match = None
        if candidates:
            best_match = max(candidates, key=lambda candidate: MATCH_SCORES.get(candidate.match_kind, 0))
            if best_match is not None:
                best_match.is_best_match = True
                best_match.save(update_fields=('is_best_match',))
                best_match_kind_summary[best_match.match_kind] = best_match_kind_summary.get(best_match.match_kind, 0) + 1

        result_type, severity = _result_from_best_match(intent, best_match)
        intent_result_summary[result_type] = intent_result_summary.get(result_type, 0) + 1
        best_match_details = dict(getattr(best_match, 'details_json', {}) or {})
        intent_result = rpki_models.ROAIntentResult.objects.create(
            name=f'{intent.name} Result',
            reconciliation_run=reconciliation_run,
            roa_intent=intent,
            tenant=intent.tenant,
            result_type=result_type,
            severity=severity,
            best_roa=getattr(best_match, 'roa', None),
            best_imported_authorization=getattr(best_match, 'imported_authorization', None),
            match_count=len(candidates),
            details_json={
                'best_match_kind': getattr(best_match, 'match_kind', None),
                'intent_prefix': intent.prefix_cidr_text,
                'intent_origin_asn': intent.origin_asn_value,
                'intent_max_length': intent.max_length,
                'comparison_scope': comparison_scope,
                'published_prefix': best_match_details.get('published_prefix'),
                'published_origin_asn': best_match_details.get('published_origin_asn'),
                'published_max_length': best_match_details.get('published_max_length'),
                'prefix_relation': best_match_details.get('prefix_relation'),
                'max_length_relation': best_match_details.get('max_length_relation'),
                'mismatch_axes': best_match_details.get('mismatch_axes', []),
                'replacement_required': best_match_details.get('replacement_required', False),
                'replacement_reason_code': best_match_details.get('replacement_reason_code'),
                'published_source': _serialize_match_source(best_match),
            },
            computed_at=now,
        )
        if best_match is not None:
            best_results_by_source.setdefault(_match_source_key(best_match), []).append(
                {
                    'intent_result_id': intent_result.pk,
                    'roa_intent_id': intent.pk,
                    'result_type': result_type,
                    'replacement_required': best_match_details.get('replacement_required', False),
                    'replacement_reason_code': best_match_details.get('replacement_reason_code'),
                }
            )

    for source_key, source_rows in published_by_source.items():
        representative = source_rows[0]
        row_matches = best_results_by_source.get(source_key, [])
        result_type, severity, published_details = _published_result_from_matches(row_matches)
        published_result_summary[result_type] = published_result_summary.get(result_type, 0) + 1

        rpki_models.PublishedROAResult.objects.create(
            name=f'{representative.source_name} Published Result',
            reconciliation_run=reconciliation_run,
            roa=representative.roa,
            imported_authorization=representative.imported_authorization,
            tenant=representative.roa.tenant if representative.roa is not None else profile.tenant,
            result_type=result_type,
            severity=severity,
            matched_intent_count=len(row_matches),
            details_json={
                'origin_asn': representative.origin_asn_value,
                'prefix_count': len(source_rows),
                'source': source_key,
                'comparison_scope': comparison_scope,
                'prefix_cidr_text': representative.prefix_cidr_text,
                'max_length': representative.max_length,
                'stale': representative.stale,
                **published_details,
            },
            computed_at=now,
        )

    reconciliation_run.status = rpki_models.ValidationRunStatus.COMPLETED
    reconciliation_run.completed_at = timezone.now()
    reconciliation_run.published_roa_count = len(published_by_source)
    reconciliation_run.intent_count = active_intents
    reconciliation_run.result_summary_json = {
        'intent_result_types': intent_result_summary,
        'published_result_types': published_result_summary,
        'best_match_kinds': best_match_kind_summary,
        'comparison_scope': comparison_scope,
        'provider_snapshot_id': getattr(resolved_snapshot, 'pk', None),
        'replacement_required_intent_count': sum(
            intent_result_summary.get(result_type, 0)
            for result_type in REPLACEMENT_INTENT_RESULT_TYPES
        ),
        'replacement_required_published_count': sum(
            count
            for result_type, count in published_result_summary.items()
            if result_type not in {
                rpki_models.PublishedROAResultType.MATCHED,
                rpki_models.PublishedROAResultType.ORPHANED,
                rpki_models.PublishedROAResultType.STALE,
            }
        ),
    }
    reconciliation_run.save(update_fields=(
        'status',
        'completed_at',
        'published_roa_count',
        'intent_count',
        'result_summary_json',
    ))
    from netbox_rpki.services.roa_lint import refresh_roa_change_plan_lint_posture, run_roa_lint

    try:
        lint_run = run_roa_lint(reconciliation_run)
        reconciliation_run.result_summary_json['lint_run_id'] = lint_run.pk
    except Exception as exc:
        reconciliation_run.result_summary_json['lint_error'] = str(exc)
    reconciliation_run.save(update_fields=('result_summary_json',))
    return reconciliation_run


def run_routing_intent_pipeline(
    profile: rpki_models.RoutingIntentProfile,
    *,
    trigger_mode: str = rpki_models.IntentRunTriggerMode.MANUAL,
    comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    provider_snapshot: rpki_models.ProviderSnapshot | int | None = None,
) -> tuple[rpki_models.IntentDerivationRun, rpki_models.ROAReconciliationRun]:
    derivation_run = derive_roa_intents(profile, trigger_mode=trigger_mode)
    reconciliation_run = reconcile_roa_intents(
        derivation_run,
        comparison_scope=comparison_scope,
        provider_snapshot=provider_snapshot,
    )
    return derivation_run, reconciliation_run


def _serialize_intent_for_plan(intent: rpki_models.ROAIntent) -> dict:
    return {
        'intent_id': intent.pk,
        'prefix_cidr_text': intent.prefix_cidr_text,
        'address_family': intent.address_family,
        'origin_asn_value': intent.origin_asn_value,
        'max_length': intent.max_length,
        'derived_state': intent.derived_state,
    }


def _serialize_published_source_for_plan(published_result: rpki_models.PublishedROAResult) -> dict:
    if published_result.roa is not None:
        return {
            'source': 'local_roa',
            'roa_id': published_result.roa.pk,
            'name': published_result.roa.name,
            'origin_asn_value': getattr(published_result.roa.origin_as, 'asn', None),
            'prefixes': [str(prefix.prefix) for prefix in published_result.roa.RoaToPrefixTable.all()],
            'max_lengths': [prefix.max_length for prefix in published_result.roa.RoaToPrefixTable.all()],
        }

    imported = published_result.imported_authorization
    return {
        'source': 'provider_imported',
        'imported_authorization_id': imported.pk,
        'name': imported.name,
        'prefix_cidr_text': imported.prefix_cidr_text,
        'origin_asn_value': imported.origin_asn_value,
        'max_length': imported.max_length,
        'external_object_id': imported.external_object_id,
    }


def _serialize_best_published_state_for_plan(intent_result: rpki_models.ROAIntentResult) -> dict:
    details = dict(intent_result.details_json or {})
    published_source = dict(details.get('published_source') or {})
    published_source.update(
        {
            'prefix_cidr_text': details.get('published_prefix'),
            'origin_asn_value': details.get('published_origin_asn'),
            'max_length': details.get('published_max_length'),
            'best_match_kind': details.get('best_match_kind'),
            'replacement_reason_code': details.get('replacement_reason_code'),
            'mismatch_axes': details.get('mismatch_axes', []),
        }
    )
    return published_source


def _replacement_reason_text(reason_code: str | None) -> str:
    if not reason_code:
        return 'the published authorization differs from intent'
    return REPLACEMENT_REASON_TEXT.get(reason_code, 'the published authorization differs from intent')


def _intent_result_requires_replacement(intent_result: rpki_models.ROAIntentResult) -> bool:
    details = intent_result.details_json or {}
    return bool(
        intent_result.result_type in REPLACEMENT_INTENT_RESULT_TYPES
        or details.get('replacement_required')
    )


def _plan_withdraw_source_key_for_intent_result(intent_result: rpki_models.ROAIntentResult) -> str | None:
    if intent_result.best_roa_id is not None:
        return f'roa:{intent_result.best_roa_id}'
    if intent_result.best_imported_authorization_id is not None:
        return f'imported:{intent_result.best_imported_authorization_id}'
    return None


def _plan_withdraw_source_key_for_published_result(published_result: rpki_models.PublishedROAResult) -> str:
    if published_result.roa_id is not None:
        return f'roa:{published_result.roa_id}'
    return f'imported:{published_result.imported_authorization_id}'


def _serialize_provider_route_payload_for_intent(intent: rpki_models.ROAIntent) -> dict:
    return {
        'asn': intent.origin_asn_value,
        'prefix': intent.prefix_cidr_text,
        'max_length': intent.max_length,
    }


def _serialize_provider_route_payload_for_imported(
    imported: rpki_models.ImportedRoaAuthorization,
) -> dict:
    payload = {
        'asn': imported.origin_asn_value,
        'prefix': imported.prefix_cidr_text,
        'max_length': imported.max_length,
    }
    comment = imported.payload_json.get('comment') if isinstance(imported.payload_json, dict) else None
    if comment:
        payload['comment'] = comment
    return payload


def create_roa_change_plan(
    reconciliation_run: rpki_models.ROAReconciliationRun,
    *,
    name: str | None = None,
) -> rpki_models.ROAChangePlan:
    if reconciliation_run.status != rpki_models.ValidationRunStatus.COMPLETED:
        raise RoutingIntentExecutionError('ROA change plans can only be created from completed reconciliation runs.')

    now = timezone.now()
    provider_account = None
    provider_snapshot = None
    if reconciliation_run.comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
        provider_snapshot = reconciliation_run.provider_snapshot
        if provider_snapshot is None:
            raise RoutingIntentExecutionError(
                'Provider-imported reconciliation runs must reference the source provider snapshot.'
            )
        provider_account = provider_snapshot.provider_account
        if provider_account is None:
            raise RoutingIntentExecutionError(
                'Provider-imported reconciliation runs must reference a provider snapshot with a provider account.'
            )

    plan = rpki_models.ROAChangePlan.objects.create(
        name=name or f'{reconciliation_run.name} Change Plan {now:%Y-%m-%d %H:%M:%S}',
        organization=reconciliation_run.organization,
        source_reconciliation_run=reconciliation_run,
        provider_account=provider_account,
        provider_snapshot=provider_snapshot,
        tenant=reconciliation_run.tenant,
        status=rpki_models.ROAChangePlanStatus.DRAFT,
    )

    create_count = 0
    withdraw_count = 0
    replacement_count = 0
    replacement_create_count = 0
    replacement_withdraw_count = 0
    replacement_reason_counts: dict[str, int] = {}
    plan_semantic_counts: dict[str, int] = {}
    skipped_counts: dict[str, int] = {}
    replacement_withdraw_sources: set[str] = set()

    for intent_result in reconciliation_run.intent_results.select_related(
        'roa_intent',
        'best_roa',
        'best_imported_authorization',
    ).all():
        if (
            intent_result.result_type == rpki_models.ROAIntentResultType.MISSING
            and intent_result.roa_intent.derived_state == rpki_models.ROAIntentDerivedState.ACTIVE
        ):
            rpki_models.ROAChangePlanItem.objects.create(
                name=f'Create {intent_result.roa_intent.name}',
                change_plan=plan,
                tenant=intent_result.tenant,
                action_type=rpki_models.ROAChangePlanAction.CREATE,
                plan_semantic=rpki_models.ROAChangePlanItemSemantic.CREATE,
                roa_intent=intent_result.roa_intent,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.ADD_ROUTE
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_route_payload_for_intent(intent_result.roa_intent)
                    if provider_account is not None
                    else {}
                ),
                after_state_json=_serialize_intent_for_plan(intent_result.roa_intent),
                reason='Intent is active but no published authorization matched.',
            )
            create_count += 1
            plan_semantic_counts[rpki_models.ROAChangePlanItemSemantic.CREATE] = (
                plan_semantic_counts.get(rpki_models.ROAChangePlanItemSemantic.CREATE, 0) + 1
            )
        elif (
            intent_result.roa_intent.derived_state == rpki_models.ROAIntentDerivedState.ACTIVE
            and _intent_result_requires_replacement(intent_result)
        ):
            replacement_reason = (intent_result.details_json or {}).get('replacement_reason_code')
            published_state = _serialize_best_published_state_for_plan(intent_result)
            target_state = _serialize_intent_for_plan(intent_result.roa_intent)
            rpki_models.ROAChangePlanItem.objects.create(
                name=f'Replace with {intent_result.roa_intent.name}',
                change_plan=plan,
                tenant=intent_result.tenant,
                action_type=rpki_models.ROAChangePlanAction.CREATE,
                plan_semantic=rpki_models.ROAChangePlanItemSemantic.REPLACE,
                roa_intent=intent_result.roa_intent,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.ADD_ROUTE
                    if provider_account is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_route_payload_for_intent(intent_result.roa_intent)
                    if provider_account is not None
                    else {}
                ),
                before_state_json=published_state,
                after_state_json=target_state,
                reason=f'Create the intended authorization because {_replacement_reason_text(replacement_reason)}.',
            )
            create_count += 1
            replacement_count += 1
            replacement_create_count += 1
            plan_semantic_counts[rpki_models.ROAChangePlanItemSemantic.REPLACE] = (
                plan_semantic_counts.get(rpki_models.ROAChangePlanItemSemantic.REPLACE, 0) + 1
            )
            if replacement_reason:
                replacement_reason_counts[replacement_reason] = replacement_reason_counts.get(replacement_reason, 0) + 1

            withdraw_source_key = _plan_withdraw_source_key_for_intent_result(intent_result)
            if withdraw_source_key is not None and withdraw_source_key not in replacement_withdraw_sources:
                rpki_models.ROAChangePlanItem.objects.create(
                    name=f'Withdraw replaced authorization for {intent_result.roa_intent.name}',
                    change_plan=plan,
                    tenant=intent_result.tenant,
                    action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
                    plan_semantic=rpki_models.ROAChangePlanItemSemantic.REPLACE,
                    roa=intent_result.best_roa,
                    imported_authorization=intent_result.best_imported_authorization,
                    provider_operation=(
                        rpki_models.ProviderWriteOperation.REMOVE_ROUTE
                        if provider_account is not None and intent_result.best_imported_authorization_id is not None
                        else ''
                    ),
                    provider_payload_json=(
                        _serialize_provider_route_payload_for_imported(intent_result.best_imported_authorization)
                        if provider_account is not None and intent_result.best_imported_authorization_id is not None
                        else {}
                    ),
                    before_state_json=published_state,
                    after_state_json=target_state,
                    reason=f'Withdraw the mismatched published authorization because {_replacement_reason_text(replacement_reason)}.',
                )
                withdraw_count += 1
                replacement_withdraw_count += 1
                plan_semantic_counts[rpki_models.ROAChangePlanItemSemantic.REPLACE] = (
                    plan_semantic_counts.get(rpki_models.ROAChangePlanItemSemantic.REPLACE, 0) + 1
                )
                replacement_withdraw_sources.add(withdraw_source_key)
        else:
            skipped_counts[intent_result.result_type] = skipped_counts.get(intent_result.result_type, 0) + 1

    for published_result in reconciliation_run.published_roa_results.select_related('roa', 'imported_authorization').all():
        if published_result.result_type == rpki_models.PublishedROAResultType.ORPHANED:
            rpki_models.ROAChangePlanItem.objects.create(
                name=f'Withdraw {published_result.name}',
                change_plan=plan,
                tenant=published_result.tenant,
                action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
                plan_semantic=rpki_models.ROAChangePlanItemSemantic.WITHDRAW,
                roa=published_result.roa,
                imported_authorization=published_result.imported_authorization,
                provider_operation=(
                    rpki_models.ProviderWriteOperation.REMOVE_ROUTE
                    if provider_account is not None and published_result.imported_authorization_id is not None
                    else ''
                ),
                provider_payload_json=(
                    _serialize_provider_route_payload_for_imported(published_result.imported_authorization)
                    if provider_account is not None and published_result.imported_authorization_id is not None
                    else {}
                ),
                before_state_json=_serialize_published_source_for_plan(published_result),
                reason='Published authorization is orphaned relative to current intent.',
            )
            withdraw_count += 1
            plan_semantic_counts[rpki_models.ROAChangePlanItemSemantic.WITHDRAW] = (
                plan_semantic_counts.get(rpki_models.ROAChangePlanItemSemantic.WITHDRAW, 0) + 1
            )
        else:
            skipped_key = f'published:{published_result.result_type}'
            if _plan_withdraw_source_key_for_published_result(published_result) not in replacement_withdraw_sources:
                skipped_counts[skipped_key] = skipped_counts.get(skipped_key, 0) + 1

    plan.summary_json = {
        'create_count': create_count,
        'withdraw_count': withdraw_count,
        'replacement_count': replacement_count,
        'replacement_create_count': replacement_create_count,
        'replacement_withdraw_count': replacement_withdraw_count,
        'replacement_reason_counts': replacement_reason_counts,
        'provider_backed': provider_account is not None,
        'provider_account_id': getattr(provider_account, 'pk', None),
        'provider_snapshot_id': getattr(provider_snapshot, 'pk', None),
        'comparison_scope': reconciliation_run.comparison_scope,
        'plan_semantic_counts': plan_semantic_counts,
        'skipped_counts': skipped_counts,
    }
    plan.save(update_fields=('summary_json',))
    from netbox_rpki.services.roa_lint import run_roa_lint
    from netbox_rpki.services.rov_simulation import simulate_roa_change_plan

    try:
        lint_run = run_roa_lint(reconciliation_run, change_plan=plan)
        plan.summary_json['lint_run_id'] = lint_run.pk
        plan.summary_json['lint_posture'] = refresh_roa_change_plan_lint_posture(plan)
    except Exception as exc:
        plan.summary_json['lint_error'] = str(exc)
    try:
        simulation_run = simulate_roa_change_plan(plan)
        plan.summary_json['simulation_run_id'] = simulation_run.pk
    except Exception as exc:
        plan.summary_json['simulation_error'] = str(exc)
    plan.save(update_fields=('summary_json',))
    return plan

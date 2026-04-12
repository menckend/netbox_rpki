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


def _default_max_length(profile: rpki_models.RoutingIntentProfile, prefix: Prefix) -> int:
    return prefix.prefix.prefixlen


def _resolve_default_origin_asn(selected_asns) -> tuple[ASN | None, list[str]]:
    warnings = []
    if len(selected_asns) == 1:
        return selected_asns[0], warnings
    if not selected_asns:
        warnings.append('No ASN matched the profile ASN selector; intents without explicit origin rules will be shadowed.')
    else:
        warnings.append('Multiple ASNs matched the profile ASN selector; intents without explicit origin rules will be shadowed.')
    return None, warnings


def _fingerprint_queryset(prefixes, asns, profile, rules, overrides) -> str:
    payload = '|'.join(
        [
            str(profile.pk),
            profile.prefix_selector_query or '',
            profile.asn_selector_query or '',
            ','.join(str(prefix.pk) for prefix in prefixes),
            ','.join(str(asn.pk) for asn in asns),
            ','.join(str(rule.pk) for rule in rules),
            ','.join(str(override.pk) for override in overrides),
        ]
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _resolve_origin_value(origin_asn: ASN | None, origin_asn_value: int | None) -> int | None:
    if origin_asn_value is not None:
        return origin_asn_value
    return getattr(origin_asn, 'asn', None)


def derive_roa_intents(
    profile: rpki_models.RoutingIntentProfile,
    *,
    trigger_mode: str = rpki_models.IntentRunTriggerMode.MANUAL,
    run_name: str | None = None,
) -> rpki_models.IntentDerivationRun:
    if not profile.enabled:
        raise RoutingIntentExecutionError('Routing intent profile is disabled.')

    prefixes = list(
        _apply_selector(
            PrefixFilterSet,
            Prefix.objects.all().select_related('tenant', 'vrf', 'role', '_site', '_region'),
            profile.selector_mode,
            profile.prefix_selector_query,
        )
    )
    selected_asns = list(
        _apply_selector(
            ASNFilterSet,
            ASN.objects.all().select_related('tenant'),
            profile.selector_mode,
            profile.asn_selector_query,
        )
    )
    rules = list(profile.rules.filter(enabled=True).select_related('origin_asn', 'match_tenant', 'match_vrf', 'match_site', 'match_region').order_by('weight', 'name', 'pk'))
    overrides = list(
        profile.organization.roa_intent_overrides.filter(enabled=True)
        .select_related('intent_profile', 'prefix', 'origin_asn', 'tenant_scope', 'vrf_scope', 'site_scope', 'region_scope')
    )
    default_origin_asn, warnings = _resolve_default_origin_asn(selected_asns)
    now = timezone.now()

    derivation_run = rpki_models.IntentDerivationRun.objects.create(
        name=run_name or f'{profile.name} Derivation {now:%Y-%m-%d %H:%M:%S}',
        organization=profile.organization,
        intent_profile=profile,
        tenant=profile.tenant,
        status=rpki_models.ValidationRunStatus.RUNNING,
        trigger_mode=trigger_mode,
        started_at=now,
        input_fingerprint=_fingerprint_queryset(prefixes, selected_asns, profile, rules, overrides),
        prefix_count_scanned=len(prefixes),
        warning_count=len(warnings),
        error_summary='\n'.join(warnings),
    )

    emitted_count = 0
    for prefix in prefixes:
        included = True
        origin_asn = default_origin_asn
        origin_asn_value = getattr(default_origin_asn, 'asn', None)
        max_length = _default_max_length(profile, prefix)
        source_rule = None
        applied_override = None
        explanation_parts = [f'Selected prefix {prefix.prefix} from profile query.']

        for rule in rules:
            if not _prefix_matches_rule(prefix, rule):
                continue

            source_rule = rule
            explanation_parts.append(f'Applied rule {rule.name} ({rule.action}).')

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

        matching_overrides = sorted(
            (
                override
                for override in overrides
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
        resolved_origin_value = _resolve_origin_value(origin_asn, origin_asn_value)
        intent_name = f'{prefix_text} -> AS{resolved_origin_value if resolved_origin_value is not None else "unresolved"}'

        rpki_models.ROAIntent.objects.create(
            name=intent_name,
            derivation_run=derivation_run,
            organization=profile.organization,
            intent_profile=profile,
            tenant=prefix.tenant or profile.tenant,
            intent_key=rpki_models.ROAIntent.build_intent_key(
                prefix_cidr_text=prefix_text,
                address_family=rpki_models.AddressFamily.IPV6 if prefix.family == 6 else rpki_models.AddressFamily.IPV4,
                origin_asn_value=resolved_origin_value,
                max_length=max_length,
                tenant_id=prefix.tenant_id,
                vrf_id=prefix.vrf_id,
                site_id=getattr(_resolve_prefix_site(prefix), 'pk', None),
                region_id=getattr(_resolve_prefix_region(prefix), 'pk', None),
            ),
            prefix=prefix,
            prefix_cidr_text=prefix_text,
            address_family=rpki_models.AddressFamily.IPV6 if prefix.family == 6 else rpki_models.AddressFamily.IPV4,
            origin_asn=origin_asn,
            origin_asn_value=resolved_origin_value,
            is_as0=is_as0,
            max_length=max_length,
            scope_tenant=prefix.tenant,
            scope_vrf=prefix.vrf,
            scope_site=_resolve_prefix_site(prefix),
            scope_region=_resolve_prefix_region(prefix),
            source_rule=source_rule,
            applied_override=applied_override,
            derived_state=derived_state,
            exposure_state=exposure_state,
            explanation=' '.join(explanation_parts),
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


def _result_from_best_match(intent: rpki_models.ROAIntent, best_match_kind: str | None) -> tuple[str, str]:
    if intent.derived_state == rpki_models.ROAIntentDerivedState.SUPPRESSED:
        return rpki_models.ROAIntentResultType.SUPPRESSED_BY_POLICY, rpki_models.ReconciliationSeverity.INFO
    if intent.derived_state != rpki_models.ROAIntentDerivedState.ACTIVE:
        return rpki_models.ROAIntentResultType.INACTIVE_INTENT, rpki_models.ReconciliationSeverity.WARNING
    if best_match_kind is None:
        return rpki_models.ROAIntentResultType.MISSING, rpki_models.ReconciliationSeverity.ERROR
    if best_match_kind == rpki_models.ROAIntentMatchKind.EXACT:
        return rpki_models.ROAIntentResultType.MATCH, rpki_models.ReconciliationSeverity.INFO
    if best_match_kind == rpki_models.ROAIntentMatchKind.STALE_CANDIDATE:
        return rpki_models.ROAIntentResultType.STALE, rpki_models.ReconciliationSeverity.WARNING
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
    result_summary = {}
    best_results_by_source: dict[str, list[str]] = {}
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
                },
            )
            candidates.append(match)

        best_match = None
        if candidates:
            best_match = max(candidates, key=lambda candidate: MATCH_SCORES.get(candidate.match_kind, 0))
            if best_match is not None:
                best_match.is_best_match = True
                best_match.save(update_fields=('is_best_match',))

        result_type, severity = _result_from_best_match(intent, getattr(best_match, 'match_kind', None))
        result_summary[result_type] = result_summary.get(result_type, 0) + 1
        rpki_models.ROAIntentResult.objects.create(
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
            },
            computed_at=now,
        )
        if best_match is not None:
            best_results_by_source.setdefault(_match_source_key(best_match), []).append(result_type)

    for source_key, source_rows in published_by_source.items():
        representative = source_rows[0]
        row_matches = best_results_by_source.get(source_key, [])
        if not row_matches:
            result_type = rpki_models.PublishedROAResultType.ORPHANED
            severity = rpki_models.ReconciliationSeverity.WARNING
        elif rpki_models.ROAIntentResultType.ASN_MISMATCH in row_matches:
            result_type = rpki_models.PublishedROAResultType.WRONG_ORIGIN
            severity = rpki_models.ReconciliationSeverity.ERROR
        elif rpki_models.ROAIntentResultType.MAX_LENGTH_OVERBROAD in row_matches:
            result_type = rpki_models.PublishedROAResultType.BROADER_THAN_NEEDED
            severity = rpki_models.ReconciliationSeverity.WARNING
        else:
            result_type = rpki_models.PublishedROAResultType.MATCHED
            severity = rpki_models.ReconciliationSeverity.INFO

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
            },
            computed_at=now,
        )

    reconciliation_run.status = rpki_models.ValidationRunStatus.COMPLETED
    reconciliation_run.completed_at = timezone.now()
    reconciliation_run.published_roa_count = len(published_by_source)
    reconciliation_run.intent_count = active_intents
    reconciliation_run.result_summary_json = result_summary
    reconciliation_run.save(update_fields=(
        'status',
        'completed_at',
        'published_roa_count',
        'intent_count',
        'result_summary_json',
    ))
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


def create_roa_change_plan(
    reconciliation_run: rpki_models.ROAReconciliationRun,
    *,
    name: str | None = None,
) -> rpki_models.ROAChangePlan:
    if reconciliation_run.status != rpki_models.ValidationRunStatus.COMPLETED:
        raise RoutingIntentExecutionError('ROA change plans can only be created from completed reconciliation runs.')

    now = timezone.now()
    plan = rpki_models.ROAChangePlan.objects.create(
        name=name or f'{reconciliation_run.name} Change Plan {now:%Y-%m-%d %H:%M:%S}',
        organization=reconciliation_run.organization,
        source_reconciliation_run=reconciliation_run,
        tenant=reconciliation_run.tenant,
        status=rpki_models.ROAChangePlanStatus.DRAFT,
    )

    create_count = 0
    withdraw_count = 0
    skipped_counts: dict[str, int] = {}

    for intent_result in reconciliation_run.intent_results.select_related('roa_intent').all():
        if (
            intent_result.result_type == rpki_models.ROAIntentResultType.MISSING
            and intent_result.roa_intent.derived_state == rpki_models.ROAIntentDerivedState.ACTIVE
        ):
            rpki_models.ROAChangePlanItem.objects.create(
                name=f'Create {intent_result.roa_intent.name}',
                change_plan=plan,
                tenant=intent_result.tenant,
                action_type=rpki_models.ROAChangePlanAction.CREATE,
                roa_intent=intent_result.roa_intent,
                after_state_json=_serialize_intent_for_plan(intent_result.roa_intent),
                reason='Intent is active but no published authorization matched.',
            )
            create_count += 1
        else:
            skipped_counts[intent_result.result_type] = skipped_counts.get(intent_result.result_type, 0) + 1

    for published_result in reconciliation_run.published_roa_results.select_related('roa', 'imported_authorization').all():
        if published_result.result_type == rpki_models.PublishedROAResultType.ORPHANED:
            rpki_models.ROAChangePlanItem.objects.create(
                name=f'Withdraw {published_result.name}',
                change_plan=plan,
                tenant=published_result.tenant,
                action_type=rpki_models.ROAChangePlanAction.WITHDRAW,
                roa=published_result.roa,
                imported_authorization=published_result.imported_authorization,
                before_state_json=_serialize_published_source_for_plan(published_result),
                reason='Published authorization is orphaned relative to current intent.',
            )
            withdraw_count += 1
        else:
            skipped_key = f'published:{published_result.result_type}'
            skipped_counts[skipped_key] = skipped_counts.get(skipped_key, 0) + 1

    plan.summary_json = {
        'create_count': create_count,
        'withdraw_count': withdraw_count,
        'skipped_counts': skipped_counts,
    }
    plan.save(update_fields=('summary_json',))
    return plan
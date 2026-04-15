from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from netbox_rpki import models as rpki_models


class IrrCoordinationError(ValueError):
    pass


@dataclass(frozen=True)
class NetboxRoutePolicy:
    stable_key: str
    address_family: str
    prefix: str
    origin_asn: str
    max_length: int | None
    roa_intent: rpki_models.ROAIntent | None


def run_irr_coordination(
    organization: rpki_models.Organization,
    *,
    sources: list[rpki_models.IrrSource] | None = None,
    run_name: str | None = None,
):
    started_at = timezone.now()
    sources = list(sources) if sources is not None else list(
        rpki_models.IrrSource.objects.filter(
            organization=organization,
            enabled=True,
        ).order_by('name', 'pk')
    )
    if not sources:
        raise IrrCoordinationError(f'No enabled IRR sources are configured for organization {organization.name}.')

    coordination_run = rpki_models.IrrCoordinationRun.objects.create(
        name=run_name or f'IRR Coordination {organization.name} {started_at:%Y-%m-%d %H:%M:%S}',
        organization=organization,
        status=rpki_models.IrrCoordinationRunStatus.RUNNING,
        started_at=started_at,
        scope_summary_json={
            'organization_id': organization.pk,
            'organization_name': organization.name,
            'source_ids': [source.pk for source in sources],
        },
    )
    coordination_run.compared_sources.set(sources)

    try:
        results = _build_coordination_results(organization=organization, sources=sources, coordination_run=coordination_run)
        summary_json = _build_run_summary(sources=sources, results=results)
        coordination_run.status = rpki_models.IrrCoordinationRunStatus.COMPLETED
        coordination_run.completed_at = timezone.now()
        coordination_run.summary_json = summary_json
        coordination_run.save(update_fields=('status', 'completed_at', 'summary_json'))
    except Exception as exc:
        coordination_run.status = rpki_models.IrrCoordinationRunStatus.FAILED
        coordination_run.completed_at = timezone.now()
        coordination_run.error_text = str(exc)
        coordination_run.save(update_fields=('status', 'completed_at', 'error_text'))
        raise

    return coordination_run


def _build_coordination_results(*, organization, sources, coordination_run):
    netbox_routes = _load_netbox_route_policy(organization)
    netbox_routes_by_key = {row.stable_key: row for row in netbox_routes}
    netbox_by_prefix = defaultdict(list)
    for row in netbox_routes:
        netbox_by_prefix[row.prefix].append(row)

    results = []
    route_presence_by_source: dict[int, set[str]] = {}

    with transaction.atomic():
        for source in sources:
            snapshot = _latest_snapshot_for_source(source)
            if snapshot is None:
                raise IrrCoordinationError(f'IRR source {source.name} has no completed snapshot to coordinate.')

            if source.sync_health == rpki_models.IrrSyncHealth.STALE:
                results.append(
                    _create_result(
                        coordination_run=coordination_run,
                        source=source,
                        snapshot=snapshot,
                        coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
                        result_type=rpki_models.IrrCoordinationResultType.STALE_SOURCE,
                        severity=rpki_models.ReconciliationSeverity.WARNING,
                        stable_object_key='',
                        summary_json={
                            'source_name': source.name,
                            'snapshot_id': snapshot.pk,
                            'message': 'Latest imported IRR snapshot is stale relative to source sync policy.',
                        },
                    )
                )

            imported_routes = list(
                rpki_models.ImportedIrrRouteObject.objects.filter(snapshot=snapshot).order_by('stable_key', 'pk')
            )
            route_presence_by_source[source.pk] = {route.stable_key for route in imported_routes}
            imported_by_key = {route.stable_key: route for route in imported_routes}
            imported_by_prefix = defaultdict(list)
            for route in imported_routes:
                imported_by_prefix[route.prefix].append(route)

            for stable_key, policy_row in netbox_routes_by_key.items():
                imported_route = imported_by_key.get(stable_key)
                if imported_route is not None:
                    results.append(
                        _create_result(
                            coordination_run=coordination_run,
                            source=source,
                            snapshot=snapshot,
                            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
                            result_type=rpki_models.IrrCoordinationResultType.MATCH,
                            severity=rpki_models.ReconciliationSeverity.INFO,
                            stable_object_key=stable_key,
                            netbox_object_key=policy_row.stable_key,
                            source_object_key=imported_route.stable_key,
                            roa_intent=policy_row.roa_intent,
                            imported_route_object=imported_route,
                            summary_json=_route_summary(policy_row, imported_route),
                        )
                    )
                else:
                    prefix_candidates = imported_by_prefix.get(policy_row.prefix, [])
                    conflict_candidate = next(
                        (candidate for candidate in prefix_candidates if candidate.origin_asn != policy_row.origin_asn),
                        None,
                    )
                    result_type = rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE
                    severity = rpki_models.ReconciliationSeverity.WARNING
                    summary_json = {
                        'netbox_prefix': policy_row.prefix,
                        'netbox_origin_asn': policy_row.origin_asn,
                        'source_name': source.name,
                        'snapshot_id': snapshot.pk,
                    }
                    imported_route_object = None
                    if conflict_candidate is not None:
                        result_type = rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT
                        severity = rpki_models.ReconciliationSeverity.ERROR
                        imported_route_object = conflict_candidate
                        summary_json['source_conflicts'] = [
                            {
                                'stable_key': candidate.stable_key,
                                'origin_asn': candidate.origin_asn,
                                'prefix': candidate.prefix,
                            }
                            for candidate in prefix_candidates
                        ]
                    results.append(
                        _create_result(
                            coordination_run=coordination_run,
                            source=source,
                            snapshot=snapshot,
                            coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
                            result_type=result_type,
                            severity=severity,
                            stable_object_key=stable_key,
                            netbox_object_key=policy_row.stable_key,
                            source_object_key=getattr(imported_route_object, 'stable_key', ''),
                            roa_intent=policy_row.roa_intent,
                            imported_route_object=imported_route_object,
                            summary_json=summary_json,
                        )
                    )

            for imported_route in imported_routes:
                if imported_route.stable_key in netbox_routes_by_key:
                    continue
                results.append(
                    _create_result(
                        coordination_run=coordination_run,
                        source=source,
                        snapshot=snapshot,
                        coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
                        result_type=rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
                        severity=rpki_models.ReconciliationSeverity.WARNING,
                        stable_object_key=imported_route.stable_key,
                        source_object_key=imported_route.stable_key,
                        imported_route_object=imported_route,
                        summary_json={
                            'source_name': source.name,
                            'snapshot_id': snapshot.pk,
                            'source_prefix': imported_route.prefix,
                            'source_origin_asn': imported_route.origin_asn,
                        },
                    )
                )

            _append_context_results(
                results=results,
                coordination_run=coordination_run,
                source=source,
                snapshot=snapshot,
                imported_routes=imported_routes,
            )

        _append_cross_source_conflicts(
            results=results,
            coordination_run=coordination_run,
            organization=organization,
            sources=sources,
            route_presence_by_source=route_presence_by_source,
            netbox_routes=netbox_routes,
        )

    return results


def _append_context_results(*, results, coordination_run, source, snapshot, imported_routes):
    aut_nums = {
        row.asn: row for row in rpki_models.ImportedIrrAutNum.objects.filter(snapshot=snapshot)
    }
    maintainers = {
        row.maintainer_name: row for row in rpki_models.ImportedIrrMaintainer.objects.filter(snapshot=snapshot)
    }

    for route in imported_routes:
        if route.origin_asn not in aut_nums:
            results.append(
                _create_result(
                    coordination_run=coordination_run,
                    source=source,
                    snapshot=snapshot,
                    coordination_family=rpki_models.IrrCoordinationFamily.AUT_NUM_CONTEXT,
                    result_type=rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP,
                    severity=rpki_models.ReconciliationSeverity.WARNING,
                    stable_object_key=route.stable_key,
                    source_object_key=route.stable_key,
                    imported_route_object=route,
                    summary_json={
                        'route_stable_key': route.stable_key,
                        'expected_aut_num': route.origin_asn,
                        'message': 'No imported aut-num record was found for the route origin ASN.',
                    },
                )
            )
        for maintainer_name in route.maintainer_names_json:
            maintainer = maintainers.get(maintainer_name)
            if maintainer is None:
                results.append(
                    _create_result(
                        coordination_run=coordination_run,
                        source=source,
                        snapshot=snapshot,
                        coordination_family=rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
                        result_type=rpki_models.IrrCoordinationResultType.UNSUPPORTED_WRITE,
                        severity=rpki_models.ReconciliationSeverity.WARNING,
                        stable_object_key=route.stable_key,
                        source_object_key=route.stable_key,
                        imported_route_object=route,
                        summary_json={
                            'route_stable_key': route.stable_key,
                            'missing_maintainer_name': maintainer_name,
                            'configured_maintainer_name': source.maintainer_name,
                            'message': 'Route references a maintainer that is not present in the imported maintainer inventory.',
                        },
                    )
                )
            else:
                results.append(
                    _create_result(
                        coordination_run=coordination_run,
                        source=source,
                        snapshot=snapshot,
                        coordination_family=rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
                        result_type=rpki_models.IrrCoordinationResultType.MATCH,
                        severity=rpki_models.ReconciliationSeverity.INFO,
                        stable_object_key=route.stable_key,
                        source_object_key=route.stable_key,
                        imported_route_object=route,
                        imported_maintainer=maintainer,
                        summary_json={
                            'route_stable_key': route.stable_key,
                            'maintainer_name': maintainer_name,
                            'configured_maintainer_name': source.maintainer_name,
                        },
                    )
                )


def _append_cross_source_conflicts(*, results, coordination_run, organization, sources, route_presence_by_source, netbox_routes):
    stable_keys = {row.stable_key for row in netbox_routes}
    for stable_key in sorted(stable_keys):
        present_sources = [
            source for source in sources
            if stable_key in route_presence_by_source.get(source.pk, set())
        ]
        if len(present_sources) == len(sources):
            continue
        missing_sources = [source for source in sources if source not in present_sources]
        if not present_sources or not missing_sources:
            continue
        for source in missing_sources:
            results.append(
                _create_result(
                    coordination_run=coordination_run,
                    source=source,
                    coordination_family=rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
                    result_type=rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT,
                    severity=rpki_models.ReconciliationSeverity.WARNING,
                    stable_object_key=stable_key,
                    summary_json={
                        'organization_id': organization.pk,
                        'stable_key': stable_key,
                        'present_in_sources': [present_source.slug for present_source in present_sources],
                        'missing_in_source': source.slug,
                        'message': 'This NetBox route policy is only present in a subset of compared IRR sources.',
                    },
                )
            )


def _create_result(
    *,
    coordination_run,
    source=None,
    snapshot=None,
    coordination_family,
    result_type,
    severity,
    stable_object_key,
    summary_json,
    netbox_object_key='',
    source_object_key='',
    roa_intent=None,
    imported_route_object=None,
    imported_aut_num=None,
    imported_maintainer=None,
):
    name_parts = [coordination_family, result_type]
    if stable_object_key:
        name_parts.append(stable_object_key)
    result = rpki_models.IrrCoordinationResult.objects.create(
        name=' | '.join(name_parts)[:200],
        coordination_run=coordination_run,
        source=source,
        snapshot=snapshot,
        coordination_family=coordination_family,
        result_type=result_type,
        severity=severity,
        stable_object_key=stable_object_key,
        netbox_object_key=netbox_object_key,
        source_object_key=source_object_key,
        roa_intent=roa_intent,
        imported_route_object=imported_route_object,
        imported_aut_num=imported_aut_num,
        imported_maintainer=imported_maintainer,
        summary_json=summary_json,
    )
    return result


def _route_summary(policy_row, imported_route):
    return {
        'netbox_prefix': policy_row.prefix,
        'netbox_origin_asn': policy_row.origin_asn,
        'netbox_max_length': policy_row.max_length,
        'source_prefix': imported_route.prefix,
        'source_origin_asn': imported_route.origin_asn,
        'source_route_set_names': imported_route.route_set_names_json,
        'source_maintainer_names': imported_route.maintainer_names_json,
    }


def _build_run_summary(*, sources, results):
    result_counts = {
        family: {
            result_type: 0
            for result_type in (
                rpki_models.IrrCoordinationResultType.MATCH,
                rpki_models.IrrCoordinationResultType.MISSING_IN_SOURCE,
                rpki_models.IrrCoordinationResultType.EXTRA_IN_SOURCE,
                rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT,
                rpki_models.IrrCoordinationResultType.UNSUPPORTED_WRITE,
                rpki_models.IrrCoordinationResultType.AMBIGUOUS_LINKAGE,
                rpki_models.IrrCoordinationResultType.STALE_SOURCE,
                rpki_models.IrrCoordinationResultType.POLICY_CONTEXT_GAP,
            )
        }
        for family in (
            rpki_models.IrrCoordinationFamily.ROUTE_OBJECT,
            rpki_models.IrrCoordinationFamily.ROUTE_SET_MEMBERSHIP,
            rpki_models.IrrCoordinationFamily.AS_SET_MEMBERSHIP,
            rpki_models.IrrCoordinationFamily.AUT_NUM_CONTEXT,
            rpki_models.IrrCoordinationFamily.MAINTAINER_SUPPORTABILITY,
        )
    }
    severity_counts = {
        rpki_models.ReconciliationSeverity.INFO: 0,
        rpki_models.ReconciliationSeverity.WARNING: 0,
        rpki_models.ReconciliationSeverity.ERROR: 0,
    }
    draftable_source_count = 0
    non_draftable_source_count = 0
    stale_source_count = 0
    cross_source_conflict_count = 0

    for source in sources:
        if source.supports_apply or source.supports_preview:
            draftable_source_count += 1
        else:
            non_draftable_source_count += 1

    for result in results:
        result_counts[result.coordination_family][result.result_type] += 1
        severity_counts[result.severity] += 1
        if result.result_type == rpki_models.IrrCoordinationResultType.STALE_SOURCE:
            stale_source_count += 1
        if result.result_type == rpki_models.IrrCoordinationResultType.SOURCE_CONFLICT:
            cross_source_conflict_count += 1

    return {
        'source_count': len(sources),
        'sources': [source.slug for source in sources],
        'result_counts': result_counts,
        'severity_counts': severity_counts,
        'draftable_source_count': draftable_source_count,
        'non_draftable_source_count': non_draftable_source_count,
        'stale_source_count': stale_source_count,
        'cross_source_conflict_count': cross_source_conflict_count,
        'latest_plan_ids': [],
    }


def _latest_snapshot_for_source(source):
    return (
        source.snapshots.filter(
            status__in=(
                rpki_models.IrrSnapshotStatus.COMPLETED,
                rpki_models.IrrSnapshotStatus.PARTIAL,
            )
        )
        .order_by('-completed_at', '-started_at', '-pk')
        .first()
    )


def _load_netbox_route_policy(organization):
    rows = []
    queryset = rpki_models.ROAIntent.objects.filter(
        organization=organization,
    ).order_by('prefix_cidr_text', 'origin_asn_value', 'pk')
    for intent in queryset:
        if intent.derived_state != rpki_models.ROAIntentDerivedState.ACTIVE:
            continue
        if not intent.prefix_cidr_text or intent.origin_asn_value is None:
            continue
        address_family = rpki_models.AddressFamily.IPV6 if ':' in intent.prefix_cidr_text else rpki_models.AddressFamily.IPV4
        route_class = 'route6' if address_family == rpki_models.AddressFamily.IPV6 else 'route'
        stable_key = f'{route_class}:{intent.prefix_cidr_text.lower()}AS{intent.origin_asn_value}'
        rows.append(
            NetboxRoutePolicy(
                stable_key=stable_key,
                address_family=address_family,
                prefix=intent.prefix_cidr_text.lower(),
                origin_asn=f'AS{intent.origin_asn_value}',
                max_length=intent.max_length,
                roa_intent=intent,
            )
        )
    return rows

from typing import Annotated

import strawberry
import strawberry_django
from strawberry import ID
from strawberry.scalars import JSON
from strawberry.types import Info

from netbox_rpki import models
from netbox_rpki.detail_specs import get_latest_provider_snapshot_diff
from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

from . import types as graphql_types


@strawberry.type
class ProviderReportingQueryMixin:

    @strawberry.field
    def provider_account_summary(self, info: Info) -> JSON:
        queryset = get_restricted_queryset(models.RpkiProviderAccount, info)
        by_provider_type: dict[str, int] = {}
        by_sync_health: dict[str, int] = {}
        sync_due_count = 0
        roa_write_supported_count = 0

        for provider_account in queryset:
            by_provider_type[provider_account.provider_type] = by_provider_type.get(provider_account.provider_type, 0) + 1
            by_sync_health[provider_account.sync_health] = by_sync_health.get(provider_account.sync_health, 0) + 1
            if provider_account.is_sync_due():
                sync_due_count += 1
            if provider_account.supports_roa_write:
                roa_write_supported_count += 1

        return {
            'total_accounts': queryset.count(),
            'by_provider_type': by_provider_type,
            'by_sync_health': by_sync_health,
            'sync_due_count': sync_due_count,
            'roa_write_supported_count': roa_write_supported_count,
        }

    @strawberry.field
    def provider_snapshot_summary(self, info: Info) -> JSON:
        queryset = get_restricted_queryset(models.ProviderSnapshot, info)
        by_status: dict[str, int] = {}
        latest_completed_at = None
        with_diff_count = 0
        visible_diff_snapshot_ids = set(
            get_restricted_queryset(models.ProviderSnapshotDiff, info)
            .values_list('comparison_snapshot_id', flat=True)
            .distinct()
        )

        for snapshot in queryset:
            by_status[snapshot.status] = by_status.get(snapshot.status, 0) + 1
            if snapshot.completed_at is not None and (latest_completed_at is None or snapshot.completed_at > latest_completed_at):
                latest_completed_at = snapshot.completed_at
            if snapshot.pk in visible_diff_snapshot_ids:
                with_diff_count += 1

        return {
            'total_snapshots': queryset.count(),
            'completed_snapshots': by_status.get(models.ValidationRunStatus.COMPLETED, 0),
            'by_status': by_status,
            'with_diff_count': with_diff_count,
            'latest_completed_at': latest_completed_at,
        }

    @strawberry.field
    def provider_snapshot_latest_diff(
        self,
        info: Info,
        snapshot_id: ID,
    ) -> Annotated['ProviderSnapshotDiffType', strawberry.lazy('.types')] | None:
        snapshot = get_restricted_queryset(models.ProviderSnapshot, info).filter(pk=snapshot_id).first()
        if snapshot is None:
            return None
        return get_latest_provider_snapshot_diff(snapshot)

    @strawberry.field
    def provider_snapshot_diff(
        self,
        info: Info,
        base_snapshot_id: ID,
        comparison_snapshot_id: ID,
    ) -> Annotated['ProviderSnapshotDiffType', strawberry.lazy('.types')] | None:
        return (
            get_restricted_queryset(models.ProviderSnapshotDiff, info)
            .filter(base_snapshot_id=base_snapshot_id, comparison_snapshot_id=comparison_snapshot_id)
            .first()
        )


def get_restricted_queryset(model, info: Info):
    queryset = model.objects.all()
    if hasattr(queryset, 'restrict'):
        return queryset.restrict(info.context.request.user, 'view')
    return queryset


def get_graphql_type_class(spec: ObjectSpec) -> type:
    return getattr(graphql_types, spec.graphql.type.class_name)


def get_graphql_field_names(spec: ObjectSpec) -> tuple[str, str]:
    return spec.graphql.detail_field_name, spec.graphql.list_field_name


GRAPHQL_TYPE_CLASS_MAP = {
    spec.registry_key: get_graphql_type_class(spec)
    for spec in GRAPHQL_OBJECT_SPECS
}

GRAPHQL_FIELD_NAME_MAP = {
    spec.registry_key: get_graphql_field_names(spec)
    for spec in GRAPHQL_OBJECT_SPECS
}


def build_query_type() -> type:
    annotations = {}
    namespace = {
        "__module__": __name__,
    }

    for spec in GRAPHQL_OBJECT_SPECS:
        type_class = GRAPHQL_TYPE_CLASS_MAP[spec.registry_key]
        detail_field_name, list_field_name = GRAPHQL_FIELD_NAME_MAP[spec.registry_key]
        annotations[detail_field_name] = type_class
        annotations[list_field_name] = list[type_class]
        namespace[detail_field_name] = strawberry_django.field()
        namespace[list_field_name] = strawberry_django.field()

    namespace["__annotations__"] = annotations
    query_class = type("NetBoxRpkiQuery", (ProviderReportingQueryMixin,), namespace)
    return strawberry.type(query_class, name="Query")


NetBoxRpkiQuery = build_query_type()


schema = [
    NetBoxRpkiQuery,
]

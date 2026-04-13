from typing import Annotated

import strawberry
import strawberry_django
from strawberry.scalars import JSON

from netbox.graphql.types import NetBoxObjectType

from netbox_rpki.detail_specs import get_latest_provider_snapshot_diff
from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec

from .filters import GRAPHQL_FILTER_CLASS_MAP

@strawberry.type
class ProviderAccountReportingMixin:

    @strawberry.field
    def last_sync_summary(self) -> JSON:
        return self.last_sync_summary_json


@strawberry.type
class ProviderSnapshotReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json

    @strawberry.field
    def latest_diff(self) -> Annotated["ProviderSnapshotDiffType", strawberry.lazy('.types')] | None:
        return get_latest_provider_snapshot_diff(self)

    @strawberry.field(name='imported_roa_authorizations')
    def imported_roa_authorizations_query(self) -> list[Annotated["ImportedRoaAuthorizationType", strawberry.lazy('.types')]]:
        return self.imported_roa_authorizations.all()

    @strawberry.field(name='imported_aspas')
    def imported_aspas_query(self) -> list[Annotated["ImportedAspaType", strawberry.lazy('.types')]]:
        return self.imported_aspas.all()

    @strawberry.field(name='imported_ca_metadata_records')
    def imported_ca_metadata_records_query(self) -> list[Annotated["ImportedCaMetadataType", strawberry.lazy('.types')]]:
        return self.imported_ca_metadata_records.all()

    @strawberry.field(name='imported_parent_links')
    def imported_parent_links_query(self) -> list[Annotated["ImportedParentLinkType", strawberry.lazy('.types')]]:
        return self.imported_parent_links.all()

    @strawberry.field(name='imported_child_links')
    def imported_child_links_query(self) -> list[Annotated["ImportedChildLinkType", strawberry.lazy('.types')]]:
        return self.imported_child_links.all()

    @strawberry.field(name='imported_resource_entitlements')
    def imported_resource_entitlements_query(self) -> list[Annotated["ImportedResourceEntitlementType", strawberry.lazy('.types')]]:
        return self.imported_resource_entitlements.all()

    @strawberry.field(name='imported_publication_points')
    def imported_publication_points_query(self) -> list[Annotated["ImportedPublicationPointType", strawberry.lazy('.types')]]:
        return self.imported_publication_points.all()

    @strawberry.field(name='imported_signed_objects')
    def imported_signed_objects_query(self) -> list[Annotated["ImportedSignedObjectType", strawberry.lazy('.types')]]:
        return self.imported_signed_objects.all()

    @strawberry.field(name='imported_certificate_observations')
    def imported_certificate_observations_query(self) -> list[Annotated["ImportedCertificateObservationType", strawberry.lazy('.types')]]:
        return self.imported_certificate_observations.all()


@strawberry.type
class ProviderSnapshotDiffReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json

    @strawberry.field
    def item_count(self) -> int:
        return self.items.count()


REPORTING_MIXINS = {
    'rpkiprovideraccount': ProviderAccountReportingMixin,
    'providersnapshot': ProviderSnapshotReportingMixin,
    'providersnapshotdiff': ProviderSnapshotDiffReportingMixin,
}


def build_graphql_type_class(spec: ObjectSpec) -> type[NetBoxObjectType]:
    reporting_mixin = REPORTING_MIXINS.get(spec.registry_key, object)
    bases = (reporting_mixin, NetBoxObjectType) if reporting_mixin is not object else (NetBoxObjectType,)
    type_class = type(
        spec.graphql.type.class_name,
        bases,
        {
            "__module__": __name__,
            "__doc__": f"Generated GraphQL type for {spec.model.__name__}.",
            "__object_spec__": spec,
        },
    )
    return strawberry_django.type(
        spec.model,
        fields=spec.graphql.type.fields,
        filters=GRAPHQL_FILTER_CLASS_MAP[spec.registry_key],
    )(type_class)


GRAPHQL_TYPE_CLASS_MAP = {}
for object_spec in GRAPHQL_OBJECT_SPECS:
    type_class = build_graphql_type_class(object_spec)
    GRAPHQL_TYPE_CLASS_MAP[object_spec.registry_key] = type_class
    globals()[object_spec.graphql.type.class_name] = type_class


__all__ = tuple(spec.graphql.type.class_name for spec in GRAPHQL_OBJECT_SPECS)

from typing import Annotated

import strawberry
import strawberry_django
from strawberry.scalars import JSON
from strawberry.types import Info

from netbox.graphql.types import NetBoxObjectType

from netbox_rpki import models
from netbox_rpki.detail_specs import get_latest_provider_snapshot_diff
from netbox_rpki.object_registry import GRAPHQL_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec
from netbox_rpki.services.lifecycle_reporting import (
    build_provider_lifecycle_health_summary,
    build_provider_lifecycle_timeline,
    build_provider_publication_diff_timeline,
    build_snapshot_publication_health_rollup,
    build_diff_publication_health_rollup,
)
from netbox_rpki.services.provider_sync_contract import (
    build_provider_account_rollup,
    build_provider_snapshot_diff_rollup,
    build_provider_snapshot_rollup,
)
from netbox_rpki.services.provider_sync_evidence import (
    get_certificate_observation_evidence_summary,
    get_certificate_observation_is_ambiguous,
    get_certificate_observation_publication_linkage_status,
    get_certificate_observation_signed_object_linkage_status,
    get_certificate_observation_source_count,
    get_certificate_observation_source_labels,
    get_publication_point_authored_linkage_status,
    get_publication_point_evidence_summary,
    get_signed_object_authored_linkage_status,
    get_signed_object_evidence_summary,
    get_signed_object_publication_linkage_status,
)

from .filters import GRAPHQL_FILTER_CLASS_MAP

@strawberry.type
class ProviderAccountReportingMixin:

    @strawberry.field
    def last_sync_summary(self) -> JSON:
        return self.last_sync_summary_json

    @strawberry.field
    def supports_aspa_write(self) -> bool:
        return models.RpkiProviderAccount.supports_aspa_write.fget(self)

    @strawberry.field
    def aspa_write_mode(self) -> str:
        return models.RpkiProviderAccount.aspa_write_mode.fget(self)

    @strawberry.field
    def aspa_write_capability(self) -> JSON:
        return models.RpkiProviderAccount.aspa_write_capability.fget(self)

    @strawberry.field
    def last_sync_rollup(self, info: Info) -> JSON:
        summary = self.last_sync_summary_json or {}
        snapshot_id = summary.get('latest_snapshot_id')
        diff_id = summary.get('latest_diff_id')
        visible_snapshot_ids = None
        visible_diff_ids = None

        if snapshot_id is not None:
            visible_snapshot_ids = set(
                models.ProviderSnapshot.objects.restrict(info.context.request.user, 'view')
                .filter(pk=snapshot_id)
                .values_list('pk', flat=True)
            )
        if diff_id is not None:
            visible_diff_ids = set(
                models.ProviderSnapshotDiff.objects.restrict(info.context.request.user, 'view')
                .filter(pk=diff_id)
                .values_list('pk', flat=True)
            )

        return build_provider_account_rollup(
            self,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    @strawberry.field
    def lifecycle_health_summary(self, info: Info) -> JSON:
        summary = self.last_sync_summary_json or {}
        snapshot_id = summary.get('latest_snapshot_id')
        diff_id = summary.get('latest_diff_id')
        visible_snapshot_ids = None
        visible_diff_ids = None

        if snapshot_id is not None:
            visible_snapshot_ids = set(
                models.ProviderSnapshot.objects.restrict(info.context.request.user, 'view')
                .filter(pk=snapshot_id)
                .values_list('pk', flat=True)
            )
        if diff_id is not None:
            visible_diff_ids = set(
                models.ProviderSnapshotDiff.objects.restrict(info.context.request.user, 'view')
                .filter(pk=diff_id)
                .values_list('pk', flat=True)
            )

        return build_provider_lifecycle_health_summary(
            self,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    @strawberry.field
    def publication_health(self) -> JSON:
        return build_provider_account_rollup(self).get('publication_health') or {}

    @strawberry.field
    def health_timeline(self, info: Info) -> JSON:
        visible_snapshot_ids = set(
            models.ProviderSnapshot.objects.restrict(info.context.request.user, 'view')
            .filter(provider_account=self)
            .values_list('pk', flat=True)
        )
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(info.context.request.user, 'view')
            .filter(provider_account=self)
            .values_list('pk', flat=True)
        )

        return build_provider_lifecycle_timeline(
            self,
            visible_snapshot_ids=visible_snapshot_ids,
            visible_diff_ids=visible_diff_ids,
        )

    @strawberry.field
    def publication_diff_timeline(self, info: Info) -> JSON:
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(info.context.request.user, 'view')
            .filter(provider_account=self)
            .values_list('pk', flat=True)
        )

        return build_provider_publication_diff_timeline(
            self,
            visible_diff_ids=visible_diff_ids,
        )


@strawberry.type
class ProviderSnapshotReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json

    @strawberry.field
    def latest_diff(self) -> Annotated["ProviderSnapshotDiffType", strawberry.lazy('.types')] | None:
        return get_latest_provider_snapshot_diff(self)

    @strawberry.field
    def latest_diff_summary(self, info: Info) -> JSON | None:
        visible_diff_ids = set(
            models.ProviderSnapshotDiff.objects.restrict(info.context.request.user, 'view')
            .filter(comparison_snapshot=self)
            .values_list('pk', flat=True)
        )
        return build_provider_snapshot_rollup(self, visible_diff_ids=visible_diff_ids)['latest_diff_summary']

    @strawberry.field
    def family_rollups(self) -> JSON:
        return build_provider_snapshot_rollup(self)['family_rollups']

    @strawberry.field
    def family_status_counts(self) -> JSON:
        return build_provider_snapshot_rollup(self)['family_status_counts']

    @strawberry.field
    def publication_health(self) -> JSON:
        return build_snapshot_publication_health_rollup(self)

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

    @strawberry.field
    def family_rollups(self) -> JSON:
        return build_provider_snapshot_diff_rollup(self)['family_rollups']

    @strawberry.field
    def family_status_counts(self) -> JSON:
        return build_provider_snapshot_diff_rollup(self)['family_status_counts']

    @strawberry.field
    def publication_diff_summary(self) -> JSON:
        return build_diff_publication_health_rollup(self)


@strawberry.type
class ValidatorInstanceReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json or {}


@strawberry.type
class ValidationRunReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json or {}


@strawberry.type
class ObjectValidationResultReportingMixin:

    @strawberry.field
    def details(self) -> JSON:
        return self.details_json or {}


@strawberry.type
class ValidatedRoaPayloadReportingMixin:

    @strawberry.field
    def details(self) -> JSON:
        return self.details_json or {}


@strawberry.type
class ValidatedAspaPayloadReportingMixin:

    @strawberry.field
    def details(self) -> JSON:
        return self.details_json or {}


@strawberry.type
class TelemetrySourceReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json or {}

    @strawberry.field
    def sync_health(self) -> str:
        return models.TelemetrySource.sync_health.fget(self)

    @strawberry.field
    def sync_health_display(self) -> str:
        return models.TelemetrySource.sync_health_display.fget(self)


@strawberry.type
class TelemetryRunReportingMixin:

    @strawberry.field
    def summary(self) -> JSON:
        return self.summary_json or {}


@strawberry.type
class BgpPathObservationReportingMixin:

    @strawberry.field
    def details(self) -> JSON:
        return self.details_json or {}


@strawberry.type
class SignedObjectSurfaceMixin:

    @strawberry.field
    def legacy_roa(self) -> Annotated["RoaType", strawberry.lazy('.types')] | None:
        try:
            return self.legacy_roa
        except models.Roa.DoesNotExist:
            return None

    @strawberry.field
    def crl_extension(self) -> Annotated["CertificateRevocationListType", strawberry.lazy('.types')] | None:
        try:
            return self.crl_extension
        except models.CertificateRevocationList.DoesNotExist:
            return None

    @strawberry.field
    def manifest_extension(self) -> Annotated["ManifestType", strawberry.lazy('.types')] | None:
        try:
            return self.manifest_extension
        except models.Manifest.DoesNotExist:
            return None

    @strawberry.field
    def trust_anchor_key_extension(self) -> Annotated["TrustAnchorKeyType", strawberry.lazy('.types')] | None:
        try:
            return self.trust_anchor_key_extension
        except models.TrustAnchorKey.DoesNotExist:
            return None

    @strawberry.field
    def aspa_extension(self) -> Annotated["ASPAType", strawberry.lazy('.types')] | None:
        try:
            return self.aspa_extension
        except models.ASPA.DoesNotExist:
            return None

    @strawberry.field
    def rsc_extension(self) -> Annotated["RSCType", strawberry.lazy('.types')] | None:
        try:
            return self.rsc_extension
        except models.RSC.DoesNotExist:
            return None

    @strawberry.field
    def imported_signed_object_observations(self) -> list[Annotated["ImportedSignedObjectType", strawberry.lazy('.types')]]:
        return self.imported_signed_object_observations.all()

    @strawberry.field
    def validation_results(self) -> list[Annotated["ObjectValidationResultType", strawberry.lazy('.types')]]:
        return self.validation_results.all()


@strawberry.type
class ImportedPublicationPointEvidenceMixin:

    @strawberry.field
    def authored_linkage_status(self) -> str:
        return get_publication_point_authored_linkage_status(self)

    @strawberry.field
    def evidence_summary(self) -> JSON:
        return get_publication_point_evidence_summary(self)


@strawberry.type
class ImportedSignedObjectEvidenceMixin:

    @strawberry.field
    def publication_linkage_status(self) -> str:
        return get_signed_object_publication_linkage_status(self)

    @strawberry.field
    def authored_linkage_status(self) -> str:
        return get_signed_object_authored_linkage_status(self)

    @strawberry.field
    def evidence_summary(self) -> JSON:
        return get_signed_object_evidence_summary(self)


@strawberry.type
class ImportedCertificateObservationEvidenceMixin:

    @strawberry.field
    def source_count(self) -> int:
        return get_certificate_observation_source_count(self)

    @strawberry.field
    def source_labels(self) -> list[str]:
        return get_certificate_observation_source_labels(self)

    @strawberry.field
    def is_ambiguous(self) -> bool:
        return get_certificate_observation_is_ambiguous(self)

    @strawberry.field
    def publication_linkage_status(self) -> str:
        return get_certificate_observation_publication_linkage_status(self)

    @strawberry.field
    def signed_object_linkage_status(self) -> str:
        return get_certificate_observation_signed_object_linkage_status(self)

    @strawberry.field
    def evidence_summary(self) -> JSON:
        return get_certificate_observation_evidence_summary(self)


REPORTING_MIXINS = {
    'validatorinstance': ValidatorInstanceReportingMixin,
    'validationrun': ValidationRunReportingMixin,
    'objectvalidationresult': ObjectValidationResultReportingMixin,
    'validatedroapayload': ValidatedRoaPayloadReportingMixin,
    'validatedaspapayload': ValidatedAspaPayloadReportingMixin,
    'telemetrysource': TelemetrySourceReportingMixin,
    'telemetryrun': TelemetryRunReportingMixin,
    'bgppathobservation': BgpPathObservationReportingMixin,
    'rpkiprovideraccount': ProviderAccountReportingMixin,
    'providersnapshot': ProviderSnapshotReportingMixin,
    'providersnapshotdiff': ProviderSnapshotDiffReportingMixin,
    'signedobject': SignedObjectSurfaceMixin,
    'importedpublicationpoint': ImportedPublicationPointEvidenceMixin,
    'importedsignedobject': ImportedSignedObjectEvidenceMixin,
    'importedcertificateobservation': ImportedCertificateObservationEvidenceMixin,
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

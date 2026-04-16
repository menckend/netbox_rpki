from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from netbox_rpki import models as rpki_models


if TYPE_CHECKING:
    from collections.abc import Mapping


ARIN_ROA_ONLY_LIMITATION_REASON = (
    'ARIN synchronization currently imports hosted ROA authorizations only; this family is not yet '
    'implemented for ARIN.'
)
KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON = (
    'Repository-derived certificate observation is linked to publication points and signed objects, '
    'and it is populated from certificate-bearing Krill metadata, but it is still not a full repository '
    'validator or canonical certificate catalog.'
)


class ProviderAdapterLookupError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderCredentialRequirement:
    field_name: str
    issue_text: str
    remediation: str


@dataclass(frozen=True)
class ProviderCredentialIssue:
    field_name: str
    issue_text: str
    remediation: str


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    sync_target_field: str = 'org_handle'
    sync_target_label: str = 'organization handle'
    sync_requires_target: bool = False
    supports_roa_read: bool = False
    supports_aspa_read: bool = False
    supports_certificate_inventory: bool = False
    supports_repository_metadata: bool = False
    supports_bulk_operations: bool = False
    roa_write_mode: str = rpki_models.ProviderRoaWriteMode.UNSUPPORTED
    supported_roa_plan_actions: tuple[str, ...] = ()
    aspa_write_mode: str = rpki_models.ProviderAspaWriteMode.UNSUPPORTED
    supported_aspa_plan_actions: tuple[str, ...] = ()
    supported_sync_families: tuple[str, ...] = ()
    family_capability_overrides: dict[str, dict[str, object]] = field(default_factory=dict)
    family_default_status_overrides: dict[str, str] = field(default_factory=dict)
    sync_summary_aliases: dict[str, str] = field(default_factory=dict)
    credential_requirements: tuple[ProviderCredentialRequirement, ...] = ()


class ProviderAdapter(ABC):
    provider_type: str
    profile: ProviderCapabilityProfile

    def sync_target_handle(self, provider_account: rpki_models.RpkiProviderAccount) -> str:
        return str(getattr(provider_account, self.profile.sync_target_field, '') or '').strip()

    def supported_sync_families(self) -> tuple[str, ...]:
        return self.profile.supported_sync_families

    def family_capability_extra(self, family: str) -> dict[str, object]:
        return dict(self.profile.family_capability_overrides.get(family, {}))

    def family_default_status(self, family: str) -> str | None:
        return self.profile.family_default_status_overrides.get(family)

    def sync_summary_aliases(self) -> dict[str, str]:
        return dict(self.profile.sync_summary_aliases)

    def credential_issues(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
    ) -> list[ProviderCredentialIssue]:
        issues: list[ProviderCredentialIssue] = []
        for requirement in self.profile.credential_requirements:
            value = str(getattr(provider_account, requirement.field_name, '') or '').strip()
            if value:
                continue
            issues.append(
                ProviderCredentialIssue(
                    field_name=requirement.field_name,
                    issue_text=requirement.issue_text,
                    remediation=requirement.remediation,
                )
            )
        return issues

    def validate_sync_account(self, provider_account: rpki_models.RpkiProviderAccount) -> None:
        if self.profile.sync_requires_target and not self.sync_target_handle(provider_account):
            raise ValueError(
                f'Provider account {provider_account.name} is missing a {self.profile.sync_target_label}.'
            )

    def ensure_roa_write_supported(self, provider_account: rpki_models.RpkiProviderAccount) -> None:
        if self.profile.roa_write_mode == rpki_models.ProviderRoaWriteMode.UNSUPPORTED:
            raise ValueError(
                f'Provider account {provider_account.name} does not support ROA write operations.'
            )

    def ensure_aspa_write_supported(self, provider_account: rpki_models.RpkiProviderAccount) -> None:
        if self.profile.aspa_write_mode == rpki_models.ProviderAspaWriteMode.UNSUPPORTED:
            raise ValueError(
                f'Provider account {provider_account.name} does not support ASPA write operations.'
            )

    def augment_sync_summary(
        self,
        summary: dict[str, object],
        resolved_family_summaries: Mapping[str, Mapping[str, object]],
    ) -> None:
        for summary_prefix, family in self.profile.sync_summary_aliases.items():
            family_summary = resolved_family_summaries.get(family, {})
            summary[f'{summary_prefix}_fetched'] = int(family_summary.get('records_fetched', 0) or 0)
            summary[f'{summary_prefix}_imported'] = int(family_summary.get('records_imported', 0) or 0)

    @abstractmethod
    def sync_inventory(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        snapshot: rpki_models.ProviderSnapshot,
    ) -> dict[str, dict[str, object]]:
        raise NotImplementedError

    def apply_roa_delta(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        delta: dict[str, list[dict]],
    ) -> dict:
        self.ensure_roa_write_supported(provider_account)
        raise ValueError(
            f'Provider account {provider_account.name} does not support ROA write operations.'
        )

    def apply_aspa_delta(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        delta: dict[str, list[dict]],
    ) -> dict:
        self.ensure_aspa_write_supported(provider_account)
        raise ValueError(
            f'Provider account {provider_account.name} does not support ASPA write operations.'
        )


class ArinProviderAdapter(ProviderAdapter):
    provider_type = rpki_models.ProviderType.ARIN
    profile = ProviderCapabilityProfile(
        sync_target_field='org_handle',
        sync_target_label='organization handle',
        sync_requires_target=False,
        supports_roa_read=True,
        supported_sync_families=(rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,),
        family_capability_overrides={
            family: {
                'capability_status': rpki_models.ProviderSyncFamilyStatus.NOT_IMPLEMENTED,
                'capability_mode': 'provider_limited',
                'capability_reason': ARIN_ROA_ONLY_LIMITATION_REASON,
            }
            for family in (
                rpki_models.ProviderSyncFamily.ASPAS,
                rpki_models.ProviderSyncFamily.CA_METADATA,
                rpki_models.ProviderSyncFamily.PARENT_LINKS,
                rpki_models.ProviderSyncFamily.CHILD_LINKS,
                rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
                rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
                rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
                rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
            )
        },
        credential_requirements=(
            ProviderCredentialRequirement('org_handle', 'organization handle is blank', 'Set org_handle.'),
            ProviderCredentialRequirement('api_key', 'API key is blank', 'Set api_key.'),
            ProviderCredentialRequirement('api_base_url', 'API base URL is blank', 'Set api_base_url.'),
        ),
    )

    def sync_inventory(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        snapshot: rpki_models.ProviderSnapshot,
    ) -> dict[str, dict[str, object]]:
        from netbox_rpki.services import provider_sync as provider_sync_service

        return provider_sync_service._import_arin_records(provider_account, snapshot)


class KrillProviderAdapter(ProviderAdapter):
    provider_type = rpki_models.ProviderType.KRILL
    profile = ProviderCapabilityProfile(
        sync_target_field='ca_handle',
        sync_target_label='Krill CA handle',
        sync_requires_target=True,
        supports_roa_read=True,
        supports_aspa_read=True,
        supports_certificate_inventory=True,
        supports_repository_metadata=True,
        supports_bulk_operations=True,
        roa_write_mode=rpki_models.ProviderRoaWriteMode.KRILL_ROUTE_DELTA,
        supported_roa_plan_actions=(
            rpki_models.ROAChangePlanAction.CREATE,
            rpki_models.ROAChangePlanAction.WITHDRAW,
        ),
        aspa_write_mode=rpki_models.ProviderAspaWriteMode.KRILL_ASPA_DELTA,
        supported_aspa_plan_actions=(
            rpki_models.ASPAChangePlanAction.CREATE,
            rpki_models.ASPAChangePlanAction.WITHDRAW,
        ),
        supported_sync_families=(
            rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
            rpki_models.ProviderSyncFamily.ASPAS,
            rpki_models.ProviderSyncFamily.CA_METADATA,
            rpki_models.ProviderSyncFamily.PARENT_LINKS,
            rpki_models.ProviderSyncFamily.CHILD_LINKS,
            rpki_models.ProviderSyncFamily.RESOURCE_ENTITLEMENTS,
            rpki_models.ProviderSyncFamily.PUBLICATION_POINTS,
            rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
            rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
        ),
        family_capability_overrides={
            rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY: {
                'capability_status': rpki_models.ProviderSyncFamilyStatus.LIMITED,
                'capability_mode': 'derived',
                'capability_sources': [
                    'published_signed_objects',
                    'publication_point_link',
                    'signed_object_link',
                    'ca_metadata',
                    'parent_links',
                    'repo_status',
                ],
                'capability_reason': KRILL_CERTIFICATE_INVENTORY_LIMITATION_REASON,
            }
        },
        family_default_status_overrides={
            rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY: rpki_models.ProviderSyncFamilyStatus.LIMITED,
        },
        sync_summary_aliases={
            'route_records': rpki_models.ProviderSyncFamily.ROA_AUTHORIZATIONS,
            'aspa_records': rpki_models.ProviderSyncFamily.ASPAS,
            'signed_object_records': rpki_models.ProviderSyncFamily.SIGNED_OBJECT_INVENTORY,
            'certificate_records': rpki_models.ProviderSyncFamily.CERTIFICATE_INVENTORY,
        },
        credential_requirements=(
            ProviderCredentialRequirement('org_handle', 'organization handle is blank', 'Set org_handle.'),
            ProviderCredentialRequirement('api_key', 'API key is blank', 'Set api_key.'),
            ProviderCredentialRequirement('api_base_url', 'API base URL is blank', 'Set api_base_url.'),
            ProviderCredentialRequirement(
                'ca_handle',
                'Krill CA handle is blank',
                'Set ca_handle for Krill-backed accounts.',
            ),
        ),
    )

    def sync_inventory(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        snapshot: rpki_models.ProviderSnapshot,
    ) -> dict[str, dict[str, object]]:
        from netbox_rpki.services import provider_sync as provider_sync_service

        return provider_sync_service._import_krill_records(provider_account, snapshot)

    def apply_roa_delta(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        delta: dict[str, list[dict]],
    ) -> dict:
        self.ensure_roa_write_supported(provider_account)
        from netbox_rpki.services import provider_write as provider_write_service

        return provider_write_service._submit_krill_route_delta(provider_account, delta)

    def apply_aspa_delta(
        self,
        provider_account: rpki_models.RpkiProviderAccount,
        delta: dict[str, list[dict]],
    ) -> dict:
        self.ensure_aspa_write_supported(provider_account)
        from netbox_rpki.services import provider_write as provider_write_service

        return provider_write_service._submit_krill_aspa_delta(provider_account, delta)


_ADAPTERS: dict[str, ProviderAdapter] = {
    adapter.provider_type: adapter
    for adapter in (
        ArinProviderAdapter(),
        KrillProviderAdapter(),
    )
}


def get_provider_adapter(
    provider_account: rpki_models.RpkiProviderAccount | None,
) -> ProviderAdapter | None:
    if provider_account is None:
        return None
    return get_provider_adapter_by_type(provider_account.provider_type)


def get_provider_adapter_by_type(provider_type: str) -> ProviderAdapter:
    adapter = _ADAPTERS.get(provider_type)
    if adapter is None:
        raise ProviderAdapterLookupError(f'Provider type {provider_type} is not supported.')
    return adapter

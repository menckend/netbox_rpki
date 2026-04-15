from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from netbox_rpki import models as rpki_models


def _exception_prefix_cidr(exception: rpki_models.ExternalManagementException) -> str:
    if exception.prefix_cidr_text:
        return exception.prefix_cidr_text
    if exception.prefix_id is not None and getattr(exception, 'prefix', None) is not None:
        return str(exception.prefix.prefix)
    return ''


def _exception_origin_asn_value(exception: rpki_models.ExternalManagementException) -> int | None:
    if exception.origin_asn_value is not None:
        return exception.origin_asn_value
    if exception.origin_asn_id is not None and getattr(exception, 'origin_asn', None) is not None:
        return exception.origin_asn.asn
    return None


def _exception_customer_asn_value(exception: rpki_models.ExternalManagementException) -> int | None:
    if exception.customer_asn_value is not None:
        return exception.customer_asn_value
    if exception.customer_asn_id is not None and getattr(exception, 'customer_asn', None) is not None:
        return exception.customer_asn.asn
    return None


def _exception_provider_asn_value(exception: rpki_models.ExternalManagementException) -> int | None:
    if exception.provider_asn_value is not None:
        return exception.provider_asn_value
    if exception.provider_asn_id is not None and getattr(exception, 'provider_asn', None) is not None:
        return exception.provider_asn.asn
    return None


def _serialize_exception(exception: rpki_models.ExternalManagementException) -> dict[str, object]:
    return {
        'id': exception.pk,
        'name': exception.name,
        'scope_type': exception.scope_type,
        'scope_type_display': exception.get_scope_type_display(),
        'owner': exception.owner,
        'reason': exception.reason,
        'starts_at': exception.starts_at.isoformat() if exception.starts_at else None,
        'review_at': exception.review_at.isoformat() if exception.review_at else None,
        'ends_at': exception.ends_at.isoformat() if exception.ends_at else None,
        'approved_by': exception.approved_by or None,
        'approved_at': exception.approved_at.isoformat() if exception.approved_at else None,
        'enabled': exception.enabled,
        'is_active': exception.is_active,
        'is_review_due': exception.is_review_due,
        'is_expired': exception.is_expired,
        'url': exception.get_absolute_url(),
    }


def _active_queryset(organization: rpki_models.Organization | int, *, reference_time=None):
    now = reference_time or timezone.now()
    organization_id = getattr(organization, 'pk', organization)
    return rpki_models.ExternalManagementException.objects.filter(
        organization_id=organization_id,
        enabled=True,
    ).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now),
    ).select_related(
        'organization',
        'prefix',
        'origin_asn',
        'roa',
        'imported_authorization',
        'customer_asn',
        'provider_asn',
        'aspa',
        'imported_aspa',
    ).order_by('scope_type', 'name')


def list_active_external_management_exceptions(organization: rpki_models.Organization | int, *, reference_time=None):
    return list(_active_queryset(organization, reference_time=reference_time))


def _score_roa_prefix_exception(exception: rpki_models.ExternalManagementException) -> int:
    return (
        (4 if exception.prefix_id else 3 if _exception_prefix_cidr(exception) else 0)
        + (2 if exception.origin_asn_id or _exception_origin_asn_value(exception) is not None else 0)
        + (1 if exception.max_length is not None else 0)
    )


def _score_aspa_customer_exception(exception: rpki_models.ExternalManagementException) -> int:
    return (
        2
        + (1 if exception.provider_asn_id or _exception_provider_asn_value(exception) is not None else 0)
    )


def _matches_roa_prefix_scope(
    exception: rpki_models.ExternalManagementException,
    *,
    prefix_cidr_text: str | None,
    origin_asn_value: int | None,
    max_length: int | None,
) -> bool:
    if exception.scope_type != rpki_models.ExternalManagementScope.ROA_PREFIX:
        return False
    scoped_prefix_cidr = _exception_prefix_cidr(exception)
    if scoped_prefix_cidr and scoped_prefix_cidr != (prefix_cidr_text or ''):
        return False
    scoped_origin_asn_value = _exception_origin_asn_value(exception)
    if scoped_origin_asn_value is not None and scoped_origin_asn_value != origin_asn_value:
        return False
    if exception.max_length is not None and exception.max_length != max_length:
        return False
    return bool(exception.prefix_id or scoped_prefix_cidr)


def match_roa_intent_exception(
    organization: rpki_models.Organization | int,
    *,
    prefix_cidr_text: str | None,
    origin_asn_value: int | None,
    max_length: int | None,
    exceptions: list[rpki_models.ExternalManagementException] | None = None,
):
    candidates = exceptions if exceptions is not None else list_active_external_management_exceptions(organization)
    matched = [
        exception
        for exception in candidates
        if _matches_roa_prefix_scope(
            exception,
            prefix_cidr_text=prefix_cidr_text,
            origin_asn_value=origin_asn_value,
            max_length=max_length,
        )
    ]
    if not matched:
        return None
    selected = max(matched, key=_score_roa_prefix_exception)
    return _serialize_exception(selected)


def match_published_roa_exception(
    organization: rpki_models.Organization | int,
    *,
    roa_id: int | None,
    imported_authorization_id: int | None,
    prefix_cidr_text: str | None,
    origin_asn_value: int | None,
    max_length: int | None,
    exceptions: list[rpki_models.ExternalManagementException] | None = None,
):
    candidates = exceptions if exceptions is not None else list_active_external_management_exceptions(organization)
    exact_matches = [
        exception
        for exception in candidates
        if (
            (exception.scope_type == rpki_models.ExternalManagementScope.ROA_OBJECT and exception.roa_id == roa_id)
            or (
                exception.scope_type == rpki_models.ExternalManagementScope.ROA_IMPORTED
                and exception.imported_authorization_id == imported_authorization_id
            )
        )
    ]
    if exact_matches:
        return _serialize_exception(exact_matches[0])
    return match_roa_intent_exception(
        organization,
        prefix_cidr_text=prefix_cidr_text,
        origin_asn_value=origin_asn_value,
        max_length=max_length,
        exceptions=candidates,
    )


def _matches_aspa_customer_scope(
    exception: rpki_models.ExternalManagementException,
    *,
    customer_asn_value: int | None,
    provider_asn_value: int | None = None,
    provider_values: tuple[int, ...] | None = None,
) -> bool:
    if exception.scope_type != rpki_models.ExternalManagementScope.ASPA_CUSTOMER:
        return False
    if _exception_customer_asn_value(exception) != customer_asn_value:
        return False
    scoped_provider = _exception_provider_asn_value(exception)
    if scoped_provider is None:
        return True
    if provider_asn_value is not None:
        return scoped_provider == provider_asn_value
    if provider_values is not None:
        return scoped_provider in provider_values
    return False


def match_aspa_intent_exception(
    organization: rpki_models.Organization | int,
    *,
    customer_asn_value: int | None,
    provider_asn_value: int | None,
    exceptions: list[rpki_models.ExternalManagementException] | None = None,
):
    candidates = exceptions if exceptions is not None else list_active_external_management_exceptions(organization)
    matched = [
        exception
        for exception in candidates
        if _matches_aspa_customer_scope(
            exception,
            customer_asn_value=customer_asn_value,
            provider_asn_value=provider_asn_value,
        )
    ]
    if not matched:
        return None
    selected = max(matched, key=_score_aspa_customer_exception)
    return _serialize_exception(selected)


def match_published_aspa_exception(
    organization: rpki_models.Organization | int,
    *,
    aspa_id: int | None,
    imported_aspa_id: int | None,
    customer_asn_value: int | None,
    provider_values: tuple[int, ...],
    exceptions: list[rpki_models.ExternalManagementException] | None = None,
):
    candidates = exceptions if exceptions is not None else list_active_external_management_exceptions(organization)
    exact_matches = [
        exception
        for exception in candidates
        if (
            (exception.scope_type == rpki_models.ExternalManagementScope.ASPA_OBJECT and exception.aspa_id == aspa_id)
            or (
                exception.scope_type == rpki_models.ExternalManagementScope.ASPA_IMPORTED
                and exception.imported_aspa_id == imported_aspa_id
            )
        )
    ]
    if exact_matches:
        return _serialize_exception(exact_matches[0])

    matched = [
        exception
        for exception in candidates
        if _matches_aspa_customer_scope(
            exception,
            customer_asn_value=customer_asn_value,
            provider_values=provider_values,
        )
    ]
    if not matched:
        return None
    selected = max(matched, key=_score_aspa_customer_exception)
    return _serialize_exception(selected)

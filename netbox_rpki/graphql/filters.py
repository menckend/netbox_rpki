import strawberry_django
from netbox.graphql.filter_mixins import autotype_decorator, BaseFilterMixin

from netbox_rpki.models import (
    Certificate,
    CertificatePrefix,
    CertificateAsn,
    Roa,
    Organization,
    RoaPrefix
)

from netbox_rpki.filtersets import (
    CertificateFilterSet,
    CertificatePrefixFilterSet,
    CertificateAsnFilterSet,
    RoaFilterSet,
    OrganizationFilterSet,
    RoaPrefixFilterSet,
)



@strawberry_django.filter(Certificate, lookups=True)
@autotype_decorator(CertificateFilterSet)

class CertificateFilter(BaseFilterMixin):
    pass


@strawberry_django.filter(CertificatePrefix, lookups=True)
@autotype_decorator(CertificatePrefixFilterSet)

class CertificatePrefixFilter(BaseFilterMixin):
    pass


@strawberry_django.filter(CertificateAsn, lookups=True)
@autotype_decorator(CertificateAsnFilterSet)

class CertificateAsnFilter(BaseFilterMixin):
    pass


@strawberry_django.filter(Roa, lookups=True)
@autotype_decorator(RoaFilterSet)

class RoaFilter(BaseFilterMixin):
    pass


@strawberry_django.filter(Organization, lookups=True)
@autotype_decorator(OrganizationFilterSet)

class OrganizationFilter(BaseFilterMixin):
    pass


@strawberry_django.filter(RoaPrefix, lookups=True)
@autotype_decorator(RoaPrefixFilterSet)

class RoaPrefixFilter(BaseFilterMixin):
    pass

__all__ = (
    CertificateFilter,
    CertificatePrefixFilter,
    CertificateAsnFilter,
    RoaFilter,
    OrganizationFilter,
    RoaPrefixFilter,
)

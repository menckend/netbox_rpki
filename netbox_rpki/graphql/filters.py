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
    CertificateASNFilterSet,
    RoaFilterSet,
    OrganizationFilterSet,
    RoaPrefixFilterSet,
)


__all__ = (
    CertificateFilter,
    CertificatePrefixFilter,
    CertificateASNFilter,
    RoaFilter,
    OrganizationFilter,
    RoaPrefixFilter,
)

@strawberry_django.filter(Certificate, lookups=True)
@autotype_decorator(CertificateFilterSet)
class CertificateFilter(BaseFilterMixin):
    pass

@strawberry_django.filter(CertificatePrefix, lookups=True)
@autotype_decorator(CertificatePrefixFilterSet)
class CertificatePrefixFilter(BaseFilterMixin):
    pass

@strawberry_django.filter(CertificateASN, lookups=True)
@autotype_decorator(CertificateASNFilterSet)
class CertificateASNFilter(BaseFilterMixin):
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


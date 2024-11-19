import strawberry_django
from netbox.graphql.filter_mixins import autotype_decorator, BaseFilterMixin

from netbox_rpki.models import (
    Certificate,
    CertificatePrefix,
    CertificateToASN,
    Roa,
    Organization,
    RoaPrefix
)

from netbox_rpki.filtersets import (
    CertificateFilterSet,
    CertificatePrefixFilterSet,
    CertificateToASNFilterSet,
    RoaFilterSet,
    OrganizationFilterSet,
    RoaPrefixFilterSet,
)


__all__ = (
    CertificateFilter,
    CertificatePrefixFilter,
    CertificateToASNFilter,
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

@strawberry_django.filter(CertificateToASN, lookups=True)
@autotype_decorator(CertificateToASNFilterSet)
class CertificateToASNFilter(BaseFilterMixin):
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


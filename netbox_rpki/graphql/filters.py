import strawberry_django
from strawberry.scalars import ID
from strawberry_django import FilterLookup

try:
    from strawberry_django import StrFilterLookup
except ImportError:
    StrFilterLookup = FilterLookup

from netbox.graphql.filters import NetBoxModelFilter

from netbox_rpki.models import (
    Certificate,
    CertificatePrefix,
    CertificateAsn,
    Roa,
    Organization,
    RoaPrefix
)

@strawberry_django.filter_type(Certificate, lookups=True)
class CertificateFilter(NetBoxModelFilter):
    name: StrFilterLookup[str] | None = strawberry_django.filter_field()
    issuer: StrFilterLookup[str] | None = strawberry_django.filter_field()
    subject: StrFilterLookup[str] | None = strawberry_django.filter_field()
    serial: StrFilterLookup[str] | None = strawberry_django.filter_field()
    auto_renews: FilterLookup[bool] | None = strawberry_django.filter_field()
    self_hosted: FilterLookup[bool] | None = strawberry_django.filter_field()
    rpki_org_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(CertificatePrefix, lookups=True)
class CertificatePrefixFilter(NetBoxModelFilter):
    prefix_id: ID | None = strawberry_django.filter_field()
    certificate_name_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(CertificateAsn, lookups=True)
class CertificateAsnFilter(NetBoxModelFilter):
    asn_id: ID | None = strawberry_django.filter_field()
    certificate_name2_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(Roa, lookups=True)
class RoaFilter(NetBoxModelFilter):
    name: StrFilterLookup[str] | None = strawberry_django.filter_field()
    auto_renews: FilterLookup[bool] | None = strawberry_django.filter_field()
    origin_as_id: ID | None = strawberry_django.filter_field()
    signed_by_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(Organization, lookups=True)
class OrganizationFilter(NetBoxModelFilter):
    org_id: StrFilterLookup[str] | None = strawberry_django.filter_field()
    name: StrFilterLookup[str] | None = strawberry_django.filter_field()
    ext_url: StrFilterLookup[str] | None = strawberry_django.filter_field()
    parent_rir_id: ID | None = strawberry_django.filter_field()


@strawberry_django.filter_type(RoaPrefix, lookups=True)
class RoaPrefixFilter(NetBoxModelFilter):
    prefix_id: ID | None = strawberry_django.filter_field()
    roa_name_id: ID | None = strawberry_django.filter_field()

__all__ = (
    CertificateFilter,
    CertificatePrefixFilter,
    CertificateAsnFilter,
    RoaFilter,
    OrganizationFilter,
    RoaPrefixFilter,
)

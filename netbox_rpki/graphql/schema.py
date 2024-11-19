from typing import Annotated, List

import strawberry
import strawberry_django

from netbox.graphql.types import NetBoxObjectType
from netbox.graphql.scalars import BigInt

from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix
)
from .filters import (
    CertificateFilter,
    CertificatePrefixFilter,
    CertificateAsnFilter,
    RoaFilter,
    OrganizationFilter,
    RoaPrefixFilter,
)


@strawberry_django.type(Organization, fields="__all__", filters=OrganizationFilter)
class OrganizationType(NetBoxObjectType):
    pass

@strawberry_django.type(Certificate, fields="__all__", filters=CertificateFilter)
class CertificateType(NetBoxObjectType):
    pass

@strawberry_django.type(CertificatePrefix, fields="__all__", filters=CertificatePrefixFilter)
class CertificatePrefixType(NetBoxObjectType):
    pass

@strawberry_django.type(CertificateAsn, fields="__all__", filters=CertificateAsnFilter)
class CertificateAsnType(NetBoxObjectType):
    pass

@strawberry_django.type(Roa, fields="__all__", filters=RoaFilter)
class RoaType(NetBoxObjectType):
    pass

@strawberry_django.type(RoaPrefix, fields="__all__", filters=RoaPrefixFilter)
class RoaPrefixType(NetBoxObjectType):
    pass

@strawberry.type(name="Query")
class NetBoxRpkiQuery:

    netbox_rpki_certificate: CertificateType = strawberry_django.field()
    netbox_rpki_certificate_list: List[CertificateType] = strawberry_django.field()
    
    netbox_rpki_certificate_asn: CertificateAsnType = strawberry_django.field()
    netbox_rpki_certificate_asn_list: List[CertificateAsnType] = strawberry_django.field()
    
    netbox_rpki_certificate_prefix: CertificatePrefixType = strawberry_django.field()
    netbox_rpki_certificate_prefix_list: List[CertificatePrefixType] = strawberry_django.field()
    
    netbox_rpki_organization: OrganizationType = strawberry_django.field()
    netbox_rpki_organization_list: List[OrganizationType] = strawberry_django.field()

    netbox_rpki_roa: RoaType = strawberry_django.field()
    netbox_rpki_roa_list: List[RoaType] = strawberry_django.field()

    netbox_rpki_roa_prefix: RoaPrefixType = strawberry_django.field()
    netbox_rpki_roa_prefix_list: List[RoaPrefixType] = strawberry_django.field()

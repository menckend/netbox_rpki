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

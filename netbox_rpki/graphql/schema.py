from typing import List

import strawberry
import strawberry_django

from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix
)
from .types import (
    CertificateType,
    CertificateAsnType,
    CertificatePrefixType,
    OrganizationType,
    RoaType,
    RoaPrefixType
)


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

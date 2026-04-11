from django.utils.text import slugify
from netaddr import IPNetwork

from ipam.models import ASN, Prefix, RIR

from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
)


def create_test_rir(name='RIR 1', slug=None, is_private=True):
    return RIR.objects.create(name=name, slug=slug or slugify(name), is_private=is_private)


def create_test_organization(org_id='org-1', name='Organization 1', **kwargs):
    return Organization.objects.create(org_id=org_id, name=name, **kwargs)


def create_test_certificate(
    name='Certificate 1',
    rpki_org=None,
    auto_renews=True,
    self_hosted=False,
    **kwargs,
):
    if rpki_org is None:
        rpki_org = create_test_organization()
    return Certificate.objects.create(
        name=name,
        rpki_org=rpki_org,
        auto_renews=auto_renews,
        self_hosted=self_hosted,
        **kwargs,
    )


def create_test_prefix(prefix='10.0.0.0/24', **kwargs):
    return Prefix.objects.create(prefix=IPNetwork(prefix), **kwargs)


def create_test_asn(asn=65001, rir=None, **kwargs):
    if rir is None:
        rir = create_test_rir(name=f'RIR {asn}', slug=f'rir-{asn}')
    return ASN.objects.create(asn=asn, rir=rir, **kwargs)


def create_test_roa(name='ROA 1', signed_by=None, auto_renews=True, **kwargs):
    if signed_by is None:
        signed_by = create_test_certificate()
    return Roa.objects.create(name=name, signed_by=signed_by, auto_renews=auto_renews, **kwargs)


def create_test_roa_prefix(prefix=None, roa=None, max_length=24, **kwargs):
    if prefix is None:
        prefix = create_test_prefix()
    if roa is None:
        roa = create_test_roa()
    return roa.RoaToPrefixTable.model.objects.create(
        prefix=prefix,
        roa_name=roa,
        max_length=max_length,
        **kwargs,
    )


def create_test_certificate_prefix(prefix=None, certificate=None, **kwargs):
    if prefix is None:
        prefix = create_test_prefix()
    if certificate is None:
        certificate = create_test_certificate()
    return CertificatePrefix.objects.create(prefix=prefix, certificate_name=certificate, **kwargs)


def create_test_certificate_asn(asn=None, certificate=None, **kwargs):
    if asn is None:
        asn = create_test_asn()
    if certificate is None:
        certificate = create_test_certificate()
    return CertificateAsn.objects.create(asn=asn, certificate_name2=certificate, **kwargs)
# pyright: reportMissingImports=false, reportMissingModuleSource=false

import json

from netaddr import IPNetwork

from ipam.models import ASN, Prefix, RIR
from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    RoaObject,
    RoaObjectPrefix,
)


MARKER_PREFIX = 'Managed by Playwright E2E'


def delete_stale_plugin_objects():
    marker_filter = {'comments__startswith': MARKER_PREFIX}

    CertificateAsn.objects.filter(**marker_filter).delete()
    CertificatePrefix.objects.filter(**marker_filter).delete()
    RoaObjectPrefix.objects.filter(**marker_filter).delete()
    RoaObject.objects.filter(**marker_filter).delete()
    Certificate.objects.filter(**marker_filter).delete()
    Organization.objects.filter(**marker_filter).delete()


def upsert_rir(name, slug):
    rir, _ = RIR.objects.update_or_create(
        slug=slug,
        defaults={
            'is_private': True,
            'name': name,
        },
    )
    return rir


def upsert_asn(asn_value, rir):
    asn, _ = ASN.objects.update_or_create(
        asn=asn_value,
        defaults={
            'rir': rir,
        },
    )
    return asn


def upsert_prefix(prefix_cidr):
    prefix, _ = Prefix.objects.get_or_create(prefix=IPNetwork(prefix_cidr))
    return prefix


delete_stale_plugin_objects()

rir = upsert_rir('NetBox RPKI Playwright RIR', 'netbox-rpki-playwright-rir')
primary_asn = upsert_asn(64561, rir)
secondary_asn = upsert_asn(64562, rir)
primary_prefix = upsert_prefix('10.250.101.0/24')
secondary_prefix = upsert_prefix('10.250.102.0/24')

fixtures = {
    'asns': {
        'primary': {
            'id': primary_asn.pk,
            'label': str(primary_asn),
        },
        'secondary': {
            'id': secondary_asn.pk,
            'label': str(secondary_asn),
        },
    },
    'marker_prefix': MARKER_PREFIX,
    'prefixes': {
        'primary': {
            'id': primary_prefix.pk,
            'label': str(primary_prefix),
        },
        'secondary': {
            'id': secondary_prefix.pk,
            'label': str(secondary_prefix),
        },
    },
    'rir': {
        'id': rir.pk,
        'label': str(rir),
    },
}

print(f'NETBOX_RPKI_E2E_FIXTURES={json.dumps(fixtures, sort_keys=True)}')

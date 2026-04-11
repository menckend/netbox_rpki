#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

require_command python3

SEED_LOG="$STATE_DIR/seed.log"

ensure_state_dir

if [ ! -d "$VENV_DIR" ]; then
    printf 'Missing virtual environment: %s\n' "$VENV_DIR" >&2
    exit 1
fi

if [ ! -d "$NETBOX_PROJECT_DIR" ]; then
    printf 'Missing NetBox project directory: %s\n' "$NETBOX_PROJECT_DIR" >&2
    exit 1
fi

(
    cd "$NETBOX_PROJECT_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    NETBOX_RPKI_ENABLE=1 python manage.py shell >"$SEED_LOG" 2>&1 <<'PY'
from datetime import date

from django.utils.text import slugify
from netaddr import IPNetwork

from ipam.models import ASN, Prefix, RIR
from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Organization,
    Roa,
    RoaPrefix,
)


MARKER = 'Managed by devrun/seed-data.sh'


def upsert(model, filters, defaults):
    instance = model.objects.filter(**filters).order_by('pk').first()
    if instance is None:
        params = defaults.copy()
        params.update(filters)
        return model.objects.create(**params), True

    changed = False
    for key, value in defaults.items():
        if getattr(instance, key) != value:
            setattr(instance, key, value)
            changed = True
    if changed:
        instance.save()
    return instance, False


def upsert_rir(name, slug):
    return upsert(
        RIR,
        {'slug': slug},
        {
            'name': name,
            'is_private': True,
        },
    )


def upsert_org(org_id, name, parent_rir, ext_url):
    return upsert(
        Organization,
        {'org_id': org_id},
        {
            'name': name,
            'parent_rir': parent_rir,
            'ext_url': ext_url,
            'comments': MARKER,
        },
    )


def upsert_certificate(name, rpki_org, **extra):
    defaults = {
        'rpki_org': rpki_org,
        'comments': MARKER,
    }
    defaults.update(extra)
    return upsert(Certificate, {'name': name}, defaults)


def upsert_asn(asn_value, rir):
    return upsert(ASN, {'asn': asn_value}, {'rir': rir})


def upsert_prefix(prefix_cidr):
    return upsert(Prefix, {'prefix': IPNetwork(prefix_cidr)}, {})


def upsert_roa(name, signed_by, **extra):
    defaults = {
        'signed_by': signed_by,
        'comments': MARKER,
    }
    defaults.update(extra)
    return upsert(Roa, {'name': name}, defaults)


def upsert_certificate_prefix(prefix, certificate):
    return upsert(
        CertificatePrefix,
        {'prefix': prefix, 'certificate_name': certificate},
        {'comments': MARKER},
    )


def upsert_certificate_asn(asn, certificate):
    return upsert(
        CertificateAsn,
        {'asn': asn, 'certificate_name2': certificate},
        {'comments': MARKER},
    )


def upsert_roa_prefix(prefix, roa, max_length):
    return upsert(
        RoaPrefix,
        {'prefix': prefix, 'roa_name': roa},
        {
            'max_length': max_length,
            'comments': MARKER,
        },
    )


created = []
reused = []


def remember(label, result):
    instance, was_created = result
    (created if was_created else reused).append(f'{label}:{instance.pk}')
    return instance


arin = remember('rir', upsert_rir('Seed ARIN', 'seed-arin'))
ripe = remember('rir', upsert_rir('Seed RIPE', 'seed-ripe'))
apnic = remember('rir', upsert_rir('Seed APNIC', 'seed-apnic'))

org_edge = remember(
    'org',
    upsert_org('seed-org-edge', 'Seed Edge Networks', arin, 'https://example.invalid/seed-edge'),
)
org_labs = remember(
    'org',
    upsert_org('seed-org-labs', 'Seed Research Labs', ripe, 'https://example.invalid/seed-labs'),
)
org_transit = remember(
    'org',
    upsert_org('seed-org-transit', 'Seed Transit Services', apnic, 'https://example.invalid/seed-transit'),
)
org_isp = remember(
    'org',
    upsert_org('seed-org-isp', 'Seed Regional ISP', arin, 'https://example.invalid/seed-isp'),
)

certificate_edge = remember(
    'certificate',
    upsert_certificate(
        'Seed Edge CA',
        org_edge,
        issuer='Seed ARIN Root',
        subject='CN=Seed Edge CA',
        serial='SEED-EDGE-001',
        valid_from=date(2025, 1, 1),
        valid_to=date(2026, 1, 1),
        auto_renews=True,
        public_key='seed-edge-pub',
        private_key='seed-edge-priv',
        publication_url='rsync://rpki.example.invalid/edge/',
        ca_repository='rsync://repo.example.invalid/edge/',
        self_hosted=True,
    ),
)
certificate_labs = remember(
    'certificate',
    upsert_certificate(
        'Seed Labs CA',
        org_labs,
        issuer='Seed RIPE Root',
        subject='CN=Seed Labs CA',
        serial='SEED-LABS-001',
        valid_from=date(2025, 2, 1),
        valid_to=date(2026, 2, 1),
        auto_renews=False,
        public_key='seed-labs-pub',
        private_key='seed-labs-priv',
        publication_url='https://rpki.example.invalid/labs/',
        ca_repository='https://repo.example.invalid/labs/',
        self_hosted=False,
    ),
)
certificate_transit = remember(
    'certificate',
    upsert_certificate(
        'Seed Transit CA',
        org_transit,
        issuer='Seed APNIC Root',
        subject='CN=Seed Transit CA',
        serial='SEED-TRANSIT-001',
        valid_from=date(2025, 3, 1),
        valid_to=date(2026, 3, 1),
        auto_renews=True,
        publication_url='https://rpki.example.invalid/transit/',
        ca_repository='https://repo.example.invalid/transit/',
        self_hosted=False,
    ),
)
certificate_isp = remember(
    'certificate',
    upsert_certificate(
        'Seed ISP CA',
        org_isp,
        issuer='Seed ARIN Root',
        subject='CN=Seed ISP CA',
        serial='SEED-ISP-001',
        valid_from=date(2025, 4, 1),
        valid_to=date(2026, 4, 1),
        auto_renews=True,
        publication_url='https://rpki.example.invalid/isp/',
        ca_repository='https://repo.example.invalid/isp/',
        self_hosted=True,
    ),
)

asn_edge = remember('asn', upsert_asn(64512, arin))
asn_edge_backup = remember('asn', upsert_asn(64513, arin))
asn_labs = remember('asn', upsert_asn(64520, ripe))
asn_transit = remember('asn', upsert_asn(64530, apnic))
asn_isp = remember('asn', upsert_asn(64540, arin))

prefix_edge_v4 = remember('prefix', upsert_prefix('10.99.0.0/24'))
prefix_edge_v6 = remember('prefix', upsert_prefix('2001:db8:99::/48'))
prefix_labs_v4 = remember('prefix', upsert_prefix('10.99.1.0/24'))
prefix_transit_v4 = remember('prefix', upsert_prefix('10.99.2.0/24'))
prefix_isp_v4 = remember('prefix', upsert_prefix('10.99.3.0/24'))

roa_edge = remember(
    'roa',
    upsert_roa(
        'Seed Edge ROA',
        certificate_edge,
        origin_as=asn_edge,
        valid_from=date(2025, 1, 15),
        valid_to=date(2025, 12, 31),
        auto_renews=True,
    ),
)
roa_labs = remember(
    'roa',
    upsert_roa(
        'Seed Labs ROA',
        certificate_labs,
        origin_as=asn_labs,
        valid_from=date(2025, 2, 15),
        valid_to=date(2025, 11, 30),
        auto_renews=False,
    ),
)
roa_transit = remember(
    'roa',
    upsert_roa(
        'Seed Transit ROA',
        certificate_transit,
        origin_as=asn_transit,
        valid_from=date(2025, 3, 15),
        valid_to=date(2026, 3, 14),
        auto_renews=True,
    ),
)

remember('certificateprefix', upsert_certificate_prefix(prefix_edge_v4, certificate_edge))
remember('certificateprefix', upsert_certificate_prefix(prefix_edge_v6, certificate_edge))
remember('certificateprefix', upsert_certificate_prefix(prefix_labs_v4, certificate_labs))
remember('certificateprefix', upsert_certificate_prefix(prefix_transit_v4, certificate_transit))
remember('certificateprefix', upsert_certificate_prefix(prefix_isp_v4, certificate_isp))

remember('certificateasn', upsert_certificate_asn(asn_edge, certificate_edge))
remember('certificateasn', upsert_certificate_asn(asn_edge_backup, certificate_edge))
remember('certificateasn', upsert_certificate_asn(asn_labs, certificate_labs))
remember('certificateasn', upsert_certificate_asn(asn_transit, certificate_transit))
remember('certificateasn', upsert_certificate_asn(asn_isp, certificate_isp))

remember('roaprefix', upsert_roa_prefix(prefix_edge_v4, roa_edge, 24))
remember('roaprefix', upsert_roa_prefix(prefix_edge_v6, roa_edge, 48))
remember('roaprefix', upsert_roa_prefix(prefix_labs_v4, roa_labs, 25))
remember('roaprefix', upsert_roa_prefix(prefix_transit_v4, roa_transit, 24))

print('SEED_MARKER', MARKER)
print('CREATED_COUNT', len(created))
print('REUSED_COUNT', len(reused))
print('ORGANIZATIONS', Organization.objects.filter(comments=MARKER).count())
print('CERTIFICATES', Certificate.objects.filter(comments=MARKER).count())
print('ROAS', Roa.objects.filter(comments=MARKER).count())
print('CERTIFICATE_PREFIXES', CertificatePrefix.objects.filter(comments=MARKER).count())
print('CERTIFICATE_ASNS', CertificateAsn.objects.filter(comments=MARKER).count())
print('ROA_PREFIXES', RoaPrefix.objects.filter(comments=MARKER).count())
print('CREATED_ITEMS', ','.join(created))
print('REUSED_ITEMS', ','.join(reused))
PY
)

printf 'SEED_LOG=%s\n' "$SEED_LOG"
tail -n 20 "$SEED_LOG"
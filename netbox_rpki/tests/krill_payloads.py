"""Deterministic Krill payload fixtures for provider sync planning and tests."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID


def _fixture_name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _build_ca_certificate(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = _fixture_name(common_name)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        .not_valid_after(datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key=private_key, algorithm=hashes.SHA256())
    )
    return private_key, certificate


def _build_leaf_certificate(
    common_name: str,
    *,
    issuer_private_key: rsa.RSAPrivateKey,
    issuer_certificate: x509.Certificate,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_fixture_name(common_name))
        .issuer_name(issuer_certificate.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        .not_valid_after(datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key=issuer_private_key, algorithm=hashes.SHA256())
    )
    return private_key, certificate


def _der_base64(certificate: x509.Certificate) -> str:
    return base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode('ascii')


def _pkcs7_base64(*, signer_key: rsa.RSAPrivateKey, signer_cert: x509.Certificate, payload: bytes) -> str:
    return base64.b64encode(
        pkcs7.PKCS7SignatureBuilder()
        .set_data(payload)
        .add_signer(signer_cert, signer_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    ).decode('ascii')


def _crl_base64(*, issuer_key: rsa.RSAPrivateKey, issuer_cert: x509.Certificate) -> str:
    crl = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer_cert.subject)
        .last_update(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        .next_update(datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc))
        .sign(private_key=issuer_key, algorithm=hashes.SHA256())
    )
    return base64.b64encode(crl.public_bytes(serialization.Encoding.DER)).decode('ascii')


_ROOT_KEY, _ROOT_CERT = _build_ca_certificate('NetBox RPKI Fixture Root')
_ROUTE_EE_KEY, _ROUTE_EE_CERT = _build_leaf_certificate(
    'NetBox RPKI Fixture Route EE',
    issuer_private_key=_ROOT_KEY,
    issuer_certificate=_ROOT_CERT,
)
_MANIFEST_EE_KEY, _MANIFEST_EE_CERT = _build_leaf_certificate(
    'NetBox RPKI Fixture Manifest EE',
    issuer_private_key=_ROOT_KEY,
    issuer_certificate=_ROOT_CERT,
)
_INCOMING_KEY, _INCOMING_CERT = _build_leaf_certificate(
    'NetBox RPKI Fixture Incoming',
    issuer_private_key=_ROOT_KEY,
    issuer_certificate=_ROOT_CERT,
)
_PARENT_SIGNING_KEY, _PARENT_SIGNING_CERT = _build_leaf_certificate(
    'NetBox RPKI Fixture Parent Signing',
    issuer_private_key=_ROOT_KEY,
    issuer_certificate=_ROOT_CERT,
)
_ROUTE_CMS_BASE64 = _pkcs7_base64(
    signer_key=_ROUTE_EE_KEY,
    signer_cert=_ROUTE_EE_CERT,
    payload=b'netbox-rpki-route-fixture',
)
_MANIFEST_CMS_BASE64 = _pkcs7_base64(
    signer_key=_MANIFEST_EE_KEY,
    signer_cert=_MANIFEST_EE_CERT,
    payload=b'netbox-rpki-manifest-fixture',
)
_INCOMING_CERT_BASE64 = _der_base64(_INCOMING_CERT)
_PARENT_SIGNING_CERT_BASE64 = _der_base64(_PARENT_SIGNING_CERT)
_CRL_BASE64 = _crl_base64(issuer_key=_ROOT_KEY, issuer_cert=_ROOT_CERT)


def _load_live_json(path: str) -> dict[str, object]:
    sample_path = Path(path)
    if not sample_path.exists():
        return {}
    return json.loads(sample_path.read_text())


_LIVE_SAMPLE_BUNDLE = _load_live_json('/tmp/krill_live_samples.json')
_LIVE_REPO_STATUS = _load_live_json('/tmp/krill_repo_status.json')


def _live_sample_value(sample_name: str, key: str) -> str:
    sample = _LIVE_SAMPLE_BUNDLE.get(sample_name, {})
    if isinstance(sample, dict):
        value = sample.get(key)
        if isinstance(value, str):
            return value
    return ''


def _live_published_roa_objects() -> list[dict[str, object]]:
    published = _LIVE_REPO_STATUS.get('published', [])
    roa_entries = []
    if isinstance(published, list):
        for item in published:
            if not isinstance(item, dict):
                continue
            uri = str(item.get('uri') or '')
            if not uri.endswith('.roa'):
                continue
            roa_entries.append(item)
    return roa_entries

KRILL_ROUTES_JSON = [
    {
        'asn': 65000,
        'prefix': '10.10.0.0/24',
        'max_length': 24,
        'comment': 'netbox_rpki sample IPv4 ROA',
        'roa_objects': [
            {
                'authorizations': ['10.10.0.0/24-24 => 65000'],
                'validity': {
                    'not_before': '2026-04-12T10:00:00Z',
                    'not_after': '2027-04-12T10:00:00Z',
                },
                'serial': '111',
                'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/v4.roa',
                'base64': _live_published_roa_objects()[0]['base64'] if _live_published_roa_objects() else _ROUTE_CMS_BASE64,
                'hash': 'hash-v4',
            }
        ],
    },
    {
        'asn': 65000,
        'prefix': '2001:db8:100::/48',
        'max_length': 48,
        'comment': 'netbox_rpki sample IPv6 ROA',
        'roa_objects': [
            {
                'authorizations': ['2001:db8:100::/48-48 => 65000'],
                'validity': {
                    'not_before': '2026-04-12T10:00:00Z',
                    'not_after': '2027-04-12T10:00:00Z',
                },
                'serial': '222',
                'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/v6.roa',
                'base64': _live_published_roa_objects()[1]['base64'] if len(_live_published_roa_objects()) > 1 else _ROUTE_CMS_BASE64,
                'hash': 'hash-v6',
            }
        ],
    },
]


KRILL_ASPAS_JSON = [
    {
        'customer': 'AS65000',
        'providers': ['AS65001', 'AS65002(v4)', 'AS65003(v6)'],
    },
    {
        'customer': 'AS65010',
        'providers': [],
    },
]


# Mirrors the documented JSON shape of `krillc show --ca <ca> --api`.
KRILL_CA_METADATA_JSON = {
    'handle': 'netbox-rpki-dev',
    'id_cert': {
        'pem': '-----BEGIN CERTIFICATE-----\nMIIBKRILLNETBOXCA==\n-----END CERTIFICATE-----\n',
        'hash': 'krill-ca-id-cert-sha256',
    },
    'repo_info': {
        'sia_base': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/',
        'rrdp_notification_uri': 'https://testbed.krill.cloud/rrdp/notification.xml',
    },
    'parents': [
        {
            'handle': 'testbed',
            'kind': 'rfc6492',
        }
    ],
    'resources': {
        'asn': 'AS65000-AS65010',
        'ipv4': '10.10.0.0/24, 10.20.0.0/24',
        'ipv6': '2001:db8:100::/48',
    },
    'resource_classes': {
        '0': {
            'name_space': '0',
            'parent_handle': 'testbed',
            'keys': {
                'active': {
                        'active_key': {
                            'key_id': 'NETBOXRPKIACTIVEKEY0001',
                            'incoming_cert': {
                                'uri': 'rsync://testbed.krill.cloud/repo/testbed/0/netbox-rpki-dev.cer',
                                'base64': _live_sample_value('incoming_cert', 'base64') or _INCOMING_CERT_BASE64,
                                'resources': {
                                    'asn': 'AS65000-AS65010',
                                    'ipv4': '10.10.0.0/24, 10.20.0.0/24',
                                'ipv6': '2001:db8:100::/48',
                            },
                        },
                        'request': None,
                    }
                }
            },
        }
    },
    'children': ['edge-customer-01'],
    'suspended_children': ['edge-customer-archive'],
}


# Mirrors the documented JSON shape of `krillc parents statuses --ca <ca> --api`.
KRILL_PARENT_STATUSES_JSON = {
    'testbed': {
        'last_exchange': {
            'timestamp': 1775988000,
            'uri': 'https://testbed.krill.cloud/rfc6492/testbed/',
            'result': 'Success',
        },
        'last_success': 1775988000,
        'all_resources': {
            'asn': 'AS65000-AS65010',
            'ipv4': '10.10.0.0/24, 10.20.0.0/24',
            'ipv6': '2001:db8:100::/48',
        },
        'classes': [
            {
                'class_name': '0',
                'resource_set': {
                    'asn': 'AS65000-AS65010',
                    'ipv4': '10.10.0.0/24, 10.20.0.0/24',
                    'ipv6': '2001:db8:100::/48',
                },
                'not_after': '2027-04-12T10:00:00Z',
                'signing_cert': {
                    'url': 'rsync://testbed.krill.cloud/repo/testbed/0/testbed.cer',
                    'cert': _live_sample_value('parent_signing_cert', 'cert') or _PARENT_SIGNING_CERT_BASE64,
                },
                'issued_certs': [
                    {
                        'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.cer',
                        'cert': _live_sample_value('incoming_cert', 'base64') or _INCOMING_CERT_BASE64,
                    }
                ],
            }
        ],
    }
}


# Mirrors the documented JSON shape of `krillc parents contact --ca <ca> --parent <parent> --api`.
KRILL_PARENT_CONTACT_JSON = {
    'type': 'rfc6492',
    'tag': None,
    'id_cert': 'MIIKRILLPARENTCONTACTCERT==',
    'parent_handle': 'testbed',
    'child_handle': 'netbox-rpki-dev',
    'service_uri': 'https://testbed.krill.cloud/rfc6492/testbed/',
}


# Mirrors the documented JSON shape of `krillc children info --ca <ca> --child <child> --api`.
KRILL_CHILD_INFO_JSON = {
    'state': 'active',
    'id_cert': {
        'pem': '-----BEGIN CERTIFICATE-----\nMIIBKRILLCHILDCA==\n-----END CERTIFICATE-----\n',
        'hash': 'krill-child-id-cert-sha256',
    },
    'entitled_resources': {
        'asn': 'AS65010',
        'ipv4': '10.20.0.0/24',
        'ipv6': '',
    },
}


# Mirrors the documented JSON shape of `krillc children connections --ca <ca> --api`.
KRILL_CHILD_CONNECTIONS_JSON = {
    'children': [
        {
            'handle': 'edge-customer-01',
            'last_exchange': {
                'timestamp': 1775988000,
                'result': 'Success',
                'user_agent': 'krill/0.16.0',
            },
            'state': 'active',
        },
        {
            'handle': 'edge-customer-archive',
            'last_exchange': None,
            'state': 'suspended',
        },
    ]
}


# Mirrors the documented JSON shape of `krillc repo show --ca <ca> --api`.
KRILL_REPO_DETAILS_JSON = {
    'service_uri': 'https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/',
    'repo_info': {
        'sia_base': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/',
        'rrdp_notification_uri': 'https://testbed.krill.cloud/rrdp/notification.xml',
    },
}


# Mirrors the documented JSON shape of `krillc repo status --ca <ca> --api`.
KRILL_REPO_STATUS_JSON = {
    'last_exchange': {
        'timestamp': 1775988000,
        'uri': 'https://testbed.krill.cloud/rfc8181/netbox-rpki-dev/',
        'result': 'Success',
    },
    'next_exchange_before': 1776024000,
    'published': [
        {
            'base64': _live_sample_value('manifest', 'base64') or _MANIFEST_CMS_BASE64,
            'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft',
        },
        {
            'base64': _live_sample_value('crl', 'base64') or _CRL_BASE64,
            'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.crl',
        },
    ],
}


__all__ = [
    'KRILL_ASPAS_JSON',
    'KRILL_CA_METADATA_JSON',
    'KRILL_CHILD_CONNECTIONS_JSON',
    'KRILL_CHILD_INFO_JSON',
    'KRILL_PARENT_CONTACT_JSON',
    'KRILL_PARENT_STATUSES_JSON',
    'KRILL_REPO_DETAILS_JSON',
    'KRILL_REPO_STATUS_JSON',
    'KRILL_ROUTES_JSON',
]

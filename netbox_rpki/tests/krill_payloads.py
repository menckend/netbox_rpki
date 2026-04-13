"""Deterministic Krill payload fixtures for provider sync planning and tests."""

from __future__ import annotations

import json
from pathlib import Path


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
                'base64': _live_published_roa_objects()[0]['base64'] if _live_published_roa_objects() else 'AAA',
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
                'base64': _live_published_roa_objects()[1]['base64'] if len(_live_published_roa_objects()) > 1 else 'BBB',
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
                            'base64': _live_sample_value('incoming_cert', 'base64') or 'MIIFlDCCBHygAwIBAgIUFmJq/upclIPirQ6V3WEoGGLK1OEwDQYJKoZIhvcNAQELBQAwMzExMC8GA1UEAxMoNzRDRDdFRkM1QUU4MTZCQ0VGMzkwRTVBNkJENjFENjJCRkQzRTBEQTAeFw0yNjA0MTIxMzU3MDVaFw0yNzA0MTExNDAyMDVaMDMxMTAvBgNVBAMTKEUxQzQ0REQ4MzY4MDM2OEFBQTAwNUI0RjI0RDY1NjgxM0E3M0JFRDQwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCprjxqHqBjId2L7Mx5VjmmGvuhtVWJP1VSgcBGIonAj0RRYwg8eTr06u9TYwdVhz/+Ix2qSxfwVPyTqjBmwgRd787s3ssSpjkoLkOW9hW7Ss5kimqAFsH3Hrmr1Mk58Jxu6dNHI8EkY6Bg3kw04TNBmsqD+8OHjgPYbm7PP2YfEURMShv186ApEyNTnYXFvsAQxasbXTwSAZTw7RwaIAjy+40kpx/SAVqi2CZCNKF2TOTep0cYYrvpuKew17MGm2tDzAVG2h2a/XT9XasT8+UoMs5ujpwYeeINLOQ4N9B88qnqDQKkKN72QAVNtEeYp7NNb4U6S+mVL5D7Q46KXzILAgMBAAGjggKeMIICmjAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBThxE3YNoA2iqoAW08k1laBOnO+1DAfBgNVHSMEGDAWgBR0zX78WugWvO85Dlpr1h1iv9Pg2jAOBgNVHQ8BAf8EBAMCAQYwaAYDVR0fBGEwXzBdoFugWYZXcnN5bmM6Ly90ZXN0YmVkLmtyaWxsLmNsb3VkL3JlcG8vdGVzdGJlZC8wLzc0Q0Q3RUZDNUFFODE2QkNFRjM5MEU1QTZCRDYxRDYyQkZEM0UwREEuY3JsMGkGCCsGAQUFBwEBBF0wWzBZBggrBgEFBQcwAoZNcnN5bmM6Ly90ZXN0YmVkLmtyaWxsLmNsb3VkL3JlcG8vNzRDRDdFRkM1QUU4MTZCQ0VGMzkwRTVBNkJENjFENjJCRkQzRTBEQS5jZXIwgf0GCCsGAQUFBwELBIHwMIHtMD8GCCsGAQUFBzAFhjNyc3luYzovL3Rlc3RiZWQua3JpbGwuY2xvdWQvcmVwby9uZXRib3gtcnBraS1kZXYvMC8wawYIKwYBBQUHMAqGX3JzeW5jOi8vdGVzdGJlZC5rcmlsbC5jbG91ZC9yZXBvL25ldGJveC1ycGtpLWRldi8wL0UxQzQ0REQ4MzY4MDM2OEFBQTAwNUI0RjI0RDY1NjgxM0E3M0JFRDQubWZ0MD0GCCsGAQUFBzANhjFodHRwczovL3Rlc3RiZWQua3JpbGwuY2xvdWQvcnJkcC9ub3RpZmljYXRpb24ueG1sMBgGA1UdIAEB/wQOMAwwCgYIKwYBBQUHDgIwLAYIKwYBBQUHAQcBAf8EHTAbMAoEAgABMAQDAgAKMA0EAgACMAcDBQAgAQ24MBoGCCsGAQUFBwEIAQH/BAswCaAHMAUCAwD96DANBgkqhkiG9w0BAQsFAAOCAQEAlwaJXkQQuUCn4j9MaEA5scIXGzVx8mkzzWbG/d0rbqNjz73J8kymS7NcDfjdzkw6CFiz7N18wfNM9Mm8lGzGufSdaubdKH7Oii0WmGGQvGutK48sZ583gDFIIQ4FZwNgbBILbQfbncWLVSs2Lvv01w4vzUCHPl/+ytdbaB6+Wj5srSYyKEjBTQShqB4bYd784K/jswsipqY0kYRI4Ev9Gqkpvkt0Htg8FNdjs5fEqkLQaGmgzp4uZCfm0Gy17ErzK3yRWx2xgIPrv7Ct9FXMR0ux+VjpqjHb8R+yCFGSz1lb517RgsOX2pQjXXBhZdGKHTs9K0A0r9/fO0AMxAzqaQ==',
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
                    'cert': _live_sample_value('parent_signing_cert', 'cert') or 'MIIKRILLSIGNINGCERT==',
                },
                'issued_certs': [
                    {
                        'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.cer',
                        'cert': _live_sample_value('incoming_cert', 'base64') or 'MIIKRILLISSUEDCERT==',
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
            'base64': _live_sample_value('manifest', 'base64') or 'MIIKRILLMFT==',
            'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft',
        },
        {
            'base64': _live_sample_value('crl', 'base64') or 'MIIKRILLCRL==',
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
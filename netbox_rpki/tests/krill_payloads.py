"""Deterministic Krill payload fixtures for provider sync planning and tests."""

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
                'base64': 'AAA',
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
                'base64': 'BBB',
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
                    'cert': 'MIIKRILLSIGNINGCERT==',
                },
                'issued_certs': [
                    {
                        'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.cer',
                        'cert': 'MIIKRILLISSUEDCERT==',
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
            'base64': 'MIIKRILLMFT==',
            'uri': 'rsync://testbed.krill.cloud/repo/netbox-rpki-dev/0/netbox-rpki-dev.mft',
        },
        {
            'base64': 'MIIKRILLCRL==',
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
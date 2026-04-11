from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from netbox_rpki import models


ValueGetter = Callable[[Any], Any]


def get_pk(instance: Any) -> Any:
    return instance.pk


@dataclass(frozen=True)
class DetailFieldSpec:
    label: str
    value: ValueGetter
    kind: str = 'text'
    url: ValueGetter | None = None
    use_header: bool = True
    empty_text: str | None = None


@dataclass(frozen=True)
class DetailActionSpec:
    permission: str
    label: str
    url_name: str
    query_param: str
    value: ValueGetter = get_pk


@dataclass(frozen=True)
class DetailTableSpec:
    title: str
    table_class_name: str
    queryset: ValueGetter


@dataclass(frozen=True)
class DetailSpec:
    model: type
    list_url_name: str
    breadcrumb_label: str
    card_title: str
    fields: tuple[DetailFieldSpec, ...]
    actions: tuple[DetailActionSpec, ...] = ()
    side_tables: tuple[DetailTableSpec, ...] = ()
    bottom_tables: tuple[DetailTableSpec, ...] = ()


ORGANIZATION_DETAIL_SPEC = DetailSpec(
    model=models.Organization,
    list_url_name='plugins:netbox_rpki:organization_list',
    breadcrumb_label='RPKI Customer Organizations',
    card_title='RPKI Organization',
    fields=(
        DetailFieldSpec(label='Organization ID', value=lambda obj: obj.org_id),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Organizaton Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Parent Regional Internet Registry',
            value=lambda obj: obj.parent_rir,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(
            label='External URL',
            value=lambda obj: obj.ext_url,
            kind='url',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_organization',
            label='RPKI Certificate',
            url_name='plugins:netbox_rpki:certificate_add',
            query_param='rpki_org',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Certificates',
            table_class_name='CertificateTable',
            queryset=lambda obj: obj.certificates.all(),
        ),
    ),
)


CERTIFICATE_DETAIL_SPEC = DetailSpec(
    model=models.Certificate,
    list_url_name='plugins:netbox_rpki:certificate_list',
    breadcrumb_label='RPKI Customer Certificates',
    card_title='RPKI Customer Certificate',
    fields=(
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(label='Issuer', value=lambda obj: obj.issuer),
        DetailFieldSpec(label='Subject', value=lambda obj: obj.subject),
        DetailFieldSpec(label='Serial', value=lambda obj: obj.serial),
        DetailFieldSpec(label='Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews?', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(label='Public Key', value=lambda obj: obj.public_key),
        DetailFieldSpec(label='Private Key', value=lambda obj: obj.private_key),
        DetailFieldSpec(label='Publication URL', value=lambda obj: obj.publication_url),
        DetailFieldSpec(label='CA Repository', value=lambda obj: obj.ca_repository),
        DetailFieldSpec(label='Self Hosted', value=lambda obj: obj.self_hosted),
        DetailFieldSpec(
            label='Parent RPKI customer/org',
            value=lambda obj: obj.rpki_org,
            kind='link',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='Prefix',
            url_name='plugins:netbox_rpki:certificateprefix_add',
            query_param='certificate_name',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ASN',
            url_name='plugins:netbox_rpki:certificateasn_add',
            query_param='certificate_name2',
        ),
        DetailActionSpec(
            permission='netbox_rpki.change_certificate',
            label='ROA',
            url_name='plugins:netbox_rpki:roa_add',
            query_param='signed_by',
        ),
    ),
    side_tables=(
        DetailTableSpec(
            title='Attested IP Netblock Resources',
            table_class_name='CertificatePrefixTable',
            queryset=lambda obj: obj.CertificateToPrefixTable.all(),
        ),
        DetailTableSpec(
            title='Attested ASN Resource',
            table_class_name='CertificateAsnTable',
            queryset=lambda obj: obj.CertificatetoASNTable.all(),
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='ROAs',
            table_class_name='RoaTable',
            queryset=lambda obj: obj.roas.all(),
        ),
    ),
)


ROA_DETAIL_SPEC = DetailSpec(
    model=models.Roa,
    list_url_name='plugins:netbox_rpki:roa_list',
    breadcrumb_label='RPKI ROAs',
    card_title='RPKI Route Origination Authorization (ROA)',
    fields=(
        DetailFieldSpec(label='Name', value=lambda obj: obj.name),
        DetailFieldSpec(
            label='Tenant',
            value=lambda obj: obj.tenant,
            kind='link',
            use_header=False,
            empty_text='None',
        ),
        DetailFieldSpec(
            label='Origination AS Number',
            value=lambda obj: obj.origin_as,
            kind='link',
            empty_text='None',
        ),
        DetailFieldSpec(label='Date Valid From', value=lambda obj: obj.valid_from),
        DetailFieldSpec(label='Date Valid To', value=lambda obj: obj.valid_to),
        DetailFieldSpec(label='Auto-renews', value=lambda obj: obj.auto_renews),
        DetailFieldSpec(
            label='Signing Certificate',
            value=lambda obj: obj.signed_by.name if obj.signed_by else None,
            kind='link',
            url=lambda obj: obj.signed_by.get_absolute_url() if obj.signed_by else None,
            empty_text='None',
        ),
    ),
    actions=(
        DetailActionSpec(
            permission='netbox_rpki.change_roa',
            label='ROA Prefix',
            url_name='plugins:netbox_rpki:roaprefix_add',
            query_param='roa_name',
        ),
    ),
    bottom_tables=(
        DetailTableSpec(
            title='Prefixes Included in this ROA',
            table_class_name='RoaPrefixTable',
            queryset=lambda obj: obj.RoaToPrefixTable.all(),
        ),
    ),
)

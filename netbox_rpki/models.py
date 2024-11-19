import ipam
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from ipam.models.asns import ASN
from ipam.models.ip import Prefix
from ipam.models import RIR


class Organization(NetBoxModel):
    org_id = models.CharField(max_length=200, editable=True)
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    ext_url = models.CharField(max_length=200, editable=True, blank=True)
    parent_rir = models.ForeignKey(
        to=RIR,
        on_delete=models.PROTECT,
        related_name='rpki_certs',
        null=True,
        blank=True
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f'{self.name}, {self.org_id}'

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:organization", args=[self.pk])


class Certificate(NetBoxModel):
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    issuer = models.CharField(max_length=200, editable=True, blank=True)
    subject = models.CharField(max_length=200, editable=True, blank=True)
    serial = models.CharField(max_length=200, editable=True, blank=True)
    valid_from = models.DateField(editable=True, blank=True, null=True)
    valid_to = models.DateField(editable=True, blank=True, null=True)
    auto_renews = models.BooleanField(editable=True)
    public_key = models.CharField(max_length=200, editable=True, blank=True)
    private_key = models.CharField(max_length=200, editable=True, blank=True)
    publication_url = models.CharField(max_length=200, editable=True, blank=True)
    ca_repository = models.CharField(max_length=200, editable=True, blank=True)
    self_hosted = models.BooleanField(max_length=200, editable=True)
    rpki_org = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f'{self.name}, {self.issuer}'

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificate", args=[self.pk])


class Roa(NetBoxModel):
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roas',
        blank=True,
        null=True
    )
    valid_from = models.DateField(editable=True, blank=True, null=True)
    valid_to = models.DateField(editable=True, blank=True, null=True)
    auto_renews = models.BooleanField(editable=True)
    signed_by = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='roas'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roa", args=[self.pk])


class RoaPrefix(NetBoxModel):
    prefix = models.ForeignKey(
        to=ipam.models.ip.Prefix,
        on_delete=models.PROTECT,
        related_name='PrefixToRoaTable'
    )
    comments = models.TextField(
        blank=True
    )
    max_length = models.IntegerField(editable=True)
    roa_name = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='RoaToPrefixTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaprefix", args=[self.pk])


class CertificatePrefix(NetBoxModel):
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='PrefixToCertificateTable'
    )
    comments = models.TextField(
        blank=True
    )
    certificate_name = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificateToPrefixTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificateprefix", args=[self.pk])


class CertificateAsn(NetBoxModel):
    asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='ASNtoCertificateTable'
    )
    comments = models.TextField(
        blank=True
    )
    certificate_name2 = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificatetoASNTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("asn",)

    def __str__(self):
        return str(self.asn)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificateasn", args=[self.pk])

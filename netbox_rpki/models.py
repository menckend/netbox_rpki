from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from ipam.models.asns import ASN
from ipam.models.ip import Prefix


class Organization(NetBoxModel):
    org_id = models.CharField(max_length=200)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f'{self.name}, {self.org_id}'

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:organization", args=[self.pk])


class Certificate(NetBoxModel):
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    serial =  models.CharField(max_length=200)
    valid_from =  models.DateField
    valid_to =  models.DateField
    public_key =  models.CharField
    private_key = models.CharField
    publication_url = models.URLField
    ca_repository = models.URLField
    self_hosted = models.BooleanField
    rpki_org = models.ForeignKey(
        to=Organization,
        on_delete=models.CASCADE,
        related_name='certificates'
    )


    class Meta:
        ordering = ("name")

    def __str__(self):
        return f'{self.name}, {self.issuer}, {self.subject}, {self.serial}, {self.valid_from}, {self.valid_to}, {self.public_key}, {self.private_key}, {self.publication_url}, {self.ca_repository}, {self.self_hosted}, {self.rpki_org}'
    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificate", args=[self.pk])


class Roa(NetBoxModel):
    name = models.CharField(max_length=200)
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.CASCADE,
        related_name='roas'
    )   
    valid_from = models.DateField
    valid_to =  models.DateField
    signed_by = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='roas'
    )
    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roa", args=[self.pk])


class RoaPrefix(NetBoxModel):
    prefix = models.ForeignKey(
        to= Prefix,
        on_delete=models.PROTECT,
        related_name='RoaPrefices'
    )
    max_length = models.IntegerField
    roa_name = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='prefixes'
    )


    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return self.prefix

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaprefix", args=[self.pk])

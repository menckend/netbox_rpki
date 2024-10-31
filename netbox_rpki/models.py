from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from ipam.models.asns import ASN
from ipam.models.ip import Prefix


class organization(NetBoxModel):
    orgId = models.CharField(max_length=200)
    orgName = models.CharField(max_length=200)

    class Meta:
        ordering = ("orgName",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:organization", args=[self.pk])


class certificate(NetBoxModel):
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    serial =  models.CharField(max_length=200)
    validFrom =  models.DateField
    validTo =  models.DateField
    publicKey =  models.CharField
    privateKey = models.CharField
    publicationUrl = models.URLField
    caRepository = models.URLField
    selfHosted = models.BooleanField
    rpkiOrg = models.ForeignKey(
        to=organization,
        on_delete=models.CASCADE,
        related_name='certificates'
    )


    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificate", args=[self.pk])


class roa(NetBoxModel):
    name = models.CharField(max_length=200)
    originas = models.ForeignKey(
        to=ASN,
        on_delete=models.CASCADE,
        related_name='asns'
    )   
    validfrom = models.DateField
    validto =  models.DateField
    signedby = models.ForeignKey(
        to=certificate,
        on_delete=models.CASCADE,
        related_name='roas'
    )
    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roa", args=[self.pk])


class roaprefices(NetBoxModel):
    prefix = models.ForeignKey(
        to= Prefix,
        on_delete=models.CASCADE,
        related_name='roausage'
    )
    maxLength = models.IntegerField
    roaName = models.ForeignKey(
        to=roa,
        on_delete=models.CASCADE,
        related_name='prefices'
    )


    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaprefices", args=[self.pk])

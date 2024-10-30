from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from ipam.models.asns import ASN
from ipam.models.ip import Prefix


class RpkiOrganization(NetBoxModel):
    orgId = models.CharField(max_length=200)
    orgName = models.CharField(max_length=200)

    class Meta:
        ordering = ("orgName",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:rpkiorganization", args=[self.pk])


class RpkiCertificate(NetBoxModel):
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
        to=RpkiOrganization,
        on_delete=models.CASCADE,
        related_name='certificates'
    )


    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:rpkicertificate", args=[self.pk])


class RpkiRoa(NetBoxModel):
    name = models.CharField(max_length=200)
    originAs = models.ForeignKey(
        to=ASN,
        on_delete=models.CASCADE,
        related_name='asns'
    )   
    validFrom = models.DateField
    validTo =  models.DateField
    signedBy = models.ForeignKey(
        to=RpkiCertificate,
        on_delete=models.CASCADE,
        related_name='roas'
    )
    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:rpkiroa", args=[self.pk])


class RpkiRoaPrefices(NetBoxModel):
    prefix = models.ForeignKey(
        to= Prefix,
        on_delete=models.CASCADE,
        related_name='roausage'
    )
    maxLength = models.IntegerField
    roaName = models.ForeignKey(
        to=RpkiRoa,
        on_delete=models.CASCADE,
        related_name='prefixes'
    )


    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:rpkiroaprefices", args=[self.pk])

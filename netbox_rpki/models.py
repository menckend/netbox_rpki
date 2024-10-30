from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


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
        return reverse("plugins:netbox_rpki:RpkiCertificate", args=[self.pk])

class RpkiOrganization(NetBoxModel):
    orgId = models.CharField(max_length=200)
    orgName = models.CharField(max_length=200)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:RpkiOrganization", args=[self.pk])

class RpkiRoa(NetBoxModel):
    name = models.CharField(max_length=200)
    originAs = foreignkey-ipam.asn
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
        return reverse("plugins:netbox_rpki:RpkiRoa", args=[self.pk])


class RpkiRoaPrefices(NetBoxModel):
    prefix = models.ForeignKey(
        to= ipam.models.ip.Prefix,
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
        return reverse("plugins:netbox_rpki:RpkiRoaPrefices", args=[self.pk])

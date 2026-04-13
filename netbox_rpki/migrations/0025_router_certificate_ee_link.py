import django.db.models.deletion
from django.db import migrations, models


def backfill_router_certificate_ee_links(apps, schema_editor):
    EndEntityCertificate = apps.get_model('netbox_rpki', 'EndEntityCertificate')
    RouterCertificate = apps.get_model('netbox_rpki', 'RouterCertificate')

    for router_certificate in RouterCertificate.objects.filter(ee_certificate__isnull=True):
        candidates = EndEntityCertificate.objects.all()

        if router_certificate.organization_id is not None:
            candidates = candidates.filter(organization_id=router_certificate.organization_id)
        if router_certificate.resource_certificate_id is not None:
            candidates = candidates.filter(resource_certificate_id=router_certificate.resource_certificate_id)
        if router_certificate.publication_point_id is not None:
            candidates = candidates.filter(publication_point_id=router_certificate.publication_point_id)
        if router_certificate.serial:
            candidates = candidates.filter(serial=router_certificate.serial)
        if router_certificate.ski:
            candidates = candidates.filter(ski=router_certificate.ski)
        if router_certificate.subject:
            candidates = candidates.filter(subject=router_certificate.subject)
        if router_certificate.issuer:
            candidates = candidates.filter(issuer=router_certificate.issuer)

        candidate_ids = list(candidates.values_list('pk', flat=True)[:2])
        if len(candidate_ids) == 1:
            router_certificate.ee_certificate_id = candidate_ids[0]
            router_certificate.save(update_fields=('ee_certificate',))


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0024_schema_normalization_phase0'),
    ]

    operations = [
        migrations.AddField(
            model_name='routercertificate',
            name='ee_certificate',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='router_certificate_extension',
                to='netbox_rpki.endentitycertificate',
            ),
        ),
        migrations.RunPython(
            code=backfill_router_certificate_ee_links,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

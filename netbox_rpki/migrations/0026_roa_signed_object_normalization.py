from django.db import migrations


def backfill_roa_signed_object_links(apps, schema_editor):
    Roa = apps.get_model('netbox_rpki', 'Roa')
    SignedObject = apps.get_model('netbox_rpki', 'SignedObject')

    for roa in Roa.objects.filter(signed_object__isnull=True):
        candidates = SignedObject.objects.filter(object_type='roa')

        if roa.signed_by_id is not None:
            candidates = candidates.filter(resource_certificate_id=roa.signed_by_id)
            if roa.signed_by.rpki_org_id is not None:
                candidates = candidates.filter(organization_id=roa.signed_by.rpki_org_id)
        if roa.valid_from is not None:
            candidates = candidates.filter(valid_from=roa.valid_from)
        if roa.valid_to is not None:
            candidates = candidates.filter(valid_to=roa.valid_to)

        candidate_ids = list(candidates.values_list('pk', flat=True)[:2])
        if len(candidate_ids) == 1:
            roa.signed_object_id = candidate_ids[0]
            roa.save(update_fields=('signed_object',))


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0025_router_certificate_ee_link'),
    ]

    operations = [
        migrations.RunPython(
            code=backfill_roa_signed_object_links,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

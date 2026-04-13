import django.db.models.deletion
from django.db import migrations, models


def backfill_validated_payload_validation_links(apps, schema_editor):
    ObjectValidationResult = apps.get_model('netbox_rpki', 'ObjectValidationResult')
    ValidatedAspaPayload = apps.get_model('netbox_rpki', 'ValidatedAspaPayload')
    ValidatedRoaPayload = apps.get_model('netbox_rpki', 'ValidatedRoaPayload')

    for payload in ValidatedRoaPayload.objects.filter(object_validation_result__isnull=True, roa__signed_object__isnull=False):
        candidate_ids = list(
            ObjectValidationResult.objects.filter(
                validation_run_id=payload.validation_run_id,
                signed_object_id=payload.roa.signed_object_id,
            ).values_list('pk', flat=True)[:2]
        )
        if len(candidate_ids) == 1:
            payload.object_validation_result_id = candidate_ids[0]
            payload.save(update_fields=('object_validation_result',))

    for payload in ValidatedAspaPayload.objects.filter(object_validation_result__isnull=True, aspa__signed_object__isnull=False):
        candidate_ids = list(
            ObjectValidationResult.objects.filter(
                validation_run_id=payload.validation_run_id,
                signed_object_id=payload.aspa.signed_object_id,
            ).values_list('pk', flat=True)[:2]
        )
        if len(candidate_ids) == 1:
            payload.object_validation_result_id = candidate_ids[0]
            payload.save(update_fields=('object_validation_result',))


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0026_roa_signed_object_normalization'),
    ]

    operations = [
        migrations.AddField(
            model_name='validatedroapayload',
            name='object_validation_result',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='validated_roa_payloads',
                to='netbox_rpki.objectvalidationresult',
            ),
        ),
        migrations.AddField(
            model_name='validatedaspapayload',
            name='object_validation_result',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='validated_aspa_payloads',
                to='netbox_rpki.objectvalidationresult',
            ),
        ),
        migrations.RunPython(
            code=backfill_validated_payload_validation_links,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

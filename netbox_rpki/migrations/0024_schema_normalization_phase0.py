import django.db.models.deletion
from django.db import migrations, models


def backfill_phase0_normalization_links(apps, schema_editor):
    SignedObject = apps.get_model('netbox_rpki', 'SignedObject')
    CertificateRevocationList = apps.get_model('netbox_rpki', 'CertificateRevocationList')
    ImportedPublicationPoint = apps.get_model('netbox_rpki', 'ImportedPublicationPoint')
    ImportedSignedObject = apps.get_model('netbox_rpki', 'ImportedSignedObject')
    ImportedCertificateObservation = apps.get_model('netbox_rpki', 'ImportedCertificateObservation')

    for crl in CertificateRevocationList.objects.filter(signed_object__isnull=True).exclude(publication_uri=''):
        signed_object_ids = list(
            SignedObject.objects.filter(
                object_type='crl',
                object_uri=crl.publication_uri,
            ).values_list('pk', flat=True)[:2]
        )
        if len(signed_object_ids) == 1:
            crl.signed_object_id = signed_object_ids[0]
            crl.save(update_fields=('signed_object',))

    for observation in ImportedCertificateObservation.objects.filter(
        models.Q(signed_object__isnull=True) | models.Q(publication_point__isnull=True)
    ):
        update_fields = []

        if observation.signed_object_id is None and observation.signed_object_uri:
            signed_object_ids = list(
                ImportedSignedObject.objects.filter(
                    provider_snapshot_id=observation.provider_snapshot_id,
                    signed_object_uri=observation.signed_object_uri,
                ).values_list('pk', flat=True)[:2]
            )
            if len(signed_object_ids) == 1:
                observation.signed_object_id = signed_object_ids[0]
                update_fields.append('signed_object')

        if observation.publication_point_id is None:
            if observation.signed_object_id is not None:
                publication_point_id = ImportedSignedObject.objects.filter(
                    pk=observation.signed_object_id,
                ).values_list('publication_point_id', flat=True).first()
                if publication_point_id is not None:
                    observation.publication_point_id = publication_point_id
                    update_fields.append('publication_point')

        if observation.publication_point_id is None and observation.publication_uri:
            publication_point_ids = list(
                ImportedPublicationPoint.objects.filter(
                    provider_snapshot_id=observation.provider_snapshot_id,
                ).filter(
                    models.Q(publication_uri=observation.publication_uri)
                    | models.Q(service_uri=observation.publication_uri)
                ).values_list('pk', flat=True)[:2]
            )
            if len(publication_point_ids) == 1:
                observation.publication_point_id = publication_point_ids[0]
                if 'publication_point' not in update_fields:
                    update_fields.append('publication_point')

        if update_fields:
            observation.save(update_fields=tuple(update_fields))


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0023_importedcertificateobservation'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificaterevocationlist',
            name='signed_object',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='crl_extension',
                to='netbox_rpki.signedobject',
            ),
        ),
        migrations.AddField(
            model_name='importedcertificateobservation',
            name='publication_point',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='certificate_observations',
                to='netbox_rpki.importedpublicationpoint',
            ),
        ),
        migrations.AddField(
            model_name='importedcertificateobservation',
            name='signed_object',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='certificate_observations',
                to='netbox_rpki.importedsignedobject',
            ),
        ),
        migrations.RunPython(
            code=backfill_phase0_normalization_links,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


def _single_match(queryset):
    matches = list(queryset[:2])
    if len(matches) == 1:
        return matches[0]
    return None


def backfill_imported_authored_links(apps, schema_editor):
    ImportedPublicationPoint = apps.get_model('netbox_rpki', 'ImportedPublicationPoint')
    ImportedSignedObject = apps.get_model('netbox_rpki', 'ImportedSignedObject')
    PublicationPoint = apps.get_model('netbox_rpki', 'PublicationPoint')
    SignedObject = apps.get_model('netbox_rpki', 'SignedObject')

    for row in ImportedPublicationPoint.objects.filter(authored_publication_point__isnull=True).iterator():
        authored_publication_point = None
        if row.organization_id is None:
            continue

        if row.publication_uri:
            authored_publication_point = _single_match(
                PublicationPoint.objects.filter(
                    organization_id=row.organization_id,
                    publication_uri=row.publication_uri,
                )
            )
        if authored_publication_point is None and row.rrdp_notification_uri:
            authored_publication_point = _single_match(
                PublicationPoint.objects.filter(
                    organization_id=row.organization_id,
                    rrdp_notify_uri=row.rrdp_notification_uri,
                )
            )
        if authored_publication_point is None and row.service_uri:
            authored_publication_point = _single_match(
                PublicationPoint.objects.filter(
                    organization_id=row.organization_id,
                    rsync_base_uri=row.service_uri,
                )
            )

        if authored_publication_point is None:
            continue

        row.authored_publication_point_id = authored_publication_point.pk
        row.save(update_fields=['authored_publication_point'])

    for row in ImportedSignedObject.objects.filter(authored_signed_object__isnull=True).iterator():
        if row.organization_id is None or not row.signed_object_uri:
            continue

        queryset = SignedObject.objects.filter(
            organization_id=row.organization_id,
            object_uri=row.signed_object_uri,
        )
        if row.signed_object_type:
            queryset = queryset.filter(object_type=row.signed_object_type)
        authored_signed_object = _single_match(queryset)
        if authored_signed_object is None:
            continue

        row.authored_signed_object_id = authored_signed_object.pk
        row.save(update_fields=['authored_signed_object'])


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0027_validated_payload_object_validation_links'),
    ]

    operations = [
        migrations.AddField(
            model_name='importedpublicationpoint',
            name='authored_publication_point',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='imported_publication_observations',
                to='netbox_rpki.publicationpoint',
            ),
        ),
        migrations.AddField(
            model_name='importedsignedobject',
            name='authored_signed_object',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='imported_signed_object_observations',
                to='netbox_rpki.signedobject',
            ),
        ),
        migrations.RunPython(backfill_imported_authored_links, migrations.RunPython.noop),
    ]

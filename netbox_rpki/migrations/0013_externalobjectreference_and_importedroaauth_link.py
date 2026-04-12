import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


def _build_provider_identity(provider_type, external_object_id, prefix_cidr_text, origin_asn_value, max_length):
    normalized_external_id = (external_object_id or '').strip()
    normalized_prefix = (prefix_cidr_text or '').strip().lower()

    if provider_type == 'arin' and normalized_external_id:
        return f'{normalized_external_id}|{normalized_prefix}'

    if normalized_external_id:
        return normalized_external_id

    return '|'.join(
        str(value)
        for value in (
            normalized_prefix,
            origin_asn_value if origin_asn_value is not None else '',
            max_length if max_length is not None else '',
        )
    )


def _build_reference_name(provider_account_name, provider_identity):
    return f'{provider_account_name} {provider_identity}'


def backfill_external_object_references(apps, schema_editor):
    ImportedRoaAuthorization = apps.get_model('netbox_rpki', 'ImportedRoaAuthorization')
    ExternalObjectReference = apps.get_model('netbox_rpki', 'ExternalObjectReference')

    imported_authorizations = ImportedRoaAuthorization.objects.select_related(
        'provider_snapshot__provider_account'
    ).order_by('pk')

    for imported in imported_authorizations.iterator():
        provider_snapshot = imported.provider_snapshot
        provider_account = getattr(provider_snapshot, 'provider_account', None)
        if provider_account is None:
            continue

        provider_identity = _build_provider_identity(
            provider_account.provider_type,
            imported.external_object_id,
            imported.prefix_cidr_text,
            imported.origin_asn_value,
            imported.max_length,
        )
        if not provider_identity:
            continue

        reference, _ = ExternalObjectReference.objects.update_or_create(
            provider_account_id=provider_account.pk,
            object_type='roa_authorization',
            provider_identity=provider_identity,
            defaults={
                'name': _build_reference_name(provider_account.name, provider_identity),
                'organization_id': imported.organization_id,
                'external_object_id': imported.external_object_id,
                'last_seen_provider_snapshot_id': provider_snapshot.pk,
                'last_seen_imported_authorization_id': imported.pk,
                'last_seen_at': provider_snapshot.fetched_at,
            },
        )
        ImportedRoaAuthorization.objects.filter(pk=imported.pk).update(external_reference_id=reference.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0134_owner'),
        ('netbox_rpki', '0012_rpkiprovideraccount_sync_interval'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalObjectReference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('object_type', models.CharField(choices=[('roa_authorization', 'ROA Authorization')], default='roa_authorization', max_length=64)),
                ('provider_identity', models.CharField(max_length=512)),
                ('external_object_id', models.CharField(blank=True, max_length=200)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='external_object_references', to='netbox_rpki.organization')),
                ('provider_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='external_object_references', to='netbox_rpki.rpkiprovideraccount')),
                ('last_seen_imported_authorization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='current_external_object_references', to='netbox_rpki.importedroaauthorization')),
                ('last_seen_provider_snapshot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='external_object_references', to='netbox_rpki.providersnapshot')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('name',),
                'constraints': [
                    models.UniqueConstraint(fields=('provider_account', 'object_type', 'provider_identity'), name='netbox_rpki_extobjref_provider_identity_unique'),
                ],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddField(
            model_name='importedroaauthorization',
            name='external_reference',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='imported_roa_authorizations', to='netbox_rpki.externalobjectreference'),
        ),
        migrations.RunPython(backfill_external_object_references, noop_reverse),
    ]

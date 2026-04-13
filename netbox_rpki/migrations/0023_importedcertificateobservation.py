import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0022_signed_object_crl_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportedCertificateObservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('certificate_key', models.CharField(max_length=64)),
                ('observation_source', models.CharField(choices=[('signed_object_ee', 'Signed Object EE Certificate'), ('ca_incoming', 'CA Incoming Certificate'), ('parent_signing', 'Parent Signing Certificate'), ('parent_issued', 'Parent Issued Certificate')], default='signed_object_ee', max_length=32)),
                ('certificate_uri', models.CharField(blank=True, max_length=500)),
                ('publication_uri', models.CharField(blank=True, max_length=500)),
                ('signed_object_uri', models.CharField(blank=True, max_length=500)),
                ('related_handle', models.CharField(blank=True, max_length=100)),
                ('class_name', models.CharField(blank=True, max_length=100)),
                ('subject', models.CharField(blank=True, max_length=500)),
                ('issuer', models.CharField(blank=True, max_length=500)),
                ('serial_number', models.CharField(blank=True, max_length=200)),
                ('not_before', models.DateTimeField(blank=True, null=True)),
                ('not_after', models.DateTimeField(blank=True, null=True)),
                ('external_object_id', models.CharField(blank=True, max_length=200)),
                ('is_stale', models.BooleanField(default=False)),
                ('payload_json', models.JSONField(blank=True, default=dict)),
                ('external_reference', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='imported_certificate_observations', to='netbox_rpki.externalobjectreference')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='imported_certificate_observations', to='netbox_rpki.organization')),
                ('provider_snapshot', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='imported_certificate_observations', to='netbox_rpki.providersnapshot')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddConstraint(
            model_name='importedcertificateobservation',
            constraint=models.UniqueConstraint(fields=('provider_snapshot', 'certificate_key'), name='nb_rpki_impcertobs_snap_key_uniq'),
        ),
    ]
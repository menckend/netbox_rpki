import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0134_owner'),
        ('netbox_rpki', '0048_external_validation_fields'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='TelemetryRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(editable=True, max_length=200)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=32)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('observed_window_start', models.DateTimeField(blank=True, null=True)),
                ('observed_window_end', models.DateTimeField(blank=True, null=True)),
                ('source_fingerprint', models.CharField(blank=True, max_length=255)),
                ('summary_json', models.JSONField(blank=True, default=dict)),
                ('error_text', models.TextField(blank=True)),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('-started_at', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.CreateModel(
            name='TelemetrySource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(editable=True, max_length=200)),
                ('slug', models.SlugField(max_length=100)),
                ('enabled', models.BooleanField(default=True)),
                ('source_type', models.CharField(choices=[('imported_mrt', 'Imported MRT Snapshot')], default='imported_mrt', max_length=32)),
                ('endpoint_label', models.CharField(blank=True, max_length=255)),
                ('collector_scope', models.CharField(blank=True, max_length=255)),
                ('import_interval', models.PositiveIntegerField(blank=True, null=True)),
                ('last_attempted_at', models.DateTimeField(blank=True, null=True)),
                ('last_run_status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=32)),
                ('summary_json', models.JSONField(blank=True, default=dict)),
                ('last_run_summary_json', models.JSONField(blank=True, default=dict)),
                ('last_successful_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='successful_for_sources', to='netbox_rpki.telemetryrun')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='telemetry_sources', to='netbox_rpki.organization')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('organization__name', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddField(
            model_name='telemetryrun',
            name='source',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='telemetry_runs', to='netbox_rpki.telemetrysource'),
        ),
        migrations.CreateModel(
            name='BgpPathObservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(editable=True, max_length=200)),
                ('observed_prefix', models.CharField(blank=True, max_length=64)),
                ('observed_origin_asn', models.PositiveIntegerField(blank=True, null=True)),
                ('observed_peer_asn', models.PositiveIntegerField(blank=True, null=True)),
                ('collector_id', models.CharField(blank=True, max_length=255)),
                ('vantage_point_label', models.CharField(blank=True, max_length=255)),
                ('raw_as_path', models.TextField(blank=True)),
                ('path_hash', models.CharField(blank=True, max_length=64)),
                ('path_asns_json', models.JSONField(blank=True, default=list)),
                ('first_observed_at', models.DateTimeField(blank=True, null=True)),
                ('last_observed_at', models.DateTimeField(blank=True, null=True)),
                ('visibility_status', models.CharField(blank=True, max_length=64)),
                ('details_json', models.JSONField(blank=True, default=dict)),
                ('origin_as', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='origin_bgp_path_observations', to='ipam.asn')),
                ('peer_as', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='peer_bgp_path_observations', to='ipam.asn')),
                ('prefix', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='bgp_path_observations', to='ipam.prefix')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='path_observations', to='netbox_rpki.telemetrysource')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('telemetry_run', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='path_observations', to='netbox_rpki.telemetryrun')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('-last_observed_at', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddConstraint(
            model_name='telemetrysource',
            constraint=models.UniqueConstraint(fields=('organization', 'slug'), name='nb_rpki_telemetrysource_org_slug_unique'),
        ),
    ]

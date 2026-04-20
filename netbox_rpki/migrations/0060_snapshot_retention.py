import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0134_owner'),
        ('netbox_rpki', '0059_provider_write_execution_partial_status'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='SnapshotRetentionPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(editable=True, max_length=200)),
                ('enabled', models.BooleanField(default=True, help_text='When enabled, purge jobs will apply this policy.')),
                ('validator_run_keep_count', models.PositiveIntegerField(blank=True, null=True, help_text='Keep at least this many recent validation runs per validator instance.')),
                ('validator_run_keep_days', models.PositiveIntegerField(blank=True, null=True, help_text='Keep validation runs completed within the last N days.')),
                ('provider_snapshot_keep_count', models.PositiveIntegerField(blank=True, null=True, help_text='Keep at least this many recent snapshots per provider account.')),
                ('provider_snapshot_keep_days', models.PositiveIntegerField(blank=True, null=True, help_text='Keep provider snapshots completed within the last N days.')),
                ('telemetry_run_keep_count', models.PositiveIntegerField(blank=True, null=True, help_text='Keep at least this many recent telemetry runs per telemetry source.')),
                ('telemetry_run_keep_days', models.PositiveIntegerField(blank=True, null=True, help_text='Keep telemetry runs completed within the last N days.')),
                ('irr_snapshot_keep_count', models.PositiveIntegerField(blank=True, null=True, help_text='Keep at least this many recent IRR snapshots per IRR source.')),
                ('irr_snapshot_keep_days', models.PositiveIntegerField(blank=True, null=True, help_text='Keep IRR snapshots completed within the last N days.')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Snapshot Retention Policy',
                'verbose_name_plural': 'Snapshot Retention Policies',
                'ordering': ('name',),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.CreateModel(
            name='SnapshotPurgeRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(editable=True, max_length=200)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('running', 'Running'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=32,
                )),
                ('dry_run', models.BooleanField(default=True, help_text='When True, no records were deleted (preview only).')),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('summary_json', models.JSONField(blank=True, default=dict)),
                ('error_text', models.TextField(blank=True)),
                ('policy', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purge_runs', to='netbox_rpki.snapshotretentionpolicy')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'verbose_name': 'Snapshot Purge Run',
                'verbose_name_plural': 'Snapshot Purge Runs',
                'ordering': ('-started_at', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]

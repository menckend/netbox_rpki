from django.db import migrations, models
import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_job_queue_name'),
        ('extras', '0134_owner'),
        ('netbox_rpki', '0057_imported_irr_provenance'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='irrwriteexecution',
            name='request_fingerprint',
            field=models.CharField(blank=True, default='', max_length=128),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='JobExecutionRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('job_class', models.CharField(max_length=128)),
                ('job_name', models.CharField(max_length=200)),
                ('dedupe_key', models.CharField(max_length=255)),
                ('disposition', models.CharField(choices=[('enqueued', 'Enqueued'), ('merged', 'Merged'), ('skipped', 'Skipped'), ('replayed', 'Replayed')], max_length=16)),
                ('requested_by', models.CharField(blank=True, max_length=150)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('request_payload_json', models.JSONField(blank=True, default=dict)),
                ('resolution_payload_json', models.JSONField(blank=True, default=dict)),
                ('job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='netbox_rpki_execution_records', to='core.job')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='job_execution_records', to='netbox_rpki.organization')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'ordering': ('-created', '-pk'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddIndex(
            model_name='jobexecutionrecord',
            index=models.Index(fields=['job_class', 'dedupe_key'], name='nb_rpki_jobexec_key_idx'),
        ),
        migrations.AddIndex(
            model_name='jobexecutionrecord',
            index=models.Index(fields=['organization', 'disposition'], name='nb_rpki_jobexec_orgdisp_idx'),
        ),
    ]

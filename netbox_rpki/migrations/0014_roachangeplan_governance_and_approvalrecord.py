import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


def backfill_approval_records(apps, schema_editor):
    ROAChangePlan = apps.get_model('netbox_rpki', 'ROAChangePlan')
    ApprovalRecord = apps.get_model('netbox_rpki', 'ApprovalRecord')

    for plan in ROAChangePlan.objects.filter(approved_at__isnull=False):
        if ApprovalRecord.objects.filter(change_plan_id=plan.pk).exists():
            continue
        ApprovalRecord.objects.create(
            name=f'{plan.name} Approval {plan.approved_at:%Y-%m-%d %H:%M:%S}',
            organization_id=plan.organization_id,
            change_plan_id=plan.pk,
            tenant_id=plan.tenant_id,
            disposition='accepted',
            recorded_by=plan.approved_by,
            recorded_at=plan.approved_at,
            ticket_reference=plan.ticket_reference,
            change_reference=plan.change_reference,
            maintenance_window_start=plan.maintenance_window_start,
            maintenance_window_end=plan.maintenance_window_end,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0134_owner'),
        ('netbox_rpki', '0013_externalobjectreference_and_importedroaauth_link'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='roachangeplan',
            name='change_reference',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='roachangeplan',
            name='maintenance_window_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='roachangeplan',
            name='maintenance_window_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='roachangeplan',
            name='ticket_reference',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddConstraint(
            model_name='roachangeplan',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_roachangeplan_valid_maintenance_window',
            ),
        ),
        migrations.CreateModel(
            name='ApprovalRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('disposition', models.CharField(default='accepted', max_length=16)),
                ('recorded_by', models.CharField(blank=True, max_length=150)),
                ('recorded_at', models.DateTimeField(blank=True, null=True)),
                ('ticket_reference', models.CharField(blank=True, max_length=200)),
                ('change_reference', models.CharField(blank=True, max_length=200)),
                ('maintenance_window_start', models.DateTimeField(blank=True, null=True)),
                ('maintenance_window_end', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('change_plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='approval_records', to='netbox_rpki.roachangeplan')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='approval_records', to='netbox_rpki.organization')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('-recorded_at', '-created', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddConstraint(
            model_name='approvalrecord',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_approvalrecord_valid_maintenance_window',
            ),
        ),
        migrations.RunPython(backfill_approval_records, migrations.RunPython.noop),
    ]
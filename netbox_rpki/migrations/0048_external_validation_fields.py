from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0047_irr_write_execution'),
    ]

    operations = [
        migrations.AddField(
            model_name='validatorinstance',
            name='summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='validationrun',
            name='summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='details_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='external_content_hash',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='external_object_key',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='external_object_uri',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='imported_signed_object',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='validation_results', to='netbox_rpki.importedsignedobject'),
        ),
        migrations.AddField(
            model_name='objectvalidationresult',
            name='match_status',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='validatedaspapayload',
            name='details_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='validatedroapayload',
            name='details_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='validatedroapayload',
            name='observed_prefix',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='validatedroapayload',
            name='prefix',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='validated_roa_payloads', to='ipam.prefix'),
        ),
    ]

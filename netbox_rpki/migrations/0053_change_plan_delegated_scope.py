from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0052_intent_delegated_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='aspachangeplan',
            name='delegated_entity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='aspa_change_plans',
                to='netbox_rpki.delegatedauthorizationentity',
            ),
        ),
        migrations.AddField(
            model_name='aspachangeplan',
            name='managed_relationship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='aspa_change_plans',
                to='netbox_rpki.managedauthorizationrelationship',
            ),
        ),
        migrations.AddField(
            model_name='roachangeplan',
            name='delegated_entity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='roa_change_plans',
                to='netbox_rpki.delegatedauthorizationentity',
            ),
        ),
        migrations.AddField(
            model_name='roachangeplan',
            name='managed_relationship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='roa_change_plans',
                to='netbox_rpki.managedauthorizationrelationship',
            ),
        ),
    ]

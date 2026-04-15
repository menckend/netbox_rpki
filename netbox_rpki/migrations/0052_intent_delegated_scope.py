from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0051_authoredcarelationship_delegated_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='aspaintent',
            name='delegated_entity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='aspa_intents',
                to='netbox_rpki.delegatedauthorizationentity',
            ),
        ),
        migrations.AddField(
            model_name='aspaintent',
            name='managed_relationship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='aspa_intents',
                to='netbox_rpki.managedauthorizationrelationship',
            ),
        ),
        migrations.AddField(
            model_name='roaintent',
            name='delegated_entity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='roa_intents',
                to='netbox_rpki.delegatedauthorizationentity',
            ),
        ),
        migrations.AddField(
            model_name='roaintent',
            name='managed_relationship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='roa_intents',
                to='netbox_rpki.managedauthorizationrelationship',
            ),
        ),
    ]

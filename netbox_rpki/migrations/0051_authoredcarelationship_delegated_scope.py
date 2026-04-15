from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0050_routingintentcontextgroup_inherits_from_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='authoredcarelationship',
            name='delegated_entity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='authored_ca_relationships',
                to='netbox_rpki.delegatedauthorizationentity',
            ),
        ),
        migrations.AddField(
            model_name='authoredcarelationship',
            name='managed_relationship',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='authored_ca_relationships',
                to='netbox_rpki.managedauthorizationrelationship',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0011_roachangeplan_applied_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='rpkiprovideraccount',
            name='sync_interval',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
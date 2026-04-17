from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0058_job_execution_lineage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='providerwriteexecution',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('running', 'Running'),
                    ('completed', 'Completed'),
                    ('failed', 'Failed'),
                    ('partial', 'Partial'),
                ],
                default='pending',
                max_length=32,
            ),
        ),
    ]

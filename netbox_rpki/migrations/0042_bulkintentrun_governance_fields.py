from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_rpki", "0041_update_lifecycle_health_event_dedupe_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="bulkintentrun",
            name="requires_secondary_approval",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="ticket_reference",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="change_reference",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="maintenance_window_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="maintenance_window_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="approved_by",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="secondary_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="secondary_approved_by",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="bulkintentrun",
            name="requested_by",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddConstraint(
            model_name="bulkintentrun",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F("maintenance_window_start"))
                ),
                name="netbox_rpki_bulkintentrun_valid_maintenance_window",
            ),
        ),
    ]

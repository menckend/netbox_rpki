from django.db import migrations, models


PROVENANCE_TYPE_CHOICES = [
    ('imported', 'Imported'),
    ('derived', 'Derived'),
    ('change_plan_sync', 'Change Plan Sync'),
    ('manual', 'Manual'),
]

CREATION_PATH_CHOICES = [
    ('live_query', 'Live Query'),
    ('snapshot_import', 'Snapshot Import'),
    ('route_reference', 'Route Reference'),
    ('route_set_reference', 'Route-Set Reference'),
    ('as_set_reference', 'AS-Set Reference'),
    ('change_plan_apply', 'Change Plan Apply'),
    ('manual_entry', 'Manual Entry'),
]

PROVENANCE_CONFIDENCE_CHOICES = [
    ('authoritative', 'Authoritative'),
    ('high', 'High'),
    ('medium', 'Medium'),
    ('low', 'Low'),
]

FRESHNESS_CHOICES = [
    ('current', 'Current'),
    ('stale', 'Stale'),
    ('historical', 'Historical'),
    ('unknown', 'Unknown'),
]


def _provenance_fields():
    return (
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteobject',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrrouteset',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrroutesetmember',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrasset',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrassetmember',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrautnum',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='provenance_type',
            field=models.CharField(choices=PROVENANCE_TYPE_CHOICES, default='imported', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='creation_path',
            field=models.CharField(choices=CREATION_PATH_CHOICES, default='live_query', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='provenance_confidence',
            field=models.CharField(choices=PROVENANCE_CONFIDENCE_CHOICES, default='high', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='freshness_status',
            field=models.CharField(choices=FRESHNESS_CHOICES, default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='importedirrmaintainer',
            name='provenance_summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0056_roa_object_convergence'),
    ]

    operations = list(_provenance_fields())

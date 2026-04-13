from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_rpki', '0021_imported_signed_object'),
    ]

    operations = [
        migrations.AlterField(
            model_name='signedobject',
            name='object_type',
            field=models.CharField(
                choices=[
                    ('roa', 'ROA'),
                    ('manifest', 'Manifest'),
                    ('crl', 'CRL'),
                    ('aspa', 'ASPA'),
                    ('rsc', 'RSC'),
                    ('tak', 'Trust Anchor Key'),
                    ('ghostbusters', 'Ghostbusters'),
                    ('other', 'Other'),
                ],
                default='other',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='importedsignedobject',
            name='signed_object_type',
            field=models.CharField(
                choices=[
                    ('roa', 'ROA'),
                    ('manifest', 'Manifest'),
                    ('crl', 'CRL'),
                    ('aspa', 'ASPA'),
                    ('rsc', 'RSC'),
                    ('tak', 'Trust Anchor Key'),
                    ('ghostbusters', 'Ghostbusters'),
                    ('other', 'Other'),
                ],
                default='other',
                max_length=32,
            ),
        ),
    ]
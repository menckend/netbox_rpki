# Generated by Django 5.1.4 on 2025-01-17 03:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ipam', '0076_natural_ordering'),
        ('netbox_rpki', '0004_assignedresources'),
    ]

    operations = [
        migrations.AlterField(
            model_name='certificate',
            name='ca_repository',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='private_key',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='public_key',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='publication_url',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='rpki_org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='certificates', to='netbox_rpki.organization'),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='self_hosted',
            field=models.BooleanField(max_length=200),
        ),
        migrations.AlterField(
            model_name='certificateasn',
            name='asn',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ASNtoCertificateTable', to='ipam.asn'),
        ),
        migrations.AlterField(
            model_name='certificateasn',
            name='certificate_name2',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='CertificatetoASNTable', to='netbox_rpki.certificate'),
        ),
        migrations.AlterField(
            model_name='certificateprefix',
            name='certificate_name',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='CertificateToPrefixTable', to='netbox_rpki.certificate'),
        ),
        migrations.AlterField(
            model_name='certificateprefix',
            name='prefix',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='PrefixToCertificateTable', to='ipam.prefix'),
        ),
        migrations.AlterField(
            model_name='roa',
            name='origin_as',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='roas', to='ipam.asn'),
        ),
        migrations.AlterField(
            model_name='roaprefix',
            name='prefix',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='PrefixToRoaTable', to='ipam.prefix'),
        ),
        migrations.AlterField(
            model_name='roaprefix',
            name='roa_name',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='RoaToPrefixTable', to='netbox_rpki.roa'),
        ),
    ]
    
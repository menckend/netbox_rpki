# Generated by Django 5.0.9 on 2024-11-06 20:05

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0121_customfield_related_object_filter'),
        ('ipam', '0070_vlangroup_vlan_id_ranges'),
        ('netbox_rpki', '0003_add_comments_fields'),
        ('tenancy', '0015_contactassignment_rename_content_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateAsn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('asn', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='CertificateASNs', to='ipam.asn')),
                ('certificate_name2', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='asns', to='netbox_rpki.certificate')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('asn',),
            },
        ),
        migrations.CreateModel(
            name='CertificatePrefix',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('certificate_name', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prefices2', to='netbox_rpki.certificate')),
                ('prefix', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='CertificatePrefices', to='ipam.prefix')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('prefix',),
            },
        ),
    ]
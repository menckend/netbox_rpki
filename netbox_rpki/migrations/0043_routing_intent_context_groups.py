import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('circuits', '0056_gfk_indexes'),
        ('dcim', '0226_modulebay_rebuild_tree'),
        ('extras', '0134_owner'),
        ('ipam', '0086_gfk_indexes'),
        ('netbox_rpki', '0042_bulkintentrun_governance_fields'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoutingIntentContextGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('context_type', models.CharField(choices=[('service', 'Service'), ('provider_edge', 'Provider Edge'), ('transit', 'Transit'), ('ix', 'Internet Exchange'), ('customer', 'Customer'), ('backbone', 'Backbone'), ('other', 'Other')], default='service', max_length=32)),
                ('description', models.TextField(blank=True)),
                ('priority', models.PositiveIntegerField(default=100)),
                ('enabled', models.BooleanField(default=True)),
                ('summary_json', models.JSONField(blank=True, default=dict)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_groups', to='netbox_rpki.organization')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('organization', 'priority', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.CreateModel(
            name='RoutingIntentContextCriterion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('comments', models.TextField(blank=True)),
                ('name', models.CharField(max_length=200)),
                ('criterion_type', models.CharField(choices=[('tenant', 'Tenant'), ('vrf', 'VRF'), ('site', 'Site'), ('region', 'Region'), ('role', 'Prefix Role'), ('tag', 'Tag'), ('custom_field', 'Custom Field'), ('provider_account', 'Provider Account'), ('circuit', 'Circuit'), ('circuit_provider', 'Circuit Provider'), ('exchange', 'Exchange')], max_length=32)),
                ('match_value', models.CharField(blank=True, max_length=255)),
                ('enabled', models.BooleanField(default=True)),
                ('weight', models.PositiveIntegerField(default=100)),
                ('context_group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='criteria', to='netbox_rpki.routingintentcontextgroup')),
                ('match_circuit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='circuits.circuit')),
                ('match_provider', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='circuits.provider')),
                ('match_provider_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='netbox_rpki.rpkiprovideraccount')),
                ('match_region', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='dcim.region')),
                ('match_site', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='dcim.site')),
                ('match_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='tenancy.tenant')),
                ('match_vrf', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='routing_intent_context_criteria', to='ipam.vrf')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='tenancy.tenant')),
            ],
            options={
                'ordering': ('context_group', 'weight', 'name'),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.AddConstraint(
            model_name='routingintentcontextgroup',
            constraint=models.UniqueConstraint(fields=('organization', 'name'), name='netbox_rpki_routingintentcontextgroup_org_name_unique'),
        ),
        migrations.AddConstraint(
            model_name='routingintentcontextcriterion',
            constraint=models.UniqueConstraint(fields=('context_group', 'name'), name='netbox_rpki_routingintentcontextcriterion_group_name_unique'),
        ),
        migrations.AddField(
            model_name='routingintentprofile',
            name='context_groups',
            field=models.ManyToManyField(blank=True, related_name='intent_profiles', to='netbox_rpki.routingintentcontextgroup'),
        ),
        migrations.AddField(
            model_name='routingintenttemplatebinding',
            name='context_groups',
            field=models.ManyToManyField(blank=True, related_name='template_bindings', to='netbox_rpki.routingintentcontextgroup'),
        ),
        migrations.AddField(
            model_name='roaintent',
            name='summary_json',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

from netaddr import IPNetwork

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from uuid import uuid4


class RoaObjectConvergenceMigrationTestCase(TransactionTestCase):
    migrate_from = ("netbox_rpki", "0055_externalmanagementexception")
    migrate_to = ("netbox_rpki", "0056_roa_object_convergence")

    def setUp(self):
        super().setUp()
        self.addCleanup(self._migrate_to_latest)
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        self._set_up_legacy_roa_state()

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def _migrate_to_latest(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _set_up_legacy_roa_state(self):
        fixture_suffix = uuid4().hex[:8]
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        Tag = self.old_apps.get_model("extras", "Tag")
        TaggedItem = self.old_apps.get_model("extras", "TaggedItem")
        RIR = self.old_apps.get_model("ipam", "RIR")
        ASN = self.old_apps.get_model("ipam", "ASN")
        Prefix = self.old_apps.get_model("ipam", "Prefix")
        Organization = self.old_apps.get_model("netbox_rpki", "Organization")
        Certificate = self.old_apps.get_model("netbox_rpki", "Certificate")
        Roa = self.old_apps.get_model("netbox_rpki", "Roa")
        RoaPrefix = self.old_apps.get_model("netbox_rpki", "RoaPrefix")

        rir = RIR(
            name=f"Migration Test RIR {fixture_suffix}",
            slug=f"migration-test-rir-{fixture_suffix}",
            is_private=True,
        )
        RIR.objects.bulk_create([rir])

        origin_asn = ASN(asn=64555, rir_id=rir.pk)
        ASN.objects.bulk_create([origin_asn])

        prefix = Prefix(prefix=IPNetwork("10.55.0.0/24"))
        Prefix.objects.bulk_create([prefix])

        organization = Organization(
            org_id=f"migration-test-org-{fixture_suffix}",
            name=f"Migration Test Org {fixture_suffix}",
        )
        Organization.objects.bulk_create([organization])

        certificate = Certificate(
            name="Migration Test Certificate",
            rpki_org_id=organization.pk,
            auto_renews=True,
            self_hosted=False,
        )
        Certificate.objects.bulk_create([certificate])

        roa = Roa(
            name="Migration Test ROA",
            signed_by_id=certificate.pk,
            origin_as_id=origin_asn.pk,
            auto_renews=True,
        )
        Roa.objects.bulk_create([roa])

        roa_prefix = RoaPrefix(
            roa_name_id=roa.pk,
            prefix_id=prefix.pk,
            max_length=24,
        )
        RoaPrefix.objects.bulk_create([roa_prefix])

        roa_tag = Tag(
            name=f"Migration ROA Tag {fixture_suffix}",
            slug=f"migration-roa-tag-{fixture_suffix}",
            color="9e9e9e",
        )
        roa_prefix_tag = Tag(
            name=f"Migration ROA Prefix Tag {fixture_suffix}",
            slug=f"migration-roa-prefix-tag-{fixture_suffix}",
            color="607d8b",
        )
        Tag.objects.bulk_create([roa_tag, roa_prefix_tag])

        roa_content_type, _ = ContentType.objects.get_or_create(
            app_label="netbox_rpki",
            model="roa",
        )
        roa_prefix_content_type, _ = ContentType.objects.get_or_create(
            app_label="netbox_rpki",
            model="roaprefix",
        )

        TaggedItem.objects.create(
            tag=roa_tag,
            content_type=roa_content_type,
            object_id=roa.pk,
        )
        TaggedItem.objects.create(
            tag=roa_prefix_tag,
            content_type=roa_prefix_content_type,
            object_id=roa_prefix.pk,
        )

        self.roa_pk = roa.pk
        self.roa_prefix_pk = roa_prefix.pk
        self.origin_asn_pk = origin_asn.pk
        self.prefix_pk = prefix.pk
        self.organization_pk = organization.pk
        self.roa_tag_slug = roa_tag.slug
        self.roa_prefix_tag_slug = roa_prefix_tag.slug

    def test_0056_preserves_tagged_roa_and_prefix_rows(self):
        ContentType = self.apps.get_model("contenttypes", "ContentType")
        TaggedItem = self.apps.get_model("extras", "TaggedItem")
        RoaObject = self.apps.get_model("netbox_rpki", "RoaObject")
        RoaObjectPrefix = self.apps.get_model("netbox_rpki", "RoaObjectPrefix")

        roa_object = RoaObject.objects.get(pk=self.roa_pk)
        roa_object_prefix = RoaObjectPrefix.objects.get(pk=self.roa_prefix_pk)

        self.assertEqual(roa_object.name, "Migration Test ROA")
        self.assertEqual(roa_object.organization_id, self.organization_pk)
        self.assertEqual(roa_object.origin_as_id, self.origin_asn_pk)

        self.assertEqual(roa_object_prefix.roa_object_id, self.roa_pk)
        self.assertEqual(roa_object_prefix.prefix_id, self.prefix_pk)
        self.assertEqual(roa_object_prefix.prefix_cidr_text, "10.55.0.0/24")
        self.assertEqual(roa_object_prefix.max_length, 24)

        roa_object_content_type = ContentType.objects.get(
            app_label="netbox_rpki",
            model="roaobject",
        )
        roa_object_prefix_content_type = ContentType.objects.get(
            app_label="netbox_rpki",
            model="roaobjectprefix",
        )

        self.assertEqual(
            list(
                TaggedItem.objects.filter(
                    content_type=roa_object_content_type,
                    object_id=roa_object.pk,
                ).values_list("tag__slug", flat=True)
            ),
            [self.roa_tag_slug],
        )
        self.assertEqual(
            list(
                TaggedItem.objects.filter(
                    content_type=roa_object_prefix_content_type,
                    object_id=roa_object_prefix.pk,
                ).values_list("tag__slug", flat=True)
            ),
            [self.roa_prefix_tag_slug],
        )

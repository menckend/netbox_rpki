import json

from django.urls import reverse
from utilities.testing import APITestCase, APIViewTestCases

from tenancy.models import Tenant
from dcim.models import Site, DeviceRole, DeviceType, Manufacturer, Device, Interface
from ipam.models import IPAddress, ASN, RIR, Prefix

from netbox_rpki.models import (
    Certificate,
    CertificateAsn,
    CertificatePrefix,
    Roa,
    RoaPrefix,
    RoaAsn,
    Organization
)

from netbox_rpki.choices import (
    CertificateStatusChoices
)


class OrganizationAPITestCase(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.CreateObjectViewTestCase,
    APIViewTestCases.UpdateObjectViewTestCase,
    APIViewTestCases.DeleteObjectViewTestCase,
    APIViewTestCases.GraphQLTestCase,
):
    model = Organization
    view_namespace = "plugins-api:netbox_rpki"
    brief_fields = ["org_id", "name", "parent_rir"]
    graphql_base_name = "netbox_bgp_community"

    create_data = [
        {"name": "rpki-testorg1", "org_id": "rpki-testorg1"},
        {"name": "rpki-testorg2", "org_id": "rpki-testorg2"},
        {"name": "rpki-testorg3", "org_id": "rpki-testorg3"},
    ]

    bulk_update_data = {
        "description": "Test Community desc",
    }
    @classmethod
    def setUpTestData(cls):
        organizations = (
            Organization(org_id="rpki-testorg1", name="rpki-testorg1"),
            Organization(org_id="rpki-testorg2", name="rpki-testorg2"),
            Organization(org_id="rpki-testorg3", name="rpki-testorg3"),
        )
        Organization.objects.bulk_create(organizations)


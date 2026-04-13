import hashlib
from datetime import timedelta

import ipam
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin
from ipam.models.asns import ASN
from ipam.models.ip import Prefix
from ipam.models import RIR


def _resolve_object_spec_for_model(model_class):
    from netbox_rpki.object_registry import OBJECT_SPECS

    for spec in OBJECT_SPECS:
        if spec.model is model_class:
            return spec
    raise LookupError(f'No object spec registered for {model_class.__name__}')


def _plugin_get_action_url(cls, action=None, rest_api=False, kwargs=None):
    from utilities.views import get_viewname

    spec = _resolve_object_spec_for_model(cls)

    if rest_api:
        viewname = f'plugins-api:netbox_rpki-api:{spec.api.basename}'
        if action:
            viewname = f'{viewname}-{action}'
    else:
        viewname = f'plugins:netbox_rpki:{spec.routes.slug}'
        if action:
            viewname = f'{viewname}_{action}'

    try:
        return reverse(viewname, kwargs=kwargs)
    except NoReverseMatch:
        return reverse(get_viewname(cls, action, rest_api), kwargs=kwargs)


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    WITHDRAWN = "withdrawn", "Withdrawn"


class ValidationState(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    VALID = "valid", "Valid"
    INVALID = "invalid", "Invalid"
    STALE = "stale", "Stale"


class RetrievalState(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    DISCOVERED = "discovered", "Discovered"
    FETCHED = "fetched", "Fetched"
    FAILED = "failed", "Failed"


class RepositoryType(models.TextChoices):
    RSYNC = "rsync", "rsync"
    RRDP = "rrdp", "RRDP"
    MIXED = "mixed", "Mixed"
    OTHER = "other", "Other"


class SignedObjectType(models.TextChoices):
    ROA = "roa", "ROA"
    MANIFEST = "manifest", "Manifest"
    CRL = "crl", "CRL"
    ASPA = "aspa", "ASPA"
    RSC = "rsc", "RSC"
    TAK = "tak", "Trust Anchor Key"
    GHOSTBUSTERS = "ghostbusters", "Ghostbusters"
    OTHER = "other", "Other"


class ValidationRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ValidationDisposition(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    NOTED = "noted", "Noted"


class RoutingIntentProfileStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class RoutingIntentSelectorMode(models.TextChoices):
    ALL = "all", "All Eligible Prefixes"
    FILTERED = "filtered", "Filtered Query"
    EXPLICIT = "explicit", "Explicit Selection"


class DefaultMaxLengthPolicy(models.TextChoices):
    EXACT = "exact", "Exact Prefix Length"
    INHERIT = "inherit", "Inherit Prefix Length"
    CUSTOM = "custom", "Custom"


class AddressFamily(models.TextChoices):
    IPV4 = "ipv4", "IPv4"
    IPV6 = "ipv6", "IPv6"


class RoutingIntentRuleAction(models.TextChoices):
    INCLUDE = "include", "Include"
    EXCLUDE = "exclude", "Exclude"
    SET_ORIGIN = "set_origin", "Set Origin ASN"
    SET_MAX_LENGTH = "set_max_length", "Set maxLength"
    REQUIRE_TAG = "require_tag", "Require Tag"
    REQUIRE_CF = "require_cf", "Require Custom Field"


class RoutingIntentRuleMaxLengthMode(models.TextChoices):
    EXACT = "exact", "Exact"
    INHERIT = "inherit", "Inherit Prefix Length"
    EXPLICIT = "explicit", "Explicit Value"


class ROAIntentOverrideAction(models.TextChoices):
    FORCE_INCLUDE = "force_include", "Force Include"
    SUPPRESS = "suppress", "Suppress"
    REPLACE_ORIGIN = "replace_origin", "Replace Origin ASN"
    REPLACE_MAX_LENGTH = "replace_max_length", "Replace maxLength"


class IntentRunTriggerMode(models.TextChoices):
    MANUAL = "manual", "Manual"
    SCHEDULED = "scheduled", "Scheduled"
    NETBOX_CHANGE = "netbox_change", "NetBox Change"
    SYNC_FOLLOWUP = "sync_followup", "Sync Follow-Up"


class ROAIntentDerivedState(models.TextChoices):
    ACTIVE = "active", "Active"
    SUPPRESSED = "suppressed", "Suppressed"
    SHADOWED = "shadowed", "Shadowed"


class ROAIntentExposureState(models.TextChoices):
    ADVERTISED = "advertised", "Advertised"
    ELIGIBLE_NOT_ADVERTISED = "eligible_not_advertised", "Eligible, Not Advertised"
    BLOCKED = "blocked", "Blocked"


class ROAIntentMatchKind(models.TextChoices):
    EXACT = "exact", "Exact"
    ORIGIN_CONFLICT = "origin_conflict", "Origin Conflict"
    PREFIX_CONFLICT = "prefix_conflict", "Prefix Conflict"
    LENGTH_BROADER = "length_broader", "Broader maxLength"
    LENGTH_NARROWER = "length_narrower", "Narrower maxLength"
    SUPERSET = "superset", "Superset"
    SUBSET = "subset", "Subset"
    STALE_CANDIDATE = "stale_candidate", "Stale Candidate"


class ReconciliationComparisonScope(models.TextChoices):
    LOCAL_ROA_RECORDS = "local_roa_records", "Local ROA Records"
    LOCAL_ASPA_RECORDS = "local_aspa_records", "Local ASPA Records"
    PROVIDER_IMPORTED = "provider_imported", "Provider Imported"
    MIXED = "mixed", "Mixed"


class ProviderType(models.TextChoices):
    ARIN = "arin", "ARIN"
    KRILL = "krill", "Krill"


class ProviderRoaWriteMode(models.TextChoices):
    UNSUPPORTED = "unsupported", "Unsupported"
    KRILL_ROUTE_DELTA = "krill_route_delta", "Krill Route Delta"


class ProviderSyncTransport(models.TextChoices):
    PRODUCTION = "production", "Production"
    OTE = "ote", "OT&E"


class ProviderSyncHealth(models.TextChoices):
    DISABLED = "disabled", "Disabled"
    NEVER_SYNCED = "never_synced", "Never Synced"
    IN_PROGRESS = "in_progress", "In Progress"
    FAILED = "failed", "Failed"
    STALE = "stale", "Stale"
    HEALTHY = "healthy", "Healthy"


class ProviderSyncFamily(models.TextChoices):
    ROA_AUTHORIZATIONS = "roa_authorizations", "ROA Authorizations"
    ASPAS = "aspas", "ASPAs"
    CA_METADATA = "ca_metadata", "CA Metadata"
    PARENT_LINKS = "parent_links", "Parent Links"
    CHILD_LINKS = "child_links", "Child Links"
    RESOURCE_ENTITLEMENTS = "resource_entitlements", "Resource Entitlements"
    PUBLICATION_POINTS = "publication_points", "Publication Points"
    CERTIFICATE_INVENTORY = "certificate_inventory", "Certificate Inventory"
    SIGNED_OBJECT_INVENTORY = "signed_object_inventory", "Signed Object Inventory"


class ProviderSyncFamilyStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"
    LIMITED = "limited", "Limited"
    NOT_IMPLEMENTED = "not_implemented", "Not Implemented"


class ExternalObjectType(models.TextChoices):
    ROA_AUTHORIZATION = "roa_authorization", "ROA Authorization"
    ASPA = "aspa", "ASPA"
    CA_METADATA = "ca_metadata", "CA Metadata"
    PARENT_LINK = "parent_link", "Parent Link"
    CHILD_LINK = "child_link", "Child Link"
    RESOURCE_ENTITLEMENT = "resource_entitlement", "Resource Entitlement"
    PUBLICATION_POINT = "publication_point", "Publication Point"
    CERTIFICATE = "certificate", "Certificate"
    SIGNED_OBJECT = "signed_object", "Signed Object"


class CertificateObservationSource(models.TextChoices):
    SIGNED_OBJECT_EE = "signed_object_ee", "Signed Object EE Certificate"
    CA_INCOMING = "ca_incoming", "CA Incoming Certificate"
    PARENT_SIGNING = "parent_signing", "Parent Signing Certificate"
    PARENT_ISSUED = "parent_issued", "Parent Issued Certificate"


class ImportedResourceEntitlementSource(models.TextChoices):
    CA = "ca", "CA"
    PARENT = "parent", "Parent"
    PARENT_CLASS = "parent_class", "Parent Class"
    CHILD = "child", "Child"


class ProviderSnapshotDiffChangeType(models.TextChoices):
    ADDED = "added", "Added"
    REMOVED = "removed", "Removed"
    CHANGED = "changed", "Changed"
    UNCHANGED = "unchanged", "Unchanged"
    REAPPEARED = "reappeared", "Reappeared"
    STALE = "stale", "Stale"


class ReconciliationSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"
    CRITICAL = "critical", "Critical"


class ROAIntentResultType(models.TextChoices):
    MATCH = "match", "Match"
    MISSING = "missing", "Missing"
    ASN_MISMATCH = "asn_mismatch", "ASN Mismatch"
    ASN_AND_MAX_LENGTH_OVERBROAD = "asn_and_max_length_overbroad", "ASN + Overbroad maxLength"
    ASN_AND_MAX_LENGTH_TOO_NARROW = "asn_and_max_length_too_narrow", "ASN + Too-Narrow maxLength"
    ASN_AND_MAX_LENGTH_MISMATCH = "asn_and_max_length_mismatch", "ASN + maxLength Mismatch"
    PREFIX_MISMATCH = "prefix_mismatch", "Prefix Mismatch"
    MAX_LENGTH_OVERBROAD = "max_length_overbroad", "maxLength Overbroad"
    MAX_LENGTH_TOO_NARROW = "max_length_too_narrow", "maxLength Too Narrow"
    STALE = "stale", "Stale"
    INACTIVE_INTENT = "inactive_intent", "Inactive Intent"
    SUPPRESSED_BY_POLICY = "suppressed_by_policy", "Suppressed by Policy"


class PublishedROAResultType(models.TextChoices):
    MATCHED = "matched", "Matched"
    ORPHANED = "orphaned", "Orphaned"
    DUPLICATE = "duplicate", "Duplicate"
    BROADER_THAN_NEEDED = "broader_than_needed", "Broader Than Needed"
    MAX_LENGTH_TOO_NARROW = "max_length_too_narrow", "maxLength Too Narrow"
    WRONG_ORIGIN = "wrong_origin", "Wrong Origin"
    WRONG_ORIGIN_AND_MAX_LENGTH_OVERBROAD = "wrong_origin_and_max_length_overbroad", "Wrong Origin + Overbroad maxLength"
    WRONG_ORIGIN_AND_MAX_LENGTH_TOO_NARROW = "wrong_origin_and_max_length_too_narrow", "Wrong Origin + Too-Narrow maxLength"
    WRONG_ORIGIN_AND_MAX_LENGTH_MISMATCH = "wrong_origin_and_max_length_mismatch", "Wrong Origin + maxLength Mismatch"
    STALE = "stale", "Stale"
    UNSCOPED = "unscoped", "Unscoped"


class ASPAIntentMatchKind(models.TextChoices):
    EXACT = "exact", "Exact"
    CUSTOMER_MISMATCH = "customer_mismatch", "Customer Mismatch"
    PROVIDER_MISMATCH = "provider_mismatch", "Provider Mismatch"
    STALE_CANDIDATE = "stale_candidate", "Stale Candidate"


class ASPAIntentResultType(models.TextChoices):
    MATCH = "match", "Match"
    MISSING = "missing", "Missing"
    MISSING_PROVIDER = "missing_provider", "Missing Provider"
    CUSTOMER_MISMATCH = "customer_mismatch", "Customer Mismatch"
    PROVIDER_MISMATCH = "provider_mismatch", "Provider Mismatch"
    STALE = "stale", "Stale"
    UNSCOPED = "unscoped", "Unscoped"


class PublishedASPAResultType(models.TextChoices):
    MATCHED = "matched", "Matched"
    ORPHANED = "orphaned", "Orphaned"
    DUPLICATE = "duplicate", "Duplicate"
    EXTRA_PROVIDER = "extra_provider", "Extra Provider"
    MISSING_PROVIDER = "missing_provider", "Missing Provider"
    CUSTOMER_MISMATCH = "customer_mismatch", "Customer Mismatch"
    STALE = "stale", "Stale"
    UNSCOPED = "unscoped", "Unscoped"


class ROAChangePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class ROAChangePlanAction(models.TextChoices):
    CREATE = "create", "Create"
    WITHDRAW = "withdraw", "Withdraw"


class ROAChangePlanItemSemantic(models.TextChoices):
    CREATE = "create", "Create"
    WITHDRAW = "withdraw", "Withdraw"
    REPLACE = "replace", "Replace"
    RESHAPE = "reshape", "Reshape"


class ProviderWriteOperation(models.TextChoices):
    ADD_ROUTE = "add_route", "Add Route"
    REMOVE_ROUTE = "remove_route", "Remove Route"


class ProviderWriteExecutionMode(models.TextChoices):
    PREVIEW = "preview", "Preview"
    APPLY = "apply", "Apply"


def validate_maintenance_window_bounds(*, start_at, end_at):
    if start_at is None or end_at is None:
        return
    if end_at < start_at:
        raise ValidationError({'maintenance_window_end': 'Maintenance window end must be on or after the start.'})


class RpkiStandardModel(NetBoxModel):
    comments = models.TextField(blank=True)
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        abstract = True


class NamedRpkiStandardModel(RpkiStandardModel):
    name = models.CharField(max_length=200, editable=True)

    class Meta:
        abstract = True


class Organization(NetBoxModel):
    org_id = models.CharField(max_length=200, editable=True)
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    ext_url = models.CharField(max_length=200, editable=True, blank=True)
    parent_rir = models.ForeignKey(
        to=RIR,
        on_delete=models.PROTECT,
        related_name='rpki_certs',
        null=True,
        blank=True
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
#        return f'{self.name}, {self.org_id}'
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:organization", args=[self.pk])


class Certificate(NetBoxModel):
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    issuer = models.CharField(max_length=200, editable=True, blank=True)
    subject = models.CharField(max_length=200, editable=True, blank=True)
    serial = models.CharField(max_length=200, editable=True, blank=True)
    valid_from = models.DateField(editable=True, blank=True, null=True)
    valid_to = models.DateField(editable=True, blank=True, null=True)
    auto_renews = models.BooleanField(editable=True)
    public_key = models.CharField(max_length=200, editable=True, blank=True)
    private_key = models.CharField(max_length=200, editable=True, blank=True)
    publication_url = models.CharField(max_length=200, editable=True, blank=True)
    ca_repository = models.CharField(max_length=200, editable=True, blank=True)
    self_hosted = models.BooleanField(max_length=200, editable=True)
    rpki_org = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    trust_anchor = models.ForeignKey(
        to='TrustAnchor',
        on_delete=models.PROTECT,
        related_name='certificates',
        blank=True,
        null=True
    )
    publication_point = models.ForeignKey(
        to='PublicationPoint',
        on_delete=models.PROTECT,
        related_name='certificates',
        blank=True,
        null=True
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
  #      return f'{self.name}, {self.issuer}'
        return self.name
    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificate", args=[self.pk])


class Roa(NetBoxModel):
    name = models.CharField(max_length=200, editable=True)
    comments = models.TextField(
        blank=True
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roas',
        blank=True,
        null=True
    )
    valid_from = models.DateField(editable=True, blank=True, null=True)
    valid_to = models.DateField(editable=True, blank=True, null=True)
    auto_renews = models.BooleanField(editable=True)
    signed_by = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='roas'
    )
    signed_object = models.OneToOneField(
        to='SignedObject',
        on_delete=models.SET_NULL,
        related_name='legacy_roa',
        blank=True,
        null=True
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roa", args=[self.pk])


class RoaPrefix(NetBoxModel):
    prefix = models.ForeignKey(
        to=ipam.models.ip.Prefix,
        on_delete=models.PROTECT,
        related_name='PrefixToRoaTable'
    )
    comments = models.TextField(
        blank=True
    )
    max_length = models.IntegerField(editable=True)
    roa_name = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='RoaToPrefixTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaprefix", args=[self.pk])


class CertificatePrefix(NetBoxModel):
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='PrefixToCertificateTable'
    )
    comments = models.TextField(
        blank=True
    )
    certificate_name = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificateToPrefixTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificateprefix", args=[self.pk])


class CertificateAsn(NetBoxModel):
    asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='ASNtoCertificateTable'
    )
    comments = models.TextField(
        blank=True
    )
    certificate_name2 = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificatetoASNTable'
    )
    tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("asn",)

    def __str__(self):
        return str(self.asn)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificateasn", args=[self.pk])


class Repository(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='repositories',
        blank=True,
        null=True
    )
    repository_type = models.CharField(
        max_length=32,
        choices=RepositoryType.choices,
        default=RepositoryType.MIXED,
    )
    rsync_base_uri = models.CharField(max_length=255, blank=True)
    rrdp_notify_uri = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )
    last_observed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:repository", args=[self.pk])


class PublicationPoint(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='publication_points',
        blank=True,
        null=True
    )
    repository = models.ForeignKey(
        to=Repository,
        on_delete=models.PROTECT,
        related_name='publication_points',
        blank=True,
        null=True
    )
    publication_uri = models.CharField(max_length=255, blank=True)
    rsync_base_uri = models.CharField(max_length=255, blank=True)
    rrdp_notify_uri = models.CharField(max_length=255, blank=True)
    retrieval_state = models.CharField(
        max_length=32,
        choices=RetrievalState.choices,
        default=RetrievalState.UNKNOWN,
    )
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )
    last_observed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:publicationpoint", args=[self.pk])


class TrustAnchor(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='trust_anchors',
        blank=True,
        null=True
    )
    subject = models.CharField(max_length=255, blank=True)
    subject_key_identifier = models.CharField(max_length=255, blank=True)
    rsync_uri = models.CharField(max_length=255, blank=True)
    rrdp_notify_uri = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )
    superseded_by = models.ForeignKey(
        to='self',
        on_delete=models.PROTECT,
        related_name='supersedes',
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:trustanchor", args=[self.pk])


class TrustAnchorLocator(NamedRpkiStandardModel):
    trust_anchor = models.ForeignKey(
        to=TrustAnchor,
        on_delete=models.PROTECT,
        related_name='locators'
    )
    rsync_uri = models.CharField(max_length=255, blank=True)
    https_uri = models.CharField(max_length=255, blank=True)
    public_key_info = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:trustanchorlocator", args=[self.pk])


class EndEntityCertificate(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='ee_certificates',
        blank=True,
        null=True
    )
    resource_certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='ee_certificates',
        blank=True,
        null=True
    )
    publication_point = models.ForeignKey(
        to=PublicationPoint,
        on_delete=models.PROTECT,
        related_name='ee_certificates',
        blank=True,
        null=True
    )
    subject = models.CharField(max_length=255, blank=True)
    issuer = models.CharField(max_length=255, blank=True)
    serial = models.CharField(max_length=200, blank=True)
    ski = models.CharField(max_length=255, blank=True)
    aki = models.CharField(max_length=255, blank=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    public_key = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:endentitycertificate", args=[self.pk])


class SignedObject(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='signed_objects',
        blank=True,
        null=True
    )
    object_type = models.CharField(
        max_length=32,
        choices=SignedObjectType.choices,
        default=SignedObjectType.OTHER,
    )
    display_label = models.CharField(max_length=255, blank=True)
    resource_certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='signed_objects',
        blank=True,
        null=True
    )
    ee_certificate = models.ForeignKey(
        to=EndEntityCertificate,
        on_delete=models.PROTECT,
        related_name='signed_objects',
        blank=True,
        null=True
    )
    publication_point = models.ForeignKey(
        to=PublicationPoint,
        on_delete=models.PROTECT,
        related_name='signed_objects',
        blank=True,
        null=True
    )
    current_manifest = models.ForeignKey(
        to='Manifest',
        on_delete=models.PROTECT,
        related_name='signed_objects',
        blank=True,
        null=True
    )
    filename = models.CharField(max_length=255, blank=True)
    object_uri = models.CharField(max_length=255, blank=True)
    repository_uri = models.CharField(max_length=255, blank=True)
    content_hash = models.CharField(max_length=255, blank=True)
    serial_or_version = models.CharField(max_length=200, blank=True)
    cms_digest_algorithm = models.CharField(max_length=128, blank=True)
    cms_signature_algorithm = models.CharField(max_length=128, blank=True)
    publication_status = models.CharField(
        max_length=32,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    raw_payload_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:signedobject", args=[self.pk])


class CertificateRevocationList(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='certificate_revocation_lists',
        blank=True,
        null=True
    )
    issuing_certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='certificate_revocation_lists'
    )
    publication_point = models.ForeignKey(
        to=PublicationPoint,
        on_delete=models.PROTECT,
        related_name='certificate_revocation_lists',
        blank=True,
        null=True
    )
    manifest = models.ForeignKey(
        to='Manifest',
        on_delete=models.PROTECT,
        related_name='certificate_revocation_lists',
        blank=True,
        null=True
    )
    crl_number = models.CharField(max_length=200, blank=True)
    this_update = models.DateTimeField(blank=True, null=True)
    next_update = models.DateTimeField(blank=True, null=True)
    publication_uri = models.CharField(max_length=255, blank=True)
    retrieval_state = models.CharField(
        max_length=32,
        choices=RetrievalState.choices,
        default=RetrievalState.UNKNOWN,
    )
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificaterevocationlist", args=[self.pk])


class RevokedCertificate(RpkiStandardModel):
    revocation_list = models.ForeignKey(
        to=CertificateRevocationList,
        on_delete=models.PROTECT,
        related_name='revoked_certificates'
    )
    certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='revocation_references',
        blank=True,
        null=True
    )
    ee_certificate = models.ForeignKey(
        to=EndEntityCertificate,
        on_delete=models.PROTECT,
        related_name='revocation_references',
        blank=True,
        null=True
    )
    serial = models.CharField(max_length=200, blank=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    revocation_reason = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("serial",)

    def __str__(self):
        return self.serial or f"Revoked certificate {self.pk}"


class Manifest(NamedRpkiStandardModel):
    signed_object = models.OneToOneField(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='manifest_extension',
        blank=True,
        null=True
    )
    manifest_number = models.CharField(max_length=200, blank=True)
    this_update = models.DateTimeField(blank=True, null=True)
    next_update = models.DateTimeField(blank=True, null=True)
    current_crl = models.ForeignKey(
        to=CertificateRevocationList,
        on_delete=models.PROTECT,
        related_name='manifests',
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:manifest", args=[self.pk])


class ManifestEntry(RpkiStandardModel):
    manifest = models.ForeignKey(
        to=Manifest,
        on_delete=models.PROTECT,
        related_name='entries'
    )
    signed_object = models.ForeignKey(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='manifest_entries',
        blank=True,
        null=True
    )
    certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='manifest_entries',
        blank=True,
        null=True
    )
    ee_certificate = models.ForeignKey(
        to=EndEntityCertificate,
        on_delete=models.PROTECT,
        related_name='manifest_entries',
        blank=True,
        null=True
    )
    revocation_list = models.ForeignKey(
        to=CertificateRevocationList,
        on_delete=models.PROTECT,
        related_name='manifest_entries',
        blank=True,
        null=True
    )
    filename = models.CharField(max_length=255)
    hash_algorithm = models.CharField(max_length=64, blank=True)
    hash_value = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("filename",)

    def __str__(self):
        return self.filename


class TrustAnchorKey(NamedRpkiStandardModel):
    trust_anchor = models.ForeignKey(
        to=TrustAnchor,
        on_delete=models.PROTECT,
        related_name='keys'
    )
    signed_object = models.OneToOneField(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='trust_anchor_key_extension',
        blank=True,
        null=True
    )
    current_public_key = models.TextField(blank=True)
    next_public_key = models.TextField(blank=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    publication_uri = models.CharField(max_length=255, blank=True)
    supersedes = models.ForeignKey(
        to='self',
        on_delete=models.PROTECT,
        related_name='successors',
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:trustanchorkey", args=[self.pk])


class ASPA(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspas',
        blank=True,
        null=True
    )
    signed_object = models.OneToOneField(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='aspa_extension',
        blank=True,
        null=True
    )
    customer_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='customer_aspas',
        blank=True,
        null=True
    )
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspa", args=[self.pk])


class ASPAProvider(RpkiStandardModel):
    aspa = models.ForeignKey(
        to=ASPA,
        on_delete=models.PROTECT,
        related_name='provider_authorizations'
    )
    provider_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='provider_aspas'
    )
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ("provider_as",)
        constraints = (
            models.UniqueConstraint(
                fields=("aspa", "provider_as"),
                name="netbox_rpki_aspaprovider_aspa_provider_unique",
            ),
        )

    def __str__(self):
        return str(self.provider_as)

    def clean(self):
        super().clean()
        if self.aspa_id is None or self.provider_as_id is None:
            return
        if self.aspa.customer_as_id == self.provider_as_id:
            raise ValidationError(
                {'provider_as': 'Provider ASN must differ from the ASPA customer ASN.'}
            )


class RSC(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='rscs',
        blank=True,
        null=True
    )
    signed_object = models.OneToOneField(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='rsc_extension',
        blank=True,
        null=True
    )
    version = models.CharField(max_length=64, blank=True)
    digest_algorithm = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:rsc", args=[self.pk])


class RSCFileHash(RpkiStandardModel):
    rsc = models.ForeignKey(
        to=RSC,
        on_delete=models.PROTECT,
        related_name='file_hashes'
    )
    filename = models.CharField(max_length=255)
    hash_algorithm = models.CharField(max_length=64, blank=True)
    hash_value = models.CharField(max_length=255, blank=True)
    artifact_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("filename",)

    def __str__(self):
        return self.filename


class RouterCertificate(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='router_certificates',
        blank=True,
        null=True
    )
    resource_certificate = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='router_certificates',
        blank=True,
        null=True
    )
    publication_point = models.ForeignKey(
        to=PublicationPoint,
        on_delete=models.PROTECT,
        related_name='router_certificates',
        blank=True,
        null=True
    )
    asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='router_certificates',
        blank=True,
        null=True
    )
    subject = models.CharField(max_length=255, blank=True)
    issuer = models.CharField(max_length=255, blank=True)
    serial = models.CharField(max_length=200, blank=True)
    ski = models.CharField(max_length=255, blank=True)
    router_public_key = models.TextField(blank=True)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routercertificate", args=[self.pk])


class ValidatorInstance(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='validator_instances',
        blank=True,
        null=True
    )
    software_name = models.CharField(max_length=128, blank=True)
    software_version = models.CharField(max_length=128, blank=True)
    base_url = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    last_run_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:validatorinstance", args=[self.pk])


class ValidationRun(NamedRpkiStandardModel):
    validator = models.ForeignKey(
        to=ValidatorInstance,
        on_delete=models.PROTECT,
        related_name='validation_runs'
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    repository_serial = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:validationrun", args=[self.pk])


class ObjectValidationResult(NamedRpkiStandardModel):
    validation_run = models.ForeignKey(
        to=ValidationRun,
        on_delete=models.PROTECT,
        related_name='object_results'
    )
    signed_object = models.ForeignKey(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='validation_results',
        blank=True,
        null=True
    )
    validation_state = models.CharField(
        max_length=32,
        choices=ValidationState.choices,
        default=ValidationState.UNKNOWN,
    )
    disposition = models.CharField(
        max_length=32,
        choices=ValidationDisposition.choices,
        default=ValidationDisposition.NOTED,
    )
    observed_at = models.DateTimeField(blank=True, null=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:objectvalidationresult", args=[self.pk])


class ValidatedRoaPayload(NamedRpkiStandardModel):
    validation_run = models.ForeignKey(
        to=ValidationRun,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads'
    )
    roa = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='validated_payloads',
        blank=True,
        null=True
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads'
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads',
        blank=True,
        null=True
    )
    max_length = models.IntegerField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:validatedroapayload", args=[self.pk])


class ValidatedAspaPayload(NamedRpkiStandardModel):
    validation_run = models.ForeignKey(
        to=ValidationRun,
        on_delete=models.PROTECT,
        related_name='validated_aspa_payloads'
    )
    aspa = models.ForeignKey(
        to=ASPA,
        on_delete=models.PROTECT,
        related_name='validated_payloads',
        blank=True,
        null=True
    )
    customer_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='validated_customer_aspa_payloads',
        blank=True,
        null=True
    )
    provider_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='validated_provider_aspa_payloads',
        blank=True,
        null=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:validatedaspapayload", args=[self.pk])


class RoutingIntentProfile(JobsMixin, NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='routing_intent_profiles'
    )
    is_default = models.BooleanField(default=False)
    status = models.CharField(
        max_length=32,
        choices=RoutingIntentProfileStatus.choices,
        default=RoutingIntentProfileStatus.DRAFT,
    )
    description = models.TextField(blank=True)
    selector_mode = models.CharField(
        max_length=32,
        choices=RoutingIntentSelectorMode.choices,
        default=RoutingIntentSelectorMode.FILTERED,
    )
    prefix_selector_query = models.TextField(blank=True)
    asn_selector_query = models.TextField(blank=True)
    default_max_length_policy = models.CharField(
        max_length=32,
        choices=DefaultMaxLengthPolicy.choices,
        default=DefaultMaxLengthPolicy.EXACT,
    )
    allow_as0 = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routingintentprofile", args=[self.pk])


class RoutingIntentRule(NamedRpkiStandardModel):
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='rules'
    )
    weight = models.PositiveIntegerField(default=100)
    action = models.CharField(
        max_length=32,
        choices=RoutingIntentRuleAction.choices,
        default=RoutingIntentRuleAction.INCLUDE,
    )
    address_family = models.CharField(
        max_length=8,
        choices=AddressFamily.choices,
        blank=True,
    )
    match_tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='routing_intent_rules',
        blank=True,
        null=True
    )
    match_vrf = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='routing_intent_rules',
        blank=True,
        null=True
    )
    match_site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='routing_intent_rules',
        blank=True,
        null=True
    )
    match_region = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='routing_intent_rules',
        blank=True,
        null=True
    )
    match_role = models.CharField(max_length=100, blank=True)
    match_tag = models.CharField(max_length=100, blank=True)
    match_custom_field = models.CharField(max_length=255, blank=True)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='routing_intent_rules',
        blank=True,
        null=True
    )
    max_length_mode = models.CharField(
        max_length=32,
        choices=RoutingIntentRuleMaxLengthMode.choices,
        default=RoutingIntentRuleMaxLengthMode.INHERIT,
    )
    max_length_value = models.PositiveSmallIntegerField(blank=True, null=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("intent_profile", "weight", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routingintentrule", args=[self.pk])


class ROAIntentOverride(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='overrides',
        blank=True,
        null=True
    )
    action = models.CharField(
        max_length=32,
        choices=ROAIntentOverrideAction.choices,
        default=ROAIntentOverrideAction.FORCE_INCLUDE,
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    max_length = models.PositiveSmallIntegerField(blank=True, null=True)
    tenant_scope = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    vrf_scope = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    site_scope = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    region_scope = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='roa_intent_overrides',
        blank=True,
        null=True
    )
    reason = models.TextField(blank=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaintentoverride", args=[self.pk])


class IntentDerivationRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='intent_derivation_runs'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='derivation_runs'
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    trigger_mode = models.CharField(
        max_length=32,
        choices=IntentRunTriggerMode.choices,
        default=IntentRunTriggerMode.MANUAL,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    input_fingerprint = models.CharField(max_length=128, blank=True)
    prefix_count_scanned = models.PositiveIntegerField(default=0)
    intent_count_emitted = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:intentderivationrun", args=[self.pk])


class ROAIntent(NamedRpkiStandardModel):
    derivation_run = models.ForeignKey(
        to='IntentDerivationRun',
        on_delete=models.PROTECT,
        related_name='roa_intents'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_intents'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='roa_intents'
    )
    intent_key = models.CharField(max_length=64)
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    address_family = models.CharField(max_length=8, choices=AddressFamily.choices)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    is_as0 = models.BooleanField(default=False)
    max_length = models.PositiveSmallIntegerField(blank=True, null=True)
    scope_tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    scope_vrf = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    scope_site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    scope_region = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True
    )
    source_rule = models.ForeignKey(
        to='RoutingIntentRule',
        on_delete=models.SET_NULL,
        related_name='derived_intents',
        blank=True,
        null=True
    )
    applied_override = models.ForeignKey(
        to='ROAIntentOverride',
        on_delete=models.SET_NULL,
        related_name='derived_intents',
        blank=True,
        null=True
    )
    derived_state = models.CharField(
        max_length=32,
        choices=ROAIntentDerivedState.choices,
        default=ROAIntentDerivedState.ACTIVE,
    )
    exposure_state = models.CharField(
        max_length=32,
        choices=ROAIntentExposureState.choices,
        default=ROAIntentExposureState.ELIGIBLE_NOT_ADVERTISED,
    )
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("derivation_run", "intent_key"),
                name="netbox_rpki_roaintent_derivation_run_intent_key_unique",
            ),
        )
        indexes = (
            models.Index(fields=("organization", "intent_profile"), name="nb_rpki_ri_org_prof_idx"),
            models.Index(fields=("prefix", "origin_asn"), name="nb_rpki_ri_pfx_org_idx"),
            models.Index(fields=("scope_tenant", "scope_site"), name="nb_rpki_ri_ten_site_idx"),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaintent", args=[self.pk])

    @classmethod
    def build_intent_key(
        cls,
        *,
        prefix_cidr_text: str,
        address_family: str,
        origin_asn_value: int | None,
        max_length: int | None,
        tenant_id: int | None = None,
        vrf_id: int | None = None,
        site_id: int | None = None,
        region_id: int | None = None,
    ) -> str:
        normalized = "|".join(
            str(value)
            for value in (
                prefix_cidr_text.strip().lower(),
                address_family,
                origin_asn_value if origin_asn_value is not None else "",
                max_length if max_length is not None else "",
                tenant_id if tenant_id is not None else "",
                vrf_id if vrf_id is not None else "",
                site_id if site_id is not None else "",
                region_id if region_id is not None else "",
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class RpkiProviderAccount(NamedRpkiStandardModel):
    DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES = 24 * 60

    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='provider_accounts'
    )
    provider_type = models.CharField(
        max_length=32,
        choices=ProviderType.choices,
        default=ProviderType.ARIN,
    )
    transport = models.CharField(
        max_length=16,
        choices=ProviderSyncTransport.choices,
        default=ProviderSyncTransport.PRODUCTION,
    )
    org_handle = models.CharField(max_length=100)
    ca_handle = models.CharField(max_length=100, blank=True)
    api_key = models.CharField(max_length=255)
    api_base_url = models.CharField(max_length=255, default='https://reg.arin.net')
    sync_enabled = models.BooleanField(default=True)
    sync_interval = models.PositiveIntegerField(blank=True, null=True)
    last_successful_sync = models.DateTimeField(blank=True, null=True)
    last_sync_status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    last_sync_summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "provider_type", "org_handle"),
                name="netbox_rpki_provideraccount_org_provider_handle_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:provideraccount", args=[self.pk])

    @property
    def sync_target_handle(self) -> str:
        if self.provider_type == ProviderType.KRILL:
            return self.ca_handle.strip()
        return self.org_handle.strip()

    @property
    def roa_write_mode(self) -> str:
        if self.provider_type == ProviderType.KRILL:
            return ProviderRoaWriteMode.KRILL_ROUTE_DELTA
        return ProviderRoaWriteMode.UNSUPPORTED

    @property
    def supports_roa_write(self) -> bool:
        return self.roa_write_mode != ProviderRoaWriteMode.UNSUPPORTED

    @property
    def roa_write_capability(self) -> dict:
        supported_actions = []
        if self.supports_roa_write:
            supported_actions = [ROAChangePlanAction.CREATE, ROAChangePlanAction.WITHDRAW]
        return {
            'supports_roa_write': self.supports_roa_write,
            'roa_write_mode': self.roa_write_mode,
            'supported_roa_plan_actions': supported_actions,
        }

    @property
    def sync_health_interval(self) -> timedelta:
        interval_minutes = self.sync_interval or self.DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES
        return timedelta(minutes=interval_minutes)

    @property
    def next_sync_due_at(self):
        if not self.sync_enabled or not self.sync_interval:
            return None
        if self.last_successful_sync is None:
            return timezone.now()
        return self.last_successful_sync + timedelta(minutes=self.sync_interval)

    def is_sync_due(self, *, reference_time=None) -> bool:
        if not self.sync_enabled or not self.sync_interval:
            return False

        if self.last_sync_status == ValidationRunStatus.RUNNING:
            return False

        if self.last_sync_status == ValidationRunStatus.FAILED:
            return True

        if self.last_successful_sync is None:
            return True

        reference_time = reference_time or timezone.now()
        due_at = self.next_sync_due_at
        if due_at is None:
            return False
        return due_at <= reference_time

    @property
    def sync_health(self) -> str:
        if not self.sync_enabled:
            return ProviderSyncHealth.DISABLED

        if self.last_sync_status == ValidationRunStatus.RUNNING:
            return ProviderSyncHealth.IN_PROGRESS

        if self.last_sync_status == ValidationRunStatus.FAILED:
            return ProviderSyncHealth.FAILED

        if self.last_successful_sync is None:
            return ProviderSyncHealth.NEVER_SYNCED

        if self.last_successful_sync + self.sync_health_interval <= timezone.now():
            return ProviderSyncHealth.STALE

        return ProviderSyncHealth.HEALTHY

    @property
    def sync_health_display(self) -> str:
        return ProviderSyncHealth(self.sync_health).label


class ProviderSyncRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='provider_sync_runs'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='sync_runs'
    )
    provider_snapshot = models.OneToOneField(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='sync_run',
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    records_fetched = models.PositiveIntegerField(default=0)
    records_imported = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providersyncrun", args=[self.pk])


class ProviderSnapshot(NamedRpkiStandardModel):
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='snapshots',
        blank=True,
        null=True,
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='provider_snapshots'
    )
    provider_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    fetched_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-fetched_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providersnapshot", args=[self.pk])


class ProviderSnapshotDiff(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='provider_snapshot_diffs'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='snapshot_diffs'
    )
    base_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='diffs_as_base'
    )
    comparison_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='diffs_as_comparison'
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    compared_at = models.DateTimeField(blank=True, null=True)
    error = models.TextField(blank=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-compared_at", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("base_snapshot", "comparison_snapshot"),
                name="netbox_rpki_providersnapshotdiff_snapshot_pair_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providersnapshotdiff", args=[self.pk])


class ProviderSnapshotDiffItem(NamedRpkiStandardModel):
    snapshot_diff = models.ForeignKey(
        to='ProviderSnapshotDiff',
        on_delete=models.PROTECT,
        related_name='items'
    )
    object_family = models.CharField(
        max_length=64,
        choices=ProviderSyncFamily.choices,
        default=ProviderSyncFamily.ROA_AUTHORIZATIONS,
    )
    change_type = models.CharField(
        max_length=32,
        choices=ProviderSnapshotDiffChangeType.choices,
        default=ProviderSnapshotDiffChangeType.CHANGED,
    )
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.SET_NULL,
        related_name='snapshot_diff_items',
        blank=True,
        null=True,
    )
    provider_identity = models.CharField(max_length=512, blank=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    before_state_json = models.JSONField(default=dict, blank=True)
    after_state_json = models.JSONField(default=dict, blank=True)
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    customer_as_value = models.PositiveBigIntegerField(blank=True, null=True)
    provider_as_value = models.PositiveBigIntegerField(blank=True, null=True)
    related_handle = models.CharField(max_length=200, blank=True)
    certificate_identifier = models.CharField(max_length=200, blank=True)
    publication_uri = models.CharField(max_length=500, blank=True)
    signed_object_uri = models.CharField(max_length=500, blank=True)
    is_stale = models.BooleanField(default=False)

    class Meta:
        ordering = ("object_family", "change_type", "provider_identity", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providersnapshotdiffitem", args=[self.pk])


class ExternalObjectReference(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='external_object_references'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='external_object_references'
    )
    object_type = models.CharField(
        max_length=64,
        choices=ExternalObjectType.choices,
        default=ExternalObjectType.ROA_AUTHORIZATION,
    )
    provider_identity = models.CharField(max_length=512)
    external_object_id = models.CharField(max_length=200, blank=True)
    last_seen_provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='external_object_references',
        blank=True,
        null=True,
    )
    last_seen_imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.SET_NULL,
        related_name='current_external_object_references',
        blank=True,
        null=True,
    )
    last_seen_imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.SET_NULL,
        related_name='current_external_object_references',
        blank=True,
        null=True,
    )
    last_seen_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_account", "object_type", "provider_identity"),
                name="netbox_rpki_extobjref_provider_identity_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:externalobjectreference", args=[self.pk])


def _build_import_key(*values: object) -> str:
    normalized = "|".join("" if value is None else str(value) for value in values)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ImportedRoaAuthorization(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_roa_authorizations'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_roa_authorizations'
    )
    authorization_key = models.CharField(max_length=64)
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='imported_roa_authorizations',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64)
    address_family = models.CharField(max_length=8, choices=AddressFamily.choices)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='imported_roa_authorizations',
        blank=True,
        null=True
    )
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    max_length = models.PositiveSmallIntegerField(blank=True, null=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_roa_authorizations',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "authorization_key"),
                name="netbox_rpki_importedroaauth_snapshot_key_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedroaauthorization", args=[self.pk])

    @classmethod
    def build_authorization_key(
        cls,
        *,
        prefix_cidr_text: str,
        address_family: str,
        origin_asn_value: int | None,
        max_length: int | None,
        external_object_id: str = '',
    ) -> str:
        normalized = "|".join(
            str(value)
            for value in (
                prefix_cidr_text.strip().lower(),
                address_family,
                origin_asn_value if origin_asn_value is not None else "",
                max_length if max_length is not None else "",
                external_object_id.strip(),
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ImportedAspa(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_aspas'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_aspas'
    )
    authorization_key = models.CharField(max_length=64)
    customer_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='imported_aspas',
        blank=True,
        null=True
    )
    customer_as_value = models.PositiveBigIntegerField(blank=True, null=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_aspas',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "authorization_key"),
                name="netbox_rpki_importedaspa_snapshot_key_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedaspa", args=[self.pk])

    @classmethod
    def build_authorization_key(
        cls,
        *,
        customer_as_value: int | None,
        external_object_id: str = '',
    ) -> str:
        normalized = "|".join(
            str(value)
            for value in (
                customer_as_value if customer_as_value is not None else "",
                external_object_id.strip(),
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ImportedAspaProvider(RpkiStandardModel):
    imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.PROTECT,
        related_name='provider_authorizations'
    )
    provider_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='imported_aspa_authorizations',
        blank=True,
        null=True
    )
    provider_as_value = models.PositiveBigIntegerField(blank=True, null=True)
    address_family = models.CharField(max_length=8, choices=AddressFamily.choices, blank=True)
    raw_provider_text = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("provider_as_value", "address_family", "raw_provider_text")
        constraints = (
            models.UniqueConstraint(
                fields=("imported_aspa", "raw_provider_text"),
                name="netbox_rpki_importedaspaprovider_aspa_raw_unique",
            ),
        )

    def __str__(self):
        if self.raw_provider_text:
            return self.raw_provider_text
        if self.provider_as is not None:
            return str(self.provider_as)
        if self.provider_as_value is not None:
            return f'AS{self.provider_as_value}'
        return self.name if hasattr(self, 'name') else 'Imported ASPA Provider'


class ImportedCaMetadata(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_ca_metadata_records'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_ca_metadata_records'
    )
    metadata_key = models.CharField(max_length=64)
    ca_handle = models.CharField(max_length=100)
    id_cert_hash = models.CharField(max_length=255, blank=True)
    publication_uri = models.CharField(max_length=500, blank=True)
    rrdp_notification_uri = models.CharField(max_length=500, blank=True)
    parent_count = models.PositiveIntegerField(default=0)
    child_count = models.PositiveIntegerField(default=0)
    suspended_child_count = models.PositiveIntegerField(default=0)
    resource_class_count = models.PositiveIntegerField(default=0)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_ca_metadata_records',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "metadata_key"),
                name="nb_rpki_impcameta_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedcametadata", args=[self.pk])

    @classmethod
    def build_metadata_key(
        cls,
        *,
        ca_handle: str,
        external_object_id: str = '',
    ) -> str:
        return _build_import_key(ca_handle.strip().lower(), external_object_id.strip())


class ImportedParentLink(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_parent_links'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_parent_links'
    )
    link_key = models.CharField(max_length=64)
    parent_handle = models.CharField(max_length=100)
    relationship_type = models.CharField(max_length=64, blank=True)
    service_uri = models.CharField(max_length=500, blank=True)
    last_exchange_at = models.DateTimeField(blank=True, null=True)
    last_exchange_result = models.CharField(max_length=64, blank=True)
    last_success_at = models.DateTimeField(blank=True, null=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_parent_links',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "link_key"),
                name="nb_rpki_impparlink_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedparentlink", args=[self.pk])

    @classmethod
    def build_link_key(
        cls,
        *,
        parent_handle: str,
        external_object_id: str = '',
    ) -> str:
        return _build_import_key(parent_handle.strip().lower(), external_object_id.strip())


class ImportedChildLink(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_child_links'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_child_links'
    )
    link_key = models.CharField(max_length=64)
    child_handle = models.CharField(max_length=100)
    state = models.CharField(max_length=64, blank=True)
    id_cert_hash = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    last_exchange_at = models.DateTimeField(blank=True, null=True)
    last_exchange_result = models.CharField(max_length=64, blank=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_child_links',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "link_key"),
                name="nb_rpki_impchildlink_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedchildlink", args=[self.pk])

    @classmethod
    def build_link_key(
        cls,
        *,
        child_handle: str,
        external_object_id: str = '',
    ) -> str:
        return _build_import_key(child_handle.strip().lower(), external_object_id.strip())


class ImportedResourceEntitlement(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_resource_entitlements'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_resource_entitlements'
    )
    entitlement_key = models.CharField(max_length=64)
    entitlement_source = models.CharField(
        max_length=32,
        choices=ImportedResourceEntitlementSource.choices,
        default=ImportedResourceEntitlementSource.CA,
    )
    related_handle = models.CharField(max_length=100, blank=True)
    class_name = models.CharField(max_length=100, blank=True)
    asn_resources = models.CharField(max_length=500, blank=True)
    ipv4_resources = models.CharField(max_length=500, blank=True)
    ipv6_resources = models.CharField(max_length=500, blank=True)
    not_after = models.DateTimeField(blank=True, null=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_resource_entitlements',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "entitlement_key"),
                name="nb_rpki_impresent_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedresourceentitlement", args=[self.pk])

    @classmethod
    def build_entitlement_key(
        cls,
        *,
        entitlement_source: str,
        related_handle: str = '',
        class_name: str = '',
        external_object_id: str = '',
    ) -> str:
        return _build_import_key(
            entitlement_source,
            related_handle.strip().lower(),
            class_name.strip(),
            external_object_id.strip(),
        )


class ImportedPublicationPoint(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_publication_points'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_publication_points'
    )
    publication_key = models.CharField(max_length=64)
    service_uri = models.CharField(max_length=500, blank=True)
    publication_uri = models.CharField(max_length=500, blank=True)
    rrdp_notification_uri = models.CharField(max_length=500, blank=True)
    last_exchange_at = models.DateTimeField(blank=True, null=True)
    last_exchange_result = models.CharField(max_length=64, blank=True)
    next_exchange_before = models.DateTimeField(blank=True, null=True)
    published_object_count = models.PositiveIntegerField(default=0)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_publication_points',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "publication_key"),
                name="nb_rpki_imppubpoint_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedpublicationpoint", args=[self.pk])

    @classmethod
    def build_publication_key(
        cls,
        *,
        service_uri: str = '',
        publication_uri: str = '',
        external_object_id: str = '',
    ) -> str:
        primary_identity = service_uri.strip() or publication_uri.strip() or external_object_id.strip()
        secondary_identity = publication_uri.strip() if primary_identity != publication_uri.strip() else ''
        return _build_import_key(primary_identity, secondary_identity)


class ImportedSignedObject(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_signed_objects'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_signed_objects'
    )
    publication_point = models.ForeignKey(
        to='ImportedPublicationPoint',
        on_delete=models.PROTECT,
        related_name='imported_signed_objects'
    )
    signed_object_key = models.CharField(max_length=64)
    signed_object_type = models.CharField(
        max_length=32,
        choices=SignedObjectType.choices,
        default=SignedObjectType.OTHER,
    )
    publication_uri = models.CharField(max_length=500, blank=True)
    signed_object_uri = models.CharField(max_length=500, blank=True)
    object_hash = models.CharField(max_length=64, blank=True)
    body_base64 = models.TextField(blank=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_signed_objects',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "signed_object_key"),
                name="nb_rpki_impsignedobj_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedsignedobject", args=[self.pk])

    @classmethod
    def build_signed_object_key(
        cls,
        *,
        publication_uri: str = '',
        signed_object_uri: str = '',
        object_hash: str = '',
    ) -> str:
        primary_identity = signed_object_uri.strip() or object_hash.strip() or publication_uri.strip()
        secondary_identity = publication_uri.strip() if primary_identity != publication_uri.strip() else ''
        tertiary_identity = object_hash.strip() if primary_identity != object_hash.strip() else ''
        return _build_import_key(primary_identity, secondary_identity, tertiary_identity)


class ImportedCertificateObservation(NamedRpkiStandardModel):
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='imported_certificate_observations'
    )
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='imported_certificate_observations'
    )
    certificate_key = models.CharField(max_length=64)
    observation_source = models.CharField(
        max_length=32,
        choices=CertificateObservationSource.choices,
        default=CertificateObservationSource.SIGNED_OBJECT_EE,
    )
    certificate_uri = models.CharField(max_length=500, blank=True)
    publication_uri = models.CharField(max_length=500, blank=True)
    signed_object_uri = models.CharField(max_length=500, blank=True)
    related_handle = models.CharField(max_length=100, blank=True)
    class_name = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    issuer = models.CharField(max_length=500, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)
    not_before = models.DateTimeField(blank=True, null=True)
    not_after = models.DateTimeField(blank=True, null=True)
    external_object_id = models.CharField(max_length=200, blank=True)
    external_reference = models.ForeignKey(
        to='ExternalObjectReference',
        on_delete=models.PROTECT,
        related_name='imported_certificate_observations',
        blank=True,
        null=True,
    )
    is_stale = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("provider_snapshot", "certificate_key"),
                name="nb_rpki_impcertobs_snap_key_uniq",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:importedcertificateobservation", args=[self.pk])

    @classmethod
    def build_certificate_key(
        cls,
        *,
        certificate_key: str,
    ) -> str:
        return _build_import_key(certificate_key.strip().lower())


class ASPAIntent(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspa_intents'
    )
    intent_key = models.CharField(max_length=64)
    customer_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='aspa_customer_intents'
    )
    provider_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='aspa_provider_intents'
    )
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "intent_key"),
                name="netbox_rpki_aspaintent_org_intent_key_unique",
            ),
        )
        indexes = (
            models.Index(fields=("organization", "customer_as", "provider_as"), name="nb_rpki_ai_org_pair_idx"),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.customer_as_id is not None and self.customer_as_id == self.provider_as_id:
            raise ValidationError({'provider_as': ['Provider ASN must differ from the ASPA customer ASN.']})

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspaintent", args=[self.pk])

    @classmethod
    def build_intent_key(
        cls,
        *,
        customer_asn_value: int | None,
        provider_asn_value: int | None,
    ) -> str:
        normalized = "|".join(
            str(value)
            for value in (
                customer_asn_value if customer_asn_value is not None else "",
                provider_asn_value if provider_asn_value is not None else "",
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ASPAIntentMatch(NamedRpkiStandardModel):
    aspa_intent = models.ForeignKey(
        to='ASPAIntent',
        on_delete=models.PROTECT,
        related_name='candidate_matches'
    )
    aspa = models.ForeignKey(
        to='ASPA',
        on_delete=models.PROTECT,
        related_name='intent_matches',
        blank=True,
        null=True
    )
    imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.PROTECT,
        related_name='intent_matches',
        blank=True,
        null=True
    )
    match_kind = models.CharField(
        max_length=32,
        choices=ASPAIntentMatchKind.choices,
        default=ASPAIntentMatchKind.EXACT,
    )
    is_best_match = models.BooleanField(default=False)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("aspa_intent", "aspa"),
                condition=models.Q(aspa__isnull=False, imported_aspa__isnull=True),
                name="netbox_rpki_aspaintentmatch_aspa_intent_aspa_unique",
            ),
            models.UniqueConstraint(
                fields=("aspa_intent", "imported_aspa"),
                condition=models.Q(aspa__isnull=True, imported_aspa__isnull=False),
                name="netbox_rpki_aspaintentmatch_aspa_intent_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(aspa__isnull=False, imported_aspa__isnull=True)
                    | models.Q(aspa__isnull=True, imported_aspa__isnull=False)
                ),
                name="netbox_rpki_aspaintentmatch_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspaintentmatch", args=[self.pk])


class ASPAReconciliationRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspa_reconciliation_runs'
    )
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='aspa_reconciliation_runs',
        blank=True,
        null=True
    )
    comparison_scope = models.CharField(
        max_length=32,
        choices=ReconciliationComparisonScope.choices,
        default=ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    intent_count = models.PositiveIntegerField(default=0)
    published_aspa_count = models.PositiveIntegerField(default=0)
    result_summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.comparison_scope == ReconciliationComparisonScope.PROVIDER_IMPORTED and self.provider_snapshot_id is None:
            raise ValidationError({'provider_snapshot': ['Provider snapshot is required for provider-imported ASPA reconciliation runs.']})

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspareconciliationrun", args=[self.pk])


class ASPAIntentResult(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ASPAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='intent_results'
    )
    aspa_intent = models.ForeignKey(
        to='ASPAIntent',
        on_delete=models.PROTECT,
        related_name='reconciliation_results'
    )
    result_type = models.CharField(
        max_length=32,
        choices=ASPAIntentResultType.choices,
        default=ASPAIntentResultType.MATCH,
    )
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    best_aspa = models.ForeignKey(
        to=ASPA,
        on_delete=models.SET_NULL,
        related_name='intent_result_matches',
        blank=True,
        null=True
    )
    best_imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.SET_NULL,
        related_name='intent_result_matches',
        blank=True,
        null=True
    )
    match_count = models.PositiveIntegerField(default=0)
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("reconciliation_run", "aspa_intent"),
                name="netbox_rpki_aspaintentresult_run_intent_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspaintentresult", args=[self.pk])


class PublishedASPAResult(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ASPAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='published_aspa_results'
    )
    aspa = models.ForeignKey(
        to=ASPA,
        on_delete=models.PROTECT,
        related_name='published_reconciliation_results',
        blank=True,
        null=True
    )
    imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.PROTECT,
        related_name='published_reconciliation_results',
        blank=True,
        null=True
    )
    result_type = models.CharField(
        max_length=64,
        choices=PublishedASPAResultType.choices,
        default=PublishedASPAResultType.MATCHED,
    )
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    matched_intent_count = models.PositiveIntegerField(default=0)
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("reconciliation_run", "aspa"),
                condition=models.Q(aspa__isnull=False, imported_aspa__isnull=True),
                name="netbox_rpki_publishedasparesult_run_aspa_unique",
            ),
            models.UniqueConstraint(
                fields=("reconciliation_run", "imported_aspa"),
                condition=models.Q(aspa__isnull=True, imported_aspa__isnull=False),
                name="netbox_rpki_publishedasparesult_run_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(aspa__isnull=False, imported_aspa__isnull=True)
                    | models.Q(aspa__isnull=True, imported_aspa__isnull=False)
                ),
                name="netbox_rpki_publishedasparesult_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:publishedasparesult", args=[self.pk])


class ROAIntentMatch(NamedRpkiStandardModel):
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='candidate_matches'
    )
    roa = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='intent_matches'
        ,
        blank=True,
        null=True
    )
    imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.PROTECT,
        related_name='intent_matches',
        blank=True,
        null=True
    )
    match_kind = models.CharField(
        max_length=32,
        choices=ROAIntentMatchKind.choices,
        default=ROAIntentMatchKind.EXACT,
    )
    is_best_match = models.BooleanField(default=False)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("roa_intent", "roa"),
                condition=models.Q(roa__isnull=False, imported_authorization__isnull=True),
                name="netbox_rpki_roaintentmatch_roa_intent_roa_unique",
            ),
            models.UniqueConstraint(
                fields=("roa_intent", "imported_authorization"),
                condition=models.Q(roa__isnull=True, imported_authorization__isnull=False),
                name="netbox_rpki_roaintentmatch_roa_intent_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(roa__isnull=False, imported_authorization__isnull=True)
                    | models.Q(roa__isnull=True, imported_authorization__isnull=False)
                ),
                name="netbox_rpki_roaintentmatch_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaintentmatch", args=[self.pk])


class ROAReconciliationRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_reconciliation_runs'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='reconciliation_runs'
    )
    basis_derivation_run = models.ForeignKey(
        to='IntentDerivationRun',
        on_delete=models.PROTECT,
        related_name='reconciliation_runs'
    )
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='reconciliation_runs',
        blank=True,
        null=True
    )
    comparison_scope = models.CharField(
        max_length=32,
        choices=ReconciliationComparisonScope.choices,
        default=ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    published_roa_count = models.PositiveIntegerField(default=0)
    intent_count = models.PositiveIntegerField(default=0)
    result_summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roareconciliationrun", args=[self.pk])


class ROALintRun(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='lint_runs'
    )
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='lint_runs',
        blank=True,
        null=True
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    finding_count = models.PositiveIntegerField(default=0)
    info_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    critical_count = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roalintrun", args=[self.pk])


class ROAIntentResult(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='intent_results'
    )
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='reconciliation_results'
    )
    result_type = models.CharField(
        max_length=32,
        choices=ROAIntentResultType.choices,
        default=ROAIntentResultType.MATCH,
    )
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    best_roa = models.ForeignKey(
        to=Roa,
        on_delete=models.SET_NULL,
        related_name='intent_result_matches',
        blank=True,
        null=True
    )
    best_imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.SET_NULL,
        related_name='intent_result_matches',
        blank=True,
        null=True
    )
    match_count = models.PositiveIntegerField(default=0)
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("reconciliation_run", "roa_intent"),
                name="netbox_rpki_roaintentresult_run_intent_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaintentresult", args=[self.pk])


class PublishedROAResult(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='published_roa_results'
    )
    roa = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='published_reconciliation_results'
        ,
        blank=True,
        null=True
    )
    imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.PROTECT,
        related_name='published_reconciliation_results',
        blank=True,
        null=True
    )
    result_type = models.CharField(
        max_length=64,
        choices=PublishedROAResultType.choices,
        default=PublishedROAResultType.MATCHED,
    )
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    matched_intent_count = models.PositiveIntegerField(default=0)
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("reconciliation_run", "roa"),
                condition=models.Q(roa__isnull=False, imported_authorization__isnull=True),
                name="netbox_rpki_publishedroaresult_run_roa_unique",
            ),
            models.UniqueConstraint(
                fields=("reconciliation_run", "imported_authorization"),
                condition=models.Q(roa__isnull=True, imported_authorization__isnull=False),
                name="netbox_rpki_publishedresult_run_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(roa__isnull=False, imported_authorization__isnull=True)
                    | models.Q(roa__isnull=True, imported_authorization__isnull=False)
                ),
                name="netbox_rpki_publishedroaresult_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:publishedroaresult", args=[self.pk])


class ROALintFinding(NamedRpkiStandardModel):
    lint_run = models.ForeignKey(
        to='ROALintRun',
        on_delete=models.PROTECT,
        related_name='findings'
    )
    roa_intent_result = models.ForeignKey(
        to='ROAIntentResult',
        on_delete=models.PROTECT,
        related_name='lint_findings',
        blank=True,
        null=True
    )
    published_roa_result = models.ForeignKey(
        to='PublishedROAResult',
        on_delete=models.PROTECT,
        related_name='lint_findings',
        blank=True,
        null=True
    )
    change_plan_item = models.ForeignKey(
        to='ROAChangePlanItem',
        on_delete=models.PROTECT,
        related_name='lint_findings',
        blank=True,
        null=True
    )
    finding_code = models.CharField(max_length=64)
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roalintfinding", args=[self.pk])


class ROAChangePlan(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_change_plans'
    )
    source_reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='change_plans'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='roa_change_plans',
        blank=True,
        null=True,
    )
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='roa_change_plans',
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=16,
        choices=ROAChangePlanStatus.choices,
        default=ROAChangePlanStatus.DRAFT,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    apply_requested_by = models.CharField(max_length=150, blank=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created", "name")
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_roachangeplan_valid_maintenance_window',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roachangeplan", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )

    @property
    def has_governance_metadata(self) -> bool:
        return any(
            (
                self.ticket_reference,
                self.change_reference,
                self.maintenance_window_start,
                self.maintenance_window_end,
            )
        )

    def get_governance_metadata(self) -> dict[str, str]:
        metadata = {}
        if self.ticket_reference:
            metadata['ticket_reference'] = self.ticket_reference
        if self.change_reference:
            metadata['change_reference'] = self.change_reference
        if self.maintenance_window_start is not None:
            metadata['maintenance_window_start'] = self.maintenance_window_start.isoformat()
        if self.maintenance_window_end is not None:
            metadata['maintenance_window_end'] = self.maintenance_window_end.isoformat()
        return metadata

    @property
    def is_provider_backed(self) -> bool:
        return self.provider_account_id is not None and self.provider_snapshot_id is not None

    @property
    def supports_provider_write(self) -> bool:
        return self.is_provider_backed and self.provider_account.supports_roa_write

    @property
    def can_preview(self) -> bool:
        return self.supports_provider_write and self.status in {
            ROAChangePlanStatus.DRAFT,
            ROAChangePlanStatus.APPROVED,
            ROAChangePlanStatus.FAILED,
        }

    @property
    def can_approve(self) -> bool:
        return self.supports_provider_write and self.status == ROAChangePlanStatus.DRAFT

    @property
    def can_apply(self) -> bool:
        return self.supports_provider_write and self.status == ROAChangePlanStatus.APPROVED


class ApprovalRecord(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='approval_records'
    )
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='approval_records'
    )
    disposition = models.CharField(
        max_length=16,
        choices=ValidationDisposition.choices,
        default=ValidationDisposition.ACCEPTED,
    )
    recorded_by = models.CharField(max_length=150, blank=True)
    recorded_at = models.DateTimeField(blank=True, null=True)
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('-recorded_at', '-created', 'name')
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_approvalrecord_valid_maintenance_window',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:approvalrecord', args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )


class ProviderWriteExecution(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='provider_write_executions'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='write_executions'
    )
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='write_executions',
        blank=True,
        null=True,
    )
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='provider_write_executions'
    )
    execution_mode = models.CharField(
        max_length=16,
        choices=ProviderWriteExecutionMode.choices,
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    requested_by = models.CharField(max_length=150, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    item_count = models.PositiveIntegerField(default=0)
    request_payload_json = models.JSONField(default=dict, blank=True)
    response_payload_json = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    followup_sync_run = models.ForeignKey(
        to='ProviderSyncRun',
        on_delete=models.PROTECT,
        related_name='provider_write_executions',
        blank=True,
        null=True,
    )
    followup_provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='followup_write_executions',
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providerwriteexecution", args=[self.pk])


class ROAChangePlanItem(NamedRpkiStandardModel):
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='items'
    )
    action_type = models.CharField(
        max_length=16,
        choices=ROAChangePlanAction.choices,
    )
    # action_type remains the physical delta; plan_semantic captures the logical change class.
    plan_semantic = models.CharField(
        max_length=16,
        choices=ROAChangePlanItemSemantic.choices,
        blank=True,
        null=True,
    )
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True
    )
    roa = models.ForeignKey(
        to=Roa,
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True
    )
    imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True
    )
    provider_operation = models.CharField(
        max_length=32,
        choices=ProviderWriteOperation.choices,
        blank=True,
    )
    provider_payload_json = models.JSONField(default=dict, blank=True)
    before_state_json = models.JSONField(default=dict, blank=True)
    after_state_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roachangeplanitem", args=[self.pk])


class ROAValidationSimulationRun(NamedRpkiStandardModel):
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='simulation_runs'
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    result_count = models.PositiveIntegerField(default=0)
    predicted_valid_count = models.PositiveIntegerField(default=0)
    predicted_invalid_count = models.PositiveIntegerField(default=0)
    predicted_not_found_count = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roavalidationsimulationrun", args=[self.pk])


class ROAValidationSimulationOutcome(models.TextChoices):
    VALID = "valid", "Valid"
    INVALID = "invalid", "Invalid"
    NOT_FOUND = "not_found", "Not Found"


class ROAValidationSimulationResult(NamedRpkiStandardModel):
    simulation_run = models.ForeignKey(
        to='ROAValidationSimulationRun',
        on_delete=models.PROTECT,
        related_name='results'
    )
    change_plan_item = models.ForeignKey(
        to='ROAChangePlanItem',
        on_delete=models.PROTECT,
        related_name='simulation_results',
        blank=True,
        null=True
    )
    outcome_type = models.CharField(
        max_length=16,
        choices=ROAValidationSimulationOutcome.choices,
        default=ROAValidationSimulationOutcome.NOT_FOUND,
    )
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roavalidationsimulationresult", args=[self.pk])


def _register_plugin_action_urls():
    for value in tuple(globals().values()):
        if not isinstance(value, type):
            continue
        if not issubclass(value, NetBoxModel):
            continue
        if value.__module__ != __name__:
            continue
        meta = getattr(value, '_meta', None)
        if meta is None or meta.abstract:
            continue
        setattr(value, '_get_action_url', classmethod(_plugin_get_action_url))


_register_plugin_action_urls()

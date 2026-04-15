import hashlib
from ipaddress import ip_network
from datetime import timedelta

import ipam
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
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


class RoutingIntentTemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class RoutingIntentTemplateBindingState(models.TextChoices):
    CURRENT = "current", "Current"
    STALE = "stale", "Stale"
    PENDING = "pending", "Pending Regeneration"
    INVALID = "invalid", "Invalid"


class RoutingIntentExceptionType(models.TextChoices):
    TRAFFIC_ENGINEERING = "traffic_engineering", "Traffic Engineering"
    ANYCAST = "anycast", "Anycast"
    MITIGATION = "mitigation", "Mitigation"
    CUSTOMER_EDGE = "customer_edge", "Customer Edge"


class RoutingIntentExceptionEffectMode(models.TextChoices):
    BROADEN = "broaden", "Broaden"
    NARROW = "narrow", "Narrow"
    SUPPRESS = "suppress", "Suppress"
    TEMPORARY_REPLACEMENT = "temporary_replacement", "Temporary Replacement"


class RoutingIntentContextType(models.TextChoices):
    SERVICE = "service", "Service"
    PROVIDER_EDGE = "provider_edge", "Provider Edge"
    TRANSIT = "transit", "Transit"
    IX = "ix", "Internet Exchange"
    CUSTOMER = "customer", "Customer"
    BACKBONE = "backbone", "Backbone"
    OTHER = "other", "Other"


class RoutingIntentContextCriterionType(models.TextChoices):
    TENANT = "tenant", "Tenant"
    VRF = "vrf", "VRF"
    SITE = "site", "Site"
    REGION = "region", "Region"
    ROLE = "role", "Prefix Role"
    TAG = "tag", "Tag"
    CUSTOM_FIELD = "custom_field", "Custom Field"
    PROVIDER_ACCOUNT = "provider_account", "Provider Account"
    CIRCUIT = "circuit", "Circuit"
    CIRCUIT_PROVIDER = "circuit_provider", "Circuit Provider"
    EXCHANGE = "exchange", "Exchange"


class BulkIntentTargetMode(models.TextChoices):
    PROFILES = "profiles", "Profiles"
    BINDINGS = "bindings", "Bindings"
    MIXED = "mixed", "Mixed"


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


class IrrSourceFamily(models.TextChoices):
    IRRD_COMPATIBLE = "irrd_compatible", "IRRd-Compatible"
    RIPE_REST = "ripe_rest", "RIPE REST"


class IrrWriteSupportMode(models.TextChoices):
    UNSUPPORTED = "unsupported", "Unsupported"
    PREVIEW_ONLY = "preview_only", "Preview Only"
    APPLY_SUPPORTED = "apply_supported", "Apply Supported"


class IrrFetchMode(models.TextChoices):
    LIVE_QUERY = "live_query", "Live Query"
    SNAPSHOT_IMPORT = "snapshot_import", "Snapshot Import"


class IrrSnapshotStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    PARTIAL = "partial", "Partial"


class IrrSyncHealth(models.TextChoices):
    DISABLED = "disabled", "Disabled"
    NEVER_SYNCED = "never_synced", "Never Synced"
    IN_PROGRESS = "in_progress", "In Progress"
    FAILED = "failed", "Failed"
    STALE = "stale", "Stale"
    HEALTHY = "healthy", "Healthy"


class IrrMemberType(models.TextChoices):
    PREFIX = "prefix", "Prefix"
    PREFIX_RANGE = "prefix_range", "Prefix Range"
    ROUTE_SET = "route_set", "Route-Set"
    AS_SET = "as_set", "AS-Set"
    ASN = "asn", "ASN"
    SET_NAME = "set_name", "Set Name"
    UNKNOWN = "unknown", "Unknown"


class IrrCoordinationRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class IrrCoordinationFamily(models.TextChoices):
    ROUTE_OBJECT = "route_object", "Route Object"
    ROUTE_SET_MEMBERSHIP = "route_set_membership", "Route-Set Membership"
    AS_SET_MEMBERSHIP = "as_set_membership", "AS-Set Membership"
    AUT_NUM_CONTEXT = "aut_num_context", "Aut-Num Context"
    MAINTAINER_SUPPORTABILITY = "maintainer_supportability", "Maintainer Supportability"


class IrrCoordinationResultType(models.TextChoices):
    MATCH = "match", "Match"
    MISSING_IN_SOURCE = "missing_in_source", "Missing In Source"
    EXTRA_IN_SOURCE = "extra_in_source", "Extra In Source"
    SOURCE_CONFLICT = "source_conflict", "Source Conflict"
    UNSUPPORTED_WRITE = "unsupported_write", "Unsupported Write"
    AMBIGUOUS_LINKAGE = "ambiguous_linkage", "Ambiguous Linkage"
    STALE_SOURCE = "stale_source", "Stale Source"
    POLICY_CONTEXT_GAP = "policy_context_gap", "Policy Context Gap"


class IrrChangePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    READY = "ready", "Ready"
    APPROVED = "approved", "Approved"
    EXECUTING = "executing", "Executing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class IrrChangePlanAction(models.TextChoices):
    CREATE = "create", "Create"
    MODIFY = "modify", "Modify"
    REPLACE = "replace", "Replace"
    DELETE = "delete", "Delete"
    NOOP = "noop", "No-op"


class IrrWriteExecutionMode(models.TextChoices):
    PREVIEW = "preview", "Preview"
    APPLY = "apply", "Apply"


class IrrWriteExecutionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    PARTIAL = "partial", "Partial"


class TelemetrySourceType(models.TextChoices):
    IMPORTED_MRT = "imported_mrt", "Imported MRT Snapshot"


class TelemetrySyncHealth(models.TextChoices):
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


class LifecycleHealthEventKind(models.TextChoices):
    SYNC_STALE = "sync_stale", "Sync Stale"
    SYNC_FAILED = "sync_failed", "Sync Failed"
    ROA_EXPIRING = "roa_expiring", "ROA Expiring"
    CERTIFICATE_EXPIRING = "certificate_expiring", "Certificate Expiring"
    EXCEPTION_EXPIRING = "exception_expiring", "Exception Expiring"
    PUBLICATION_STALE = "publication_stale", "Publication Stale"
    PUBLICATION_EXCHANGE_FAILED = "publication_exchange_failed", "Publication Exchange Failed"
    PUBLICATION_ATTENTION = "publication_attention", "Publication Attention"
    PUBLICATION_DIFF = "publication_diff", "Publication Diff"


class LifecycleHealthEventSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class LifecycleHealthEventStatus(models.TextChoices):
    OPEN = "open", "Open"
    REPEATED = "repeated", "Repeated"
    RESOLVED = "resolved", "Resolved"


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
    AWAITING_2ND = "awaiting_2nd", "Awaiting Secondary Approval"
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


class ROALintSuppressionScope(models.TextChoices):
    INTENT = "intent", "Intent"
    PROFILE = "profile", "Profile"
    ORG = "org", "Organization"
    PREFIX = "prefix", "Prefix"


class ExternalManagementScope(models.TextChoices):
    ROA_PREFIX = "roa_prefix", "ROA Prefix"
    ROA_OBJECT = "roa_object", "ROA Object"
    ROA_IMPORTED = "roa_imported", "Imported ROA Object"
    ASPA_CUSTOMER = "aspa_customer", "ASPA Customer"
    ASPA_OBJECT = "aspa_object", "ASPA Object"
    ASPA_IMPORTED = "aspa_imported", "Imported ASPA Object"


class ProviderWriteOperation(models.TextChoices):
    ADD_ROUTE = "add_route", "Add Route"
    REMOVE_ROUTE = "remove_route", "Remove Route"
    ADD_PROVIDER_SET = "add_provider_set", "Add Provider Set"
    REMOVE_PROVIDER_SET = "remove_provider_set", "Remove Provider Set"


class ProviderWriteExecutionMode(models.TextChoices):
    PREVIEW = "preview", "Preview"
    APPLY = "apply", "Apply"


class RollbackBundleStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class ProviderAspaWriteMode(models.TextChoices):
    UNSUPPORTED = "unsupported", "Unsupported"
    KRILL_ASPA_DELTA = "krill_aspa_delta", "Krill ASPA Delta"


class ASPAChangePlanStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    AWAITING_2ND = "awaiting_2nd", "Awaiting Secondary Approval"
    APPROVED = "approved", "Approved"
    APPLYING = "applying", "Applying"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class ASPAChangePlanAction(models.TextChoices):
    CREATE = "create", "Create"
    WITHDRAW = "withdraw", "Withdraw"


class ASPAChangePlanItemSemantic(models.TextChoices):
    CREATE = "create", "Create"
    WITHDRAW = "withdraw", "Withdraw"
    REPLACE = "replace", "Replace"
    ADD_PROVIDER = "add_provider", "Add Provider"
    REMOVE_PROVIDER = "remove_provider", "Remove Provider"
    RESHAPE = "reshape", "Reshape"


class PublicationState(models.TextChoices):
    DRAFT = "draft", "Draft"
    AWAITING_SECONDARY_APPROVAL = "awaiting_secondary_approval", "Awaiting Secondary Approval"
    APPROVED_PENDING_APPLY = "approved_pending_apply", "Approved — Pending Apply"
    APPLY_IN_PROGRESS = "apply_in_progress", "Apply In Progress"
    APPLY_FAILED = "apply_failed", "Apply Failed"
    APPLIED_AWAITING_VERIFICATION = "applied_awaiting_verification", "Applied — Awaiting Verification"
    VERIFIED = "verified", "Verified"
    VERIFIED_WITH_DRIFT = "verified_with_drift", "Verified With Drift"
    VERIFICATION_FAILED = "verification_failed", "Verification Failed"
    ROLLED_BACK = "rolled_back", "Rolled Back"
    SUPERSEDED = "superseded", "Superseded"


# --- Section N: Downstream/Delegated Authorization choices ---

class DelegatedAuthorizationEntityKind(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    PARTNER = "partner", "Partner"
    DELEGATED = "delegated", "Delegated Entity"
    DOWNSTREAM = "downstream", "Downstream Operator"
    OTHER = "other", "Other"


class ManagedAuthorizationRelationshipRole(models.TextChoices):
    MANAGING_PARTY = "managing_party", "Managing Party"
    DELEGATING_PARTY = "delegating_party", "Delegating Party"


class ManagedAuthorizationRelationshipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PENDING = "pending", "Pending"
    SUSPENDED = "suspended", "Suspended"
    TERMINATED = "terminated", "Terminated"


class DelegatedPublicationWorkflowStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ARCHIVED = "archived", "Archived"


class AuthoredAsSetMemberType(models.TextChoices):
    ASN = "asn", "ASN"
    AS_SET = "as_set", "AS-Set"


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


LEGACY_DIRECT_NETBOX_MODEL_EXCEPTIONS = ()


class Organization(NamedRpkiStandardModel):
    org_id = models.CharField(max_length=200, editable=True)
    ext_url = models.CharField(max_length=200, editable=True, blank=True)
    parent_rir = models.ForeignKey(
        to=RIR,
        on_delete=models.PROTECT,
        related_name='rpki_certs',
        null=True,
        blank=True
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
#        return f'{self.name}, {self.org_id}'
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:organization", args=[self.pk])


class Certificate(NamedRpkiStandardModel):
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

    class Meta:
        ordering = ("name",)

    def __str__(self):
  #      return f'{self.name}, {self.issuer}'
        return self.name
    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificate", args=[self.pk])


class RoaObject(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_objects',
        blank=True,
        null=True
    )
    signed_object = models.OneToOneField(
        to='SignedObject',
        on_delete=models.PROTECT,
        related_name='roa_extension',
        blank=True,
        null=True
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='roa_objects',
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

    def clean(self):
        super().clean()
        if self.signed_object_id is None:
            return

        errors = []
        if self.signed_object.object_type != SignedObjectType.ROA:
            errors.append('Signed object must use the ROA object type.')
        if (
            self.organization_id is not None
            and self.signed_object.organization_id is not None
            and self.organization_id != self.signed_object.organization_id
        ):
            errors.append('Signed object must belong to the same organization as the ROA object.')
        if (
            self.valid_from is not None
            and self.signed_object.valid_from is not None
            and self.valid_from != self.signed_object.valid_from
        ):
            errors.append('Signed object valid-from date must match the ROA valid-from date.')
        if (
            self.valid_to is not None
            and self.signed_object.valid_to is not None
            and self.valid_to != self.signed_object.valid_to
        ):
            errors.append('Signed object valid-to date must match the ROA valid-to date.')

        if errors:
            raise ValidationError({'signed_object': errors})

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaobject", args=[self.pk])

    @property
    def signed_by(self):
        return getattr(self.signed_object, 'resource_certificate', None)

    @property
    def RoaToPrefixTable(self):
        return self.prefix_authorizations


class RoaObjectPrefix(RpkiStandardModel):
    roa_object = models.ForeignKey(
        to=RoaObject,
        on_delete=models.PROTECT,
        related_name='prefix_authorizations'
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='roa_object_prefixes',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    max_length = models.PositiveSmallIntegerField()
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ("roa_object", "prefix_cidr_text")

    def __str__(self):
        return self.prefix_cidr_text or str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaobjectprefix", args=[self.pk])

    @property
    def roa_name(self):
        return self.roa_object


Roa = RoaObject
RoaPrefix = RoaObjectPrefix


class CertificatePrefix(RpkiStandardModel):
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='PrefixToCertificateTable'
    )
    certificate_name = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificateToPrefixTable'
    )

    class Meta:
        ordering = ("prefix",)

    def __str__(self):
        return str(self.prefix)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:certificateprefix", args=[self.pk])


class CertificateAsn(RpkiStandardModel):
    asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='ASNtoCertificateTable'
    )
    certificate_name2 = models.ForeignKey(
        to=Certificate,
        on_delete=models.PROTECT,
        related_name='CertificatetoASNTable'
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

    def clean(self):
        super().clean()

        errors: dict[str, list[str]] = {}
        if (
            self.organization_id is not None
            and self.resource_certificate_id is not None
            and self.resource_certificate.rpki_org_id is not None
            and self.organization_id != self.resource_certificate.rpki_org_id
        ):
            errors.setdefault('resource_certificate', []).append(
                'Resource certificate must belong to the same organization as the end-entity certificate.'
            )
        if (
            self.organization_id is not None
            and self.publication_point_id is not None
            and self.publication_point.organization_id is not None
            and self.organization_id != self.publication_point.organization_id
        ):
            errors.setdefault('publication_point', []).append(
                'Publication point must belong to the same organization as the end-entity certificate.'
            )

        if errors:
            raise ValidationError(errors)

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

    def clean(self):
        super().clean()

        errors: dict[str, list[str]] = {}
        if (
            self.organization_id is not None
            and self.resource_certificate_id is not None
            and self.resource_certificate.rpki_org_id is not None
            and self.organization_id != self.resource_certificate.rpki_org_id
        ):
            errors.setdefault('resource_certificate', []).append(
                'Resource certificate must belong to the same organization as the signed object.'
            )
        if (
            self.organization_id is not None
            and self.ee_certificate_id is not None
            and self.ee_certificate.organization_id is not None
            and self.organization_id != self.ee_certificate.organization_id
        ):
            errors.setdefault('ee_certificate', []).append(
                'EE certificate must belong to the same organization as the signed object.'
            )
        if (
            self.organization_id is not None
            and self.publication_point_id is not None
            and self.publication_point.organization_id is not None
            and self.organization_id != self.publication_point.organization_id
        ):
            errors.setdefault('publication_point', []).append(
                'Publication point must belong to the same organization as the signed object.'
            )
        if (
            self.ee_certificate_id is not None
            and self.resource_certificate_id is not None
            and self.ee_certificate.resource_certificate_id is not None
            and self.resource_certificate_id != self.ee_certificate.resource_certificate_id
        ):
            errors.setdefault('ee_certificate', []).append(
                'EE certificate must use the same resource certificate as the signed object.'
            )
        if (
            self.ee_certificate_id is not None
            and self.publication_point_id is not None
            and self.ee_certificate.publication_point_id is not None
            and self.publication_point_id != self.ee_certificate.publication_point_id
        ):
            errors.setdefault('ee_certificate', []).append(
                'EE certificate must use the same publication point as the signed object.'
            )
        if (
            self.ee_certificate_id is not None
            and self.valid_from is not None
            and self.ee_certificate.valid_from is not None
            and self.valid_from != self.ee_certificate.valid_from
        ):
            errors.setdefault('ee_certificate', []).append(
                'EE certificate valid-from date must match the signed object valid-from date.'
            )
        if (
            self.ee_certificate_id is not None
            and self.valid_to is not None
            and self.ee_certificate.valid_to is not None
            and self.valid_to != self.ee_certificate.valid_to
        ):
            errors.setdefault('ee_certificate', []).append(
                'EE certificate valid-to date must match the signed object valid-to date.'
            )

        if errors:
            raise ValidationError(errors)

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
    signed_object = models.OneToOneField(
        to=SignedObject,
        on_delete=models.PROTECT,
        related_name='crl_extension',
        blank=True,
        null=True
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
    ee_certificate = models.OneToOneField(
        to=EndEntityCertificate,
        on_delete=models.PROTECT,
        related_name='router_certificate_extension',
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

    def clean(self):
        super().clean()
        if self.ee_certificate_id is None:
            return

        errors = []
        if (
            self.organization_id is not None
            and self.ee_certificate.organization_id is not None
            and self.organization_id != self.ee_certificate.organization_id
        ):
            errors.append('EE certificate must belong to the same organization as the router certificate.')
        if (
            self.resource_certificate_id is not None
            and self.ee_certificate.resource_certificate_id is not None
            and self.resource_certificate_id != self.ee_certificate.resource_certificate_id
        ):
            errors.append('EE certificate must use the same resource certificate as the router certificate.')
        if (
            self.publication_point_id is not None
            and self.ee_certificate.publication_point_id is not None
            and self.publication_point_id != self.ee_certificate.publication_point_id
        ):
            errors.append('EE certificate must use the same publication point as the router certificate.')

        if errors:
            raise ValidationError({'ee_certificate': errors})

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
    summary_json = models.JSONField(default=dict, blank=True)

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
    summary_json = models.JSONField(default=dict, blank=True)

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
    imported_signed_object = models.ForeignKey(
        to='ImportedSignedObject',
        on_delete=models.PROTECT,
        related_name='validation_results',
        blank=True,
        null=True,
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
    match_status = models.CharField(max_length=32, blank=True)
    external_object_uri = models.CharField(max_length=500, blank=True)
    external_content_hash = models.CharField(max_length=255, blank=True)
    external_object_key = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    details_json = models.JSONField(default=dict, blank=True)

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
    roa_object = models.ForeignKey(
        to=RoaObject,
        on_delete=models.PROTECT,
        related_name='validated_payloads',
        blank=True,
        null=True
    )
    object_validation_result = models.ForeignKey(
        to=ObjectValidationResult,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads',
        blank=True,
        null=True
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads',
        blank=True,
        null=True,
    )
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='validated_roa_payloads',
        blank=True,
        null=True
    )
    max_length = models.IntegerField(blank=True, null=True)
    observed_prefix = models.CharField(max_length=64, blank=True)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.object_validation_result_id is None:
            return

        errors = []
        if self.object_validation_result.validation_run_id != self.validation_run_id:
            errors.append('Object validation result must belong to the same validation run as the validated ROA payload.')
        if (
            self.roa_object_id is not None
            and self.roa_object.signed_object_id is not None
            and self.object_validation_result.signed_object_id is not None
            and self.roa_object.signed_object_id != self.object_validation_result.signed_object_id
        ):
            errors.append('Object validation result must reference the same signed object as the validated ROA payload.')

        if errors:
            raise ValidationError({'object_validation_result': errors})

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:validatedroapayload", args=[self.pk])

    @property
    def roa(self):
        return self.roa_object


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
    object_validation_result = models.ForeignKey(
        to=ObjectValidationResult,
        on_delete=models.PROTECT,
        related_name='validated_aspa_payloads',
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
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.object_validation_result_id is None:
            return

        errors = []
        if self.object_validation_result.validation_run_id != self.validation_run_id:
            errors.append('Object validation result must belong to the same validation run as the validated ASPA payload.')
        if (
            self.aspa_id is not None
            and self.aspa.signed_object_id is not None
            and self.object_validation_result.signed_object_id is not None
            and self.aspa.signed_object_id != self.object_validation_result.signed_object_id
        ):
            errors.append('Object validation result must reference the same signed object as the validated ASPA payload.')

        if errors:
            raise ValidationError({'object_validation_result': errors})

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
    context_groups = models.ManyToManyField(
        to='RoutingIntentContextGroup',
        related_name='intent_profiles',
        blank=True,
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


class RoutingIntentContextGroup(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='routing_intent_context_groups'
    )
    context_type = models.CharField(
        max_length=32,
        choices=RoutingIntentContextType.choices,
        default=RoutingIntentContextType.SERVICE,
    )
    description = models.TextField(blank=True)
    priority = models.PositiveIntegerField(default=100)
    enabled = models.BooleanField(default=True)
    summary_json = models.JSONField(default=dict, blank=True)
    inherits_from = models.ForeignKey(
        to='self',
        on_delete=models.SET_NULL,
        related_name='inheriting_groups',
        blank=True,
        null=True,
        help_text=(
            'Parent context group whose enabled criteria are prepended before evaluating '
            'this group\'s own criteria.  Enables layered policy reuse without duplicating criteria.'
        ),
    )

    class Meta:
        ordering = ("organization", "priority", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="netbox_rpki_routingintentcontextgroup_org_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routingintentcontextgroup", args=[self.pk])

    def clean(self):
        super().clean()
        if self.inherits_from_id is not None and self.inherits_from_id == self.pk:
            raise ValidationError({'inherits_from': 'A context group cannot inherit from itself.'})
        if (
            self.inherits_from_id is not None
            and self.pk is not None
            and self.inherits_from.organization_id != self.organization_id
        ):
            raise ValidationError({
                'inherits_from': 'Inherited context group must belong to the same organization.'
            })


class RoutingIntentContextCriterion(NamedRpkiStandardModel):
    context_group = models.ForeignKey(
        to='RoutingIntentContextGroup',
        on_delete=models.PROTECT,
        related_name='criteria'
    )
    criterion_type = models.CharField(
        max_length=32,
        choices=RoutingIntentContextCriterionType.choices,
    )
    match_tenant = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_vrf = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_region = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_circuit = models.ForeignKey(
        to='circuits.Circuit',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_provider = models.ForeignKey(
        to='circuits.Provider',
        on_delete=models.PROTECT,
        related_name='routing_intent_context_criteria',
        blank=True,
        null=True
    )
    match_value = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    weight = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ("context_group", "weight", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("context_group", "name"),
                name="netbox_rpki_routingintentcontextcriterion_group_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routingintentcontextcriterion", args=[self.pk])

    def clean(self):
        super().clean()

        required_field_by_type = {
            RoutingIntentContextCriterionType.TENANT: 'match_tenant',
            RoutingIntentContextCriterionType.VRF: 'match_vrf',
            RoutingIntentContextCriterionType.SITE: 'match_site',
            RoutingIntentContextCriterionType.REGION: 'match_region',
            RoutingIntentContextCriterionType.ROLE: 'match_value',
            RoutingIntentContextCriterionType.TAG: 'match_value',
            RoutingIntentContextCriterionType.CUSTOM_FIELD: 'match_value',
            RoutingIntentContextCriterionType.PROVIDER_ACCOUNT: 'match_provider_account',
            RoutingIntentContextCriterionType.CIRCUIT: 'match_circuit',
            RoutingIntentContextCriterionType.CIRCUIT_PROVIDER: 'match_provider',
            RoutingIntentContextCriterionType.EXCHANGE: 'match_value',
        }
        if self.criterion_type not in required_field_by_type:
            if not self.criterion_type:
                raise ValidationError({'criterion_type': ['This field is required.']})
            raise ValidationError({'criterion_type': ['Select a valid choice.']})
        required_field = required_field_by_type[self.criterion_type]
        populated_fields = {
            'match_tenant': self.match_tenant_id,
            'match_vrf': self.match_vrf_id,
            'match_site': self.match_site_id,
            'match_region': self.match_region_id,
            'match_provider_account': self.match_provider_account_id,
            'match_circuit': self.match_circuit_id,
            'match_provider': self.match_provider_id,
            'match_value': self.match_value,
        }

        if populated_fields[required_field] in (None, ''):
            raise ValidationError({required_field: [f'{required_field} is required for criterion type {self.criterion_type}.']})

        invalid_fields = [
            field_name
            for field_name, value in populated_fields.items()
            if field_name != required_field and value not in (None, '')
        ]
        if invalid_fields:
            raise ValidationError({
                required_field: [
                    'Criterion type {criterion_type} must not set unrelated match fields: {fields}.'.format(
                        criterion_type=self.criterion_type,
                        fields=', '.join(sorted(invalid_fields)),
                    )
                ]
            })

        if (
            self.match_provider_account_id is not None
            and self.context_group_id is not None
            and self.match_provider_account.organization_id != self.context_group.organization_id
        ):
            raise ValidationError({
                'match_provider_account': ['Provider account organization must match the context group organization.']
            })


class RoutingIntentPolicyBundle(NamedRpkiStandardModel):
    """
    A reusable, named collection of routing-intent policy context groups.

    Policy bundles let operators compose a set of context groups into a named
    unit that can be referenced by multiple profiles or template bindings.
    This provides explicit policy-reuse semantics distinct from priority ordering
    or ad-hoc per-profile group lists.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='routing_intent_policy_bundles',
    )
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    context_groups = models.ManyToManyField(
        to='RoutingIntentContextGroup',
        related_name='policy_bundles',
        blank=True,
        help_text='Context groups included in this policy bundle, evaluated in priority order.',
    )

    class Meta:
        ordering = ("organization", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="nb_rpki_routingintentpolicybundle_org_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:routingintentpolicybundle", args=[self.pk])


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


class RoutingIntentTemplate(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='routing_intent_templates'
    )
    status = models.CharField(
        max_length=32,
        choices=RoutingIntentTemplateStatus.choices,
        default=RoutingIntentTemplateStatus.DRAFT,
    )
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    template_version = models.PositiveIntegerField(default=1)
    template_fingerprint = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="netbox_rpki_routingintenttemplate_org_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.template_version < 1:
            raise ValidationError({'template_version': ['Template version must be at least 1.']})


class RoutingIntentTemplateRule(NamedRpkiStandardModel):
    template = models.ForeignKey(
        to='RoutingIntentTemplate',
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
        related_name='routing_intent_template_rules',
        blank=True,
        null=True
    )
    match_vrf = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='routing_intent_template_rules',
        blank=True,
        null=True
    )
    match_site = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='routing_intent_template_rules',
        blank=True,
        null=True
    )
    match_region = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='routing_intent_template_rules',
        blank=True,
        null=True
    )
    match_role = models.CharField(max_length=100, blank=True)
    match_tag = models.CharField(max_length=100, blank=True)
    match_custom_field = models.CharField(max_length=255, blank=True)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='routing_intent_template_rules',
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
        ordering = ("template", "weight", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("template", "name"),
                name="netbox_rpki_routingintenttemplaterule_template_name_unique",
            ),
        )

    def __str__(self):
        return self.name


class RoutingIntentTemplateBinding(NamedRpkiStandardModel):
    template = models.ForeignKey(
        to='RoutingIntentTemplate',
        on_delete=models.PROTECT,
        related_name='bindings'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='template_bindings'
    )
    enabled = models.BooleanField(default=True)
    binding_priority = models.PositiveIntegerField(default=100)
    binding_label = models.CharField(max_length=200, blank=True)
    origin_asn_override = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='routing_intent_template_bindings',
        blank=True,
        null=True
    )
    max_length_mode = models.CharField(
        max_length=32,
        choices=RoutingIntentRuleMaxLengthMode.choices,
        default=RoutingIntentRuleMaxLengthMode.INHERIT,
    )
    max_length_value = models.PositiveSmallIntegerField(blank=True, null=True)
    prefix_selector_query = models.TextField(blank=True)
    asn_selector_query = models.TextField(blank=True)
    context_groups = models.ManyToManyField(
        to='RoutingIntentContextGroup',
        related_name='template_bindings',
        blank=True,
    )
    state = models.CharField(
        max_length=32,
        choices=RoutingIntentTemplateBindingState.choices,
        default=RoutingIntentTemplateBindingState.PENDING,
    )
    last_compiled_fingerprint = models.CharField(max_length=128, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("intent_profile", "binding_priority", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("intent_profile", "name"),
                name="netbox_rpki_routingintenttemplatebinding_profile_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        template_org_id = getattr(getattr(self, 'template', None), 'organization_id', None)
        profile_org_id = getattr(getattr(self, 'intent_profile', None), 'organization_id', None)
        if template_org_id is not None and profile_org_id is not None and template_org_id != profile_org_id:
            raise ValidationError({'template': ['Template organization must match the bound routing intent profile organization.']})


class RoutingIntentException(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    template_binding = models.ForeignKey(
        to='RoutingIntentTemplateBinding',
        on_delete=models.PROTECT,
        related_name='exceptions',
        blank=True,
        null=True
    )
    exception_type = models.CharField(
        max_length=32,
        choices=RoutingIntentExceptionType.choices,
        default=RoutingIntentExceptionType.TRAFFIC_ENGINEERING,
    )
    effect_mode = models.CharField(
        max_length=32,
        choices=RoutingIntentExceptionEffectMode.choices,
        default=RoutingIntentExceptionEffectMode.SUPPRESS,
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    max_length = models.PositiveSmallIntegerField(blank=True, null=True)
    tenant_scope = models.ForeignKey(
        to='tenancy.Tenant',
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    vrf_scope = models.ForeignKey(
        to='ipam.VRF',
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    site_scope = models.ForeignKey(
        to='dcim.Site',
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    region_scope = models.ForeignKey(
        to='dcim.Region',
        on_delete=models.PROTECT,
        related_name='routing_intent_exceptions',
        blank=True,
        null=True
    )
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    reason = models.TextField(blank=True)
    approved_by = models.CharField(max_length=200, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(intent_profile__isnull=False) | models.Q(template_binding__isnull=False),
                name="netbox_rpki_routingintentexception_requires_scope_target",
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.intent_profile_id is None and self.template_binding_id is None:
            raise ValidationError(
                {'intent_profile': ['Either an intent profile or a template binding is required for an exception.']}
            )
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({'ends_at': ['End time must be on or after the start time.']})
        if self.intent_profile_id and self.intent_profile.organization_id != self.organization_id:
            raise ValidationError({'intent_profile': ['Intent profile organization must match the exception organization.']})
        binding = getattr(self, 'template_binding', None)
        if binding is not None:
            binding_profile = getattr(binding, 'intent_profile', None)
            binding_profile_id = getattr(binding, 'intent_profile_id', None)
            if binding_profile is not None and binding_profile.organization_id != self.organization_id:
                raise ValidationError({'template_binding': ['Template binding organization must match the exception organization.']})
            if self.intent_profile_id and binding_profile_id is not None and binding_profile_id != self.intent_profile_id:
                raise ValidationError({'template_binding': ['Template binding must belong to the selected intent profile.']})


class ExternalManagementException(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
    )
    scope_type = models.CharField(
        max_length=32,
        choices=ExternalManagementScope.choices,
        default=ExternalManagementScope.ROA_PREFIX,
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    prefix_cidr_text = models.CharField(max_length=64, blank=True)
    origin_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    origin_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    max_length = models.PositiveSmallIntegerField(blank=True, null=True)
    roa_object = models.ForeignKey(
        to='RoaObject',
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    imported_authorization = models.ForeignKey(
        to='ImportedRoaAuthorization',
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    customer_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='external_management_customer_exceptions',
        blank=True,
        null=True,
    )
    customer_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    provider_asn = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='external_management_provider_exceptions',
        blank=True,
        null=True,
    )
    provider_asn_value = models.PositiveBigIntegerField(blank=True, null=True)
    aspa = models.ForeignKey(
        to='ASPA',
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    imported_aspa = models.ForeignKey(
        to='ImportedAspa',
        on_delete=models.PROTECT,
        related_name='external_management_exceptions',
        blank=True,
        null=True,
    )
    owner = models.CharField(max_length=150)
    reason = models.TextField()
    starts_at = models.DateTimeField(blank=True, null=True)
    review_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=200, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    enabled = models.BooleanField(default=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('organization', 'scope_type', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:externalmanagementexception", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}

        if self.prefix_id and not self.prefix_cidr_text:
            self.prefix_cidr_text = str(self.prefix.prefix)
        if self.origin_asn_id and self.origin_asn_value is None:
            self.origin_asn_value = self.origin_asn.asn
        if self.customer_asn_id and self.customer_asn_value is None:
            self.customer_asn_value = self.customer_asn.asn
        if self.provider_asn_id and self.provider_asn_value is None:
            self.provider_asn_value = self.provider_asn.asn

        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            errors['ends_at'] = 'End time must be on or after the start time.'
        if self.review_at and self.starts_at and self.review_at < self.starts_at:
            errors['review_at'] = 'Review date must be on or after the start time.'
        if self.approved_at and not self.approved_by:
            errors['approved_by'] = 'Approved-by is required when approved-at is set.'

        if self.prefix_id and self.prefix_cidr_text and self.prefix_cidr_text != str(self.prefix.prefix):
            errors['prefix_cidr_text'] = 'Prefix CIDR must match the selected prefix.'
        if self.origin_asn_id and self.origin_asn_value is not None and self.origin_asn_value != self.origin_asn.asn:
            errors['origin_asn_value'] = 'Origin ASN value must match the selected origin ASN.'
        if self.customer_asn_id and self.customer_asn_value is not None and self.customer_asn_value != self.customer_asn.asn:
            errors['customer_asn_value'] = 'Customer ASN value must match the selected customer ASN.'
        if self.provider_asn_id and self.provider_asn_value is not None and self.provider_asn_value != self.provider_asn.asn:
            errors['provider_asn_value'] = 'Provider ASN value must match the selected provider ASN.'

        scope_fields = {
            ExternalManagementScope.ROA_PREFIX: (
                bool(self.prefix_id or self.prefix_cidr_text),
                ('roa_object', 'imported_authorization', 'customer_asn', 'customer_asn_value', 'provider_asn', 'provider_asn_value', 'aspa', 'imported_aspa'),
            ),
            ExternalManagementScope.ROA_OBJECT: (
                self.roa_object_id is not None,
                ('prefix', 'prefix_cidr_text', 'origin_asn', 'origin_asn_value', 'max_length', 'imported_authorization', 'customer_asn', 'customer_asn_value', 'provider_asn', 'provider_asn_value', 'aspa', 'imported_aspa'),
            ),
            ExternalManagementScope.ROA_IMPORTED: (
                self.imported_authorization_id is not None,
                ('prefix', 'prefix_cidr_text', 'origin_asn', 'origin_asn_value', 'max_length', 'roa_object', 'customer_asn', 'customer_asn_value', 'provider_asn', 'provider_asn_value', 'aspa', 'imported_aspa'),
            ),
            ExternalManagementScope.ASPA_CUSTOMER: (
                bool(self.customer_asn_id or self.customer_asn_value is not None),
                ('prefix', 'prefix_cidr_text', 'origin_asn', 'origin_asn_value', 'max_length', 'roa_object', 'imported_authorization', 'aspa', 'imported_aspa'),
            ),
            ExternalManagementScope.ASPA_OBJECT: (
                self.aspa_id is not None,
                ('prefix', 'prefix_cidr_text', 'origin_asn', 'origin_asn_value', 'max_length', 'roa_object', 'imported_authorization', 'customer_asn', 'customer_asn_value', 'provider_asn', 'provider_asn_value', 'imported_aspa'),
            ),
            ExternalManagementScope.ASPA_IMPORTED: (
                self.imported_aspa_id is not None,
                ('prefix', 'prefix_cidr_text', 'origin_asn', 'origin_asn_value', 'max_length', 'roa_object', 'imported_authorization', 'customer_asn', 'customer_asn_value', 'provider_asn', 'provider_asn_value', 'aspa'),
            ),
        }

        scope_is_valid, forbidden_fields = scope_fields[self.scope_type]
        if not scope_is_valid:
            errors['scope_type'] = 'The selected scope type requires a matching target.'

        for field_name in forbidden_fields:
            value = getattr(self, field_name)
            if value not in (None, ''):
                errors[field_name] = f'Must be empty for {self.get_scope_type_display().lower()} exceptions.'

        if self.scope_type == ExternalManagementScope.ROA_PREFIX and not (self.prefix_id or self.prefix_cidr_text):
            errors['prefix_cidr_text'] = 'A prefix-scoped exception requires a prefix or prefix CIDR text.'

        if self.scope_type == ExternalManagementScope.ROA_OBJECT and self.roa_object_id is not None:
            organization_id = self.roa_object.organization_id
            if organization_id is not None and organization_id != self.organization_id:
                errors['organization'] = 'Organization must match the selected ROA.'
        if self.scope_type == ExternalManagementScope.ROA_IMPORTED and self.imported_authorization_id is not None:
            if self.imported_authorization.organization_id != self.organization_id:
                errors['organization'] = 'Organization must match the selected imported authorization.'
        if self.scope_type == ExternalManagementScope.ASPA_OBJECT and self.aspa_id is not None:
            if self.aspa.organization_id != self.organization_id:
                errors['organization'] = 'Organization must match the selected ASPA.'
        if self.scope_type == ExternalManagementScope.ASPA_IMPORTED and self.imported_aspa_id is not None:
            if self.imported_aspa.organization_id != self.organization_id:
                errors['organization'] = 'Organization must match the selected imported ASPA.'

        if errors:
            raise ValidationError(errors)

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        if not self.enabled:
            return False
        if self.starts_at is not None and self.starts_at > now:
            return False
        if self.ends_at is not None and self.ends_at <= now:
            return False
        return True

    @property
    def roa(self):
        return self.roa_object

    @property
    def is_expired(self) -> bool:
        return self.ends_at is not None and self.ends_at <= timezone.now()

    @property
    def is_review_due(self) -> bool:
        return self.review_at is not None and self.review_at <= timezone.now()


class BulkIntentRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='bulk_intent_runs'
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
    target_mode = models.CharField(
        max_length=32,
        choices=BulkIntentTargetMode.choices,
        default=BulkIntentTargetMode.BINDINGS,
    )
    baseline_fingerprint = models.CharField(max_length=128, blank=True)
    resulting_fingerprint = models.CharField(max_length=128, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    summary_json = models.JSONField(default=dict, blank=True)

    # Governance metadata
    requires_secondary_approval = models.BooleanField(default=False)
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    secondary_approved_at = models.DateTimeField(blank=True, null=True)
    secondary_approved_by = models.CharField(max_length=150, blank=True)
    requested_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("-started_at", "name")
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_bulkintentrun_valid_maintenance_window',
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )
        if self.pk:
            try:
                original = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                original = None
            if (
                original is not None
                and original.status != ValidationRunStatus.PENDING
                and original.requires_secondary_approval != self.requires_secondary_approval
            ):
                raise ValidationError({
                    'requires_secondary_approval': (
                        'Cannot change dual-approval requirement after the run has left PENDING status.'
                    )
                })

    @property
    def has_governance_metadata(self) -> bool:
        return any(
            (
                self.ticket_reference,
                self.change_reference,
                self.maintenance_window_start,
                self.approved_at,
                self.requested_by,
            )
        )


class BulkIntentRunScopeResult(NamedRpkiStandardModel):
    bulk_run = models.ForeignKey(
        to='BulkIntentRun',
        on_delete=models.PROTECT,
        related_name='scope_results'
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='bulk_run_scope_results',
        blank=True,
        null=True
    )
    template_binding = models.ForeignKey(
        to='RoutingIntentTemplateBinding',
        on_delete=models.PROTECT,
        related_name='bulk_run_scope_results',
        blank=True,
        null=True
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    scope_kind = models.CharField(max_length=32, blank=True)
    scope_key = models.CharField(max_length=200, blank=True)
    derivation_run = models.ForeignKey(
        to='IntentDerivationRun',
        on_delete=models.PROTECT,
        related_name='bulk_scope_results',
        blank=True,
        null=True
    )
    reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='bulk_scope_results',
        blank=True,
        null=True
    )
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='bulk_scope_results',
        blank=True,
        null=True
    )
    prefix_count_scanned = models.PositiveIntegerField(default=0)
    intent_count_emitted = models.PositiveIntegerField(default=0)
    plan_item_count = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=("bulk_run", "scope_key"),
                name="netbox_rpki_bulkintentrunscoperesult_scope_key_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(intent_profile__isnull=False) | models.Q(template_binding__isnull=False),
                name="netbox_rpki_bulkintentrunscoperesult_requires_target",
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.intent_profile_id is None and self.template_binding_id is None:
            raise ValidationError(
                {'intent_profile': ['Either an intent profile or a template binding is required for a bulk scope result.']}
            )
        if self.template_binding_id and self.intent_profile_id:
            if self.template_binding.intent_profile_id != self.intent_profile_id:
                raise ValidationError({'template_binding': ['Template binding must belong to the selected intent profile.']})
        if self.intent_profile_id and self.intent_profile.organization_id != self.bulk_run.organization_id:
            raise ValidationError({'intent_profile': ['Intent profile organization must match the bulk run organization.']})
        if self.template_binding_id and self.template_binding.intent_profile.organization_id != self.bulk_run.organization_id:
            raise ValidationError({'template_binding': ['Template binding organization must match the bulk run organization.']})


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
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='roa_intents',
        blank=True,
        null=True,
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
    summary_json = models.JSONField(default=dict, blank=True)

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

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this ROA intent.'

        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must belong to the same organization as this ROA intent.'
            )

        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must reference the same delegated entity as this ROA intent.'
            )

        if errors:
            raise ValidationError(errors)

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
        delegated_entity_id: int | None = None,
        managed_relationship_id: int | None = None,
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
                delegated_entity_id if delegated_entity_id is not None else "",
                managed_relationship_id if managed_relationship_id is not None else "",
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
    def aspa_write_mode(self) -> str:
        if self.provider_type == ProviderType.KRILL:
            return ProviderAspaWriteMode.KRILL_ASPA_DELTA
        return ProviderAspaWriteMode.UNSUPPORTED

    @property
    def supports_aspa_write(self) -> bool:
        return self.aspa_write_mode != ProviderAspaWriteMode.UNSUPPORTED

    @property
    def aspa_write_capability(self) -> dict:
        supported_actions = []
        if self.supports_aspa_write:
            supported_actions = [ASPAChangePlanAction.CREATE, ASPAChangePlanAction.WITHDRAW]
        return {
            'supports_aspa_write': self.supports_aspa_write,
            'aspa_write_mode': self.aspa_write_mode,
            'supported_aspa_plan_actions': supported_actions,
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

    # --- Explicit capability matrix (H.6) ---

    @property
    def supports_roa_read(self) -> bool:
        return self.provider_type in (ProviderType.KRILL, ProviderType.ARIN)

    @property
    def supports_aspa_read(self) -> bool:
        return self.provider_type == ProviderType.KRILL

    @property
    def supports_certificate_inventory(self) -> bool:
        return self.provider_type == ProviderType.KRILL

    @property
    def supports_repository_metadata(self) -> bool:
        return self.provider_type == ProviderType.KRILL

    @property
    def supports_bulk_operations(self) -> bool:
        return self.provider_type == ProviderType.KRILL

    @property
    def capability_matrix(self) -> dict:
        return {
            'supports_roa_read': self.supports_roa_read,
            'supports_roa_write': self.supports_roa_write,
            'supports_aspa_read': self.supports_aspa_read,
            'supports_aspa_write': self.supports_aspa_write,
            'supports_certificate_inventory': self.supports_certificate_inventory,
            'supports_repository_metadata': self.supports_repository_metadata,
            'supports_bulk_operations': self.supports_bulk_operations,
        }


class IrrSource(NamedRpkiStandardModel):
    DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES = 24 * 60

    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='irr_sources',
    )
    slug = models.SlugField(max_length=100)
    enabled = models.BooleanField(default=True)
    source_family = models.CharField(
        max_length=32,
        choices=IrrSourceFamily.choices,
        default=IrrSourceFamily.IRRD_COMPATIBLE,
    )
    write_support_mode = models.CharField(
        max_length=32,
        choices=IrrWriteSupportMode.choices,
        default=IrrWriteSupportMode.UNSUPPORTED,
    )
    default_database_label = models.CharField(max_length=100, blank=True)
    query_base_url = models.CharField(max_length=255, blank=True)
    whois_host = models.CharField(max_length=255, blank=True)
    whois_port = models.PositiveIntegerField(blank=True, null=True)
    http_username = models.CharField(max_length=255, blank=True)
    http_password = models.CharField(max_length=255, blank=True)
    api_key = models.CharField(max_length=255, blank=True)
    maintainer_name = models.CharField(max_length=255, blank=True)
    sync_interval = models.PositiveIntegerField(blank=True, null=True)
    last_successful_snapshot = models.ForeignKey(
        to='IrrSnapshot',
        on_delete=models.SET_NULL,
        related_name='successful_for_sources',
        blank=True,
        null=True,
    )
    last_attempted_at = models.DateTimeField(blank=True, null=True)
    last_sync_status = models.CharField(
        max_length=32,
        choices=IrrSnapshotStatus.choices,
        default=IrrSnapshotStatus.PENDING,
    )
    summary_json = models.JSONField(default=dict, blank=True)
    last_sync_summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('organization__name', 'name')
        constraints = (
            models.UniqueConstraint(
                fields=('organization', 'slug'),
                name='nb_rpki_irrsource_org_slug_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    @property
    def supports_preview(self) -> bool:
        return self.write_support_mode in {
            IrrWriteSupportMode.PREVIEW_ONLY,
            IrrWriteSupportMode.APPLY_SUPPORTED,
        }

    @property
    def supports_apply(self) -> bool:
        return self.write_support_mode == IrrWriteSupportMode.APPLY_SUPPORTED

    @property
    def sync_health_interval(self) -> timedelta:
        interval_minutes = self.sync_interval or self.DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES
        return timedelta(minutes=interval_minutes)

    @property
    def sync_health(self) -> str:
        if not self.enabled:
            return IrrSyncHealth.DISABLED
        if self.last_sync_status == IrrSnapshotStatus.RUNNING:
            return IrrSyncHealth.IN_PROGRESS
        if self.last_sync_status == IrrSnapshotStatus.FAILED:
            return IrrSyncHealth.FAILED
        if self.last_successful_snapshot_id is None:
            return IrrSyncHealth.NEVER_SYNCED
        reference_time = self.last_successful_snapshot.completed_at or self.last_successful_snapshot.started_at
        if reference_time is None:
            return IrrSyncHealth.NEVER_SYNCED
        if reference_time + self.sync_health_interval <= timezone.now():
            return IrrSyncHealth.STALE
        return IrrSyncHealth.HEALTHY

    @property
    def sync_health_display(self) -> str:
        return IrrSyncHealth(self.sync_health).label


class IrrSnapshot(NamedRpkiStandardModel):
    source = models.ForeignKey(
        to='IrrSource',
        on_delete=models.PROTECT,
        related_name='snapshots',
    )
    status = models.CharField(
        max_length=32,
        choices=IrrSnapshotStatus.choices,
        default=IrrSnapshotStatus.PENDING,
    )
    fetch_mode = models.CharField(
        max_length=32,
        choices=IrrFetchMode.choices,
        default=IrrFetchMode.LIVE_QUERY,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    source_serial = models.CharField(max_length=100, blank=True)
    source_last_modified = models.DateTimeField(blank=True, null=True)
    source_fingerprint = models.CharField(max_length=255, blank=True)
    error_text = models.TextField(blank=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-started_at', '-created')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})


class ImportedIrrObjectBase(NamedRpkiStandardModel):
    snapshot = models.ForeignKey(
        to='IrrSnapshot',
        on_delete=models.PROTECT,
        related_name='%(class)s_rows',
    )
    source = models.ForeignKey(
        to='IrrSource',
        on_delete=models.PROTECT,
        related_name='%(class)s_rows',
    )
    rpsl_object_class = models.CharField(max_length=32)
    rpsl_pk = models.CharField(max_length=255)
    stable_key = models.CharField(max_length=255)
    object_text = models.TextField(blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    source_database_label = models.CharField(max_length=100, blank=True)

    class Meta:
        abstract = True
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})


class ImportedIrrRouteObject(ImportedIrrObjectBase):
    address_family = models.CharField(max_length=16, choices=AddressFamily.choices)
    prefix = models.CharField(max_length=64)
    origin_asn = models.CharField(max_length=32)
    route_set_names_json = models.JSONField(default=list, blank=True)
    maintainer_names_json = models.JSONField(default=list, blank=True)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirrouteobj_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrRouteSet(ImportedIrrObjectBase):
    set_name = models.CharField(max_length=255)
    maintainer_names_json = models.JSONField(default=list, blank=True)
    member_count = models.PositiveIntegerField(default=0)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirrouteset_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrRouteSetMember(ImportedIrrObjectBase):
    parent_route_set = models.ForeignKey(
        to='ImportedIrrRouteSet',
        on_delete=models.PROTECT,
        related_name='members',
    )
    member_text = models.CharField(max_length=255)
    member_type = models.CharField(
        max_length=32,
        choices=IrrMemberType.choices,
        default=IrrMemberType.UNKNOWN,
    )
    normalized_prefix = models.CharField(max_length=64, blank=True)
    normalized_set_name = models.CharField(max_length=255, blank=True)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirroutesetmember_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrAsSet(ImportedIrrObjectBase):
    set_name = models.CharField(max_length=255)
    maintainer_names_json = models.JSONField(default=list, blank=True)
    member_count = models.PositiveIntegerField(default=0)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirasset_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrAsSetMember(ImportedIrrObjectBase):
    parent_as_set = models.ForeignKey(
        to='ImportedIrrAsSet',
        on_delete=models.PROTECT,
        related_name='members',
    )
    member_text = models.CharField(max_length=255)
    member_type = models.CharField(
        max_length=32,
        choices=IrrMemberType.choices,
        default=IrrMemberType.UNKNOWN,
    )
    normalized_asn = models.CharField(max_length=32, blank=True)
    normalized_set_name = models.CharField(max_length=255, blank=True)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirassetmember_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrAutNum(ImportedIrrObjectBase):
    asn = models.CharField(max_length=32)
    as_name = models.CharField(max_length=255, blank=True)
    import_policy_summary = models.TextField(blank=True)
    export_policy_summary = models.TextField(blank=True)
    maintainer_names_json = models.JSONField(default=list, blank=True)
    admin_contact_handles_json = models.JSONField(default=list, blank=True)
    tech_contact_handles_json = models.JSONField(default=list, blank=True)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirautnum_snapshot_stable_key_unique',
            ),
        )


class ImportedIrrMaintainer(ImportedIrrObjectBase):
    maintainer_name = models.CharField(max_length=255)
    auth_summary_json = models.JSONField(default=list, blank=True)
    admin_contact_handles_json = models.JSONField(default=list, blank=True)
    upd_to_addresses_json = models.JSONField(default=list, blank=True)

    class Meta(ImportedIrrObjectBase.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('snapshot', 'stable_key'),
                name='nb_rpki_iirmaintainer_snapshot_stable_key_unique',
            ),
        )


class IrrCoordinationRun(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='irr_coordination_runs',
    )
    status = models.CharField(
        max_length=32,
        choices=IrrCoordinationRunStatus.choices,
        default=IrrCoordinationRunStatus.PENDING,
    )
    compared_sources = models.ManyToManyField(
        to='IrrSource',
        related_name='coordination_runs',
        blank=True,
    )
    scope_summary_json = models.JSONField(default=dict, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_text = models.TextField(blank=True)

    class Meta:
        ordering = ('-started_at', '-created')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})


class IrrCoordinationResult(NamedRpkiStandardModel):
    coordination_run = models.ForeignKey(
        to='IrrCoordinationRun',
        on_delete=models.PROTECT,
        related_name='results',
    )
    source = models.ForeignKey(
        to='IrrSource',
        on_delete=models.PROTECT,
        related_name='coordination_results',
        blank=True,
        null=True,
    )
    snapshot = models.ForeignKey(
        to='IrrSnapshot',
        on_delete=models.PROTECT,
        related_name='coordination_results',
        blank=True,
        null=True,
    )
    coordination_family = models.CharField(
        max_length=64,
        choices=IrrCoordinationFamily.choices,
    )
    result_type = models.CharField(
        max_length=64,
        choices=IrrCoordinationResultType.choices,
    )
    severity = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        default=ReconciliationSeverity.INFO,
    )
    stable_object_key = models.CharField(max_length=255, blank=True)
    netbox_object_key = models.CharField(max_length=255, blank=True)
    source_object_key = models.CharField(max_length=255, blank=True)
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='irr_coordination_results',
        blank=True,
        null=True,
    )
    imported_route_object = models.ForeignKey(
        to='ImportedIrrRouteObject',
        on_delete=models.PROTECT,
        related_name='coordination_results',
        blank=True,
        null=True,
    )
    imported_aut_num = models.ForeignKey(
        to='ImportedIrrAutNum',
        on_delete=models.PROTECT,
        related_name='coordination_results',
        blank=True,
        null=True,
    )
    imported_maintainer = models.ForeignKey(
        to='ImportedIrrMaintainer',
        on_delete=models.PROTECT,
        related_name='coordination_results',
        blank=True,
        null=True,
    )
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('coordination_run', 'source', 'coordination_family', 'stable_object_key', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})


class IrrChangePlan(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='irr_change_plans',
    )
    coordination_run = models.ForeignKey(
        to='IrrCoordinationRun',
        on_delete=models.PROTECT,
        related_name='change_plans',
    )
    source = models.ForeignKey(
        to='IrrSource',
        on_delete=models.PROTECT,
        related_name='change_plans',
    )
    snapshot = models.ForeignKey(
        to='IrrSnapshot',
        on_delete=models.PROTECT,
        related_name='change_plans',
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=16,
        choices=IrrChangePlanStatus.choices,
        default=IrrChangePlanStatus.DRAFT,
    )
    write_support_mode = models.CharField(
        max_length=32,
        choices=IrrWriteSupportMode.choices,
        default=IrrWriteSupportMode.UNSUPPORTED,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    execution_requested_by = models.CharField(max_length=150, blank=True)
    execution_started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    canceled_at = models.DateTimeField(blank=True, null=True)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-created', 'name')
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='nb_rpki_irrchangeplan_valid_maintenance_window',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )
        errors = {}
        if self.coordination_run_id is not None and self.coordination_run.organization_id != self.organization_id:
            errors['coordination_run'] = 'Coordination run must belong to the same organization as the IRR change plan.'
        if self.source_id is not None and self.source.organization_id != self.organization_id:
            errors['source'] = 'IRR source must belong to the same organization as the IRR change plan.'
        if self.snapshot_id is not None:
            if self.source_id is None:
                errors['source'] = 'IRR source is required when snapshot is set.'
            elif self.snapshot.source_id != self.source_id:
                errors['snapshot'] = 'IRR snapshot must belong to the selected IRR source.'
        if errors:
            raise ValidationError(errors)

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

    @property
    def supports_preview(self) -> bool:
        return self.write_support_mode in {
            IrrWriteSupportMode.PREVIEW_ONLY,
            IrrWriteSupportMode.APPLY_SUPPORTED,
        }

    @property
    def supports_apply(self) -> bool:
        return self.write_support_mode == IrrWriteSupportMode.APPLY_SUPPORTED

    @property
    def can_preview(self) -> bool:
        return self.supports_preview and self.status in {
            IrrChangePlanStatus.DRAFT,
            IrrChangePlanStatus.READY,
            IrrChangePlanStatus.APPROVED,
            IrrChangePlanStatus.FAILED,
        }

    @property
    def can_apply(self) -> bool:
        return self.supports_apply and self.status in {
            IrrChangePlanStatus.DRAFT,
            IrrChangePlanStatus.READY,
            IrrChangePlanStatus.APPROVED,
            IrrChangePlanStatus.FAILED,
        }


class IrrChangePlanItem(NamedRpkiStandardModel):
    change_plan = models.ForeignKey(
        to='IrrChangePlan',
        on_delete=models.PROTECT,
        related_name='items',
    )
    coordination_result = models.ForeignKey(
        to='IrrCoordinationResult',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True,
    )
    object_family = models.CharField(
        max_length=64,
        choices=IrrCoordinationFamily.choices,
    )
    action = models.CharField(
        max_length=16,
        choices=IrrChangePlanAction.choices,
        default=IrrChangePlanAction.NOOP,
    )
    stable_object_key = models.CharField(max_length=255, blank=True)
    source_object_key = models.CharField(max_length=255, blank=True)
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='irr_change_plan_items',
        blank=True,
        null=True,
    )
    imported_route_object = models.ForeignKey(
        to='ImportedIrrRouteObject',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True,
    )
    imported_aut_num = models.ForeignKey(
        to='ImportedIrrAutNum',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True,
    )
    imported_maintainer = models.ForeignKey(
        to='ImportedIrrMaintainer',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True,
    )
    before_state_json = models.JSONField(default=dict, blank=True)
    after_state_json = models.JSONField(default=dict, blank=True)
    request_payload_json = models.JSONField(default=dict, blank=True)
    response_summary_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        errors = {}
        if self.coordination_result_id is not None and self.coordination_result.coordination_run_id != self.change_plan.coordination_run_id:
            errors['coordination_result'] = 'Coordination result must belong to the change plan coordination run.'
        if self.action != IrrChangePlanAction.NOOP and not any(
            (
                self.roa_intent_id,
                self.imported_route_object_id,
                self.imported_aut_num_id,
                self.imported_maintainer_id,
            )
        ):
            errors['action'] = 'Actionable IRR change plan items must reference at least one related object.'
        if errors:
            raise ValidationError(errors)


class IrrWriteExecution(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='irr_write_executions',
    )
    source = models.ForeignKey(
        to='IrrSource',
        on_delete=models.PROTECT,
        related_name='write_executions',
    )
    change_plan = models.ForeignKey(
        to='IrrChangePlan',
        on_delete=models.PROTECT,
        related_name='write_executions',
    )
    execution_mode = models.CharField(
        max_length=16,
        choices=IrrWriteExecutionMode.choices,
    )
    status = models.CharField(
        max_length=16,
        choices=IrrWriteExecutionStatus.choices,
        default=IrrWriteExecutionStatus.PENDING,
    )
    requested_by = models.CharField(max_length=150, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    item_count = models.PositiveIntegerField(default=0)
    request_payload_json = models.JSONField(default=dict, blank=True)
    response_payload_json = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ('-started_at', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        errors = {}
        if self.source_id is not None and self.source.organization_id != self.organization_id:
            errors['source'] = 'IRR source must belong to the same organization as the IRR write execution.'
        if self.change_plan_id is not None:
            if self.change_plan.organization_id != self.organization_id:
                errors['change_plan'] = 'IRR change plan must belong to the same organization as the IRR write execution.'
            if self.source_id is not None and self.change_plan.source_id != self.source_id:
                errors['source'] = 'IRR write execution source must match the IRR change plan source.'
        if errors:
            raise ValidationError(errors)


class TelemetrySource(NamedRpkiStandardModel):
    DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES = 24 * 60

    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='telemetry_sources',
    )
    slug = models.SlugField(max_length=100)
    enabled = models.BooleanField(default=True)
    source_type = models.CharField(
        max_length=32,
        choices=TelemetrySourceType.choices,
        default=TelemetrySourceType.IMPORTED_MRT,
    )
    endpoint_label = models.CharField(max_length=255, blank=True)
    collector_scope = models.CharField(max_length=255, blank=True)
    import_interval = models.PositiveIntegerField(blank=True, null=True)
    last_successful_run = models.ForeignKey(
        to='TelemetryRun',
        on_delete=models.SET_NULL,
        related_name='successful_for_sources',
        blank=True,
        null=True,
    )
    last_attempted_at = models.DateTimeField(blank=True, null=True)
    last_run_status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    summary_json = models.JSONField(default=dict, blank=True)
    last_run_summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('organization__name', 'name')
        constraints = (
            models.UniqueConstraint(
                fields=('organization', 'slug'),
                name='nb_rpki_telemetrysource_org_slug_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    @property
    def sync_health_interval(self) -> timedelta:
        interval_minutes = self.import_interval or self.DEFAULT_SYNC_HEALTH_INTERVAL_MINUTES
        return timedelta(minutes=interval_minutes)

    @property
    def sync_health(self) -> str:
        if not self.enabled:
            return TelemetrySyncHealth.DISABLED
        if self.last_run_status == ValidationRunStatus.RUNNING:
            return TelemetrySyncHealth.IN_PROGRESS
        if self.last_run_status == ValidationRunStatus.FAILED:
            return TelemetrySyncHealth.FAILED
        if self.last_successful_run_id is None:
            return TelemetrySyncHealth.NEVER_SYNCED
        reference_time = self.last_successful_run.completed_at or self.last_successful_run.started_at
        if reference_time is None:
            return TelemetrySyncHealth.NEVER_SYNCED
        if reference_time + self.sync_health_interval <= timezone.now():
            return TelemetrySyncHealth.STALE
        return TelemetrySyncHealth.HEALTHY

    @property
    def sync_health_display(self) -> str:
        return TelemetrySyncHealth(self.sync_health).label


class TelemetryRun(NamedRpkiStandardModel):
    source = models.ForeignKey(
        to='TelemetrySource',
        on_delete=models.PROTECT,
        related_name='telemetry_runs',
    )
    status = models.CharField(
        max_length=32,
        choices=ValidationRunStatus.choices,
        default=ValidationRunStatus.PENDING,
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    observed_window_start = models.DateTimeField(blank=True, null=True)
    observed_window_end = models.DateTimeField(blank=True, null=True)
    source_fingerprint = models.CharField(max_length=255, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    error_text = models.TextField(blank=True)

    class Meta:
        ordering = ('-started_at', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})


class BgpPathObservation(NamedRpkiStandardModel):
    telemetry_run = models.ForeignKey(
        to='TelemetryRun',
        on_delete=models.PROTECT,
        related_name='path_observations',
    )
    source = models.ForeignKey(
        to='TelemetrySource',
        on_delete=models.PROTECT,
        related_name='path_observations',
    )
    prefix = models.ForeignKey(
        to=Prefix,
        on_delete=models.PROTECT,
        related_name='bgp_path_observations',
        blank=True,
        null=True,
    )
    observed_prefix = models.CharField(max_length=64, blank=True)
    origin_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='origin_bgp_path_observations',
        blank=True,
        null=True,
    )
    observed_origin_asn = models.PositiveIntegerField(blank=True, null=True)
    peer_as = models.ForeignKey(
        to=ASN,
        on_delete=models.PROTECT,
        related_name='peer_bgp_path_observations',
        blank=True,
        null=True,
    )
    observed_peer_asn = models.PositiveIntegerField(blank=True, null=True)
    collector_id = models.CharField(max_length=255, blank=True)
    vantage_point_label = models.CharField(max_length=255, blank=True)
    raw_as_path = models.TextField(blank=True)
    path_hash = models.CharField(max_length=64, blank=True)
    path_asns_json = models.JSONField(default=list, blank=True)
    first_observed_at = models.DateTimeField(blank=True, null=True)
    last_observed_at = models.DateTimeField(blank=True, null=True)
    visibility_status = models.CharField(max_length=64, blank=True)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-last_observed_at', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return _plugin_get_action_url(type(self), kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        errors = {}
        if self.telemetry_run_id is not None and self.source_id is not None and self.telemetry_run.source_id != self.source_id:
            errors['source'] = 'Telemetry source must match the telemetry run source.'
        if errors:
            raise ValidationError(errors)


class LifecycleHealthPolicy(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='lifecycle_health_policies',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_policies',
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    sync_stale_after_minutes = models.PositiveIntegerField(default=120)
    roa_expiry_warning_days = models.PositiveIntegerField(default=30)
    certificate_expiry_warning_days = models.PositiveIntegerField(default=30)
    exception_expiry_warning_days = models.PositiveIntegerField(default=30)
    publication_exchange_failure_threshold = models.PositiveIntegerField(default=1)
    publication_stale_after_minutes = models.PositiveIntegerField(default=180)
    certificate_expired_grace_minutes = models.PositiveIntegerField(default=0)
    alert_repeat_after_minutes = models.PositiveIntegerField(default=360)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        constraints = (
            models.UniqueConstraint(
                fields=('organization',),
                condition=Q(provider_account__isnull=True),
                name='nb_rpki_lchpolicy_org_default_unique',
            ),
            models.UniqueConstraint(
                fields=('provider_account',),
                condition=Q(provider_account__isnull=False),
                name='nb_rpki_lchpolicy_provider_unique',
            ),
        )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if (
            self.provider_account_id is not None
            and self.organization_id is not None
            and self.provider_account.organization_id != self.organization_id
        ):
            raise ValidationError(
                {
                    'provider_account': (
                        'Provider account must belong to the same organization as the lifecycle health policy.'
                    )
                }
            )

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:lifecyclehealthpolicy', args=[self.pk])


class LifecycleHealthHook(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='lifecycle_health_hooks',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_hooks',
        blank=True,
        null=True,
    )
    policy = models.ForeignKey(
        to='LifecycleHealthPolicy',
        on_delete=models.PROTECT,
        related_name='hooks',
        blank=True,
        null=True,
    )
    enabled = models.BooleanField(default=True)
    target_url = models.CharField(max_length=500)
    secret = models.CharField(max_length=255, blank=True)
    headers_json = models.JSONField(default=dict, blank=True)
    event_kinds_json = models.JSONField(default=list, blank=True)
    send_resolved = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:lifecyclehealthhook', args=[self.pk])

    def clean(self):
        super().clean()
        if (
            self.provider_account_id is not None
            and self.organization_id is not None
            and self.provider_account.organization_id != self.organization_id
        ):
            raise ValidationError(
                {
                    'provider_account': (
                        'Provider account must belong to the same organization as the lifecycle health hook.'
                    )
                }
            )
        if self.policy_id is not None:
            if self.policy.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        'policy': (
                            'Lifecycle health policy must belong to the same organization as the lifecycle health hook.'
                        )
                    }
                )
            if (
                self.policy.provider_account_id is not None
                and self.provider_account_id is not None
                and self.policy.provider_account_id != self.provider_account_id
            ):
                raise ValidationError(
                    {
                        'policy': (
                            'Provider-scoped lifecycle health policy must match the lifecycle health hook provider account.'
                        )
                    }
                )


class LifecycleHealthEvent(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='lifecycle_health_events',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_events',
    )
    policy = models.ForeignKey(
        to='LifecycleHealthPolicy',
        on_delete=models.PROTECT,
        related_name='events',
        blank=True,
        null=True,
    )
    hook = models.ForeignKey(
        to='LifecycleHealthHook',
        on_delete=models.PROTECT,
        related_name='events',
    )
    related_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_events',
        blank=True,
        null=True,
    )
    related_snapshot_diff = models.ForeignKey(
        to='ProviderSnapshotDiff',
        on_delete=models.PROTECT,
        related_name='lifecycle_health_events',
        blank=True,
        null=True,
    )
    event_kind = models.CharField(max_length=64, choices=LifecycleHealthEventKind.choices)
    severity = models.CharField(max_length=16, choices=LifecycleHealthEventSeverity.choices)
    status = models.CharField(max_length=16, choices=LifecycleHealthEventStatus.choices, default=LifecycleHealthEventStatus.OPEN)
    dedupe_key = models.CharField(max_length=255)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    last_emitted_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    payload_json = models.JSONField(default=dict, blank=True)
    delivery_error = models.TextField(blank=True)

    class Meta:
        ordering = ('-last_seen_at', '-created')
        constraints = (
            models.UniqueConstraint(
                fields=('hook', 'dedupe_key'),
                condition=Q(status__in=(
                    LifecycleHealthEventStatus.OPEN,
                    LifecycleHealthEventStatus.REPEATED,
                )),
                name='nb_rpki_lchevent_hook_dedupe_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('plugins:netbox_rpki:lifecyclehealthevent', args=[self.pk])

    def clean(self):
        super().clean()
        if self.provider_account_id is not None and self.organization_id is not None and self.provider_account.organization_id != self.organization_id:
            raise ValidationError(
                {
                    'provider_account': (
                        'Provider account must belong to the same organization as the lifecycle health event.'
                    )
                }
            )
        if self.hook_id is not None:
            if self.hook.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        'hook': (
                            'Lifecycle health hook must belong to the same organization as the lifecycle health event.'
                        )
                    }
                )
            if self.hook.provider_account_id is not None and self.hook.provider_account_id != self.provider_account_id:
                raise ValidationError(
                    {
                        'hook': (
                            'Lifecycle health hook provider account must match the lifecycle health event provider account.'
                        )
                    }
                )
            if self.policy_id is not None and self.hook.policy_id is not None and self.policy_id != self.hook.policy_id:
                raise ValidationError(
                    {
                        'policy': (
                            'Lifecycle health event policy must match the lifecycle health hook policy.'
                        )
                    }
                )


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
    authored_publication_point = models.ForeignKey(
        to='PublicationPoint',
        on_delete=models.PROTECT,
        related_name='imported_publication_observations',
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

    def clean(self):
        super().clean()
        if (
            self.authored_publication_point_id is not None
            and self.organization_id is not None
            and self.authored_publication_point.organization_id is not None
            and self.authored_publication_point.organization_id != self.organization_id
        ):
            raise ValidationError(
                {
                    'authored_publication_point': (
                        'Authored publication point must belong to the same organization as the imported publication point.'
                    )
                }
            )

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
    authored_signed_object = models.ForeignKey(
        to='SignedObject',
        on_delete=models.PROTECT,
        related_name='imported_signed_object_observations',
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

    def clean(self):
        super().clean()

        errors = []
        if self.authored_signed_object_id is not None:
            if (
                self.organization_id is not None
                and self.authored_signed_object.organization_id is not None
                and self.authored_signed_object.organization_id != self.organization_id
            ):
                errors.append(
                    'Authored signed object must belong to the same organization as the imported signed object.'
                )
            if (
                self.signed_object_type
                and self.authored_signed_object.object_type
                and self.authored_signed_object.object_type != self.signed_object_type
            ):
                errors.append('Authored signed object must use the same object type as the imported signed object.')
            if (
                self.publication_point_id is not None
                and self.publication_point.authored_publication_point_id is not None
                and self.authored_signed_object.publication_point_id is not None
                and self.authored_signed_object.publication_point_id
                != self.publication_point.authored_publication_point_id
            ):
                errors.append(
                    'Authored signed object must use the same authored publication point as the imported signed object.'
                )

        if errors:
            raise ValidationError({'authored_signed_object': errors})

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
    publication_point = models.ForeignKey(
        to='ImportedPublicationPoint',
        on_delete=models.PROTECT,
        related_name='certificate_observations',
        blank=True,
        null=True,
    )
    signed_object = models.ForeignKey(
        to='ImportedSignedObject',
        on_delete=models.PROTECT,
        related_name='certificate_observations',
        blank=True,
        null=True,
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
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='aspa_intents',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='aspa_intents',
        blank=True,
        null=True,
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
        errors = {}
        if self.customer_as_id is not None and self.customer_as_id == self.provider_as_id:
            errors['provider_as'] = ['Provider ASN must differ from the ASPA customer ASN.']

        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this ASPA intent.'

        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must belong to the same organization as this ASPA intent.'
            )

        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must reference the same delegated entity as this ASPA intent.'
            )

        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspaintent", args=[self.pk])

    @classmethod
    def build_intent_key(
        cls,
        *,
        customer_asn_value: int | None,
        provider_asn_value: int | None,
        delegated_entity_id: int | None = None,
        managed_relationship_id: int | None = None,
    ) -> str:
        normalized = "|".join(
            str(value)
            for value in (
                customer_asn_value if customer_asn_value is not None else "",
                provider_asn_value if provider_asn_value is not None else "",
                delegated_entity_id if delegated_entity_id is not None else "",
                managed_relationship_id if managed_relationship_id is not None else "",
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
    roa_object = models.ForeignKey(
        to=RoaObject,
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
                fields=("roa_intent", "roa_object"),
                condition=models.Q(roa_object__isnull=False, imported_authorization__isnull=True),
                name="netbox_rpki_roaintentmatch_intent_roa_object_unique",
            ),
            models.UniqueConstraint(
                fields=("roa_intent", "imported_authorization"),
                condition=models.Q(roa_object__isnull=True, imported_authorization__isnull=False),
                name="netbox_rpki_roaintentmatch_roa_intent_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(roa_object__isnull=False, imported_authorization__isnull=True)
                    | models.Q(roa_object__isnull=True, imported_authorization__isnull=False)
                ),
                name="netbox_rpki_roaintentmatch_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roaintentmatch", args=[self.pk])

    @property
    def roa(self):
        return self.roa_object


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
    best_roa_object = models.ForeignKey(
        to=RoaObject,
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

    @property
    def best_roa(self):
        return self.best_roa_object


class PublishedROAResult(NamedRpkiStandardModel):
    reconciliation_run = models.ForeignKey(
        to='ROAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='published_roa_results'
    )
    roa_object = models.ForeignKey(
        to=RoaObject,
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
                fields=("reconciliation_run", "roa_object"),
                condition=models.Q(roa_object__isnull=False, imported_authorization__isnull=True),
                name="netbox_rpki_publishedroaresult_run_roa_object_unique",
            ),
            models.UniqueConstraint(
                fields=("reconciliation_run", "imported_authorization"),
                condition=models.Q(roa_object__isnull=True, imported_authorization__isnull=False),
                name="netbox_rpki_publishedresult_run_imported_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(roa_object__isnull=False, imported_authorization__isnull=True)
                    | models.Q(roa_object__isnull=True, imported_authorization__isnull=False)
                ),
                name="netbox_rpki_publishedroaresult_exactly_one_source",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:publishedroaresult", args=[self.pk])

    @property
    def roa(self):
        return self.roa_object


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


class ROALintAcknowledgement(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_lint_acknowledgements'
    )
    change_plan = models.ForeignKey(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='lint_acknowledgements'
    )
    lint_run = models.ForeignKey(
        to='ROALintRun',
        on_delete=models.PROTECT,
        related_name='acknowledgements'
    )
    finding = models.ForeignKey(
        to='ROALintFinding',
        on_delete=models.PROTECT,
        related_name='acknowledgements'
    )
    acknowledged_by = models.CharField(max_length=150, blank=True)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('-acknowledged_at', '-created', 'name')
        constraints = (
            models.UniqueConstraint(
                fields=('change_plan', 'finding'),
                name='netbox_rpki_roalintack_change_plan_finding_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roalintacknowledgement", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}
        if self.finding_id and self.lint_run_id and self.finding.lint_run_id != self.lint_run_id:
            errors['finding'] = 'Finding must belong to the selected lint run.'
        if self.lint_run_id and self.change_plan_id and self.lint_run.change_plan_id != self.change_plan_id:
            errors['lint_run'] = 'Lint run must belong to the selected change plan.'
        if self.change_plan_id and self.organization_id and self.change_plan.organization_id != self.organization_id:
            errors['organization'] = 'Organization must match the acknowledged change plan.'
        if errors:
            raise ValidationError(errors)


class ROALintSuppression(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_lint_suppressions'
    )
    finding_code = models.CharField(max_length=64)
    scope_type = models.CharField(
        max_length=16,
        choices=ROALintSuppressionScope.choices,
        default=ROALintSuppressionScope.INTENT,
    )
    intent_profile = models.ForeignKey(
        to='RoutingIntentProfile',
        on_delete=models.PROTECT,
        related_name='lint_suppressions',
        blank=True,
        null=True,
    )
    roa_intent = models.ForeignKey(
        to='ROAIntent',
        on_delete=models.PROTECT,
        related_name='lint_suppressions',
        blank=True,
        null=True,
    )
    prefix_cidr_text = models.CharField(
        max_length=50,
        blank=True,
        help_text='Required for prefix-scoped suppressions. CIDR notation, e.g. 192.0.2.0/24.',
    )
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    fact_fingerprint = models.CharField(max_length=64, blank=True, default='')
    fact_context_json = models.JSONField(default=dict, blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_matched_at = models.DateTimeField(blank=True, null=True)
    match_count = models.PositiveIntegerField(default=0)
    lifted_by = models.CharField(max_length=150, blank=True)
    lifted_at = models.DateTimeField(blank=True, null=True)
    lift_reason = models.TextField(blank=True)

    class Meta:
        ordering = ('-created_at', '-created', 'name')
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(
                        scope_type=ROALintSuppressionScope.INTENT,
                        roa_intent__isnull=False,
                        intent_profile__isnull=True,
                        prefix_cidr_text='',
                    )
                    | models.Q(
                        scope_type=ROALintSuppressionScope.PROFILE,
                        roa_intent__isnull=True,
                        intent_profile__isnull=False,
                        prefix_cidr_text='',
                    )
                    | models.Q(
                        scope_type=ROALintSuppressionScope.ORG,
                        roa_intent__isnull=True,
                        intent_profile__isnull=True,
                        prefix_cidr_text='',
                    )
                    | models.Q(
                        scope_type=ROALintSuppressionScope.PREFIX,
                        roa_intent__isnull=True,
                        intent_profile__isnull=True,
                        prefix_cidr_text__gt='',
                    )
                ),
                name='netbox_rpki_roalintsuppression_exact_scope_target',
            ),
            models.UniqueConstraint(
                fields=('finding_code', 'roa_intent', 'fact_fingerprint'),
                condition=models.Q(scope_type=ROALintSuppressionScope.INTENT, lifted_at__isnull=True),
                name='netbox_rpki_roalintsuppression_active_intent_unique',
            ),
            models.UniqueConstraint(
                fields=('finding_code', 'intent_profile', 'fact_fingerprint'),
                condition=models.Q(scope_type=ROALintSuppressionScope.PROFILE, lifted_at__isnull=True),
                name='netbox_rpki_roalintsuppression_active_profile_unique',
            ),
            models.UniqueConstraint(
                fields=('finding_code', 'organization'),
                condition=models.Q(scope_type=ROALintSuppressionScope.ORG, lifted_at__isnull=True),
                name='netbox_rpki_roalintsuppression_active_org_unique',
            ),
            models.UniqueConstraint(
                fields=('finding_code', 'organization', 'prefix_cidr_text'),
                condition=models.Q(scope_type=ROALintSuppressionScope.PREFIX, lifted_at__isnull=True),
                name='netbox_rpki_roalintsuppression_active_prefix_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roalintsuppression", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}
        if self.scope_type == ROALintSuppressionScope.INTENT:
            if self.roa_intent_id is None:
                errors['roa_intent'] = 'ROA intent is required for intent-scoped suppressions.'
            if self.intent_profile_id is not None:
                errors['intent_profile'] = 'Intent profile must be empty for intent-scoped suppressions.'
        if self.scope_type == ROALintSuppressionScope.PROFILE:
            if self.intent_profile_id is None:
                errors['intent_profile'] = 'Intent profile is required for profile-scoped suppressions.'
            if self.roa_intent_id is not None:
                errors['roa_intent'] = 'ROA intent must be empty for profile-scoped suppressions.'
            if self.prefix_cidr_text:
                errors['prefix_cidr_text'] = 'Prefix CIDR must be empty for profile-scoped suppressions.'
        if self.scope_type == ROALintSuppressionScope.ORG:
            if self.roa_intent_id is not None:
                errors['roa_intent'] = 'Must be empty for org-scoped suppressions.'
            if self.intent_profile_id is not None:
                errors['intent_profile'] = 'Must be empty for org-scoped suppressions.'
            if self.prefix_cidr_text:
                errors['prefix_cidr_text'] = 'Must be empty for org-scoped suppressions.'
        if self.scope_type == ROALintSuppressionScope.PREFIX:
            if self.roa_intent_id is not None:
                errors['roa_intent'] = 'Must be empty for prefix-scoped suppressions.'
            if self.intent_profile_id is not None:
                errors['intent_profile'] = 'Must be empty for prefix-scoped suppressions.'
            if not self.prefix_cidr_text:
                errors['prefix_cidr_text'] = 'Prefix CIDR is required for prefix-scoped suppressions.'
            else:
                try:
                    ip_network(self.prefix_cidr_text, strict=False)
                except ValueError:
                    errors['prefix_cidr_text'] = 'Enter a valid CIDR prefix, e.g. 192.0.2.0/24.'
        if self.roa_intent_id and self.organization_id and self.roa_intent.organization_id != self.organization_id:
            errors['organization'] = 'Organization must match the suppressed ROA intent.'
        if self.intent_profile_id and self.organization_id and self.intent_profile.organization_id != self.organization_id:
            errors['organization'] = 'Organization must match the suppressed intent profile.'
        if self.scope_type in (ROALintSuppressionScope.INTENT, ROALintSuppressionScope.PROFILE) and not self.fact_fingerprint:
            errors['fact_fingerprint'] = 'A suppression must record the finding facts it applies to.'
        if self.lifted_at is not None and not self.lifted_by:
            errors['lifted_by'] = 'Lifted-by is required when a suppression is lifted.'
        if errors:
            raise ValidationError(errors)

    @property
    def is_active(self) -> bool:
        if self.lifted_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True


class ROALintRuleConfig(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_lint_rule_configs',
    )
    finding_code = models.CharField(
        max_length=64,
        help_text='The lint rule code from LINT_RULE_SPECS this override applies to.',
    )
    severity_override = models.CharField(
        max_length=16,
        choices=ReconciliationSeverity.choices,
        blank=True,
        help_text='Leave blank to use the rule default.',
    )
    approval_impact_override = models.CharField(
        max_length=64,
        blank=True,
        help_text=(
            'One of: informational, acknowledgement_required, blocking. '
            'Leave blank to use the rule default.'
        ),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)
        constraints = (
            models.UniqueConstraint(
                fields=('organization', 'finding_code'),
                name='netbox_rpki_roalintruleconfig_org_code_unique',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roalintruleconfig", args=[self.pk])

    def clean(self):
        super().clean()
        from netbox_rpki.services.roa_lint import LINT_RULE_SPECS

        errors = {}
        valid_codes = set(LINT_RULE_SPECS.keys())
        if self.finding_code and self.finding_code not in valid_codes:
            errors['finding_code'] = f'Unknown finding code. Valid codes: {sorted(valid_codes)}'
        valid_approval_impacts = {'', 'informational', 'acknowledgement_required', 'blocking'}
        if self.approval_impact_override not in valid_approval_impacts:
            errors['approval_impact_override'] = 'Must be one of: informational, acknowledgement_required, blocking.'
        if errors:
            raise ValidationError(errors)


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
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='roa_change_plans',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
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
    requires_secondary_approval = models.BooleanField(default=False)
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    secondary_approved_at = models.DateTimeField(blank=True, null=True)
    secondary_approved_by = models.CharField(max_length=150, blank=True)
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
        errors = {}
        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this ROA change plan.'
        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must belong to the same organization as this ROA change plan.'
            )
        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must reference the same delegated entity as this ROA change plan.'
            )
        if (
            self.provider_account_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.provider_account_id is not None
            and self.managed_relationship.provider_account_id != self.provider_account_id
        ):
            errors['provider_account'] = (
                'Provider account must match the managed relationship when both are set on this ROA change plan.'
            )
        if self.pk:
            try:
                original = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                original = None
            if (
                original is not None
                and original.status != ROAChangePlanStatus.DRAFT
                and original.requires_secondary_approval != self.requires_secondary_approval
            ):
                errors['requires_secondary_approval'] = (
                    'Cannot change dual-approval requirement after the plan has left DRAFT status.'
                )
        if errors:
            raise ValidationError(errors)

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
            ROAChangePlanStatus.AWAITING_2ND,
            ROAChangePlanStatus.APPROVED,
            ROAChangePlanStatus.FAILED,
        }

    @property
    def can_approve(self) -> bool:
        return self.supports_provider_write and self.status == ROAChangePlanStatus.DRAFT

    @property
    def can_acknowledge_lint(self) -> bool:
        return self.supports_provider_write

    @property
    def can_approve_secondary(self) -> bool:
        return self.supports_provider_write and self.status == ROAChangePlanStatus.AWAITING_2ND

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
        related_name='approval_records',
        blank=True,
        null=True,
    )
    aspa_change_plan = models.ForeignKey(
        to='ASPAChangePlan',
        on_delete=models.PROTECT,
        related_name='approval_records',
        blank=True,
        null=True,
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
    simulation_review_json = models.JSONField(default=dict, blank=True)

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
            models.CheckConstraint(
                condition=(
                    models.Q(change_plan__isnull=False, aspa_change_plan__isnull=True)
                    | models.Q(change_plan__isnull=True, aspa_change_plan__isnull=False)
                ),
                name='netbox_rpki_approvalrecord_exactly_one_plan_target',
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

    @property
    def target_change_plan(self):
        return self.change_plan or self.aspa_change_plan


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
        related_name='provider_write_executions',
        blank=True,
        null=True,
    )
    aspa_change_plan = models.ForeignKey(
        to='ASPAChangePlan',
        on_delete=models.PROTECT,
        related_name='provider_write_executions',
        blank=True,
        null=True,
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
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(change_plan__isnull=False, aspa_change_plan__isnull=True)
                    | models.Q(change_plan__isnull=True, aspa_change_plan__isnull=False)
                ),
                name='netbox_rpki_providerwriteexecution_exactly_one_plan_target',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:providerwriteexecution", args=[self.pk])

    @property
    def target_change_plan(self):
        return self.change_plan or self.aspa_change_plan

    @property
    def object_family(self) -> str:
        if self.aspa_change_plan_id is not None:
            return 'aspa'
        return 'roa'


class ROAChangePlanRollbackBundle(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='roa_rollback_bundles',
    )
    source_plan = models.OneToOneField(
        to='ROAChangePlan',
        on_delete=models.PROTECT,
        related_name='rollback_bundle',
    )
    rollback_delta_json = models.JSONField(
        default=dict,
        help_text=(
            'The inverse of the applied delta. '
            'ROA creates become withdraws; withdraws become creates.'
        ),
    )
    item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=RollbackBundleStatus.choices,
        default=RollbackBundleStatus.AVAILABLE,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    apply_requested_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    apply_response_json = models.JSONField(default=dict, blank=True)
    apply_error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created", "name")
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_roa_rollback_valid_mw',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roachangeplanrollbackbundle", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )

    @property
    def can_approve(self) -> bool:
        return self.status == RollbackBundleStatus.AVAILABLE

    @property
    def can_apply(self) -> bool:
        return self.status == RollbackBundleStatus.APPROVED


class ASPAChangePlan(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspa_change_plans'
    )
    source_reconciliation_run = models.ForeignKey(
        to='ASPAReconciliationRun',
        on_delete=models.PROTECT,
        related_name='change_plans'
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='aspa_change_plans',
        blank=True,
        null=True,
    )
    provider_snapshot = models.ForeignKey(
        to='ProviderSnapshot',
        on_delete=models.PROTECT,
        related_name='aspa_change_plans',
        blank=True,
        null=True,
    )
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='aspa_change_plans',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='aspa_change_plans',
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=16,
        choices=ASPAChangePlanStatus.choices,
        default=ASPAChangePlanStatus.DRAFT,
    )
    requires_secondary_approval = models.BooleanField(default=False)
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=150, blank=True)
    secondary_approved_at = models.DateTimeField(blank=True, null=True)
    secondary_approved_by = models.CharField(max_length=150, blank=True)
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
                name='netbox_rpki_aspachangeplan_valid_maintenance_window',
            ),
        )
        indexes = (
            models.Index(fields=('organization', 'status'), name='nb_rpki_acp_org_status_idx'),
            models.Index(fields=('provider_account', 'status'), name='nb_rpki_acp_prv_status_idx'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplan", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )
        errors = {}
        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this ASPA change plan.'
        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must belong to the same organization as this ASPA change plan.'
            )
        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = (
                'Managed relationship must reference the same delegated entity as this ASPA change plan.'
            )
        if (
            self.provider_account_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.provider_account_id is not None
            and self.managed_relationship.provider_account_id != self.provider_account_id
        ):
            errors['provider_account'] = (
                'Provider account must match the managed relationship when both are set on this ASPA change plan.'
            )
        if self.pk:
            try:
                original = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                original = None
            if (
                original is not None
                and original.status != ASPAChangePlanStatus.DRAFT
                and original.requires_secondary_approval != self.requires_secondary_approval
            ):
                errors['requires_secondary_approval'] = (
                    'Cannot change dual-approval requirement after the plan has left DRAFT status.'
                )
        if errors:
            raise ValidationError(errors)
        if self.provider_snapshot_id is not None and self.provider_account_id is None:
            raise ValidationError({'provider_account': 'Provider account is required when provider snapshot is set.'})
        if (
            self.provider_snapshot_id is not None
            and self.provider_account_id is not None
            and self.provider_snapshot.provider_account_id != self.provider_account_id
        ):
            raise ValidationError({'provider_snapshot': 'Provider snapshot must belong to the selected provider account.'})

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
        return self.is_provider_backed and self.provider_account.supports_aspa_write

    @property
    def can_preview(self) -> bool:
        return self.supports_provider_write and self.status in {
            ASPAChangePlanStatus.DRAFT,
            ASPAChangePlanStatus.AWAITING_2ND,
            ASPAChangePlanStatus.APPROVED,
            ASPAChangePlanStatus.FAILED,
        }

    @property
    def can_approve(self) -> bool:
        return self.supports_provider_write and self.status == ASPAChangePlanStatus.DRAFT

    @property
    def can_approve_secondary(self) -> bool:
        return self.supports_provider_write and self.status == ASPAChangePlanStatus.AWAITING_2ND

    @property
    def can_apply(self) -> bool:
        return self.supports_provider_write and self.status == ASPAChangePlanStatus.APPROVED


class ASPAChangePlanRollbackBundle(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='aspa_rollback_bundles',
    )
    source_plan = models.OneToOneField(
        to='ASPAChangePlan',
        on_delete=models.PROTECT,
        related_name='rollback_bundle',
    )
    rollback_delta_json = models.JSONField(default=dict)
    item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=RollbackBundleStatus.choices,
        default=RollbackBundleStatus.AVAILABLE,
    )
    ticket_reference = models.CharField(max_length=200, blank=True)
    change_reference = models.CharField(max_length=200, blank=True)
    maintenance_window_start = models.DateTimeField(blank=True, null=True)
    maintenance_window_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    apply_requested_by = models.CharField(max_length=150, blank=True)
    apply_started_at = models.DateTimeField(blank=True, null=True)
    applied_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    apply_response_json = models.JSONField(default=dict, blank=True)
    apply_error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created", "name")
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(maintenance_window_start__isnull=True)
                    | models.Q(maintenance_window_end__isnull=True)
                    | models.Q(maintenance_window_end__gte=models.F('maintenance_window_start'))
                ),
                name='netbox_rpki_aspa_rollback_valid_mw',
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplanrollbackbundle", args=[self.pk])

    def clean(self):
        super().clean()
        validate_maintenance_window_bounds(
            start_at=self.maintenance_window_start,
            end_at=self.maintenance_window_end,
        )

    @property
    def can_approve(self) -> bool:
        return self.status == RollbackBundleStatus.AVAILABLE

    @property
    def can_apply(self) -> bool:
        return self.status == RollbackBundleStatus.APPROVED


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
    roa_object = models.ForeignKey(
        to=RoaObject,
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

    @property
    def roa(self):
        return self.roa_object


class ASPAChangePlanItem(NamedRpkiStandardModel):
    change_plan = models.ForeignKey(
        to='ASPAChangePlan',
        on_delete=models.PROTECT,
        related_name='items'
    )
    action_type = models.CharField(
        max_length=16,
        choices=ASPAChangePlanAction.choices,
    )
    plan_semantic = models.CharField(
        max_length=24,
        choices=ASPAChangePlanItemSemantic.choices,
        blank=True,
        null=True,
    )
    aspa_intent = models.ForeignKey(
        to='ASPAIntent',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True
    )
    aspa = models.ForeignKey(
        to='ASPA',
        on_delete=models.PROTECT,
        related_name='change_plan_items',
        blank=True,
        null=True
    )
    imported_aspa = models.ForeignKey(
        to='ImportedAspa',
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
        indexes = (
            models.Index(fields=('change_plan', 'action_type'), name='nb_rpki_acpi_plan_action_idx'),
            models.Index(fields=('change_plan', 'plan_semantic'), name='nb_rpki_acpi_plan_sem_idx'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:aspachangeplanitem", args=[self.pk])

    def clean(self):
        super().clean()
        if not any((self.aspa_intent_id, self.aspa_id, self.imported_aspa_id)):
            raise ValidationError(
                'ASPA change plan items must reference at least one related intent or published object.'
            )


class ROAValidationSimulationOutcome(models.TextChoices):
    VALID = "valid", "Valid"
    INVALID = "invalid", "Invalid"
    NOT_FOUND = "not_found", "Not Found"


class ROAValidationSimulationApprovalImpact(models.TextChoices):
    INFORMATIONAL = "informational", "Informational"
    ACKNOWLEDGEMENT_REQUIRED = "acknowledgement_required", "Acknowledgement Required"
    BLOCKING = "blocking", "Blocking"


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
    plan_fingerprint = models.CharField(max_length=64, blank=True)
    overall_approval_posture = models.CharField(
        max_length=32,
        choices=ROAValidationSimulationApprovalImpact.choices,
        default=ROAValidationSimulationApprovalImpact.INFORMATIONAL,
    )
    is_current_for_plan = models.BooleanField(default=False)
    partially_constrained = models.BooleanField(default=False)
    summary_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-started_at", "name")
        indexes = (
            models.Index(fields=('change_plan', 'overall_approval_posture'), name='nb_rpki_simrun_plan_post_idx'),
            models.Index(fields=('change_plan', 'is_current_for_plan'), name='nb_rpki_simrun_plan_curr_idx'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:roavalidationsimulationrun", args=[self.pk])


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
    approval_impact = models.CharField(
        max_length=32,
        choices=ROAValidationSimulationApprovalImpact.choices,
        default=ROAValidationSimulationApprovalImpact.INFORMATIONAL,
    )
    scenario_type = models.CharField(max_length=64, blank=True)
    details_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("name",)
        indexes = (
            models.Index(fields=('simulation_run', 'approval_impact'), name='nb_rpki_simres_run_appr_idx'),
            models.Index(fields=('simulation_run', 'scenario_type'), name='nb_rpki_simres_run_scen_idx'),
        )

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


# --- N: Downstream/Delegated Authorization models ---

class DelegatedAuthorizationEntity(NamedRpkiStandardModel):
    """
    A downstream customer or delegated entity that holds RPKI authority under
    this organization's CA hierarchy.

    Represents the authorization subject in a delegated-RPKI or downstream
    managed-routing-security relationship.  The entity may be a customer
    organization, a downstream ISP partner, or any party that has been granted
    resource delegation.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='delegated_authorization_entities',
        help_text='Upstream organization that manages this delegated entity.',
    )
    kind = models.CharField(
        max_length=32,
        choices=DelegatedAuthorizationEntityKind.choices,
        default=DelegatedAuthorizationEntityKind.CUSTOMER,
    )
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    asn = models.BigIntegerField(blank=True, null=True, help_text='Primary ASN for this entity, if applicable.')
    enabled = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("organization", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="nb_rpki_delegatedauthentity_org_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:delegatedauthorizationentity", args=[self.pk])


class ManagedAuthorizationRelationship(NamedRpkiStandardModel):
    """
    Maps an organization to a delegated authorization entity and defines the
    authority role and operational status of that relationship.

    A single organization may have multiple managed authorization relationships
    covering different downstream entities, resource classes, or operational scopes.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='managed_authorization_relationships',
    )
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='managed_authorization_relationships',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='managed_authorization_relationships',
        blank=True,
        null=True,
    )
    role = models.CharField(
        max_length=32,
        choices=ManagedAuthorizationRelationshipRole.choices,
        default=ManagedAuthorizationRelationshipRole.MANAGING_PARTY,
    )
    status = models.CharField(
        max_length=32,
        choices=ManagedAuthorizationRelationshipStatus.choices,
        default=ManagedAuthorizationRelationshipStatus.ACTIVE,
    )
    service_uri = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("organization", "delegated_entity", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "delegated_entity"),
                name="nb_rpki_managedauthrelationship_org_entity_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:managedauthorizationrelationship", args=[self.pk])

    def clean(self):
        super().clean()
        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            raise ValidationError({
                'delegated_entity': 'Delegated entity must belong to the same organization as this relationship.'
            })


class DelegatedPublicationWorkflow(NamedRpkiStandardModel):
    """
    Represents an upstream-managed publication workflow for a downstream entity.

    Captures the operational workflow by which a managing organization provisions,
    maintains, and verifies RPKI publication on behalf of a delegated entity.
    This includes references to the CA handles, service endpoints, and approval
    status.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='delegated_publication_workflows',
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='publication_workflows',
    )
    parent_ca_handle = models.CharField(max_length=100, blank=True)
    child_ca_handle = models.CharField(max_length=100, blank=True)
    publication_server_uri = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=32,
        choices=DelegatedPublicationWorkflowStatus.choices,
        default=DelegatedPublicationWorkflowStatus.DRAFT,
    )
    requires_approval = models.BooleanField(default=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("organization", "managed_relationship", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "managed_relationship", "name"),
                name="nb_rpki_delegatedpubworkflow_org_rel_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:delegatedpublicationworkflow", args=[self.pk])


# --- A.4: Authored CA hierarchy topology ---

class AuthoredCaRelationshipType(models.TextChoices):
    PARENT = "parent", "Parent"
    CHILD = "child", "Child"


class AuthoredCaRelationshipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DECOMMISSIONED = "decommissioned", "Decommissioned"


class AuthoredCaRelationship(NamedRpkiStandardModel):
    """
    First-class authored representation of a parent/child CA authority relationship.

    Models the local organization's view of CA authority topology as an authored
    construct, distinct from imported (observed) topology captured in
    ImportedParentLink and ImportedChildLink.  Both sides refer to CA handles
    within the local account hierarchy; the parent handle is optional when the
    relationship represents a top-of-hierarchy (self-signed TA) CA.
    """
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='authored_ca_relationships',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='authored_ca_relationships',
        blank=True,
        null=True,
    )
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='authored_ca_relationships',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='authored_ca_relationships',
        blank=True,
        null=True,
    )
    child_ca_handle = models.CharField(max_length=100)
    parent_ca_handle = models.CharField(max_length=100, blank=True)
    relationship_type = models.CharField(
        max_length=16,
        choices=AuthoredCaRelationshipType.choices,
        default=AuthoredCaRelationshipType.PARENT,
    )
    status = models.CharField(
        max_length=32,
        choices=AuthoredCaRelationshipStatus.choices,
        default=AuthoredCaRelationshipStatus.ACTIVE,
    )
    service_uri = models.CharField(max_length=500, blank=True)
    imported_parent_link = models.ForeignKey(
        to='ImportedParentLink',
        on_delete=models.SET_NULL,
        related_name='authored_ca_relationships',
        blank=True,
        null=True,
    )
    imported_child_link = models.ForeignKey(
        to='ImportedChildLink',
        on_delete=models.SET_NULL,
        related_name='authored_ca_relationships',
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("organization", "child_ca_handle", "parent_ca_handle")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "child_ca_handle", "parent_ca_handle"),
                name="nb_rpki_authoredcarelationship_org_child_parent_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:authoredcarelationship", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this authored CA relationship.'

        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = 'Managed relationship must belong to the same organization as this authored CA relationship.'

        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = 'Managed relationship must reference the same delegated entity as this authored CA relationship.'

        if (
            self.provider_account_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.provider_account_id is not None
            and self.managed_relationship.provider_account_id != self.provider_account_id
        ):
            errors['provider_account'] = 'Provider account must match the managed relationship when both are set.'

        if errors:
            raise ValidationError(errors)


class AuthoredAsSet(NamedRpkiStandardModel):
    organization = models.ForeignKey(
        to=Organization,
        on_delete=models.PROTECT,
        related_name='authored_as_sets',
    )
    provider_account = models.ForeignKey(
        to='RpkiProviderAccount',
        on_delete=models.PROTECT,
        related_name='authored_as_sets',
        blank=True,
        null=True,
    )
    delegated_entity = models.ForeignKey(
        to='DelegatedAuthorizationEntity',
        on_delete=models.PROTECT,
        related_name='authored_as_sets',
        blank=True,
        null=True,
    )
    managed_relationship = models.ForeignKey(
        to='ManagedAuthorizationRelationship',
        on_delete=models.PROTECT,
        related_name='authored_as_sets',
        blank=True,
        null=True,
    )
    set_name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("organization", "set_name", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("organization", "set_name"),
                name="nb_rpki_authoredasset_org_set_name_unique",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:authoredasset", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.delegated_entity_id is not None
            and self.delegated_entity.organization_id != self.organization_id
        ):
            errors['delegated_entity'] = 'Delegated entity must belong to the same organization as this AS-set.'

        if (
            self.managed_relationship_id is not None
            and self.managed_relationship.organization_id != self.organization_id
        ):
            errors['managed_relationship'] = 'Managed relationship must belong to the same organization as this AS-set.'

        if (
            self.provider_account_id is not None
            and self.provider_account.organization_id != self.organization_id
        ):
            errors['provider_account'] = 'Provider account must belong to the same organization as this AS-set.'

        if (
            self.delegated_entity_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.delegated_entity_id != self.delegated_entity_id
        ):
            errors['managed_relationship'] = 'Managed relationship delegated entity must match the AS-set delegated entity.'

        if (
            self.provider_account_id is not None
            and self.managed_relationship_id is not None
            and self.managed_relationship.provider_account_id is not None
            and self.managed_relationship.provider_account_id != self.provider_account_id
        ):
            errors['provider_account'] = 'Provider account must match the managed relationship when both are set.'

        if errors:
            raise ValidationError(errors)


class AuthoredAsSetMember(NamedRpkiStandardModel):
    authored_as_set = models.ForeignKey(
        to='AuthoredAsSet',
        on_delete=models.PROTECT,
        related_name='members',
    )
    member_type = models.CharField(
        max_length=16,
        choices=AuthoredAsSetMemberType.choices,
        default=AuthoredAsSetMemberType.ASN,
    )
    member_asn_value = models.BigIntegerField(blank=True, null=True)
    nested_set_name = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("authored_as_set", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_rpki:authoredassetmember", args=[self.pk])

    @property
    def member_text(self) -> str:
        if self.member_type == AuthoredAsSetMemberType.ASN and self.member_asn_value is not None:
            return f'AS{self.member_asn_value}'
        if self.member_type == AuthoredAsSetMemberType.AS_SET:
            return self.nested_set_name.strip().upper()
        return ''

    def clean(self):
        super().clean()
        errors = {}

        if self.member_type == AuthoredAsSetMemberType.ASN:
            if self.member_asn_value is None:
                errors['member_asn_value'] = 'ASN members require member_asn_value.'
            if self.nested_set_name:
                errors['nested_set_name'] = 'ASN members must not define nested_set_name.'
        elif self.member_type == AuthoredAsSetMemberType.AS_SET:
            if not self.nested_set_name.strip():
                errors['nested_set_name'] = 'AS-set members require nested_set_name.'
            if self.member_asn_value is not None:
                errors['member_asn_value'] = 'AS-set members must not define member_asn_value.'

        if errors:
            raise ValidationError(errors)


_register_plugin_action_urls()

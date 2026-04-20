"""Scale tier definitions and synthetic data generators for provider-scale load tests.

Three tiers model realistic RPKI operator estate sizes:

SMALL (100 ROA payloads)
    Representative of a small enterprise running a handful of prefixes.
    **Always runs** when the load-test lane is invoked — suitable for CI.

MEDIUM (500 ROA payloads)
    Representative of a large enterprise or regional operator.
    Opt-in: set ``NETBOX_RPKI_ENABLE_LOAD_TESTS=medium`` (or ``all``).

PROVIDER (5 000 ROA payloads)
    Representative of a CSP / hyperscale / NaaS operator.
    Opt-in: set ``NETBOX_RPKI_ENABLE_LOAD_TESTS=provider`` (or ``all``).

The synthetic batch builder (``build_synthetic_routinator_batch``) generates
deterministic Routinator-style import batches that feed directly into
:func:`~netbox_rpki.services.external_validation.persist_validation_run`
without requiring any pre-existing IPAM routing data.

Provenance
----------
Feature ID : TEST-006
Issue      : https://github.com/menckend/netbox_rpki/issues/65
Theme      : confidence-and-testing / scale
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Environment variable that controls which tiers run
# ---------------------------------------------------------------------------

LOAD_TEST_ENV_VAR = 'NETBOX_RPKI_ENABLE_LOAD_TESTS'
"""
Control which load-test tiers are executed.

Values
------
(unset)
    Only SMALL runs.  Safe for every CI job — SMALL completes in < 30 s.
medium
    SMALL + MEDIUM tiers run.
provider
    SMALL + MEDIUM + PROVIDER tiers run.
all
    Alias for ``provider``.
"""


# ---------------------------------------------------------------------------
# Scale tier descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScaleTier:
    """
    Describes a single load-test scale tier.

    Attributes
    ----------
    name:
        Human-readable label (e.g. ``'small'``).
    roa_payloads_per_snapshot:
        Number of ROA payload rows written per synthetic snapshot import.
        Drives ``ObjectValidationResult`` + ``ValidatedRoaPayload`` row counts.
    snapshot_count:
        Number of ``ValidationRun`` records created in the purge-scale scenario.
    import_budget_seconds:
        Maximum wall-clock seconds allowed for a single ``persist_validation_run``
        call.  Regression failures include the actual elapsed time.
    purge_budget_seconds:
        Maximum wall-clock seconds allowed for a single ``run_snapshot_purge``
        (dry-run) call over *snapshot_count* runs.
    query_budget_seconds:
        Maximum wall-clock seconds allowed for the aggregate dashboard query
        over *roa_payloads_per_snapshot* payload rows.
    """

    name: str
    roa_payloads_per_snapshot: int
    snapshot_count: int
    import_budget_seconds: float
    purge_budget_seconds: float
    query_budget_seconds: float


# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

SMALL = ScaleTier(
    name='small',
    roa_payloads_per_snapshot=100,
    snapshot_count=10,
    import_budget_seconds=30.0,
    purge_budget_seconds=10.0,
    query_budget_seconds=2.0,
)
"""SMALL: 100 ROA payloads/snapshot, 10 snapshots — always runs in CI."""

MEDIUM = ScaleTier(
    name='medium',
    roa_payloads_per_snapshot=500,
    snapshot_count=50,
    import_budget_seconds=90.0,
    purge_budget_seconds=30.0,
    query_budget_seconds=5.0,
)
"""MEDIUM: 500 ROA payloads/snapshot, 50 snapshots — opt-in (``medium`` or ``all``)."""

PROVIDER = ScaleTier(
    name='provider',
    roa_payloads_per_snapshot=5_000,
    snapshot_count=200,
    import_budget_seconds=600.0,
    purge_budget_seconds=120.0,
    query_budget_seconds=30.0,
)
"""PROVIDER: 5 000 ROA payloads/snapshot, 200 snapshots — opt-in (``provider`` or ``all``)."""

ALL_TIERS: tuple[ScaleTier, ...] = (SMALL, MEDIUM, PROVIDER)


# ---------------------------------------------------------------------------
# Tier gating helper
# ---------------------------------------------------------------------------

def is_tier_enabled(tier: ScaleTier) -> bool:
    """Return ``True`` if *tier* should run given the current environment.

    SMALL is always enabled.  MEDIUM and PROVIDER require the
    :data:`LOAD_TEST_ENV_VAR` environment variable to be set to the
    appropriate value.
    """
    if tier is SMALL:
        return True
    value = os.environ.get(LOAD_TEST_ENV_VAR, '').lower().strip()
    if value in ('all', 'provider'):
        return True
    if value == 'medium' and tier is MEDIUM:
        return True
    return False


# ---------------------------------------------------------------------------
# Synthetic batch builder
# ---------------------------------------------------------------------------

def build_synthetic_routinator_batch(roa_count: int, *, serial: str = '1') -> dict:
    """Build a synthetic Routinator-style import batch with *roa_count* ROA entries.

    The returned dict is suitable for direct use with
    :func:`~netbox_rpki.services.external_validation.persist_validation_run`.
    All FK fields (``roa_object``, ``prefix``, ``origin_as``) are ``None``,
    so no pre-existing IPAM data is needed.

    Provenance
    ----------
    - Addresses are drawn from ``10.0.0.0/8`` space; each /24 is unique
      for up to 65 536 entries.
    - ASNs cycle through ``AS65000``–``AS65999`` deterministically.
    - ``object_key`` values encode the *serial* so concurrent test runs with
      different serials do not collide.

    Parameters
    ----------
    roa_count:
        Number of ROA entries to generate.
    serial:
        Repository serial embedded in batch metadata and object keys.
        Use distinct serials for independent snapshots in purge tests.
    """
    observations: list[dict] = []
    payloads: list[dict] = []

    for i in range(roa_count):
        octet2 = (i // 256) % 256
        octet3 = i % 256
        observed_prefix = f'10.{octet2}.{octet3}.0/24'
        origin_asn = 65000 + (i % 1000)
        content_hash = f'load-hash-{serial}-{i:06d}'
        object_key = f'roa:rsync://load.example/pub/{serial}/roa-{i:06d}.roa:{content_hash}'

        observations.append({
            'object_key': object_key,
            'validation_state': 'valid',
            'disposition': 'noted',
            'match_status': 'unmatched',
            'external_object_uri': f'rsync://load.example/pub/{serial}/roa-{i:06d}.roa',
            'external_content_hash': content_hash,
            'observed_at': '2026-01-01T00:00:00+00:00',
            'reason': '',
            'details_json': {},
        })
        payloads.append({
            'object_key': object_key,
            'observed_prefix': observed_prefix,
            'max_length': 24,
            'details_json': {
                'vrp_kind': 'roa',
                'ta': 'load-ta',
                'source_record': {
                    'prefix': observed_prefix,
                    'asn': f'AS{origin_asn}',
                    'maxLength': 24,
                },
            },
        })

    return {
        'metadata': {
            'repository_serial': serial,
            'generated': '2026-01-01T00:00:00+00:00',
            'fetch_mode': 'snapshot_import',
        },
        'object_observations': observations,
        'roa_payloads': payloads,
        'aspa_payloads': [],
    }

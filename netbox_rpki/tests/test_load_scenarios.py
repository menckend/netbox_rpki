"""Load-test scenarios for provider-scale RPKI workflows.

Tests are organised into three scenario families, each offered at the SMALL,
MEDIUM, and PROVIDER scale tiers defined in ``load_scenarios.py``:

1. **Single-snapshot import** — measures wall-clock time for one
   ``persist_validation_run`` call at N ROA payloads.  The SMALL baseline
   always runs; MEDIUM and PROVIDER are opt-in via the
   ``NETBOX_RPKI_ENABLE_LOAD_TESTS`` environment variable.

2. **Snapshot-purge scale** — creates M ``ValidationRun`` records via
   ``bulk_create`` (cheap setup), then measures ``run_snapshot_purge``
   (dry-run) query and compute time.

3. **Aggregate dashboard query** — bulk-inserts N ``ValidatedRoaPayload``
   rows, then measures common ORM filter / aggregate patterns (count,
   state-distribution group-by, recent-runs list).

All timing assertions use generous budgets so a shared CI runner will not
produce spurious failures.  When a test *does* exceed the budget, the failure
message reports the actual elapsed time against the budget, making regression
triage straightforward.

Running load tests
------------------
::

    # Only SMALL tier (default CI):
    cd devrun && ./dev.sh test load

    # SMALL + MEDIUM:
    NETBOX_RPKI_ENABLE_LOAD_TESTS=medium ./dev.sh test load

    # All tiers (SMALL + MEDIUM + PROVIDER):
    NETBOX_RPKI_ENABLE_LOAD_TESTS=provider ./dev.sh test load

Provenance
----------
Feature ID : TEST-006
Issue      : https://github.com/menckend/netbox_rpki/issues/65
Theme      : confidence-and-testing / scale
"""
from __future__ import annotations

from datetime import timedelta
from time import perf_counter
from unittest import skipUnless

from django.db.models import Count
from django.test import TestCase
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.services.data_lifecycle import build_snapshot_storage_impact, run_snapshot_purge
from netbox_rpki.services.external_validation import persist_validation_run
from netbox_rpki.tests.load_scenarios import (
    LOAD_TEST_ENV_VAR,
    MEDIUM,
    PROVIDER,
    SMALL,
    ScaleTier,
    build_synthetic_routinator_batch,
    is_tier_enabled,
)
from netbox_rpki.tests.utils import (
    create_test_organization,
    create_test_snapshot_retention_policy,
    create_test_validator_instance,
)


# ---------------------------------------------------------------------------
# Shared mixin
# ---------------------------------------------------------------------------

class _LoadTestMixin:
    """Shared helpers for timing assertions."""

    def assertElapsedUnder(self, elapsed: float, budget: float, scenario_label: str = '') -> None:
        """Fail with an informative message if *elapsed* exceeds *budget* seconds."""
        label = f' [{scenario_label}]' if scenario_label else ''
        self.assertLess(
            elapsed,
            budget,
            f'Performance regression{label}: '
            f'{elapsed:.2f}s exceeded {budget:.0f}s budget.',
        )


# ---------------------------------------------------------------------------
# Scenario 1: Single-snapshot import throughput
#
# Measures persist_validation_run() wall-clock time for one synthetic
# snapshot batch.  Tests that DB INSERT throughput does not regress.
# ---------------------------------------------------------------------------

class _SingleImportTestBase(_LoadTestMixin):
    """Base for single-import throughput tests.

    Not a TestCase itself — concrete subclasses inherit from both this
    class and ``TestCase`` to prevent base-class discovery.
    """

    tier: ScaleTier

    def setUp(self):
        self.org = create_test_organization(
            org_id=f'load-{self.tier.name}',
            name=f'Load Test Org ({self.tier.name})',
        )
        self.validator = create_test_validator_instance(
            name=f'Load Validator ({self.tier.name})',
            organization=self.org,
            software_name='Routinator',
            base_url='https://load.example/',
        )

    def _make_run(self, serial: str) -> rpki_models.ValidationRun:
        return rpki_models.ValidationRun.objects.create(
            name=f'Load Import {self.tier.name} {serial}',
            validator=self.validator,
            status=rpki_models.ValidationRunStatus.RUNNING,
            started_at=timezone.now(),
            summary_json={},
        )

    def test_import_throughput(self):
        """persist_validation_run completes within the tier budget."""
        batch = build_synthetic_routinator_batch(
            self.tier.roa_payloads_per_snapshot, serial='import-1'
        )
        run = self._make_run('import-1')

        start = perf_counter()
        completed_run = persist_validation_run(run, batch)
        elapsed = perf_counter() - start

        self.assertElapsedUnder(elapsed, self.tier.import_budget_seconds, f'{self.tier.name} import')

        # Correctness: run status and row counts must be exact.
        self.assertEqual(completed_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertEqual(
            rpki_models.ValidatedRoaPayload.objects.filter(validation_run=run).count(),
            self.tier.roa_payloads_per_snapshot,
        )
        self.assertEqual(
            rpki_models.ObjectValidationResult.objects.filter(validation_run=run).count(),
            self.tier.roa_payloads_per_snapshot,
        )
        self.assertIn('validated_roa_payload_count', completed_run.summary_json)
        self.assertEqual(
            completed_run.summary_json['validated_roa_payload_count'],
            self.tier.roa_payloads_per_snapshot,
        )

    def test_repeated_import_idempotent_row_counts(self):
        """Two sequential imports each produce their own isolated payload rows."""
        for serial in ('repeat-1', 'repeat-2'):
            batch = build_synthetic_routinator_batch(
                self.tier.roa_payloads_per_snapshot, serial=serial
            )
            run = self._make_run(serial)
            persist_validation_run(run, batch)

        total = rpki_models.ValidatedRoaPayload.objects.filter(
            validation_run__validator=self.validator
        ).count()
        self.assertEqual(total, self.tier.roa_payloads_per_snapshot * 2)


class SmallEstateSingleImportTestCase(_SingleImportTestBase, TestCase):
    """SMALL tier — 100 ROA payloads.  Always runs in CI.

    Estate: 1 validator, 1 snapshot, 100 validated ROA payload rows.
    Budget: {import_budget}s for persist_validation_run.
    """.format(import_budget=SMALL.import_budget_seconds)
    tier = SMALL


@skipUnless(
    is_tier_enabled(MEDIUM),
    f'Set {LOAD_TEST_ENV_VAR}=medium (or all) to run medium-scale load tests.',
)
class MediumEstateSingleImportTestCase(_SingleImportTestBase, TestCase):
    """MEDIUM tier — 500 ROA payloads.  Opt-in via NETBOX_RPKI_ENABLE_LOAD_TESTS.

    Estate: 1 validator, 1 snapshot, 500 validated ROA payload rows.
    Budget: {import_budget}s for persist_validation_run.
    """.format(import_budget=MEDIUM.import_budget_seconds)
    tier = MEDIUM


@skipUnless(
    is_tier_enabled(PROVIDER),
    f'Set {LOAD_TEST_ENV_VAR}=provider (or all) to run provider-scale load tests.',
)
class ProviderEstateSingleImportTestCase(_SingleImportTestBase, TestCase):
    """PROVIDER tier — 5 000 ROA payloads.  Opt-in via NETBOX_RPKI_ENABLE_LOAD_TESTS.

    Estate: 1 validator, 1 snapshot, 5 000 validated ROA payload rows.
    Budget: {import_budget}s for persist_validation_run.
    """.format(import_budget=PROVIDER.import_budget_seconds)
    tier = PROVIDER


# ---------------------------------------------------------------------------
# Scenario 2: Snapshot-purge scale
#
# Creates M empty ValidationRun records (via bulk_create — fast setup),
# then measures build_snapshot_storage_impact and run_snapshot_purge
# (dry-run only) query/compute throughput.
# ---------------------------------------------------------------------------

class _PurgeScaleTestBase(_LoadTestMixin):
    """Base for snapshot-purge scale tests.

    Not a TestCase itself — concrete subclasses inherit from both this
    class and ``TestCase`` to prevent base-class discovery.
    """

    tier: ScaleTier

    # Keep only the 3 most-recent runs — ensures most of the M runs are
    # eligible for purge and the keep-set computation has work to do.
    _KEEP_COUNT = 3

    def setUp(self):
        self.org = create_test_organization(
            org_id=f'purge-{self.tier.name}',
            name=f'Purge Test Org ({self.tier.name})',
        )
        self.validator = create_test_validator_instance(
            name=f'Purge Validator ({self.tier.name})',
            organization=self.org,
        )
        self.policy = create_test_snapshot_retention_policy(
            name=f'Load Policy ({self.tier.name})',
            validator_run_keep_count=self._KEEP_COUNT,
        )
        self._bulk_create_runs(self.tier.snapshot_count)

    def _bulk_create_runs(self, count: int) -> None:
        """Cheaply insert *count* completed ValidationRun records."""
        now = timezone.now()
        runs = [
            rpki_models.ValidationRun(
                name=f'Bulk Run {self.tier.name} {i:05d}',
                validator=self.validator,
                status=rpki_models.ValidationRunStatus.COMPLETED,
                started_at=now - timedelta(days=i, hours=1),
                completed_at=now - timedelta(days=i),
                summary_json={},
            )
            for i in range(count)
        ]
        rpki_models.ValidationRun.objects.bulk_create(runs)

    def test_storage_impact_query_throughput(self):
        """build_snapshot_storage_impact completes within the tier budget."""
        start = perf_counter()
        impact = build_snapshot_storage_impact(self.policy)
        elapsed = perf_counter() - start

        self.assertElapsedUnder(elapsed, self.tier.purge_budget_seconds, f'{self.tier.name} storage-impact')

        # Correctness: the family entry must reflect the created runs.
        validator_family = next(
            f for f in impact['families'] if f['family'] == 'validator_run'
        )
        self.assertEqual(validator_family['total'], self.tier.snapshot_count)
        expected_purge = self.tier.snapshot_count - self._KEEP_COUNT
        self.assertEqual(validator_family['would_purge'], expected_purge)

    def test_dry_run_purge_throughput(self):
        """run_snapshot_purge(dry_run=True) completes within the tier budget."""
        start = perf_counter()
        purge_run = run_snapshot_purge(self.policy, dry_run=True)
        elapsed = perf_counter() - start

        self.assertElapsedUnder(elapsed, self.tier.purge_budget_seconds, f'{self.tier.name} dry-run purge')

        self.assertEqual(purge_run.status, rpki_models.ValidationRunStatus.COMPLETED)
        self.assertTrue(purge_run.dry_run)
        family_summary = purge_run.summary_json['families']['validator_run']
        self.assertEqual(family_summary['eligible'], self.tier.snapshot_count - self._KEEP_COUNT)
        # dry-run: nothing actually deleted.
        self.assertEqual(family_summary['purged'], 0)


class SmallEstatePurgeScaleTestCase(_PurgeScaleTestBase, TestCase):
    """SMALL purge tier — {count} ValidationRun records.  Always runs in CI.

    Budget: {budget}s for purge compute + queries.
    """.format(count=SMALL.snapshot_count, budget=SMALL.purge_budget_seconds)
    tier = SMALL


@skipUnless(
    is_tier_enabled(MEDIUM),
    f'Set {LOAD_TEST_ENV_VAR}=medium (or all) to run medium-scale load tests.',
)
class MediumEstatePurgeScaleTestCase(_PurgeScaleTestBase, TestCase):
    """MEDIUM purge tier — {count} ValidationRun records.  Opt-in.

    Budget: {budget}s for purge compute + queries.
    """.format(count=MEDIUM.snapshot_count, budget=MEDIUM.purge_budget_seconds)
    tier = MEDIUM


@skipUnless(
    is_tier_enabled(PROVIDER),
    f'Set {LOAD_TEST_ENV_VAR}=provider (or all) to run provider-scale load tests.',
)
class ProviderEstatePurgeScaleTestCase(_PurgeScaleTestBase, TestCase):
    """PROVIDER purge tier — {count} ValidationRun records.  Opt-in.

    Budget: {budget}s for purge compute + queries.
    """.format(count=PROVIDER.snapshot_count, budget=PROVIDER.purge_budget_seconds)
    tier = PROVIDER


# ---------------------------------------------------------------------------
# Scenario 3: Aggregate dashboard query performance
#
# Bulk-inserts N ValidatedRoaPayload rows (bypassing persist_validation_run
# for fast setup), then measures the ORM queries that drive the API list
# endpoint and dashboard count widgets.
# ---------------------------------------------------------------------------

class _QueryScaleTestBase(_LoadTestMixin):
    """Base for aggregate dashboard query tests.

    Not a TestCase itself — concrete subclasses inherit from both this
    class and ``TestCase`` to prevent base-class discovery.
    """

    tier: ScaleTier

    def setUp(self):
        self.org = create_test_organization(
            org_id=f'query-{self.tier.name}',
            name=f'Query Test Org ({self.tier.name})',
        )
        self.validator = create_test_validator_instance(
            name=f'Query Validator ({self.tier.name})',
            organization=self.org,
        )
        self.run = rpki_models.ValidationRun.objects.create(
            name=f'Query Run ({self.tier.name})',
            validator=self.validator,
            status=rpki_models.ValidationRunStatus.COMPLETED,
            started_at=timezone.now() - timedelta(minutes=5),
            completed_at=timezone.now(),
            summary_json={},
        )
        self._bulk_insert_payloads(self.tier.roa_payloads_per_snapshot)

    def _bulk_insert_payloads(self, count: int) -> None:
        """Cheaply bulk-insert *count* ValidatedRoaPayload rows."""
        rows = []
        for i in range(count):
            octet2 = (i // 256) % 256
            octet3 = i % 256
            state = (
                rpki_models.ValidationState.VALID if i % 5 != 0
                else rpki_models.ValidationState.INVALID
            )
            rows.append(
                rpki_models.ValidatedRoaPayload(
                    name=f'Query Payload {self.tier.name} {i:06d}',
                    validation_run=self.run,
                    observed_prefix=f'10.{octet2}.{octet3}.0/24',
                    max_length=24,
                    details_json={'vrp_kind': 'roa'},
                )
            )
        rpki_models.ValidatedRoaPayload.objects.bulk_create(rows, batch_size=1000)

    def test_payload_count_query_throughput(self):
        """COUNT(*) over all payloads for a run completes within budget."""
        start = perf_counter()
        count = rpki_models.ValidatedRoaPayload.objects.filter(
            validation_run=self.run
        ).count()
        elapsed = perf_counter() - start

        self.assertElapsedUnder(elapsed, self.tier.query_budget_seconds, f'{self.tier.name} count query')
        self.assertEqual(count, self.tier.roa_payloads_per_snapshot)

    def test_payload_prefix_list_query_throughput(self):
        """Fetching observed_prefix values from first page completes within budget."""
        start = perf_counter()
        prefixes = list(
            rpki_models.ValidatedRoaPayload.objects
            .filter(validation_run=self.run)
            .values_list('observed_prefix', flat=True)
            .order_by('observed_prefix')[:100]
        )
        elapsed = perf_counter() - start

        self.assertElapsedUnder(
            elapsed, self.tier.query_budget_seconds, f'{self.tier.name} prefix list query'
        )
        self.assertEqual(len(prefixes), min(100, self.tier.roa_payloads_per_snapshot))

    def test_recent_runs_list_query_throughput(self):
        """Listing recent ValidationRun records for a validator completes within budget."""
        start = perf_counter()
        runs = list(
            rpki_models.ValidationRun.objects
            .filter(validator=self.validator)
            .order_by('-completed_at')
            .values('pk', 'name', 'status', 'completed_at')[:25]
        )
        elapsed = perf_counter() - start

        self.assertElapsedUnder(
            elapsed, self.tier.query_budget_seconds, f'{self.tier.name} recent runs query'
        )
        self.assertGreaterEqual(len(runs), 1)


class SmallEstateQueryTestCase(_QueryScaleTestBase, TestCase):
    """SMALL query tier — {count} ValidatedRoaPayload rows.  Always runs in CI.

    Budget: {budget}s per query.
    """.format(count=SMALL.roa_payloads_per_snapshot, budget=SMALL.query_budget_seconds)
    tier = SMALL


@skipUnless(
    is_tier_enabled(MEDIUM),
    f'Set {LOAD_TEST_ENV_VAR}=medium (or all) to run medium-scale load tests.',
)
class MediumEstateQueryTestCase(_QueryScaleTestBase, TestCase):
    """MEDIUM query tier — {count} ValidatedRoaPayload rows.  Opt-in.

    Budget: {budget}s per query.
    """.format(count=MEDIUM.roa_payloads_per_snapshot, budget=MEDIUM.query_budget_seconds)
    tier = MEDIUM


@skipUnless(
    is_tier_enabled(PROVIDER),
    f'Set {LOAD_TEST_ENV_VAR}=provider (or all) to run provider-scale load tests.',
)
class ProviderEstateQueryTestCase(_QueryScaleTestBase, TestCase):
    """PROVIDER query tier — {count} ValidatedRoaPayload rows.  Opt-in.

    Budget: {budget}s per query.
    """.format(count=PROVIDER.roa_payloads_per_snapshot, budget=PROVIDER.query_budget_seconds)
    tier = PROVIDER

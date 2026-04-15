from netbox.jobs import JobRunner
from core.choices import JobStatusChoices
from core.models import Job

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    build_bulk_routing_intent_baseline_fingerprint,
    evaluate_lifecycle_health_events,
    run_aspa_reconciliation_pipeline,
    run_bulk_routing_intent_pipeline,
    run_routing_intent_pipeline,
    sync_irr_source,
    sync_provider_account,
)


class RunRoutingIntentProfileJob(JobRunner):
    class Meta:
        name = 'RPKI Intent Reconciliation'

    def run(self, profile_pk, comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS, provider_snapshot_pk=None, *args, **kwargs):
        profile = rpki_models.RoutingIntentProfile.objects.get(pk=profile_pk)
        self.logger.info(f'Running routing-intent pipeline for profile {profile.name} ({profile.pk})')
        derivation_run, reconciliation_run = run_routing_intent_pipeline(
            profile,
            trigger_mode=rpki_models.IntentRunTriggerMode.MANUAL,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        self.job.data = {
            'profile_pk': profile.pk,
            'derivation_run_pk': derivation_run.pk,
            'reconciliation_run_pk': reconciliation_run.pk,
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': provider_snapshot_pk,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(
            f'Completed routing-intent pipeline with derivation run {derivation_run.pk} '
            f'and reconciliation run {reconciliation_run.pk}'
        )


class RunAspaReconciliationJob(JobRunner):
    class Meta:
        name = 'ASPA Reconciliation'

    @classmethod
    def get_job_name(
        cls,
        organization: rpki_models.Organization | int,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
    ) -> str:
        organization_pk = organization.pk if hasattr(organization, 'pk') else organization
        return f'{cls.name} [{organization_pk}:{comparison_scope}]'

    @classmethod
    def get_active_job_for_organization(
        cls,
        organization: rpki_models.Organization | int,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(organization, comparison_scope),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_organization(
        cls,
        organization: rpki_models.Organization | int,
        *,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
        provider_snapshot=None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(organization, rpki_models.Organization):
            organization = rpki_models.Organization.objects.get(pk=organization)

        existing_job = cls.get_active_job_for_organization(organization, comparison_scope)
        if existing_job is not None:
            return existing_job, False

        running_filter = {
            'organization': organization,
            'status': rpki_models.ValidationRunStatus.RUNNING,
            'comparison_scope': comparison_scope,
        }
        if comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
            running_filter['provider_snapshot'] = provider_snapshot
        if rpki_models.ASPAReconciliationRun.objects.filter(**running_filter).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(organization, comparison_scope),
            user=user,
            schedule_at=schedule_at,
            organization_pk=organization.pk,
            comparison_scope=comparison_scope,
            provider_snapshot_pk=getattr(provider_snapshot, 'pk', provider_snapshot),
        )
        return job, True

    def run(
        self,
        organization_pk,
        comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
        provider_snapshot_pk=None,
        *args,
        **kwargs,
    ):
        organization = rpki_models.Organization.objects.get(pk=organization_pk)
        self.logger.info(f'Running ASPA reconciliation for organization {organization.name} ({organization.pk})')
        reconciliation_run = run_aspa_reconciliation_pipeline(
            organization,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        self.job.data = {
            'organization_pk': organization.pk,
            'aspa_reconciliation_run_pk': reconciliation_run.pk,
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': provider_snapshot_pk,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed ASPA reconciliation run {reconciliation_run.pk}')


class RunBulkRoutingIntentJob(JobRunner):
    class Meta:
        name = 'Bulk Routing Intent Run'

    @classmethod
    def _normalize_pk_tuple(cls, values):
        return tuple(sorted(int(getattr(value, 'pk', value)) for value in (values or ())))

    @classmethod
    def get_job_name(
        cls,
        organization: rpki_models.Organization | int,
        *,
        profiles=(),
        bindings=(),
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
        create_change_plans: bool = False,
    ) -> str:
        organization_pk = organization.pk if hasattr(organization, 'pk') else organization
        baseline_fingerprint = build_bulk_routing_intent_baseline_fingerprint(
            profiles=cls._normalize_pk_tuple(profiles),
            bindings=cls._normalize_pk_tuple(bindings),
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        )
        return f'{cls.name} [{organization_pk}:{baseline_fingerprint[:12]}]'

    @classmethod
    def get_active_job_for_request(
        cls,
        organization: rpki_models.Organization | int,
        *,
        profiles=(),
        bindings=(),
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
        create_change_plans: bool = False,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(
                organization,
                profiles=profiles,
                bindings=bindings,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
                create_change_plans=create_change_plans,
            ),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_organization(
        cls,
        organization: rpki_models.Organization | int,
        *,
        profiles=(),
        bindings=(),
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
        create_change_plans: bool = False,
        run_name: str | None = None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(organization, rpki_models.Organization):
            organization = rpki_models.Organization.objects.get(pk=organization)

        profile_pks = cls._normalize_pk_tuple(profiles)
        binding_pks = cls._normalize_pk_tuple(bindings)
        baseline_fingerprint = build_bulk_routing_intent_baseline_fingerprint(
            profiles=profile_pks,
            bindings=binding_pks,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        )

        existing_job = cls.get_active_job_for_request(
            organization,
            profiles=profile_pks,
            bindings=binding_pks,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        )
        if existing_job is not None:
            return existing_job, False

        if rpki_models.BulkIntentRun.objects.filter(
            organization=organization,
            status=rpki_models.ValidationRunStatus.RUNNING,
            baseline_fingerprint=baseline_fingerprint,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(
                organization,
                profiles=profile_pks,
                bindings=binding_pks,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
                create_change_plans=create_change_plans,
            ),
            user=user,
            schedule_at=schedule_at,
            organization_pk=organization.pk,
            profile_pks=profile_pks,
            binding_pks=binding_pks,
            comparison_scope=comparison_scope,
            provider_snapshot_pk=getattr(provider_snapshot, 'pk', provider_snapshot),
            create_change_plans=create_change_plans,
            run_name=run_name,
        )
        return job, True

    def run(
        self,
        organization_pk,
        profile_pks=(),
        binding_pks=(),
        comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot_pk=None,
        create_change_plans=False,
        run_name=None,
        *args,
        **kwargs,
    ):
        organization = rpki_models.Organization.objects.get(pk=organization_pk)
        profiles = tuple(rpki_models.RoutingIntentProfile.objects.filter(pk__in=tuple(profile_pks)).order_by('pk'))
        bindings = tuple(
            rpki_models.RoutingIntentTemplateBinding.objects.filter(pk__in=tuple(binding_pks)).order_by('pk')
        )
        self.logger.info(
            f'Running bulk routing-intent pipeline for organization {organization.name} ({organization.pk})'
        )
        bulk_run = run_bulk_routing_intent_pipeline(
            organization=organization,
            profiles=profiles,
            bindings=bindings,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
            create_change_plans=create_change_plans,
            run_name=run_name,
        )
        self.job.data = {
            'organization_pk': organization.pk,
            'bulk_intent_run_pk': bulk_run.pk,
            'profile_pks': list(profile_pks),
            'binding_pks': list(binding_pks),
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': provider_snapshot_pk,
            'create_change_plans': create_change_plans,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed bulk routing-intent run {bulk_run.pk}')


class SyncProviderAccountJob(JobRunner):
    class Meta:
        name = 'Provider ROA Sync'

    @classmethod
    def get_job_name(cls, provider_account: rpki_models.RpkiProviderAccount | int) -> str:
        provider_account_pk = provider_account.pk if hasattr(provider_account, 'pk') else provider_account
        return f'{cls.name} [{provider_account_pk}]'

    @classmethod
    def get_active_job_for_provider_account(cls, provider_account: rpki_models.RpkiProviderAccount | int):
        return Job.objects.filter(
            name=cls.get_job_name(provider_account),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_provider_account(
        cls,
        provider_account: rpki_models.RpkiProviderAccount | int,
        *,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(provider_account, rpki_models.RpkiProviderAccount):
            provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account)

        if not provider_account.sync_enabled:
            raise ValueError(f'Provider account {provider_account.name} is disabled for sync.')

        existing_job = cls.get_active_job_for_provider_account(provider_account)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.ProviderSyncRun.objects.filter(
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(provider_account),
            user=user,
            schedule_at=schedule_at,
            provider_account_pk=provider_account.pk,
        )
        return job, True

    def run(self, provider_account_pk, *args, **kwargs):
        provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account_pk)
        self.logger.info(f'Running provider sync for account {provider_account.name} ({provider_account.pk})')
        sync_run, snapshot = sync_provider_account(provider_account)
        self.job.data = {
            'provider_account_pk': provider_account.pk,
            'provider_sync_run_pk': sync_run.pk,
            'provider_snapshot_pk': snapshot.pk,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(
            f'Completed provider sync with sync run {sync_run.pk} and provider snapshot {snapshot.pk}'
        )


class SyncIrrSourceJob(JobRunner):
    class Meta:
        name = 'IRR Source Import'

    @classmethod
    def get_job_name(
        cls,
        irr_source: rpki_models.IrrSource | int,
        *,
        fetch_mode: str = rpki_models.IrrFetchMode.LIVE_QUERY,
        snapshot_file: str | None = None,
    ) -> str:
        irr_source_pk = irr_source.pk if hasattr(irr_source, 'pk') else irr_source
        suffix = f':{snapshot_file}' if snapshot_file else ''
        return f'{cls.name} [{irr_source_pk}:{fetch_mode}{suffix}]'

    @classmethod
    def get_active_job_for_source(
        cls,
        irr_source: rpki_models.IrrSource | int,
        *,
        fetch_mode: str = rpki_models.IrrFetchMode.LIVE_QUERY,
        snapshot_file: str | None = None,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(irr_source, fetch_mode=fetch_mode, snapshot_file=snapshot_file),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_source(
        cls,
        irr_source: rpki_models.IrrSource | int,
        *,
        fetch_mode: str = rpki_models.IrrFetchMode.LIVE_QUERY,
        snapshot_file: str | None = None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(irr_source, rpki_models.IrrSource):
            irr_source = rpki_models.IrrSource.objects.get(pk=irr_source)

        if not irr_source.enabled:
            raise ValueError(f'IRR source {irr_source.name} is disabled.')

        existing_job = cls.get_active_job_for_source(
            irr_source,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        if existing_job is not None:
            return existing_job, False

        if rpki_models.IrrSnapshot.objects.filter(
            source=irr_source,
            status=rpki_models.IrrSnapshotStatus.RUNNING,
            fetch_mode=fetch_mode,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(irr_source, fetch_mode=fetch_mode, snapshot_file=snapshot_file),
            user=user,
            schedule_at=schedule_at,
            irr_source_pk=irr_source.pk,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        return job, True

    def run(
        self,
        irr_source_pk,
        fetch_mode=rpki_models.IrrFetchMode.LIVE_QUERY,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        irr_source = rpki_models.IrrSource.objects.get(pk=irr_source_pk)
        self.logger.info(f'Running IRR import for source {irr_source.name} ({irr_source.pk})')
        snapshot = sync_irr_source(
            irr_source,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        self.job.data = {
            'irr_source_pk': irr_source.pk,
            'irr_snapshot_pk': snapshot.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed IRR import with snapshot {snapshot.pk}')


class EvaluateLifecycleHealthJob(JobRunner):
    class Meta:
        name = 'Lifecycle Health Evaluation'

    @classmethod
    def get_job_name(cls, provider_account: rpki_models.RpkiProviderAccount | int) -> str:
        provider_account_pk = provider_account.pk if hasattr(provider_account, 'pk') else provider_account
        return f'{cls.name} [{provider_account_pk}]'

    @classmethod
    def get_active_job_for_provider_account(cls, provider_account: rpki_models.RpkiProviderAccount | int):
        return Job.objects.filter(
            name=cls.get_job_name(provider_account),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_provider_account(
        cls,
        provider_account: rpki_models.RpkiProviderAccount | int,
        *,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(provider_account, rpki_models.RpkiProviderAccount):
            provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account)

        existing_job = cls.get_active_job_for_provider_account(provider_account)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.LifecycleHealthEvent.objects.filter(
            provider_account=provider_account,
            status=rpki_models.LifecycleHealthEventStatus.OPEN,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(provider_account),
            user=user,
            schedule_at=schedule_at,
            provider_account_pk=provider_account.pk,
        )
        return job, True

    def run(self, provider_account_pk, *args, **kwargs):
        provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account_pk)
        self.logger.info(
            f'Evaluating lifecycle-health events for provider account {provider_account.name} ({provider_account.pk})'
        )
        result = evaluate_lifecycle_health_events(provider_account)
        self.job.data = {
            'provider_account_pk': provider_account.pk,
            'candidate_count': result['candidate_count'],
            'event_count': result['event_count'],
            'opened_count': result['opened_count'],
            'repeated_count': result['repeated_count'],
            'resolved_count': result['resolved_count'],
        }
        self.job.save(update_fields=('data',))
        self.logger.info(
            f'Completed lifecycle-health evaluation with {result["event_count"]} event(s)'
        )

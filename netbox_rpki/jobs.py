from netbox.jobs import JobRunner
from core.choices import JobStatusChoices
from core.models import Job

from netbox_rpki import models as rpki_models
from netbox_rpki.services import (
    TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
    VALIDATOR_FETCH_MODE_LIVE_API,
    apply_irr_change_plan,
    build_bulk_routing_intent_baseline_fingerprint,
    create_irr_change_plans,
    evaluate_lifecycle_health_events,
    preview_irr_change_plan,
    run_aspa_reconciliation_pipeline,
    run_bulk_routing_intent_pipeline,
    run_irr_coordination,
    run_routing_intent_pipeline,
    sync_telemetry_source,
    sync_irr_source,
    sync_provider_account,
    sync_validator_instance,
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


class SyncValidatorInstanceJob(JobRunner):
    class Meta:
        name = 'Validator Import'

    @classmethod
    def get_job_name(
        cls,
        validator: rpki_models.ValidatorInstance | int,
        *,
        fetch_mode: str = VALIDATOR_FETCH_MODE_LIVE_API,
        snapshot_file: str | None = None,
    ) -> str:
        validator_pk = validator.pk if hasattr(validator, 'pk') else validator
        suffix = f':{snapshot_file}' if snapshot_file else ''
        return f'{cls.name} [{validator_pk}:{fetch_mode}{suffix}]'

    @classmethod
    def get_active_job_for_validator(
        cls,
        validator: rpki_models.ValidatorInstance | int,
        *,
        fetch_mode: str = VALIDATOR_FETCH_MODE_LIVE_API,
        snapshot_file: str | None = None,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(validator, fetch_mode=fetch_mode, snapshot_file=snapshot_file),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_validator(
        cls,
        validator: rpki_models.ValidatorInstance | int,
        *,
        fetch_mode: str = VALIDATOR_FETCH_MODE_LIVE_API,
        snapshot_file: str | None = None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(validator, rpki_models.ValidatorInstance):
            validator = rpki_models.ValidatorInstance.objects.get(pk=validator)

        existing_job = cls.get_active_job_for_validator(
            validator,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        if existing_job is not None:
            return existing_job, False

        if rpki_models.ValidationRun.objects.filter(
            validator=validator,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(validator, fetch_mode=fetch_mode, snapshot_file=snapshot_file),
            user=user,
            schedule_at=schedule_at,
            validator_pk=validator.pk,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        return job, True

    def run(
        self,
        validator_pk,
        fetch_mode=VALIDATOR_FETCH_MODE_LIVE_API,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        validator = rpki_models.ValidatorInstance.objects.get(pk=validator_pk)
        self.logger.info(f'Running validator import for {validator.name} ({validator.pk})')
        run = sync_validator_instance(
            validator,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        self.job.data = {
            'validator_pk': validator.pk,
            'validation_run_pk': run.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed validator import with validation run {run.pk}')


class SyncTelemetrySourceJob(JobRunner):
    class Meta:
        name = 'Telemetry Import'

    @classmethod
    def get_job_name(
        cls,
        source: rpki_models.TelemetrySource | int,
        *,
        snapshot_file: str,
    ) -> str:
        source_pk = source.pk if hasattr(source, 'pk') else source
        return f'{cls.name} [{source_pk}:{snapshot_file}]'

    @classmethod
    def get_active_job_for_source(
        cls,
        source: rpki_models.TelemetrySource | int,
        *,
        snapshot_file: str,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(source, snapshot_file=snapshot_file),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_source(
        cls,
        source: rpki_models.TelemetrySource | int,
        *,
        snapshot_file: str,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(source, rpki_models.TelemetrySource):
            source = rpki_models.TelemetrySource.objects.get(pk=source)

        if not source.enabled:
            raise ValueError(f'Telemetry source {source.name} is disabled.')

        existing_job = cls.get_active_job_for_source(source, snapshot_file=snapshot_file)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.TelemetryRun.objects.filter(
            source=source,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(source, snapshot_file=snapshot_file),
            user=user,
            schedule_at=schedule_at,
            telemetry_source_pk=source.pk,
            fetch_mode=TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
            snapshot_file=snapshot_file,
        )
        return job, True

    def run(
        self,
        telemetry_source_pk,
        fetch_mode=TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        source = rpki_models.TelemetrySource.objects.get(pk=telemetry_source_pk)
        self.logger.info(f'Running telemetry import for source {source.name} ({source.pk})')
        run = sync_telemetry_source(source, snapshot_file=snapshot_file)
        self.job.data = {
            'telemetry_source_pk': source.pk,
            'telemetry_run_pk': run.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed telemetry import with run {run.pk}')


class RunIrrCoordinationJob(JobRunner):
    class Meta:
        name = 'IRR Coordination'

    @classmethod
    def get_job_name(cls, organization: rpki_models.Organization | int) -> str:
        organization_pk = organization.pk if hasattr(organization, 'pk') else organization
        return f'{cls.name} [{organization_pk}]'

    @classmethod
    def get_active_job_for_organization(cls, organization: rpki_models.Organization | int):
        return Job.objects.filter(
            name=cls.get_job_name(organization),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_organization(
        cls,
        organization: rpki_models.Organization | int,
        *,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(organization, rpki_models.Organization):
            organization = rpki_models.Organization.objects.get(pk=organization)

        existing_job = cls.get_active_job_for_organization(organization)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.IrrCoordinationRun.objects.filter(
            organization=organization,
            status=rpki_models.IrrCoordinationRunStatus.RUNNING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(organization),
            user=user,
            schedule_at=schedule_at,
            organization_pk=organization.pk,
        )
        return job, True

    def run(self, organization_pk, *args, **kwargs):
        organization = rpki_models.Organization.objects.get(pk=organization_pk)
        self.logger.info(f'Running IRR coordination for organization {organization.name} ({organization.pk})')
        coordination_run = run_irr_coordination(organization)
        self.job.data = {
            'organization_pk': organization.pk,
            'irr_coordination_run_pk': coordination_run.pk,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed IRR coordination run {coordination_run.pk}')


class CreateIrrChangePlansJob(JobRunner):
    class Meta:
        name = 'IRR Change Plan Drafting'

    @classmethod
    def get_job_name(cls, coordination_run: rpki_models.IrrCoordinationRun | int) -> str:
        coordination_run_pk = coordination_run.pk if hasattr(coordination_run, 'pk') else coordination_run
        return f'{cls.name} [{coordination_run_pk}]'

    @classmethod
    def get_active_job_for_coordination_run(cls, coordination_run: rpki_models.IrrCoordinationRun | int):
        return Job.objects.filter(
            name=cls.get_job_name(coordination_run),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_coordination_run(
        cls,
        coordination_run: rpki_models.IrrCoordinationRun | int,
        *,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(coordination_run, rpki_models.IrrCoordinationRun):
            coordination_run = rpki_models.IrrCoordinationRun.objects.get(pk=coordination_run)

        existing_job = cls.get_active_job_for_coordination_run(coordination_run)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.IrrChangePlan.objects.filter(
            coordination_run=coordination_run,
            status=rpki_models.IrrChangePlanStatus.EXECUTING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(coordination_run),
            user=user,
            schedule_at=schedule_at,
            coordination_run_pk=coordination_run.pk,
        )
        return job, True

    def run(self, coordination_run_pk, *args, **kwargs):
        coordination_run = rpki_models.IrrCoordinationRun.objects.get(pk=coordination_run_pk)
        self.logger.info(f'Creating IRR change plans for coordination run {coordination_run.name} ({coordination_run.pk})')
        plans = create_irr_change_plans(coordination_run)
        self.job.data = {
            'irr_coordination_run_pk': coordination_run.pk,
            'irr_change_plan_pks': [plan.pk for plan in plans],
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Created {len(plans)} IRR change plans for coordination run {coordination_run.pk}')


class ExecuteIrrChangePlanJob(JobRunner):
    class Meta:
        name = 'IRR Change Plan Execution'

    @classmethod
    def get_job_name(
        cls,
        change_plan: rpki_models.IrrChangePlan | int,
        *,
        execution_mode: str = rpki_models.IrrWriteExecutionMode.PREVIEW,
    ) -> str:
        change_plan_pk = change_plan.pk if hasattr(change_plan, 'pk') else change_plan
        return f'{cls.name} [{change_plan_pk}:{execution_mode}]'

    @classmethod
    def get_active_job_for_change_plan(
        cls,
        change_plan: rpki_models.IrrChangePlan | int,
        *,
        execution_mode: str = rpki_models.IrrWriteExecutionMode.PREVIEW,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(change_plan, execution_mode=execution_mode),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_change_plan(
        cls,
        change_plan: rpki_models.IrrChangePlan | int,
        *,
        execution_mode: str = rpki_models.IrrWriteExecutionMode.PREVIEW,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(change_plan, rpki_models.IrrChangePlan):
            change_plan = rpki_models.IrrChangePlan.objects.get(pk=change_plan)

        existing_job = cls.get_active_job_for_change_plan(change_plan, execution_mode=execution_mode)
        if existing_job is not None:
            return existing_job, False

        if rpki_models.IrrWriteExecution.objects.filter(
            change_plan=change_plan,
            execution_mode=execution_mode,
            status=rpki_models.IrrWriteExecutionStatus.RUNNING,
        ).exists():
            return None, False

        job = cls.enqueue(
            name=cls.get_job_name(change_plan, execution_mode=execution_mode),
            user=user,
            schedule_at=schedule_at,
            change_plan_pk=change_plan.pk,
            execution_mode=execution_mode,
        )
        return job, True

    def run(
        self,
        change_plan_pk,
        execution_mode=rpki_models.IrrWriteExecutionMode.PREVIEW,
        *args,
        **kwargs,
    ):
        change_plan = rpki_models.IrrChangePlan.objects.get(pk=change_plan_pk)
        self.logger.info(
            f'Running IRR change plan {execution_mode} for {change_plan.name} ({change_plan.pk})'
        )
        if execution_mode == rpki_models.IrrWriteExecutionMode.APPLY:
            execution, _ = apply_irr_change_plan(change_plan)
        else:
            execution, _ = preview_irr_change_plan(change_plan)
        self.job.data = {
            'irr_change_plan_pk': change_plan.pk,
            'irr_write_execution_pk': execution.pk,
            'execution_mode': execution_mode,
        }
        self.job.save(update_fields=('data',))
        self.logger.info(f'Completed IRR change plan {execution_mode} as execution {execution.pk}')


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

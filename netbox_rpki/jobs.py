from netbox.jobs import JobRunner
from core.choices import JobStatusChoices
from core.models import Job
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.structured_logging import emit_structured_log
from netbox_rpki.services import (
    TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
    VALIDATOR_FETCH_MODE_LIVE_API,
    apply_irr_change_plan,
    build_bulk_routing_intent_baseline_fingerprint,
    create_irr_change_plans,
    create_roa_change_plan,
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


def _requested_by_value(user) -> str:
    if user is None:
        return ''
    if isinstance(user, str):
        return user
    return getattr(user, 'username', '') or ''


def _serialize_job_reference(job: Job | None) -> dict:
    if job is None:
        return {}
    return {
        'id': job.pk,
        'name': job.name,
        'status': job.status,
    }


def _record_job_execution(
    *,
    organization=None,
    job: Job | None = None,
    job_class: str,
    job_name: str,
    dedupe_key: str,
    disposition: str,
    requested_by: str = '',
    schedule_at=None,
    request_payload=None,
    resolution_payload=None,
):
    recorded_at = timezone.now()
    create_kwargs = {
        'name': f'{job_name} {rpki_models.JobExecutionDisposition(disposition).label} {recorded_at:%Y-%m-%d %H:%M:%S}',
        'job': job,
        'job_class': job_class,
        'job_name': job_name,
        'dedupe_key': dedupe_key,
        'disposition': disposition,
        'requested_by': requested_by,
        'scheduled_at': schedule_at,
        'request_payload_json': request_payload or {},
        'resolution_payload_json': resolution_payload or {},
    }
    if isinstance(organization, rpki_models.Organization):
        create_kwargs['organization'] = organization
    elif organization is not None:
        create_kwargs['organization_id'] = organization
    return rpki_models.JobExecutionRecord.objects.create(
        **create_kwargs,
    )


def _enqueue_with_lineage(
    *,
    job_runner_class,
    organization=None,
    job_name: str,
    dedupe_key: str,
    request_payload: dict,
    user=None,
    schedule_at=None,
    existing_job: Job | None = None,
    skip_resolution: dict | None = None,
    enqueue_kwargs: dict | None = None,
):
    requested_by = _requested_by_value(user)
    job_class = job_runner_class.__name__

    if existing_job is not None:
        _record_job_execution(
            organization=organization,
            job=existing_job,
            job_class=job_class,
            job_name=job_name,
            dedupe_key=dedupe_key,
            disposition=rpki_models.JobExecutionDisposition.MERGED,
            requested_by=requested_by,
            schedule_at=schedule_at,
            request_payload=request_payload,
            resolution_payload={
                'reason': 'active_job',
                'job': _serialize_job_reference(existing_job),
            },
        )
        emit_structured_log(
            'job.enqueue.decision',
            subsystem='jobs',
            job_class=job_class,
            job_name=job_name,
            dedupe_key=dedupe_key,
            disposition=rpki_models.JobExecutionDisposition.MERGED,
            requested_by=requested_by,
            existing_job_id=existing_job.pk,
        )
        return existing_job, False

    if skip_resolution is not None:
        _record_job_execution(
            organization=organization,
            job_class=job_class,
            job_name=job_name,
            dedupe_key=dedupe_key,
            disposition=rpki_models.JobExecutionDisposition.SKIPPED,
            requested_by=requested_by,
            schedule_at=schedule_at,
            request_payload=request_payload,
            resolution_payload=skip_resolution,
        )
        emit_structured_log(
            'job.enqueue.decision',
            subsystem='jobs',
            job_class=job_class,
            job_name=job_name,
            dedupe_key=dedupe_key,
            disposition=rpki_models.JobExecutionDisposition.SKIPPED,
            requested_by=requested_by,
            skip_reason=skip_resolution.get('reason'),
        )
        return None, False

    job = job_runner_class.enqueue(
        name=job_name,
        user=user,
        schedule_at=schedule_at,
        **(enqueue_kwargs or {}),
    )
    _record_job_execution(
        organization=organization,
        job=job,
        job_class=job_class,
        job_name=job_name,
        dedupe_key=dedupe_key,
        disposition=rpki_models.JobExecutionDisposition.ENQUEUED,
        requested_by=requested_by,
        schedule_at=schedule_at,
        request_payload=request_payload,
        resolution_payload={
            'reason': 'job_enqueued',
            'job': _serialize_job_reference(job),
        },
    )
    emit_structured_log(
        'job.enqueue.decision',
        subsystem='jobs',
        job_class=job_class,
        job_name=job_name,
        dedupe_key=dedupe_key,
        disposition=rpki_models.JobExecutionDisposition.ENQUEUED,
        requested_by=requested_by,
        job_id=job.pk,
    )
    return job, True


class RunRoutingIntentProfileJob(JobRunner):
    class Meta:
        name = 'RPKI Intent Reconciliation'

    @classmethod
    def get_job_name(
        cls,
        profile: rpki_models.RoutingIntentProfile | int,
        *,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
    ) -> str:
        profile_pk = profile.pk if hasattr(profile, 'pk') else profile
        provider_snapshot_pk = getattr(provider_snapshot, 'pk', provider_snapshot) or 'none'
        return f'{cls.name} [{profile_pk}:{comparison_scope}:{provider_snapshot_pk}]'

    @classmethod
    def get_active_job_for_profile(
        cls,
        profile: rpki_models.RoutingIntentProfile | int,
        *,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(
                profile,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
            ),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_profile(
        cls,
        profile: rpki_models.RoutingIntentProfile | int,
        *,
        comparison_scope: str = rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
        provider_snapshot=None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(profile, rpki_models.RoutingIntentProfile):
            profile = rpki_models.RoutingIntentProfile.objects.get(pk=profile)

        provider_snapshot_pk = getattr(provider_snapshot, 'pk', provider_snapshot)
        job_name = cls.get_job_name(
            profile,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        dedupe_key = job_name
        request_payload = {
            'profile_pk': profile.pk,
            'organization_pk': profile.organization_id,
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': provider_snapshot_pk,
        }
        existing_job = cls.get_active_job_for_profile(
            profile,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        if comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
            running_filter = {
                'intent_profile': profile,
                'status': rpki_models.ValidationRunStatus.RUNNING,
                'comparison_scope': comparison_scope,
                'provider_snapshot': provider_snapshot,
            }
        else:
            running_filter = {
                'intent_profile': profile,
                'status': rpki_models.ValidationRunStatus.RUNNING,
                'comparison_scope': comparison_scope,
            }
        skip_resolution = None
        active_run = rpki_models.ROAReconciliationRun.objects.filter(**running_filter).order_by('-started_at', '-pk').first()
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_reconciliation',
                'run_model': 'ROAReconciliationRun',
                'run_id': active_run.pk,
                'comparison_scope': comparison_scope,
                'provider_snapshot_pk': provider_snapshot_pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=profile.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'profile_pk': profile.pk,
                'comparison_scope': comparison_scope,
                'provider_snapshot_pk': provider_snapshot_pk,
            },
        )

    def run(self, profile_pk, comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS, provider_snapshot_pk=None, *args, **kwargs):
        profile = rpki_models.RoutingIntentProfile.objects.get(pk=profile_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            profile_id=profile.pk,
            profile_name=profile.name,
            comparison_scope=comparison_scope,
            provider_snapshot_pk=provider_snapshot_pk,
        )
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            profile_id=profile.pk,
            derivation_run_pk=derivation_run.pk,
            reconciliation_run_pk=reconciliation_run.pk,
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

        provider_snapshot_pk = getattr(provider_snapshot, 'pk', provider_snapshot)
        job_name = cls.get_job_name(organization, comparison_scope)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': organization.pk,
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': provider_snapshot_pk,
        }
        existing_job = cls.get_active_job_for_organization(organization, comparison_scope)
        running_filter = {
            'organization': organization,
            'status': rpki_models.ValidationRunStatus.RUNNING,
            'comparison_scope': comparison_scope,
        }
        if comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED:
            running_filter['provider_snapshot'] = provider_snapshot
        active_run = rpki_models.ASPAReconciliationRun.objects.filter(**running_filter).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_reconciliation',
                'run_model': 'ASPAReconciliationRun',
                'run_id': active_run.pk,
                'comparison_scope': comparison_scope,
                'provider_snapshot_pk': provider_snapshot_pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'organization_pk': organization.pk,
                'comparison_scope': comparison_scope,
                'provider_snapshot_pk': provider_snapshot_pk,
            },
        )

    def run(
        self,
        organization_pk,
        comparison_scope=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
        provider_snapshot_pk=None,
        *args,
        **kwargs,
    ):
        organization = rpki_models.Organization.objects.get(pk=organization_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            organization_name=organization.name,
            comparison_scope=comparison_scope,
            provider_snapshot_pk=provider_snapshot_pk,
        )
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            reconciliation_run_pk=reconciliation_run.pk,
        )


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
        job_name = cls.get_job_name(
            organization,
            profiles=profile_pks,
            bindings=binding_pks,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        )
        dedupe_key = f'{organization.pk}:{baseline_fingerprint}'
        request_payload = {
            'organization_pk': organization.pk,
            'profile_pks': list(profile_pks),
            'binding_pks': list(binding_pks),
            'comparison_scope': comparison_scope,
            'provider_snapshot_pk': getattr(provider_snapshot, 'pk', provider_snapshot),
            'create_change_plans': create_change_plans,
            'run_name': run_name,
            'baseline_fingerprint': baseline_fingerprint,
        }

        existing_job = cls.get_active_job_for_request(
            organization,
            profiles=profile_pks,
            bindings=binding_pks,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
        )
        active_run = rpki_models.BulkIntentRun.objects.filter(
            organization=organization,
            status=rpki_models.ValidationRunStatus.RUNNING,
            baseline_fingerprint=baseline_fingerprint,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_bulk_run',
                'run_model': 'BulkIntentRun',
                'run_id': active_run.pk,
                'baseline_fingerprint': baseline_fingerprint,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'organization_pk': organization.pk,
                'profile_pks': profile_pks,
                'binding_pks': binding_pks,
                'comparison_scope': comparison_scope,
                'provider_snapshot_pk': getattr(provider_snapshot, 'pk', provider_snapshot),
                'create_change_plans': create_change_plans,
                'run_name': run_name,
            },
        )

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
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            organization_name=organization.name,
            profile_pks=list(profile_pks),
            binding_pks=list(binding_pks),
            comparison_scope=comparison_scope,
            provider_snapshot_pk=provider_snapshot_pk,
            create_change_plans=create_change_plans,
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            bulk_intent_run_pk=bulk_run.pk,
        )


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

        job_name = cls.get_job_name(provider_account)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': provider_account.organization_id,
            'provider_account_pk': provider_account.pk,
        }
        existing_job = cls.get_active_job_for_provider_account(provider_account)
        active_run = rpki_models.ProviderSyncRun.objects.filter(
            provider_account=provider_account,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_provider_sync',
                'run_model': 'ProviderSyncRun',
                'run_id': active_run.pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=provider_account.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'provider_account_pk': provider_account.pk,
            },
        )

    def run(self, provider_account_pk, *args, **kwargs):
        provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            provider_account_id=provider_account.pk,
            provider_account_name=provider_account.name,
            provider_type=provider_account.provider_type,
        )
        sync_run, snapshot = sync_provider_account(provider_account)
        self.job.data = {
            'provider_account_pk': provider_account.pk,
            'provider_sync_run_pk': sync_run.pk,
            'provider_snapshot_pk': snapshot.pk,
        }
        self.job.save(update_fields=('data',))
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            provider_account_id=provider_account.pk,
            provider_sync_run_pk=sync_run.pk,
            provider_snapshot_pk=snapshot.pk,
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

        job_name = cls.get_job_name(irr_source, fetch_mode=fetch_mode, snapshot_file=snapshot_file)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': irr_source.organization_id,
            'irr_source_pk': irr_source.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        existing_job = cls.get_active_job_for_source(
            irr_source,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        active_run = rpki_models.IrrSnapshot.objects.filter(
            source=irr_source,
            status=rpki_models.IrrSnapshotStatus.RUNNING,
            fetch_mode=fetch_mode,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_irr_snapshot',
                'run_model': 'IrrSnapshot',
                'run_id': active_run.pk,
                'fetch_mode': fetch_mode,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=irr_source.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'irr_source_pk': irr_source.pk,
                'fetch_mode': fetch_mode,
                'snapshot_file': snapshot_file,
            },
        )

    def run(
        self,
        irr_source_pk,
        fetch_mode=rpki_models.IrrFetchMode.LIVE_QUERY,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        irr_source = rpki_models.IrrSource.objects.get(pk=irr_source_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_source_id=irr_source.pk,
            irr_source_name=irr_source.name,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_source_id=irr_source.pk,
            irr_snapshot_pk=snapshot.pk,
        )


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

        job_name = cls.get_job_name(validator, fetch_mode=fetch_mode, snapshot_file=snapshot_file)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': validator.organization_id,
            'validator_pk': validator.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        existing_job = cls.get_active_job_for_validator(
            validator,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        active_run = rpki_models.ValidationRun.objects.filter(
            validator=validator,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_validation',
                'run_model': 'ValidationRun',
                'run_id': active_run.pk,
                'fetch_mode': fetch_mode,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=validator.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'validator_pk': validator.pk,
                'fetch_mode': fetch_mode,
                'snapshot_file': snapshot_file,
            },
        )

    def run(
        self,
        validator_pk,
        fetch_mode=VALIDATOR_FETCH_MODE_LIVE_API,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        validator = rpki_models.ValidatorInstance.objects.get(pk=validator_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            validator_id=validator.pk,
            validator_name=validator.name,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            validator_id=validator.pk,
            validation_run_pk=run.pk,
        )


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

        job_name = cls.get_job_name(source, snapshot_file=snapshot_file)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': source.organization_id,
            'telemetry_source_pk': source.pk,
            'fetch_mode': TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
            'snapshot_file': snapshot_file,
        }
        existing_job = cls.get_active_job_for_source(source, snapshot_file=snapshot_file)
        active_run = rpki_models.TelemetryRun.objects.filter(
            source=source,
            status=rpki_models.ValidationRunStatus.RUNNING,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_telemetry_import',
                'run_model': 'TelemetryRun',
                'run_id': active_run.pk,
                'snapshot_file': snapshot_file,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=source.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'telemetry_source_pk': source.pk,
                'fetch_mode': TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
                'snapshot_file': snapshot_file,
            },
        )

    def run(
        self,
        telemetry_source_pk,
        fetch_mode=TELEMETRY_FETCH_MODE_SNAPSHOT_IMPORT,
        snapshot_file=None,
        *args,
        **kwargs,
    ):
        source = rpki_models.TelemetrySource.objects.get(pk=telemetry_source_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            telemetry_source_id=source.pk,
            telemetry_source_name=source.name,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        run = sync_telemetry_source(source, snapshot_file=snapshot_file)
        self.job.data = {
            'telemetry_source_pk': source.pk,
            'telemetry_run_pk': run.pk,
            'fetch_mode': fetch_mode,
            'snapshot_file': snapshot_file,
        }
        self.job.save(update_fields=('data',))
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            telemetry_source_id=source.pk,
            telemetry_run_pk=run.pk,
        )


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

        job_name = cls.get_job_name(organization)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': organization.pk,
        }
        existing_job = cls.get_active_job_for_organization(organization)
        active_run = rpki_models.IrrCoordinationRun.objects.filter(
            organization=organization,
            status=rpki_models.IrrCoordinationRunStatus.RUNNING,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_run is not None:
            skip_resolution = {
                'reason': 'running_irr_coordination',
                'run_model': 'IrrCoordinationRun',
                'run_id': active_run.pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'organization_pk': organization.pk,
            },
        )

    def run(self, organization_pk, *args, **kwargs):
        organization = rpki_models.Organization.objects.get(pk=organization_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            organization_name=organization.name,
        )
        coordination_run = run_irr_coordination(organization)
        self.job.data = {
            'organization_pk': organization.pk,
            'irr_coordination_run_pk': coordination_run.pk,
        }
        self.job.save(update_fields=('data',))
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            organization_id=organization.pk,
            irr_coordination_run_pk=coordination_run.pk,
        )


class CreateROAChangePlanJob(JobRunner):
    class Meta:
        name = 'ROA Change Plan Drafting'

    @classmethod
    def get_job_name(cls, reconciliation_run: rpki_models.ROAReconciliationRun | int) -> str:
        reconciliation_run_pk = reconciliation_run.pk if hasattr(reconciliation_run, 'pk') else reconciliation_run
        return f'{cls.name} [{reconciliation_run_pk}]'

    @classmethod
    def get_active_job_for_reconciliation_run(
        cls,
        reconciliation_run: rpki_models.ROAReconciliationRun | int,
    ):
        return Job.objects.filter(
            name=cls.get_job_name(reconciliation_run),
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        ).order_by('created').first()

    @classmethod
    def enqueue_for_reconciliation_run(
        cls,
        reconciliation_run: rpki_models.ROAReconciliationRun | int,
        *,
        plan_name: str | None = None,
        user=None,
        schedule_at=None,
    ):
        if not isinstance(reconciliation_run, rpki_models.ROAReconciliationRun):
            reconciliation_run = rpki_models.ROAReconciliationRun.objects.get(pk=reconciliation_run)

        job_name = cls.get_job_name(reconciliation_run)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': reconciliation_run.organization_id,
            'reconciliation_run_pk': reconciliation_run.pk,
            'plan_name': plan_name,
        }
        existing_job = cls.get_active_job_for_reconciliation_run(reconciliation_run)
        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=reconciliation_run.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            enqueue_kwargs={
                'reconciliation_run_pk': reconciliation_run.pk,
                'plan_name': plan_name,
            },
        )

    def run(self, reconciliation_run_pk, plan_name=None, *args, **kwargs):
        reconciliation_run = rpki_models.ROAReconciliationRun.objects.get(pk=reconciliation_run_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            roa_reconciliation_run_id=reconciliation_run.pk,
            roa_reconciliation_run_name=reconciliation_run.name,
            plan_name=plan_name,
        )
        plan = create_roa_change_plan(reconciliation_run, name=plan_name)
        self.job.data = {
            'roa_reconciliation_run_pk': reconciliation_run.pk,
            'roa_change_plan_pk': plan.pk,
        }
        self.job.save(update_fields=('data',))
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            roa_reconciliation_run_id=reconciliation_run.pk,
            roa_change_plan_pk=plan.pk,
            item_count=plan.items.count(),
        )


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

        job_name = cls.get_job_name(coordination_run)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': coordination_run.organization_id,
            'coordination_run_pk': coordination_run.pk,
        }
        existing_job = cls.get_active_job_for_coordination_run(coordination_run)
        active_plan = rpki_models.IrrChangePlan.objects.filter(
            coordination_run=coordination_run,
            status=rpki_models.IrrChangePlanStatus.EXECUTING,
        ).order_by('-execution_started_at', '-pk').first()
        skip_resolution = None
        if active_plan is not None:
            skip_resolution = {
                'reason': 'executing_change_plan',
                'run_model': 'IrrChangePlan',
                'run_id': active_plan.pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=coordination_run.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'coordination_run_pk': coordination_run.pk,
            },
        )

    def run(self, coordination_run_pk, *args, **kwargs):
        coordination_run = rpki_models.IrrCoordinationRun.objects.get(pk=coordination_run_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_coordination_run_id=coordination_run.pk,
            irr_coordination_run_name=coordination_run.name,
        )
        plans = create_irr_change_plans(coordination_run)
        self.job.data = {
            'irr_coordination_run_pk': coordination_run.pk,
            'irr_change_plan_pks': [plan.pk for plan in plans],
        }
        self.job.save(update_fields=('data',))
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_coordination_run_id=coordination_run.pk,
            irr_change_plan_count=len(plans),
        )


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

        job_name = cls.get_job_name(change_plan, execution_mode=execution_mode)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': change_plan.organization_id,
            'change_plan_pk': change_plan.pk,
            'execution_mode': execution_mode,
        }
        existing_job = cls.get_active_job_for_change_plan(change_plan, execution_mode=execution_mode)
        active_execution = rpki_models.IrrWriteExecution.objects.filter(
            change_plan=change_plan,
            execution_mode=execution_mode,
            status=rpki_models.IrrWriteExecutionStatus.RUNNING,
        ).order_by('-started_at', '-pk').first()
        skip_resolution = None
        if active_execution is not None:
            skip_resolution = {
                'reason': 'running_irr_write_execution',
                'run_model': 'IrrWriteExecution',
                'run_id': active_execution.pk,
                'execution_mode': execution_mode,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=change_plan.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'change_plan_pk': change_plan.pk,
                'execution_mode': execution_mode,
            },
        )

    def run(
        self,
        change_plan_pk,
        execution_mode=rpki_models.IrrWriteExecutionMode.PREVIEW,
        *args,
        **kwargs,
    ):
        change_plan = rpki_models.IrrChangePlan.objects.get(pk=change_plan_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_change_plan_id=change_plan.pk,
            irr_change_plan_name=change_plan.name,
            execution_mode=execution_mode,
        )
        if execution_mode == rpki_models.IrrWriteExecutionMode.APPLY:
            execution, payload = apply_irr_change_plan(
                change_plan,
                requested_by=_requested_by_value(getattr(self.job, 'user', None)),
                replay_safe=True,
            )
        else:
            execution, payload = preview_irr_change_plan(
                change_plan,
                requested_by=_requested_by_value(getattr(self.job, 'user', None)),
                replay_safe=True,
            )
        self.job.data = {
            'irr_change_plan_pk': change_plan.pk,
            'irr_write_execution_pk': execution.pk,
            'execution_mode': execution_mode,
        }
        self.job.save(update_fields=('data',))
        if payload.get('replayed'):
            _record_job_execution(
                organization=change_plan.organization,
                job=self.job,
                job_class=type(self).__name__,
                job_name=type(self).get_job_name(change_plan, execution_mode=execution_mode),
                dedupe_key=type(self).get_job_name(change_plan, execution_mode=execution_mode),
                disposition=rpki_models.JobExecutionDisposition.REPLAYED,
                requested_by=_requested_by_value(getattr(self.job, 'user', None)),
                request_payload={
                    'change_plan_pk': change_plan.pk,
                    'execution_mode': execution_mode,
                    'request_fingerprint': payload.get('request_fingerprint'),
                },
                resolution_payload={
                    'reason': 'replay_safe_execution',
                    'irr_write_execution_pk': execution.pk,
                    'request_fingerprint': payload.get('request_fingerprint'),
                },
            )
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            irr_change_plan_id=change_plan.pk,
            irr_write_execution_pk=execution.pk,
            execution_mode=execution_mode,
        )


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

        job_name = cls.get_job_name(provider_account)
        dedupe_key = job_name
        request_payload = {
            'organization_pk': provider_account.organization_id,
            'provider_account_pk': provider_account.pk,
        }
        existing_job = cls.get_active_job_for_provider_account(provider_account)
        active_event = rpki_models.LifecycleHealthEvent.objects.filter(
            provider_account=provider_account,
            status=rpki_models.LifecycleHealthEventStatus.OPEN,
        ).order_by('-last_seen_at', '-pk').first()
        skip_resolution = None
        if active_event is not None:
            skip_resolution = {
                'reason': 'open_lifecycle_event',
                'run_model': 'LifecycleHealthEvent',
                'run_id': active_event.pk,
            }

        return _enqueue_with_lineage(
            job_runner_class=cls,
            organization=provider_account.organization,
            job_name=job_name,
            dedupe_key=dedupe_key,
            request_payload=request_payload,
            user=user,
            schedule_at=schedule_at,
            existing_job=existing_job,
            skip_resolution=skip_resolution,
            enqueue_kwargs={
                'provider_account_pk': provider_account.pk,
            },
        )

    def run(self, provider_account_pk, *args, **kwargs):
        provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account_pk)
        emit_structured_log(
            'job.run.start',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            provider_account_id=provider_account.pk,
            provider_account_name=provider_account.name,
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
        emit_structured_log(
            'job.run.complete',
            subsystem='jobs',
            logger=self.logger,
            job_class=type(self).__name__,
            provider_account_id=provider_account.pk,
            event_count=result['event_count'],
            opened_count=result['opened_count'],
            repeated_count=result['repeated_count'],
            resolved_count=result['resolved_count'],
        )

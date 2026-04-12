from netbox.jobs import JobRunner
from core.choices import JobStatusChoices
from core.models import Job

from netbox_rpki import models as rpki_models
from netbox_rpki.services import run_aspa_reconciliation_pipeline, run_routing_intent_pipeline, sync_provider_account


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

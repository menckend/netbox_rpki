from netbox.jobs import JobRunner

from netbox_rpki import models as rpki_models
from netbox_rpki.services import run_routing_intent_pipeline


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
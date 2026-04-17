from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import RunRoutingIntentProfileJob
from netbox_rpki.services import run_routing_intent_pipeline


class Command(BaseCommand):
    help = 'Execute derivation and reconciliation for a routing intent profile.'

    def add_arguments(self, parser):
        parser.add_argument('--profile', type=int, required=True, help='RoutingIntentProfile primary key')
        parser.add_argument(
            '--comparison-scope',
            choices=rpki_models.ReconciliationComparisonScope.values,
            default=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            help='Published-state source to compare against.',
        )
        parser.add_argument(
            '--provider-snapshot',
            type=int,
            help='ProviderSnapshot primary key when using provider_imported reconciliation.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the pipeline as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        profile_pk = options['profile']
        try:
            profile = rpki_models.RoutingIntentProfile.objects.get(pk=profile_pk)
        except rpki_models.RoutingIntentProfile.DoesNotExist as exc:
            raise CommandError(f'RoutingIntentProfile {profile_pk} does not exist.') from exc

        comparison_scope = options['comparison_scope']
        provider_snapshot_pk = options.get('provider_snapshot')

        if options['enqueue']:
            provider_snapshot = None
            if provider_snapshot_pk is not None:
                try:
                    provider_snapshot = rpki_models.ProviderSnapshot.objects.get(pk=provider_snapshot_pk)
                except rpki_models.ProviderSnapshot.DoesNotExist as exc:
                    raise CommandError(f'ProviderSnapshot {provider_snapshot_pk} does not exist.') from exc

            job, created = RunRoutingIntentProfileJob.enqueue_for_profile(
                profile,
                comparison_scope=comparison_scope,
                provider_snapshot=provider_snapshot,
            )
            if job is not None and created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for profile {profile.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Existing job {job.pk} is already active for profile {profile.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'Routing-intent reconciliation is already running for profile {profile.pk}.'))
            return

        derivation_run, reconciliation_run = run_routing_intent_pipeline(
            profile,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed derivation run {derivation_run.pk} and reconciliation run {reconciliation_run.pk} '
                f'for profile {profile.pk}.'
            )
        )

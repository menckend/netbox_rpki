from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import RunAspaReconciliationJob
from netbox_rpki.services import run_aspa_reconciliation_pipeline


class Command(BaseCommand):
    help = 'Execute ASPA reconciliation for an organization.'

    def add_arguments(self, parser):
        parser.add_argument('--organization', type=int, required=True, help='Organization primary key')
        parser.add_argument(
            '--comparison-scope',
            choices=rpki_models.ReconciliationComparisonScope.values,
            default=rpki_models.ReconciliationComparisonScope.LOCAL_ASPA_RECORDS,
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
            help='Enqueue the reconciliation as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        organization_pk = options['organization']
        try:
            organization = rpki_models.Organization.objects.get(pk=organization_pk)
        except rpki_models.Organization.DoesNotExist as exc:
            raise CommandError(f'Organization {organization_pk} does not exist.') from exc

        comparison_scope = options['comparison_scope']
        provider_snapshot_pk = options.get('provider_snapshot')

        if comparison_scope == rpki_models.ReconciliationComparisonScope.PROVIDER_IMPORTED and provider_snapshot_pk is None:
            raise CommandError('--provider-snapshot is required when using provider_imported reconciliation.')

        if options['enqueue']:
            job = RunAspaReconciliationJob.enqueue(
                instance=organization,
                organization_pk=organization.pk,
                comparison_scope=comparison_scope,
                provider_snapshot_pk=provider_snapshot_pk,
            )
            self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for organization {organization.pk}.'))
            return

        reconciliation_run = run_aspa_reconciliation_pipeline(
            organization,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot_pk,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed ASPA reconciliation run {reconciliation_run.pk} for organization {organization.pk}.'
            )
        )

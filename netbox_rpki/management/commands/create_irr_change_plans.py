from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import CreateIrrChangePlansJob
from netbox_rpki.services import create_irr_change_plans


class Command(BaseCommand):
    help = 'Create source-specific IRR change plans from one completed IRR coordination run.'

    def add_arguments(self, parser):
        parser.add_argument('--coordination-run', type=int, required=True, help='IRR coordination run primary key')
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue IRR change-plan drafting as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        coordination_run_pk = options['coordination_run']
        try:
            coordination_run = rpki_models.IrrCoordinationRun.objects.get(pk=coordination_run_pk)
        except rpki_models.IrrCoordinationRun.DoesNotExist as exc:
            raise CommandError(f'IRR coordination run {coordination_run_pk} does not exist.') from exc

        if options['enqueue']:
            job, created = CreateIrrChangePlansJob.enqueue_for_coordination_run(coordination_run)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for IRR coordination run {coordination_run.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Job {job.pk} is already queued for IRR coordination run {coordination_run.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'IRR coordination run {coordination_run.pk} already has an active change-plan drafting execution.'))
            return

        plans = create_irr_change_plans(coordination_run)
        self.stdout.write(
            self.style.SUCCESS(
                f'Created {len(plans)} IRR change plans for coordination run {coordination_run.pk}.'
            )
        )

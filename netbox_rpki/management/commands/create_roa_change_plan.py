from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import CreateROAChangePlanJob
from netbox_rpki.services import create_roa_change_plan


class Command(BaseCommand):
    help = 'Create a draft ROA change plan from a completed ROA reconciliation run.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reconciliation-run',
            type=int,
            required=True,
            help='ROAReconciliationRun primary key',
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Optional name for the generated change plan.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue change-plan drafting as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        reconciliation_run_pk = options['reconciliation_run']
        try:
            reconciliation_run = rpki_models.ROAReconciliationRun.objects.get(pk=reconciliation_run_pk)
        except rpki_models.ROAReconciliationRun.DoesNotExist as exc:
            raise CommandError(
                f'ROAReconciliationRun {reconciliation_run_pk} does not exist.'
            ) from exc

        if options['enqueue']:
            job, created = CreateROAChangePlanJob.enqueue_for_reconciliation_run(
                reconciliation_run,
                plan_name=options.get('name'),
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Enqueued job {job.pk} for reconciliation run {reconciliation_run.pk}.'
                    )
                )
            elif job is not None:
                self.stdout.write(
                    self.style.WARNING(
                        f'Job {job.pk} is already queued for reconciliation run {reconciliation_run.pk}.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'A change plan is already being drafted for reconciliation run {reconciliation_run.pk}.'
                    )
                )
            return

        plan = create_roa_change_plan(reconciliation_run, name=options.get('name'))
        self.stdout.write(
            self.style.SUCCESS(
                f'Created ROA change plan {plan.pk} ("{plan.name}") '
                f'with {plan.items.count()} items from reconciliation run {reconciliation_run.pk}.'
            )
        )

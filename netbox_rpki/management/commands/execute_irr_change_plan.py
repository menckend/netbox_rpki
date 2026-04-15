from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import ExecuteIrrChangePlanJob
from netbox_rpki.services import apply_irr_change_plan, preview_irr_change_plan


class Command(BaseCommand):
    help = 'Preview or apply one IRR change plan against its configured source adapter.'

    def add_arguments(self, parser):
        parser.add_argument('--change-plan', type=int, required=True, help='IRR change plan primary key')
        parser.add_argument(
            '--mode',
            choices=rpki_models.IrrWriteExecutionMode.values,
            default=rpki_models.IrrWriteExecutionMode.PREVIEW,
            help='Execution mode: preview or apply.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the IRR change-plan execution as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        change_plan_pk = options['change_plan']
        execution_mode = options['mode']
        try:
            change_plan = rpki_models.IrrChangePlan.objects.get(pk=change_plan_pk)
        except rpki_models.IrrChangePlan.DoesNotExist as exc:
            raise CommandError(f'IRR change plan {change_plan_pk} does not exist.') from exc

        if options['enqueue']:
            job, created = ExecuteIrrChangePlanJob.enqueue_for_change_plan(
                change_plan,
                execution_mode=execution_mode,
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Enqueued job {job.pk} for IRR change plan {change_plan.pk} ({execution_mode}).'
                    )
                )
            elif job is not None:
                self.stdout.write(
                    self.style.WARNING(
                        f'Job {job.pk} is already queued for IRR change plan {change_plan.pk} ({execution_mode}).'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'IRR change plan {change_plan.pk} already has an active {execution_mode} execution.'
                    )
                )
            return

        if execution_mode == rpki_models.IrrWriteExecutionMode.APPLY:
            execution, _ = apply_irr_change_plan(change_plan)
        else:
            execution, _ = preview_irr_change_plan(change_plan)
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed IRR change plan {execution_mode} execution {execution.pk} for plan {change_plan.pk}.'
            )
        )

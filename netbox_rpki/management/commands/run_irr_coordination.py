from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import RunIrrCoordinationJob
from netbox_rpki.services import run_irr_coordination


class Command(BaseCommand):
    help = 'Compare NetBox route policy and imported IRR state for one organization.'

    def add_arguments(self, parser):
        parser.add_argument('--organization', type=int, required=True, help='Organization primary key')
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the coordination run as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        organization_pk = options['organization']
        try:
            organization = rpki_models.Organization.objects.get(pk=organization_pk)
        except rpki_models.Organization.DoesNotExist as exc:
            raise CommandError(f'Organization {organization_pk} does not exist.') from exc

        if options['enqueue']:
            job, created = RunIrrCoordinationJob.enqueue_for_organization(organization)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for organization {organization.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Job {job.pk} is already queued for organization {organization.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'Organization {organization.pk} already has an IRR coordination run in progress.'))
            return

        coordination_run = run_irr_coordination(organization)
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed IRR coordination run {coordination_run.pk} for organization {organization.pk}.'
            )
        )

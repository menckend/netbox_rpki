from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import SyncTelemetrySourceJob
from netbox_rpki.services import sync_telemetry_source


class Command(BaseCommand):
    help = 'Import BGP telemetry observations from a configured telemetry source.'

    def add_arguments(self, parser):
        parser.add_argument('--telemetry-source', type=int, required=True, help='TelemetrySource primary key')
        parser.add_argument(
            '--snapshot-file',
            required=True,
            help='Path to a normalized JSON snapshot derived from MRT data.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the import as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        source_pk = options['telemetry_source']
        snapshot_file = options['snapshot_file']

        try:
            source = rpki_models.TelemetrySource.objects.get(pk=source_pk)
        except rpki_models.TelemetrySource.DoesNotExist as exc:
            raise CommandError(f'TelemetrySource {source_pk} does not exist.') from exc

        if options['enqueue']:
            job, created = SyncTelemetrySourceJob.enqueue_for_source(
                source,
                snapshot_file=snapshot_file,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for telemetry source {source.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Job {job.pk} is already queued for telemetry source {source.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'Telemetry source {source.pk} already has an import in progress.'))
            return

        run = sync_telemetry_source(source, snapshot_file=snapshot_file)
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed telemetry import run {run.pk} for telemetry source {source.pk}.'
            )
        )

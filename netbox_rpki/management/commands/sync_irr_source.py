from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import SyncIrrSourceJob
from netbox_rpki.services import sync_irr_source


class Command(BaseCommand):
    help = 'Import IRR state from a configured IRR source.'

    def add_arguments(self, parser):
        parser.add_argument('--irr-source', type=int, required=True, help='IrrSource primary key')
        parser.add_argument(
            '--fetch-mode',
            choices=rpki_models.IrrFetchMode.values,
            default=rpki_models.IrrFetchMode.LIVE_QUERY,
            help='Whether to import from the live source or a snapshot file.',
        )
        parser.add_argument(
            '--snapshot-file',
            help='Path to an RPSL snapshot file. Only valid with --fetch-mode snapshot_import.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the import as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        irr_source_pk = options['irr_source']
        fetch_mode = options['fetch_mode']
        snapshot_file = options['snapshot_file']

        try:
            irr_source = rpki_models.IrrSource.objects.get(pk=irr_source_pk)
        except rpki_models.IrrSource.DoesNotExist as exc:
            raise CommandError(f'IrrSource {irr_source_pk} does not exist.') from exc

        if fetch_mode != rpki_models.IrrFetchMode.SNAPSHOT_IMPORT and snapshot_file:
            raise CommandError('--snapshot-file is only valid with --fetch-mode snapshot_import.')
        if fetch_mode == rpki_models.IrrFetchMode.SNAPSHOT_IMPORT and not snapshot_file:
            raise CommandError('--snapshot-file is required with --fetch-mode snapshot_import.')

        if options['enqueue']:
            try:
                job, created = SyncIrrSourceJob.enqueue_for_source(
                    irr_source,
                    fetch_mode=fetch_mode,
                    snapshot_file=snapshot_file,
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for IRR source {irr_source.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Job {job.pk} is already queued for IRR source {irr_source.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'IRR source {irr_source.pk} already has an import in progress.'))
            return

        snapshot = sync_irr_source(
            irr_source,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed IRR import snapshot {snapshot.pk} for IRR source {irr_source.pk}.'
            )
        )

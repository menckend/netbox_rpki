from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import SyncValidatorInstanceJob
from netbox_rpki.services import (
    VALIDATOR_FETCH_MODE_LIVE_API,
    VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT,
    VALIDATOR_FETCH_MODES,
    sync_validator_instance,
)


class Command(BaseCommand):
    help = 'Import external validation observations from a configured validator instance.'

    def add_arguments(self, parser):
        parser.add_argument('--validator-instance', type=int, required=True, help='ValidatorInstance primary key')
        parser.add_argument(
            '--fetch-mode',
            choices=VALIDATOR_FETCH_MODES,
            default=VALIDATOR_FETCH_MODE_LIVE_API,
            help='Whether to import from the live validator API or a snapshot file.',
        )
        parser.add_argument(
            '--snapshot-file',
            help='Path to a Routinator jsonext snapshot. Only valid with --fetch-mode snapshot_import.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the import as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        validator_pk = options['validator_instance']
        fetch_mode = options['fetch_mode']
        snapshot_file = options['snapshot_file']

        try:
            validator = rpki_models.ValidatorInstance.objects.get(pk=validator_pk)
        except rpki_models.ValidatorInstance.DoesNotExist as exc:
            raise CommandError(f'ValidatorInstance {validator_pk} does not exist.') from exc

        if fetch_mode != VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT and snapshot_file:
            raise CommandError('--snapshot-file is only valid with --fetch-mode snapshot_import.')
        if fetch_mode == VALIDATOR_FETCH_MODE_SNAPSHOT_IMPORT and not snapshot_file:
            raise CommandError('--snapshot-file is required with --fetch-mode snapshot_import.')

        if options['enqueue']:
            job, created = SyncValidatorInstanceJob.enqueue_for_validator(
                validator,
                fetch_mode=fetch_mode,
                snapshot_file=snapshot_file,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for validator instance {validator.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(f'Job {job.pk} is already queued for validator instance {validator.pk}.'))
            else:
                self.stdout.write(self.style.WARNING(f'Validator instance {validator.pk} already has an import in progress.'))
            return

        run = sync_validator_instance(
            validator,
            fetch_mode=fetch_mode,
            snapshot_file=snapshot_file,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed validator import run {run.pk} for validator instance {validator.pk}.'
            )
        )

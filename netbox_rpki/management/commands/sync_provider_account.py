from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import SyncProviderAccountJob
from netbox_rpki.services import sync_provider_account


class Command(BaseCommand):
    help = 'Import ROA state from a configured provider account.'

    def add_arguments(self, parser):
        parser.add_argument('--provider-account', type=int, required=True, help='ProviderAccount primary key')
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the sync as a NetBox background job instead of running synchronously.',
        )

    def handle(self, *args, **options):
        provider_account_pk = options['provider_account']
        try:
            provider_account = rpki_models.RpkiProviderAccount.objects.get(pk=provider_account_pk)
        except rpki_models.RpkiProviderAccount.DoesNotExist as exc:
            raise CommandError(f'ProviderAccount {provider_account_pk} does not exist.') from exc

        if options['enqueue']:
            try:
                job, created = SyncProviderAccountJob.enqueue_for_provider_account(provider_account)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for provider account {provider_account.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(
                    f'Job {job.pk} is already queued for provider account {provider_account.pk}.'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Provider account {provider_account.pk} already has a sync in progress.'
                ))
            return

        sync_run, snapshot = sync_provider_account(provider_account)
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed provider sync run {sync_run.pk} and provider snapshot {snapshot.pk} '
                f'for provider account {provider_account.pk}.'
            )
        )
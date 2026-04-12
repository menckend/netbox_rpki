from django.core.management.base import BaseCommand
from django.utils import timezone

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import SyncProviderAccountJob


class Command(BaseCommand):
    help = 'Scan scheduled provider accounts and enqueue sync jobs for accounts that are due.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report due accounts without enqueuing jobs.')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of due accounts to process.')

    def handle(self, *args, **options):
        now = timezone.now()
        queryset = rpki_models.RpkiProviderAccount.objects.select_related('organization').filter(
            sync_enabled=True,
            sync_interval__isnull=False,
        ).order_by('pk')
        due_accounts = [account for account in queryset if account.is_sync_due(reference_time=now)]

        if options['limit'] is not None:
            due_accounts = due_accounts[:options['limit']]

        if options['dry_run']:
            for provider_account in due_accounts:
                self.stdout.write(
                    f'Due provider account {provider_account.pk} ({provider_account.name}) '
                    f'health={provider_account.sync_health}.'
                )
            self.stdout.write(self.style.SUCCESS(f'Identified {len(due_accounts)} due provider account(s).'))
            return

        enqueued_count = 0
        skipped_count = 0
        for provider_account in due_accounts:
            job, created = SyncProviderAccountJob.enqueue_for_provider_account(provider_account)
            if created:
                enqueued_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Enqueued job {job.pk} for provider account {provider_account.pk}.'
                    )
                )
            else:
                skipped_count += 1
                if job is not None:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Job {job.pk} is already queued for provider account {provider_account.pk}.'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Provider account {provider_account.pk} already has a sync in progress.'
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'Processed {len(due_accounts)} due provider account(s): '
                f'{enqueued_count} enqueued, {skipped_count} skipped.'
            )
        )
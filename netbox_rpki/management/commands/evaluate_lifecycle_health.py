from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import EvaluateLifecycleHealthJob
from netbox_rpki.services.lifecycle_reporting import evaluate_lifecycle_health_events


class Command(BaseCommand):
    help = 'Evaluate lifecycle-health events for provider accounts.'

    def add_arguments(self, parser):
        parser.add_argument('--provider-account', type=int, help='ProviderAccount primary key to evaluate.')
        parser.add_argument('--dry-run', action='store_true', help='Report selected provider accounts without evaluating them.')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of provider accounts to process.')
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue lifecycle-health evaluation jobs instead of running synchronously.',
        )

    def _get_provider_account(self, provider_account_pk: int) -> rpki_models.RpkiProviderAccount:
        try:
            return rpki_models.RpkiProviderAccount.objects.select_related('organization').get(pk=provider_account_pk)
        except rpki_models.RpkiProviderAccount.DoesNotExist as exc:
            raise CommandError(f'ProviderAccount {provider_account_pk} does not exist.') from exc

    def _get_provider_accounts(self, provider_account_pk: int | None):
        if provider_account_pk is not None:
            return [self._get_provider_account(provider_account_pk)]

        return list(
            rpki_models.RpkiProviderAccount.objects.select_related('organization').filter(
                sync_enabled=True,
            )
            .exclude(last_sync_status=rpki_models.ValidationRunStatus.RUNNING)
            .order_by('pk')
        )

    def handle(self, *args, **options):
        provider_account_pk = options.get('provider_account')
        provider_accounts = self._get_provider_accounts(provider_account_pk)
        if options['limit'] is not None:
            provider_accounts = provider_accounts[:options['limit']]

        if options['dry_run']:
            for provider_account in provider_accounts:
                self.stdout.write(
                    f'Would evaluate provider account {provider_account.pk} ({provider_account.name}) '
                    f'health={provider_account.sync_health}.'
                )
            self.stdout.write(self.style.SUCCESS(f'Identified {len(provider_accounts)} provider account(s) for evaluation.'))
            return

        if options['enqueue']:
            enqueued_count = 0
            skipped_count = 0
            for provider_account in provider_accounts:
                job, created = EvaluateLifecycleHealthJob.enqueue_for_provider_account(provider_account)
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
                                f'Provider account {provider_account.pk} already has an evaluation in progress.'
                            )
                        )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Processed {len(provider_accounts)} provider account(s): '
                    f'{enqueued_count} enqueued, {skipped_count} skipped.'
                )
            )
            return

        evaluated_count = 0
        for provider_account in provider_accounts:
            result = evaluate_lifecycle_health_events(provider_account)
            evaluated_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Evaluated provider account {provider_account.pk}: '
                    f'{result["opened_count"]} opened, {result["repeated_count"]} repeated, '
                    f'{result["resolved_count"]} resolved.'
                )
            )

        self.stdout.write(self.style.SUCCESS(f'Processed {evaluated_count} provider account(s).'))

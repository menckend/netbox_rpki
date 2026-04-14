from django.core.management.base import BaseCommand, CommandError

from netbox_rpki import models as rpki_models
from netbox_rpki.jobs import RunBulkRoutingIntentJob
from netbox_rpki.services import run_bulk_routing_intent_pipeline


class Command(BaseCommand):
    help = 'Execute a bulk routing-intent run across one or more profiles and template bindings.'

    def add_arguments(self, parser):
        parser.add_argument('--organization', type=int, required=True, help='Organization primary key')
        parser.add_argument(
            '--profiles',
            nargs='*',
            type=int,
            default=(),
            help='RoutingIntentProfile primary keys to include in the run.',
        )
        parser.add_argument(
            '--bindings',
            nargs='*',
            type=int,
            default=(),
            help='RoutingIntentTemplateBinding primary keys to include in the run.',
        )
        parser.add_argument(
            '--comparison-scope',
            choices=rpki_models.ReconciliationComparisonScope.values,
            default=rpki_models.ReconciliationComparisonScope.LOCAL_ROA_RECORDS,
            help='Published-state source to compare against.',
        )
        parser.add_argument(
            '--provider-snapshot',
            type=int,
            help='ProviderSnapshot primary key when using provider_imported reconciliation.',
        )
        parser.add_argument(
            '--create-change-plans',
            action='store_true',
            help='Create draft ROA change plans for each qualifying scope result.',
        )
        parser.add_argument(
            '--run-name',
            help='Optional name for the resulting BulkIntentRun.',
        )
        parser.add_argument(
            '--enqueue',
            action='store_true',
            help='Enqueue the bulk run as a NetBox background job instead of running synchronously.',
        )

    def _get_organization(self, organization_pk: int) -> rpki_models.Organization:
        try:
            return rpki_models.Organization.objects.get(pk=organization_pk)
        except rpki_models.Organization.DoesNotExist as exc:
            raise CommandError(f'Organization {organization_pk} does not exist.') from exc

    def _get_profiles(self, organization: rpki_models.Organization, profile_pks: tuple[int, ...]) -> tuple[rpki_models.RoutingIntentProfile, ...]:
        profiles = tuple(
            rpki_models.RoutingIntentProfile.objects.filter(
                pk__in=tuple(profile_pks),
                organization=organization,
            ).order_by('pk')
        )
        if len(profiles) != len(set(profile_pks)):
            raise CommandError('All selected routing intent profiles must exist and belong to the selected organization.')
        return profiles

    def _get_bindings(self, organization: rpki_models.Organization, binding_pks: tuple[int, ...]) -> tuple[rpki_models.RoutingIntentTemplateBinding, ...]:
        bindings = tuple(
            rpki_models.RoutingIntentTemplateBinding.objects.filter(
                pk__in=tuple(binding_pks),
                intent_profile__organization=organization,
            ).select_related('intent_profile').order_by('pk')
        )
        if len(bindings) != len(set(binding_pks)):
            raise CommandError('All selected template bindings must exist and belong to the selected organization.')
        return bindings

    def _get_provider_snapshot(self, organization: rpki_models.Organization, provider_snapshot_pk: int | None):
        if provider_snapshot_pk is None:
            return None
        try:
            provider_snapshot = rpki_models.ProviderSnapshot.objects.get(pk=provider_snapshot_pk)
        except rpki_models.ProviderSnapshot.DoesNotExist as exc:
            raise CommandError(f'ProviderSnapshot {provider_snapshot_pk} does not exist.') from exc
        if provider_snapshot.organization_id != organization.pk:
            raise CommandError('Provider snapshot must belong to the selected organization.')
        return provider_snapshot

    def handle(self, *args, **options):
        organization = self._get_organization(options['organization'])
        profiles = self._get_profiles(organization, tuple(options['profiles'] or ()))
        bindings = self._get_bindings(organization, tuple(options['bindings'] or ()))
        provider_snapshot = self._get_provider_snapshot(organization, options.get('provider_snapshot'))
        comparison_scope = options['comparison_scope']
        create_change_plans = options['create_change_plans']
        run_name = options.get('run_name')

        if not profiles and not bindings:
            raise CommandError('Select at least one routing intent profile or template binding.')

        if options['enqueue']:
            try:
                job, created = RunBulkRoutingIntentJob.enqueue_for_organization(
                    organization=organization,
                    profiles=profiles,
                    bindings=bindings,
                    comparison_scope=comparison_scope,
                    provider_snapshot=provider_snapshot,
                    create_change_plans=create_change_plans,
                    run_name=run_name,
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

            if created:
                self.stdout.write(self.style.SUCCESS(f'Enqueued job {job.pk} for organization {organization.pk}.'))
            elif job is not None:
                self.stdout.write(self.style.WARNING(
                    f'Job {job.pk} is already queued for organization {organization.pk}.'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Organization {organization.pk} already has a matching bulk routing-intent run in progress.'
                ))
            return

        bulk_run = run_bulk_routing_intent_pipeline(
            organization=organization,
            profiles=profiles,
            bindings=bindings,
            comparison_scope=comparison_scope,
            provider_snapshot=provider_snapshot,
            create_change_plans=create_change_plans,
            run_name=run_name,
        )
        summary = dict(bulk_run.summary_json or {})
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed bulk intent run {bulk_run.pk} with '
                f'{summary.get("scope_result_count", 0)} scope result(s) and '
                f'{summary.get("change_plan_count", 0)} change plan(s).'
            )
        )

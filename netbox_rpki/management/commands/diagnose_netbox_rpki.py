from django.core.management.base import BaseCommand

from netbox_rpki.services.install_diagnostics import (
    build_install_diagnostic_report,
    render_install_diagnostic_json,
    render_install_diagnostic_text,
)


class Command(BaseCommand):
    help = 'Run install-time self-diagnostics for the netbox_rpki plugin.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=('text', 'json'),
            default='text',
            help='Render output as operator-friendly text or machine-readable JSON.',
        )

    def handle(self, *args, **options):
        report = build_install_diagnostic_report()
        if options['format'] == 'json':
            self.stdout.write(render_install_diagnostic_json(report))
            return

        self.stdout.write(render_install_diagnostic_text(report))

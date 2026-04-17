import json
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from netbox_rpki.structured_logging import emit_structured_log, sanitize_log_data, sanitize_url, subsystem_debug_enabled


class StructuredLoggingTestCase(SimpleTestCase):
    def test_sanitize_log_data_redacts_secrets_and_summarizes_sensitive_payloads(self):
        sanitized = sanitize_log_data(
            {
                'Authorization': 'Bearer super-secret-token',
                'api_key': 'krill-token',
                'override': 'override-secret',
                'url': 'https://rpki.example/api?apikey=secret-token&mode=full',
                'payload_json': {
                    'objects': [{'object_text': 'route: 198.51.100.0/24\norigin: AS64500\n'}],
                },
                'nested': {
                    'http_password': 'secret-password',
                },
            }
        )

        self.assertEqual(sanitized['Authorization'], '<redacted>')
        self.assertEqual(sanitized['api_key'], '<redacted>')
        self.assertEqual(sanitized['override'], '<redacted>')
        self.assertEqual(
            sanitized['url'],
            'https://rpki.example/api?apikey=%3Credacted%3E&mode=full',
        )
        self.assertTrue(sanitized['payload_json']['redacted'])
        self.assertEqual(sanitized['payload_json']['kind'], 'mapping')
        self.assertEqual(sanitized['nested']['http_password'], '<redacted>')

    def test_sanitize_url_redacts_sensitive_query_parameters(self):
        self.assertEqual(
            sanitize_url('https://example.invalid/v1/roa?apikey=token&foo=bar&signature=abc'),
            'https://example.invalid/v1/roa?apikey=%3Credacted%3E&foo=bar&signature=%3Credacted%3E',
        )

    @override_settings(
        PLUGINS_CONFIG={
            'netbox_rpki': {
                'structured_logging': {
                    'debug_subsystems': ['provider_sync', 'jobs'],
                },
            },
        }
    )
    def test_subsystem_debug_enabled_honors_plugin_settings(self):
        self.assertTrue(subsystem_debug_enabled('provider_sync'))
        self.assertTrue(subsystem_debug_enabled('jobs'))
        self.assertFalse(subsystem_debug_enabled('irr_write'))

    @override_settings(
        PLUGINS_CONFIG={
            'netbox_rpki': {
                'structured_logging': {
                    'debug_subsystems': ['provider_sync'],
                },
            },
        }
    )
    def test_emit_structured_log_skips_debug_events_when_subsystem_disabled(self):
        logger = Mock()

        result = emit_structured_log(
            'provider_write.krill.submit.start',
            subsystem='provider_write',
            logger=logger,
            debug=True,
            url='https://provider.invalid/api?apikey=secret',
        )

        self.assertIsNone(result)
        logger.info.assert_not_called()

    @override_settings(
        PLUGINS_CONFIG={
            'netbox_rpki': {
                'structured_logging': {
                    'debug_subsystems': ['provider_write'],
                },
            },
        }
    )
    def test_emit_structured_log_emits_json_with_redaction(self):
        logger = Mock()

        emit_structured_log(
            'provider_write.krill.submit.start',
            subsystem='provider_write',
            logger=logger,
            debug=True,
            headers={'Authorization': 'Bearer real-token'},
            request_body={'override': 'secret', 'objects': [{'object_text': 'route: 203.0.113.0/24'}]},
            url='https://provider.invalid/api?apikey=real-token',
        )

        logger.info.assert_called_once()
        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(payload['event'], 'provider_write.krill.submit.start')
        self.assertEqual(payload['subsystem'], 'provider_write')
        self.assertEqual(payload['headers']['Authorization'], '<redacted>')
        self.assertEqual(payload['request_body']['redacted'], True)
        self.assertEqual(payload['url'], 'https://provider.invalid/api?apikey=%3Credacted%3E')

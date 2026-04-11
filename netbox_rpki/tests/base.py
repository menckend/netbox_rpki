from django.urls import reverse

from utilities.testing import APITestCase, TestCase
from utilities.testing.utils import extract_form_failures


class PluginAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_rpki'


class PluginViewTestCase(TestCase):
    def plugin_url(self, name, instance=None):
        kwargs = {'pk': instance.pk} if instance is not None else None
        return reverse(f'plugins:netbox_rpki:{name}', kwargs=kwargs)

    def assertFormErrors(self, response, *expected_text):
        failures = extract_form_failures(response.content)
        haystack = ' '.join(failures) if failures else response.content.decode(errors='ignore')
        for text in expected_text:
            self.assertIn(text, haystack)
from django.contrib import admin

from netbox.admin import admin_site
from netbox.tests.dummy_plugin.models import DummyModel


@admin.register(DummyModel, site=admin_site)
class DummyModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'number')

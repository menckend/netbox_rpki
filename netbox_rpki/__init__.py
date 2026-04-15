from importlib.metadata import PackageNotFoundError, version

from django.conf import settings
from netbox.plugins import PluginConfig

from .compatibility import emit_runtime_compatibility_warning

try:
    __version__ = version('netbox_rpki')
except PackageNotFoundError:
    __version__ = '0+unknown'


class RpkiConfig(PluginConfig):
    name = 'netbox_rpki'
    verbose_name = 'Netbox RPKI'
    description = 'RPKI objects for Netbox'
    version = __version__
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_rpki'
    min_version = '4.5.0'
    max_version = '4.5.99'
    required_settings = []
    default_settings = {
        'top_level_menu': True
        }

    def ready(self):
        super().ready()

        from . import jobs  # noqa: F401

        # Register per-group top-level menus when top_level_menu is enabled.
        # super().ready() looks for navigation.menu (singular); since we export
        # navigation.menus instead, we register each entry manually here.
        from . import navigation as _nav
        from netbox.plugins import register_menu as _register_menu
        for _m in getattr(_nav, 'menus', ()):
            _register_menu(_m)
        emit_runtime_compatibility_warning(netbox_version=getattr(settings, 'VERSION', self.min_version))


config = RpkiConfig

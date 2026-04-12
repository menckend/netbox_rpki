from importlib.metadata import PackageNotFoundError, version

from netbox.plugins import PluginConfig

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


config = RpkiConfig

from netbox.plugins import PluginConfig
from netbox_rpki.version import __version__


class RpkiConfig(PluginConfig):
    name = 'netbox_rpki'
    verbose_name = 'Netbox RPKI'
    description = 'RPKI objects for Netbox'
    version = __version__
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_rpki'
    min_version = '4.1.0'
    max_version = '4.1.7'
    required_settings = []
    default_settings = {
        'top_level_menu': True
        }


config = RpkiConfig

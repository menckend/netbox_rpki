from netbox.plugins import PluginConfig
from netbox_rpki.version import __version__

# import api

class RpkiConfig(PluginConfig):
    name = 'netbox_rpki'
    verbose_name = 'Netbox RPKI'
    description = 'RPKI objects for Netbox'
    version = __version__
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_rpki'
    min_verserion = '4.1.0'
    required_settings = []
    default_settings = {
        'top_level_menu': True
        }

config = RpkiConfig

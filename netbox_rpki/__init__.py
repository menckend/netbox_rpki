__author__ = """Mencken Davidson"""
__email__ = "mencken@gmail.com"

from netbox.plugins import PluginConfig
from netbox_rpki._version import __version__

# import api


class rpki_config(PluginConfig):
    name = 'netbox_rpki'
    verbose_name = 'RPKI functionality for Netbox'
    description = 'Add RPKI data elements to Netbox.'
    version = 0.1
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_rpki'
    default_settings = {
        'top_level_menu': True
        }


config = rpki_config

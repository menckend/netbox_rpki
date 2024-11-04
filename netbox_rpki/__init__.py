__author__ = """H.L. Mencken Davidson"""
__email__ = "netbox_rpki@toomanydavidsons.com"

from netbox.plugins import PluginConfig
from netbox_rpki._version import __version__

# import api

class rpki_config(PluginConfig):
    name = 'netbox_rpki'
    verbose_name = 'RPKI functionality for Netbox'
    description = 'Add RPKI data elements to Netbox.'
    version = __version__
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_rpki'
    default_settings = {
        'top_level_menu': True
        }

config = rpki_config

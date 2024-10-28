__author__ = """Mencken Davidson"""
__email__ = "mencken@gmail.com"

from netbox.plugins import PluginConfig
from netbox_ptov._version import __version__


class ptov_config(PluginConfig):
    name = 'netbox_ptov'
    verbose_name = 'Physical to Virtual-lab'
    description = 'Builds GNS3 labs with config and topology scraped from Arista switches in device tabls'
    version = 0.1
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'netbox_ptov'
    default_settings = {
        'top_level_menu': False
        }


config = ptov_config

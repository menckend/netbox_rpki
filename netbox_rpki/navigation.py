from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
from netbox.plugins.utils import get_plugin_config


resource_menu_items = (
    PluginMenuItem(
        link='plugins:netbox_rpki:organization_list',
        link_text='RIR Customer Orgs',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:organization_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_rpki:certificate_list',
        link_text='Resource Certificates',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:certificate_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_rpki:certificateprefix_list',
        link_text='Assigned Prefices',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:certificateprefix_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_rpki:certificateasn_list',
        link_text='Assigned ASNs ',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:certificateasn_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
)
roa_menu_items = (
    PluginMenuItem(
        link='plugins:netbox_rpki:roa_list',
        link_text='ROAs',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:roa_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_rpki:roaprefix_list',
        link_text='ROA Prefices',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:roaprefix_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
)
plugin_settings = settings.PLUGINS_CONFIG.get('netbox_rpki', {})

if plugin_settings.get('top_level_menu'):
    menu = PluginMenu(
        label="RPKI",
        groups=(
            ("Resources", resource_menu_items),
            ("ROAs", roa_menu_items),
        ),
        icon_class="mdi mdi-bootstrap"
    )
else:
    menu_items = (
        resource_menu_items + roa_menu_items
    )

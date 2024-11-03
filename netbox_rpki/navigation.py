from django.conf import settings

from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu


_menu_items = (
    PluginMenuItem(
        link='plugins:netbox_rpki:organization_list',
        link_text='Organizations',
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
        link_text='Customer Certificates',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:certificate_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),

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
    )

)
plugin_settings = settings.PLUGINS_CONFIG.get('netbox_rpki', {})

if plugin_settings.get('top_level_menu'):
    menu = PluginMenu(
        label="RPKI",
        groups=(("RPKI", _menu_items),),
        icon_class="mdi mdi-bootstrap",
    )
else:
    menu_items = _menu_items

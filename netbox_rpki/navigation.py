from django.conf import settings

from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu


_menu_items = (
    PluginMenuItem(
        link='plugins:netbox_rpki:rpkiorganization_list',
        link_text='RPKI Organizations',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:rpkiorganization_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),

    PluginMenuItem(
        link='plugins:netbox_rpki:rpkicertificate_list',
        link_text='RPKI Customer Certificates',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:rpkicertificate_add',
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),

    PluginMenuItem(
        link='plugins:netbox_rpki:rpkiroa_list',
        link_text='RPKI ROAs',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_rpki:rpkiroa_add',
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

"""Menu buttons for netbox_ptov plugin

Defines the menu/sidebar objects used by Django/Netbox when the netbox_ptov plugin is installed"""


from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu


gns3srv_buttons = (
    PluginMenuButton(
        link="plugins:netbox_ptov:gns3srv_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
    ),
)

ptovjob_buttons = (
    PluginMenuButton(
        link="plugins:netbox_ptov:ptovjob_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
    ),
)


_menu_items = (
    PluginMenuItem(
        link="plugins:netbox_ptov:golab",
        link_text="Run a V-Lab",
    ),
    PluginMenuItem(
        link="plugins:netbox_ptov:gns3srv_list",
        link_text="GNS3 Servers",
        buttons=gns3srv_buttons,
    ),
#    PluginMenuItem(
#        link="plugins:netbox_ptov:ptovjob_list",
#        link_text="Virtual-lab templates",
#        buttons=ptovjob_buttons,
#    ),
)

plugin_settings = settings.PLUGINS_CONFIG.get('netbox_ptov', {})

if plugin_settings.get('top_level_menu'):
    menu = PluginMenu(  
        label="P to V-lab (Arista)",
        groups=(("P to V-lab (Arista)", _menu_items),),
        icon_class="mdi mdi-bootstrap",
    )
else:
    menu_items = _menu_items

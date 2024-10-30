"""Menu buttons for netbox_ptov plugin

Defines the menu/sidebar objects used by Django/Netbox when the netbox_ptov plugin is installed"""


from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu


rpkiOrganization_buttons = (
    PluginMenuButton(
        link="plugins:netbox_rpki:rpkiOrganization_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
    )
)

rpkiCertificate_buttons = (
    PluginMenuButton(
        link="plugins:netbox_rpki:rpkiCertificate_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
    )
)

rpkiRoa_buttons = (
    PluginMenuButton(
        link="plugins:netbox_rpki:rpkiRoa_add",
        title="Add",
        icon_class="mdi mdi-plus-thick",
    )
)


_menu_items = (
    PluginMenuItem(
        link="plugins:netbox_rpki:rpkiOrganization_list",
        link_text="RPKI Organizations",
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_rpki:rpkiOrganization_add",
                title="Add",
                icon_class="mdi mdi-plus-thick",
            )
        ),
    ),

    PluginMenuItem(
        link="plugins:netbox_rpki:rpkiCertificates_list",
        link_text="RPKI Customer Certificates",
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_rpki:rpkiCertificate_add",
                title="Add",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),

    PluginMenuItem(
        link="plugins:netbox_rpki:rpkiRoa_list",
        link_text="RPKI ROAs",
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_rpki:rpkiRoa_add",
                title="Add",
                icon_class="mdi mdi-plus-thick",
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

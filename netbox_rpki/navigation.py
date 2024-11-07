from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
from netbox.plugins.utils import get_plugin_config


from django.conf import settings

from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu


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
        ),
            ("ROAs", roa_menu_items),
        ),
        icon_class="mdi mdi-bootstrap",
    )
else:
    menu_items = (
        resource_menu_items,
        roa_menu_items
    )
































































menu_name = "RPKI"
top_level_menu = get_plugin_config("netbox_rpki", "top_level_menu")

organization_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:organization_list',
    link_text='RIR Customer Orgs',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:organization_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

certificate_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:certificate_list',
    link_text='Resource Certificates',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:certificate_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

certprefix_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:certificate_list',
    link_text='IP Prefix Resources',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:certificateprefix_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

certasn_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:certificateasn_list',
    link_text='AS Number Resources',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:certificateasn_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

roa_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:roa_list',
    link_text='ROAs',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:roa_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

roaprefix_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:roaprefix_list',
    link_text='ROA Prefices',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            'plugins:netbox_rpki:roaprefix_add',
            title='Add',
            "mdi mdi-plus-thick",
            permissions=["netbox_rpki.add_view"],
        ),
    ),
)

plugin_settings = settings.PLUGINS_CONFIG.get('netbox_rpki', {})

if plugin_settings.get('top_level_menu'):
    menu = PluginMenu(
        label=menu_name,
        groups=(
            (
                _("Resources"),
                (
                    organization_menu_item,
                    certificate_menu_item,
                    certprefix_menu_item,
                    certasn_menu_item,
                ),
            ),
            (
                _("ROAs"),
                (
                    roa_menu_item,
                    roaprefix_menu_item,
                ),
            ),
         ),
        icon_class="mdi mdi-dns",
    )
else:
    menu_items = (
        organization_menu_item,
        certificate_menu_item,
        certprefix_menu_item,
        certasn_menu_item,
        roa_menu_item,
        roaprefix_menu_item,
    )

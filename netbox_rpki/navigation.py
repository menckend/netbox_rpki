from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu
from netbox.plugins.utils import get_plugin_config


organization_menu_item = PluginMenuItem(
    link='plugins:netbox_rpki:organization_list',
    link_text='RIR Customer Orgs',
    permissions=["netbox_rpki.view_view"],
    buttons=(
        PluginMenuButton(
            link='plugins:netbox_rpki:organization_add',
            _("Add"),
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
            link='plugins:netbox_rpki:certificate_add',
            _("Add"),
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
            link='plugins:netbox_rpki:certificateprefix_add',
            _("Add"),
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
            link='plugins:netbox_rpki:certificateasn_add',
            _("Add"),
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
            link='plugins:netbox_rpki:roa_add',
            _("Add"),
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
            link='plugins:netbox_rpki:roaprefix_add',
            _("Add"),
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

from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu

from netbox_rpki.object_registry import get_navigation_groups


def build_menu_item(spec):
    return PluginMenuItem(
        link=spec.list_url_name,
        link_text=spec.navigation.label,
        buttons=(
            PluginMenuButton(
                link=spec.add_url_name,
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    )


navigation_groups = {
    group_name: tuple(build_menu_item(spec) for spec in specs)
    for group_name, specs in get_navigation_groups()
}

resource_menu_items = navigation_groups.get('Resources', ())
roa_menu_items = navigation_groups.get('ROAs', ())

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

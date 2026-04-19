from django.conf import settings
from netbox.plugins import PluginMenuButton, PluginMenuItem, PluginMenu

from netbox_rpki.maturity import get_badge, is_hidden
from netbox_rpki.object_registry import get_navigation_groups


plugin_settings = settings.PLUGINS_CONFIG.get('netbox_rpki', {})
_hide_experimental = plugin_settings.get('hide_experimental', False)

OPERATIONS_MENU_ITEM = PluginMenuItem(
    link='plugins:netbox_rpki:operations_dashboard',
    link_text='Operations',
    permissions=[
        'netbox_rpki.view_rpkiprovideraccount',
        'netbox_rpki.view_roaobject',
        'netbox_rpki.view_certificate',
    ],
)

PROVIDER_SYNC_HEALTH_MENU_ITEM = PluginMenuItem(
    link='plugins:netbox_rpki:provideraccount_summary',
    link_text='Provider Sync Health',
    permissions=[
        'netbox_rpki.view_rpkiprovideraccount',
    ],
)

IRR_DIVERGENCE_MENU_ITEM = PluginMenuItem(
    link='plugins:netbox_rpki:irr_divergence_dashboard',
    link_text='IRR Divergence Dashboard',
    permissions=[
        'netbox_rpki.view_irrcoordinationresult',
    ],
)

INTENT_AUTHORITY_MAP_MENU_ITEM = PluginMenuItem(
    link='plugins:netbox_rpki:intent_authority_map',
    link_text='Intent Authority Map',
    permissions=[
        'netbox_rpki.view_roaintent',
        'netbox_rpki.view_roaintentresult',
        'netbox_rpki.view_roareconciliationrun',
    ],
)


def build_menu_item(spec):
    buttons = ()
    if spec.navigation.show_add_button and spec.view is not None and spec.view.supports_create:
        buttons = (
            PluginMenuButton(
                link=spec.add_url_name,
                title='Add',
                icon_class='mdi mdi-plus-thick',
            ),
        )

    return PluginMenuItem(
        link=spec.list_url_name,
        link_text=spec.navigation.label,
        buttons=buttons,
    )


navigation_groups = {
    group_name: tuple(build_menu_item(spec) for spec in specs)
    for group_name, specs in get_navigation_groups()
    if not is_hidden(group_name, hide_experimental=_hide_experimental)
}
navigation_groups['Intent'] = (INTENT_AUTHORITY_MAP_MENU_ITEM,) + navigation_groups.get('Intent', ())
if not is_hidden('IRR', hide_experimental=_hide_experimental):
    navigation_groups['IRR'] = navigation_groups.get('IRR', ()) + (IRR_DIVERGENCE_MENU_ITEM,)
navigation_groups['Resources'] = navigation_groups.get('Resources', ()) + (
    PROVIDER_SYNC_HEALTH_MENU_ITEM,
    OPERATIONS_MENU_ITEM,
)

menu_groups = tuple(
    (group_name, navigation_groups.get(group_name, ()))
    for group_name, _specs in get_navigation_groups()
    if not is_hidden(group_name, hide_experimental=_hide_experimental)
)

resource_menu_items = navigation_groups.get('Resources', ())
roa_menu_items = navigation_groups.get('ROAs', ())

if plugin_settings.get('top_level_menu'):
    menus = tuple(
        PluginMenu(
            label=f'RPKI {group_name}{get_badge(group_name)}',
            groups=[(group_name, items)],
            icon_class='mdi mdi-bootstrap',
        )
        for group_name, items in menu_groups
    )
else:
    menu_items = tuple(
        item
        for _group_name, group_items in menu_groups
        for item in group_items
    )

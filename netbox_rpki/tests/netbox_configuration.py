import os
from copy import deepcopy

from netbox.configuration_testing import *  # noqa: F401,F403


DATABASES = deepcopy(DATABASES)
DATABASES['default'].update({
    'NAME': os.getenv('NETBOX_TEST_DB_NAME', DATABASES['default']['NAME']),
    'USER': os.getenv('NETBOX_TEST_DB_USER', DATABASES['default']['USER']),
    'PASSWORD': os.getenv('NETBOX_TEST_DB_PASSWORD', DATABASES['default']['PASSWORD']),
    'HOST': os.getenv('NETBOX_TEST_DB_HOST', DATABASES['default']['HOST']),
    'PORT': os.getenv('NETBOX_TEST_DB_PORT', DATABASES['default']['PORT']),
})
DATABASES['default'].setdefault('TEST', {})
DATABASES['default']['TEST']['NAME'] = os.getenv(
    'NETBOX_TEST_DB_TEST_NAME',
    f"test_{DATABASES['default']['NAME']}_rpki",
)

REDIS = deepcopy(REDIS)
for section_name in ('tasks', 'caching'):
    REDIS[section_name].update({
        'HOST': os.getenv('NETBOX_TEST_REDIS_HOST', REDIS[section_name]['HOST']),
        'PORT': os.getenv('NETBOX_TEST_REDIS_PORT', REDIS[section_name]['PORT']),
        'PASSWORD': os.getenv('NETBOX_TEST_REDIS_PASSWORD', REDIS[section_name]['PASSWORD']),
    })

PLUGINS = [plugin_name for plugin_name in PLUGINS if plugin_name != 'netbox_rpki']
PLUGINS.append('netbox_rpki')

PLUGINS_CONFIG = {
    **globals().get('PLUGINS_CONFIG', {}),
    'netbox_rpki': {
        'top_level_menu': True,
    },
}
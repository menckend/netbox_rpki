# NetBox RPKI Plugin

Netbox plugin for adding BGP RPKI elements.

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_rpki)
* [Repository](https://github.com/menckend/netbox_rpki)
* [Python Package](https://pypi.org/project/netbox_rpki/)

## Features

* RPKI stuf....




## Compatibility

| NetBox Version | Plugin Version |
|----------------|----------------|
|     4.1        |      0.1.x     |

## Installing

For adding to a NetBox Docker setup see
[the general instructions for using netbox-docker with plugins](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins).

Install using pip:

```bash
pip install netbox_rpki
```

or by adding to your `local_requirements.txt` or `plugin_requirements.txt` (netbox-docker):

```bash
netbox_rpki
```

Enable the plugin in `/opt/netbox/netbox/netbox/configuration.py`,
 or if you use netbox-docker, your `/configuration/plugins.py` file :

```python
PLUGINS = [
    'netbox_rpki'
]

PLUGINS_CONFIG = {
    "netbox_rpki": {'top_level_menu': False},
}
```

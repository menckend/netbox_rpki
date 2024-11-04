# NetBox RPKI Plugin

Netbox plugin for adding BGP RPKI elements.

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_rpki)
* [Repository](https://github.com/menckend/netbox_rpki)
* [Python Package](https://pypi.org/project/netbox_rpki/)

## Features

Implements data models and forms for Resource Public Key Infrastructure (RPKI) items.  Models included are:
*Regional Internet Registry ("RIR)
   * Existing model in Netbox IPAM table
   * Used as a foreign key (parent) to the RPKI "Organization" model
* Organization
   * A customer/consumer of RIR services such as RPKI (and IP address and ASN allocations)
   * "Child" relationship to IPAM RIR "parent" model 
   * Parent relationship to "Customer certificate" model
* Customer Certificate
   * The X.509 certificate used to sign a customer's ROAs
   * May be either self-hosted or managed by the RIR (as part of a "managed" RPKI service)
   * Each customer certificate has a child->parent relationship to a single RPKI Organization object
* Route Origination Authorization (ROA)
   * A statement that a specific AS number is authorized to originate a specific set of IP prefices.
   * Each ROA has a child->parent relationship to a single RPKI ROA object
* ROA prefix
   * A specific prefix that is included in the scope of a specific ROA

* RPKI stuf....




## Compatibility

| NetBox Version | Plugin Version |
|----------------|----------------|
|     4.1        |      0.0.2     |

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

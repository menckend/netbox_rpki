# NetBox PtoV Plugin

Netbox plugin for pulling runstate (config and topology) from Arista switches and replicating them in a GNS3 virtual lab using Arista cEOS containers

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_ptov)
* [Repository](https://github.com/menckend/netbox_ptov)
* [Python Package](https://pypi.org/project/netbox-ptov/)

## Features

* Creates a new model/table for storing the DNS names of your GNS3 servers.  [("Boring, Sidney; borrring, borrrrrrring"](https://youtu.be/ieqxmg4pmZo?si=rXJtimC0e0_QpEp7&t=147), I know.)

* Provides a screen/page that prompts you to:
  * Select a GNS3 server and as few or as many Arista switches as you want from your devices table.
  * Enter a set of Arista EOS credentials
  * Enter a project-name to use for a new project on the GNS3 server ![image](./images/ptov-pic1.png)


* **Programmatically instantiates a GNS3 virtual-lab**, populated with Arista **cEOS container/nodes**, each of which is:
  * **MLAG friendly**  (each container is configured to use the system-mac address of the "real" switch it is emulating)
  * Running a (cEOS/lab conformed) copy of the **startup-config of the switch it is emulating**
  * Running the same cEOS version as the switch that it is emulating (if you have a matching Docker template installed on your GNS3 server)
  * Happy to run as an EVPN/VXLAN fabric, if that's your bag.
  * Has "links" provisioned in the vlab, **mirroring the inter-switch links of the "live" switches you're modeling** (detected when inspecting th LLDP tables of the switches)
* Returns a URL ![image](./images/ptov-pic2.png)

* ...at which you can access the virtual-lab you just created. ![image](./images/ptov-pic3.png)


## Contemplated Use-cases

Change modeling, obviously.  Invasive troubleshooting of pesky routing issues that you wouldn't want to spend *six hours* setting up a vlab for, but that would be well-worth the effort if it only took two minutes to set up.   (The 14-switch topology shown in the images above took just under 60 seconds instantiate.)

## Under the hood

All of the heavy lifting is done by the [dcnodatg package](https://menckend.github.io/dcnodatg)

## Compatibility

| NetBox Version | Plugin Version |
|----------------|----------------|
|     4.1        |      0.1.x     |

## Installing

For adding to a NetBox Docker setup see
[the general instructions for using netbox-docker with plugins](https://github.com/netbox-community/netbox-docker/wiki/Using-Netbox-Plugins).

Install using pip:

```bash
pip install netbox_ptov
```

or by adding to your `local_requirements.txt` or `plugin_requirements.txt` (netbox-docker):

```bash
netbox_ptov
```

Enable the plugin in `/opt/netbox/netbox/netbox/configuration.py`,
 or if you use netbox-docker, your `/configuration/plugins.py` file :

```python
PLUGINS = [
    'netbox_ptov'
]

PLUGINS_CONFIG = {
    "netbox_ptov": {'top_level_menu': False},
}
```

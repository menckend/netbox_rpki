# NetBox RPKI Plugin

Netbox plugin for adding BGP RPKI elements.

* Free software: Apache-2.0
* [Documentation](https://menckend.github.io/netbox_rpki)
* [Repository](https://github.com/menckend/netbox_rpki)
* [Python Package](https://pypi.org/project/netbox_rpki/)

## Features

Implements data models and forms for modeling Resource Public Key Infrastructure (RPKI) items.  On organization the publishes ROAs (either self-hosted, or through a RIR's hosted-RPKI service) can use this plugin to create a self-hosted record of the critical RPKI elements such as resource certificates and ROAs 

### Models / DB tables

#### Organization
   - Represents a customer/consumer of Regional Internet Registrar (RIR) RPKI services
   - Fields
      - org-id, name, ext_url, parent_rir (foreign key to IPAM ASN)

#### Resource Certificate
   - Represents the "Resource Certificate" element of the RPKI architecture
     - An X.509 certificate with RFC3779-style extensions for IPs/ASNs
     - Signed by an RIR's RPKI trust-anchor certificate
     - Attests to authority for at least one ASN and at least one IP netblock
     - Used to sign the RPKI End Entity (EE) certificates which are used to sign individual ROAs
   - May be either self-hosted/managed/published (managed by customer) or managed by the RIR (as part of a "managed" RPKI service)
   - Fields
      - name, issuer, subject, serial, valid_from, valid_to, auto_renews, public_key, private_key, publication_url, ca_repository, self_hosted, rpki_org (foreign key to rpki organization)

#### Route Origination Authorization (ROA)
   - Represents the RPKI Route Origination Authorization (ROA) object
   - An artifact attesting that a specific ASN is authorized to originate a specific set of IP prefixes into BGP on the Internet
   - Is signed by an ephemeral "EE" certificate, which was signed by a more durable resource certificate.
   - When a non-zero ASN value is specified, the ROA is interpreted as authorizing origination
   - When an ASN of zero is specified, the ROA is interpreted as indicating that there is NO ASN that is authorized to originate routes for the specified prefix
     - Netbox does not permit an ASN value of zero, though -- I suggest earmarking AS 99999999 and commenting it as a place-holder for ASN 0
   - Fields
      - name, origin_as (foreign key to IPAM ASN model), valid_from, valid_to, auto_renews, signed_by (foreign key to rpki customer certificate)

#### ROA prefix
   - Represents the attestion relationship between an ROA and a prefix.
   - This model/table is not explicitly accessible via the UI menu

#### ROA ASN
   - Represents the attestion relationship between an ROA and an ASN.
   - This model/table is not explicitly accessible via the UI menu

#### Certificate prefix
   - Represents the attestion relationship between an ROA and a prefix.
   - This model/table is not explicitly accessible via the UI menu

#### Certificate ASN
   - Represents the attestion relationship between an ROA's EE certificate and an ASN.
   - This model/table is not explicitly accessible via the UI menu





## Screencaps

### RPKI Organizations/Certificates/Resources

![image](/images/rpki-org-detail.png)

![image](/images/rpki-cert-detail.png)

![image](/images/rpki-certasn-detail.png)

![image](/images/rpki-certprefix-detail.png)

### RPKI ROAs

![image](/images/rpki-roa-detail.png)

![image](/images/rpki-roaprefix-detail.png)




## Compatibility

[netbox-plugin.yaml](netbox-plugin.yaml)

The plugin currently declares NetBox compatibility for the 4.5.x release line.

Validation completed against real development installs of:

- NetBox 4.5.0
- NetBox 4.5.7

Validation evidence for both versions includes successful plugin bootstrap and `manage.py check` with the plugin enabled, plus the full Python test suite passing (`185` tests). Browser smoke coverage was also run successfully against the NetBox 4.5.0 environment (`7` Playwright specs passed).


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

Run  `python -m manage.py migrate` from the .../netbox/netbox/ directory in your netbox installation. (or include the manage.py migrate command in Dockerfile-Plugins if using netbox-docker.)

## Browser E2E Tests

The repo includes a minimal Playwright suite under `tests/e2e/` for real plugin Web UI CRUD coverage.

- It targets a running local NetBox dev instance, defaulting to `http://127.0.0.1:8000`
- It logs in as the local `admin` user created by `devrun/dev.sh start`
- It prepares only the core NetBox prerequisites the plugin forms depend on and cleans up prior E2E-marked plugin objects
- It does not require `dev.sh seed`, though seeded data remains compatible with the suite
- The recommended entry point in WSL is `cd devrun && ./dev.sh e2e`

See `tests/e2e/README.md` for setup, environment variables, and exact commands.

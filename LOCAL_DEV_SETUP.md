# Local Dev Setup Checklist

This checklist sets up a WSL-native NetBox development environment for working on the `netbox_rpki` plugin without polluting the rest of the WSL image with project-specific Python packages.

Python runs directly inside WSL virtual environments. PostgreSQL and Redis run as containers.

## Baseline decisions

- Use WSL 2 Ubuntu as the primary development environment.
- Keep active source checkouts under the Linux filesystem, for example `~/src/`.
- Use one Python virtual environment per NetBox release line.
- Run PostgreSQL and Redis as containers instead of long-lived native WSL services.
- Start against NetBox `v4.5.7`, then add recent secondary targets such as `v4.4.10`.
- Avoid using the Windows-mounted OneDrive path for active WSL development.
- Add your WSL user to the `docker` group so the container workflow does not require root.

## Checklist

- [ ] Confirm WSL distro, Python, git, Docker, and Compose availability.
- [ ] Create a Linux-side workspace layout under `~/src` and `~/.virtualenvs`.
- [ ] Clone `netbox_rpki` into WSL under `~/src/netbox_rpki`.
- [ ] Clone NetBox into WSL and pin a working tree to `v4.5.7`.
- [ ] Create a dedicated virtual environment for NetBox `v4.5.7`.
- [ ] Install NetBox requirements into the `v4.5.7` virtual environment.
- [ ] Install `netbox_rpki` in editable mode into the same virtual environment.
- [ ] Start PostgreSQL and Redis containers for a local NetBox dev instance.
- [ ] Create a local NetBox `configuration.py` for the `v4.5.7` checkout.
- [ ] Enable the plugin in `PLUGINS` and add minimal `PLUGINS_CONFIG`.
- [ ] Run NetBox migrations and create a superuser.
- [ ] Start NetBox and confirm clean startup with the plugin enabled.
- [ ] Capture any import, migration, serializer, URL, or test failures from the plugin.
- [ ] Use the reusable scripts in `devrun/` instead of one-off setup commands.
- [ ] Create a second release-pinned environment for another recent NetBox release.
- [ ] Add lightweight scripts or notes for repeating the setup later.

## Recommended paths

```text
~/src/netbox_rpki
~/src/netbox-v4.5.7
~/src/netbox-v4.4.10
~/.virtualenvs/netbox-4.5.7
~/.virtualenvs/netbox-4.4.10
```

## Container services

Use the local compose stack under `devrun/` to provide PostgreSQL and Redis on `127.0.0.1:5432` and `127.0.0.1:6379` respectively.

```bash
cd ~/src/netbox_rpki/devrun
./start.sh
./status.sh
```

`bootstrap-netbox.sh` creates or updates `.env` for the local container stack, so you do not need a separate copy step unless you want to override it manually.

## Reusable Commands

Run these directly in the WSL-remote VS Code terminal from `~/src/netbox_rpki/devrun`.

```bash
./dev.sh start
./dev.sh e2e
./dev.sh seed
./dev.sh status
./dev.sh stop
```

`dev.sh start` is the primary entry point. It idempotently brings up the container stack, refreshes the NetBox development configuration, runs migrations, refreshes collected static assets, ensures the local `admin` user exists, and then starts the NetBox development server.

`dev.sh status` reports the current NetBox checkout, virtualenv, generated config path, container health, and whether the development server is already running.

`dev.sh seed` idempotently populates the local development database with a broad sample RPKI object graph covering organizations, certificates, ROAs, prefixes, and ASN assignments. Use it when you want a non-empty UI for manual clickthrough or browser-driven smoke checks.

`dev.sh e2e` runs the Playwright browser suite through the local WSL wrapper. It reuses a user-local Node install if present, installs npm dependencies and Playwright Chromium on demand, injects the local Chromium library overrides needed on minimal WSL images, and then runs the browser suite against the local NetBox instance.

`dev.sh stop` stops the NetBox development server for the current checkout and brings down the local PostgreSQL and Redis containers.

The smaller scripts remain available if you want them for debugging or one-off tasks:

```bash
./bootstrap-netbox.sh
./check-netbox.sh
./runserver.sh
./status.sh
./stop.sh
```

`runserver.sh` still starts the NetBox development server with the plugin enabled by default. Override the bind target with `NETBOX_RUN_HOST` and `NETBOX_RUN_PORT` if needed.

## Target commands

```bash
mkdir -p ~/src ~/.virtualenvs
python3.12 -m venv ~/.virtualenvs/netbox-4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
python -m pip install --upgrade pip setuptools wheel

git clone https://github.com/netbox-community/netbox.git ~/src/netbox-v4.5.7
cd ~/src/netbox-v4.5.7
git checkout v4.5.7
python -m pip install -r requirements.txt

git clone <plugin-remote-or-local-mirror> ~/src/netbox_rpki
cd ~/src/netbox_rpki
python -m pip install -e .
```

## Notes

- NetBox `main` is not the right first target for reviving this plugin. Start with the current stable release tag.
- The plugin currently advertises old compatibility bounds and will likely need packaging, API, tests, and UI cleanup before it boots cleanly on NetBox `4.5.x`.
- Python package isolation remains in per-release WSL virtual environments.
- Native PostgreSQL and Redis server packages were removed from WSL after the container stack was established.
- Existing WSL shells opened before the `docker` group change need to be restarted before they can use Docker without root.

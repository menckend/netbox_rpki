# Local Development Environment

This document is the source of truth for the WSL-native development environment used for ongoing work on the `netbox_rpki` plugin.

It covers two things:

1. How to create the local environment that the `devrun/` scripts expect.
2. How to use that environment during normal plugin development, testing, and browser-based verification.

The current default target is NetBox `4.5.7`.

## What The `devrun/` Scripts Assume

By default, the scripts in [`devrun/`](/home/mencken/src/netbox_rpki/devrun) assume this layout:

```text
~/src/netbox_rpki
~/src/netbox-v4.5.7
~/src/netbox-v4.5.7/netbox
~/.virtualenvs/netbox-4.5.7
~/.config/netbox-rpki-dev
~/src/krill_for_netbox_rpki            # optional
```

Important defaults from [`devrun/common.sh`](/home/mencken/src/netbox_rpki/devrun/common.sh):

- `NETBOX_RELEASE=4.5.7`
- `NETBOX_SRC=$HOME/src/netbox-v${NETBOX_RELEASE}`
- `NETBOX_PROJECT_DIR=$NETBOX_SRC/netbox`
- `VENV_DIR=$HOME/.virtualenvs/netbox-${NETBOX_RELEASE}`
- `STATE_DIR=$HOME/.config/netbox-rpki-dev`
- `KRILL_ROOT=$HOME/src/krill_for_netbox_rpki`

If you keep the same naming convention, the scripts work without extra environment variables.

## Host Prerequisites

The scripts run Python directly in WSL, and run PostgreSQL and Redis as Docker containers.

Install these on the WSL host before using `devrun/`:

- `git`
- `python3.12` and `python3.12-venv`
- `docker` with `docker compose`
- `pg_isready` from the PostgreSQL client packages
- `redis-cli` from the Redis tools package
- `curl`

If you plan to run browser E2E tests, also install:

- `node`, `npm`, and `npx`

If you plan to let `devrun/e2e.sh` unpack local Chromium shared libraries on a minimal WSL image, it also expects:

- `apt`
- `apt-cache`
- `dpkg-deb`

On Ubuntu/WSL, a practical starting point is:

```bash
sudo apt update
sudo apt install -y \
    git \
    curl \
    python3.12 \
    python3.12-venv \
    docker.io \
    docker-compose-plugin \
    postgresql-client \
    redis-tools
```

If Docker is configured with the `docker` group, restart your shell after changing group membership.

## One-Time Setup

### 1. Create the workspace roots

```bash
mkdir -p ~/src ~/.virtualenvs
```

### 2. Clone the NetBox source tree

The scripts expect a release-pinned checkout whose directory name matches the release.

```bash
git clone https://github.com/netbox-community/netbox.git ~/src/netbox-v4.5.7
cd ~/src/netbox-v4.5.7
git checkout v4.5.7
```

The important path is the inner project directory containing `manage.py`:

```text
~/src/netbox-v4.5.7/netbox
```

### 3. Create the matching virtualenv

```bash
python3.12 -m venv ~/.virtualenvs/netbox-4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### 4. Install NetBox requirements into that virtualenv

Install the requirements from the NetBox checkout into the release-matched virtualenv.

```bash
cd ~/src/netbox-v4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
python -m pip install -r requirements.txt
```

The `devrun/bootstrap-netbox.sh` script later drops a `netbox.pth` file into this virtualenv so imports resolve to the local NetBox source tree under `~/src/netbox-v4.5.7/netbox`.

### 5. Clone and install the plugin in editable mode

```bash
git clone <your-netbox_rpki-remote> ~/src/netbox_rpki
cd ~/src/netbox_rpki
source ~/.virtualenvs/netbox-4.5.7/bin/activate
python -m pip install -e ".[test]"
```

`-e .` is enough for the plugin itself. `-e ".[test]"` is the more useful development setup because it also installs the repo's Python-side tooling extras such as `black`, `flake8`, `pre-commit`, and `pytest`.

### 6. Start the local environment through `devrun`

From the plugin repo:

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh start
```

On first run this does all of the environment preparation that should be automated:

- starts the local PostgreSQL and Redis containers from [`docker-compose.yml`](/home/mencken/src/netbox_rpki/devrun/docker-compose.yml)
- creates or refreshes `devrun/.env`
- creates `~/.config/netbox-rpki-dev/credentials.env`
- writes NetBox `configuration.py` at `~/src/netbox-v4.5.7/netbox/netbox/configuration.py`
- enables the plugin automatically when `NETBOX_RPKI_ENABLE=1`
- runs `manage.py migrate`
- runs `manage.py collectstatic`
- runs `manage.py check`
- creates or updates the local `admin` superuser
- starts an RQ worker
- starts the NetBox development server
- starts Krill too, if a compatible Krill workspace exists

You do not need to hand-maintain `configuration.py`, database credentials, or the local admin user if you use `./dev.sh start`.

## Optional Krill Workspace

Krill is optional for general plugin work, but it is part of the local environment for hosted-provider sync and write flows.

The `devrun` scripts do not install Krill for you. They only auto-detect and use an external workspace if these files exist:

- `~/src/krill_for_netbox_rpki/scripts/start-krill.sh`
- `~/src/krill_for_netbox_rpki/scripts/stop-krill.sh`
- `~/src/krill_for_netbox_rpki/etc/krill.conf`
- `~/src/krill_for_netbox_rpki/cargo-root/bin/krill`

The current local Krill workspace on this machine follows this shape:

```text
~/src/krill_for_netbox_rpki/
  cargo-root/bin/krill
  cargo-root/bin/krillc
  etc/krill.conf
  scripts/env.sh
  scripts/start-krill.sh
  scripts/stop-krill.sh
  var/data
  var/log
  var/run
```

The local `krill.conf` serves Krill on `https://localhost:3001/`, stores state under `~/src/krill_for_netbox_rpki/var/data`, and writes logs and the PID file under `var/log` and `var/run`.

The installed local binary is currently `krill 0.16.0`, rooted under `~/src/krill_for_netbox_rpki/cargo-root`.

Practical guidance:

- If you are not working on provider sync or Krill-backed write flows, you can ignore Krill.
- If the workspace exists, `./dev.sh start` will start it and `./dev.sh stop` will stop it.
- If the workspace does not exist, `devrun` skips Krill and the rest of the NetBox environment still works.

## Generated Local State

After the first successful bootstrap, these generated files matter:

- `devrun/.env`
  Used by Docker Compose for the local PostgreSQL container credentials.
- `~/.config/netbox-rpki-dev/credentials.env`
  Stores generated values such as `NETBOX_DATABASE_PASSWORD`, `NETBOX_ADMIN_PASSWORD`, `NETBOX_SECRET_KEY`, and `NETBOX_API_TOKEN_PEPPER`.
- `~/src/netbox-v4.5.7/netbox/netbox/configuration.py`
  Generated NetBox config for the local dev instance.
- `~/.config/netbox-rpki-dev/*.log`
  Logs from migrations, checks, collectstatic, seeding, and superuser creation.

## Normal Daily Workflow

The common loop is:

1. Start the stack.
2. Develop in the plugin repo.
3. Run focused Python tests while iterating.
4. Run the full plugin suite before concluding the change.
5. Run browser E2E when the change affects UI behavior.
6. Stop the stack when finished.

### Start the stack

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh start
```

This is the normal entry point. Use it instead of manually starting containers, writing config, or launching NetBox by hand.

### Check status

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh status
```

This reports:

- active release
- NetBox project path
- virtualenv path
- generated config and credentials paths
- whether `runserver`, the worker, and Krill are running
- Docker container status
- PostgreSQL and Redis reachability

### Seed reusable sample data

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh seed
```

This populates the local database with a reusable sample RPKI object graph. It is useful for manual browser clickthrough and exploratory UI work. It is not required for the Playwright suite.

### Stop the stack

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh stop
```

This stops:

- the NetBox development server
- the RQ worker
- Krill, if the external Krill workspace is installed
- the local PostgreSQL and Redis containers

## Running Tests During Development

### Python test suite

The primary Python test runner for this plugin is NetBox's Django test command, not `pytest`.

Run the full plugin suite from the NetBox project directory:

```bash
cd ~/src/netbox-v4.5.7/netbox
NETBOX_RPKI_ENABLE=1 ~/.virtualenvs/netbox-4.5.7/bin/python \
    manage.py test --keepdb --noinput netbox_rpki.tests
```

Run focused tests the same way:

```bash
cd ~/src/netbox-v4.5.7/netbox
NETBOX_RPKI_ENABLE=1 ~/.virtualenvs/netbox-4.5.7/bin/python \
    manage.py test --keepdb --noinput netbox_rpki.tests.test_provider_sync
```

Useful points:

- `--keepdb` makes repeated local runs much faster.
- `--noinput` keeps the command non-interactive.
- `NETBOX_RPKI_ENABLE=1` is required so the plugin is loaded during the test run.

### Basic environment validation

If you only want to compare baseline NetBox startup versus plugin-enabled startup:

```bash
cd ~/src/netbox_rpki/devrun
./check-netbox.sh
```

This writes baseline and plugin-enabled check logs under `~/.config/netbox-rpki-dev/`.

### Browser E2E suite

The Playwright suite expects a running local NetBox instance with the plugin enabled.

One-time browser runtime prep:

```bash
cd ~/src/netbox_rpki/devrun
./e2e.sh install
```

Run the browser suite:

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh e2e
```

Other useful forms:

```bash
cd ~/src/netbox_rpki/devrun
./e2e.sh headed
./e2e.sh tests/e2e/netbox-rpki/roas.spec.js --project=chromium
```

The wrapper installs npm dependencies and Playwright Chromium on demand, checks that NetBox is reachable at `http://127.0.0.1:8000`, and then runs the suite.

## Script Reference

Primary entry points in [`devrun/`](/home/mencken/src/netbox_rpki/devrun):

- `./dev.sh start`
  Full bootstrap plus local NetBox startup.
- `./dev.sh status`
  Show the current environment and process status.
- `./dev.sh seed`
  Seed reusable sample plugin data.
- `./dev.sh e2e`
  Run the Playwright suite.
- `./dev.sh stop`
  Stop NetBox, worker, Krill, and containers.

Secondary scripts for debugging:

- `./bootstrap-netbox.sh`
  Regenerate credentials, config, migrations, collectstatic, and admin user setup without starting `runserver`.
- `./runserver.sh`
  Start just the NetBox dev server.
- `./worker.sh`
  Start just the RQ worker.
- `./check-netbox.sh`
  Compare baseline NetBox checks and plugin-enabled checks.
- `./status.sh`
  Lower-level status report used by `dev.sh status`.
- `./stop.sh`
  Lower-level stop script used by `dev.sh stop`.

## Useful Overrides

If you want to target a different NetBox checkout or virtualenv, override the defaults explicitly.

Example for NetBox `4.5.0`:

```bash
cd ~/src/netbox_rpki/devrun
NETBOX_RELEASE=4.5.0 ./dev.sh start
```

Or set paths directly:

```bash
cd ~/src/netbox_rpki/devrun
NETBOX_PROJECT_DIR=~/src/netbox-v4.5.7/netbox \
VENV_DIR=~/.virtualenvs/netbox-4.5.7 \
./dev.sh start
```

Common overrides:

- `NETBOX_RELEASE`
- `NETBOX_SRC`
- `NETBOX_PROJECT_DIR`
- `VENV_DIR`
- `KRILL_ROOT`
- `NETBOX_RUN_HOST`
- `NETBOX_RUN_PORT`
- `NETBOX_E2E_BASE_URL`
- `NODE_LTS_BIN`

## Recommended Development Habit

Use the script-driven workflow consistently:

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh start
```

Then iterate with direct Django test commands from the NetBox checkout, and use:

```bash
./dev.sh e2e
./dev.sh stop
```

That keeps the local environment reproducible and aligned with the paths and assumptions already encoded in this repo.

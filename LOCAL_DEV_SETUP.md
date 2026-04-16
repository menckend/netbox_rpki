# Local Development Environment

This document covers how to set up and use the local development environment for the `netbox_rpki` plugin. The environment runs Python natively on the host (Linux or WSL) and uses Docker containers for PostgreSQL, Redis, Routinator, and IRRd.

The current default target is NetBox **4.5.7**.

**Contents:**
- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [One-Time Setup](#one-time-setup)
- [Daily Workflow](#daily-workflow)
- [Running Tests](#running-tests)
- [Browser E2E Tests](#browser-e2e-tests)
- [Local IRRd Lab](#local-irrd-lab)
- [Optional: Krill](#optional-krill)
- [Environment Overrides](#environment-overrides)
- [Script Reference](#script-reference)
- [Generated State Reference](#generated-state-reference)

---

## Quick Start

If you already have git, Python 3.12+, Docker, `pg_isready`, `redis-cli`, and `curl` installed:

```bash
# 1. Create workspace directories
mkdir -p ~/src ~/.virtualenvs

# 2. Clone and pin NetBox
git clone https://github.com/netbox-community/netbox.git ~/src/netbox-v4.5.7
cd ~/src/netbox-v4.5.7 && git checkout v4.5.7

# 3. Create a virtualenv and install NetBox dependencies
python3.12 -m venv ~/.virtualenvs/netbox-4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Clone and install the plugin
git clone <your-netbox_rpki-remote> ~/src/netbox_rpki
cd ~/src/netbox_rpki
pip install -e ".[test]"

# 5. Start everything
cd devrun && ./dev.sh start

# 6. (Optional) Seed the local IRRd with sample data
./dev.sh irrd seed
```

After step 5, NetBox is running at `http://127.0.0.1:8000` with the plugin enabled. Step 6 is only needed if you are working on IRR integration features. The rest of this document explains each step and the ongoing workflow in detail.

---

## Prerequisites

### Required

| Package | Purpose |
|---|---|
| `git` | Source control |
| `python3.12` and `python3.12-venv` | Plugin and NetBox runtime (3.12 is the minimum; 3.13+ also works) |
| `docker` with `docker compose` | PostgreSQL, Redis, Routinator, and IRRd containers |
| `pg_isready` (from `postgresql-client`) | Startup health checks |
| `redis-cli` (from `redis-tools`) | Startup health checks |
| `curl` | Service verification |

### For browser E2E tests (optional)

| Package | Purpose |
|---|---|
| `node`, `npm`, `npx` | Playwright test runner |
| `apt`, `apt-cache`, `dpkg-deb` | Only needed if `e2e.sh` must unpack Chromium shared libraries on a minimal image |

### Ubuntu/WSL install example

```bash
sudo apt update
sudo apt install -y \
    git curl python3.12 python3.12-venv \
    docker.io docker-compose-plugin \
    postgresql-client redis-tools
```

> If you add yourself to the `docker` group, restart your shell before continuing.

---

## One-Time Setup

### 1. Create the workspace directories

```bash
mkdir -p ~/src ~/.virtualenvs
```

### 2. Clone and pin the NetBox source tree

The `devrun/` scripts expect a release-pinned checkout with a directory name that matches the release tag:

```bash
git clone https://github.com/netbox-community/netbox.git ~/src/netbox-v4.5.7
cd ~/src/netbox-v4.5.7
git checkout v4.5.7
```

### 3. Create the virtualenv

```bash
python3.12 -m venv ~/.virtualenvs/netbox-4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
pip install --upgrade pip setuptools wheel
```

### 4. Install NetBox dependencies

```bash
cd ~/src/netbox-v4.5.7
source ~/.virtualenvs/netbox-4.5.7/bin/activate
pip install -r requirements.txt
```

### 5. Clone and install the plugin

```bash
git clone <your-netbox_rpki-remote> ~/src/netbox_rpki
cd ~/src/netbox_rpki
source ~/.virtualenvs/netbox-4.5.7/bin/activate
pip install -e ".[test]"
```

The `[test]` extra installs development tooling (`black`, `flake8`, `pre-commit`). Use `pip install -e .` if you only need the plugin itself.

### 6. Start the local environment

```bash
cd ~/src/netbox_rpki/devrun
./dev.sh start
```

On first run, this performs all remaining setup automatically:

- Starts PostgreSQL, Redis, Routinator, and IRRd containers
- Generates credentials in `~/.config/netbox-rpki-dev/credentials.env`
- Generates `devrun/.env` for Docker Compose
- Writes `configuration.py` into the NetBox checkout
- Runs `manage.py migrate`, `collectstatic`, and `check`
- Creates an `admin` superuser (password stored in `credentials.env`)
- Creates a `ValidatorInstance` pointing at the local Routinator
- Starts an RQ worker and the NetBox development server
- Starts Krill if an [external Krill workspace](#optional-krill) is detected

You do not need to hand-maintain `configuration.py`, database credentials, or the admin user.

### 7. Verify

```bash
./dev.sh status            # process and service health summary
curl -sS http://127.0.0.1:8000/api/ | head   # NetBox API
```

---

## Daily Workflow

The recommended development loop:

1. **Iterate on code** in `~/src/netbox_rpki/`.
2. **Run tests** — most test runs need only PostgreSQL and Redis, not the full stack.
3. **Start the full stack** only when you need the browser UI or manual verification.
4. **Run E2E tests** when the change affects the UI.
5. **Stop the stack** when finished.

All commands below assume you are in `~/src/netbox_rpki/devrun/`.

### Start / stop / status

```bash
./dev.sh start     # full bootstrap + dev server
./dev.sh status    # show running processes and service health
./dev.sh stop      # stop everything (server, worker, Krill, containers)
```

### Seed sample data

```bash
./dev.sh seed
```

Populates the database with a reusable RPKI object graph for manual browser work. Not required for the Playwright E2E suite.

---

## Running Tests

The test runner is **Django's `manage.py test`**, not `pytest`. Always use the `devrun` wrapper, which manages the test settings, database, and service containers for you.

### Test lanes

```bash
./dev.sh test fast       # quick structural smoke checks (~seconds)
./dev.sh test contract   # registry/UI/API/GraphQL surface contracts
./dev.sh test provider   # fixture-backed provider sync/write workflows
./dev.sh test live-provider   # opt-in real-backend integration tests
./dev.sh test full       # the complete netbox_rpki.tests suite
```

Running `./dev.sh test` with no argument defaults to `contract`.
The `provider` lane is optional and is mainly for fixture-backed hosted-provider sync/write behavior; most day-to-day work should stay on `fast`, `contract`, or explicit labels.
The `live-provider` lane is separate on purpose: it is reserved for real backend integration coverage, defaults to a clean skip unless `NETBOX_RPKI_ENABLE_LIVE_PROVIDER_TESTS=1`, and discovers only modules named `netbox_rpki/tests/test_live_*.py`.

### Focused tests

Pass explicit Django test labels after the lane keyword (or in place of it):

```bash
./dev.sh test netbox_rpki.tests.test_provider_sync --verbosity 2
./dev.sh test contract --verbosity 2
```

### What the test wrapper does

- Uses the dedicated test settings module `netbox_rpki.tests.netbox_configuration` (not the dev `configuration.py`)
- Sets `NETBOX_RPKI_ENABLE=1` so the plugin loads
- Starts only PostgreSQL and Redis via Docker Compose
- Passes `--keepdb` and `--noinput` to `manage.py test` for speed

Most test runs do **not** require `./dev.sh start`.

### Raw Django command (escape hatch)

If you need to run `manage.py test` directly for debugging:

```bash
cd ~/src/netbox-v4.5.7/netbox
NETBOX_CONFIGURATION=netbox_rpki.tests.netbox_configuration \
NETBOX_RPKI_ENABLE=1 \
~/.virtualenvs/netbox-4.5.7/bin/python manage.py test \
  --keepdb --noinput netbox_rpki.tests.test_provider_sync
```

### Environment validation

Compare baseline NetBox startup with and without the plugin:

```bash
./check-netbox.sh
```

---

## Browser E2E Tests

The Playwright suite requires a running NetBox instance with the plugin enabled.

### One-time setup

```bash
./e2e.sh install    # installs npm deps + Playwright Chromium
```

### Run the suite

```bash
./dev.sh start      # ensure the stack is up
./dev.sh e2e        # run headless
```

### Other modes

```bash
./e2e.sh headed                                             # headed browser
./e2e.sh ui                                                 # Playwright UI mode
./e2e.sh tests/e2e/netbox-rpki/roas.spec.js --project=chromium   # single spec
```

The wrapper checks that NetBox is reachable at `http://127.0.0.1:8000` before running tests.

---

## Local IRRd Lab

IRRd runs as a Docker container managed by `devrun/docker-compose.yml`. There is no host-level IRRd install step.

> **Note:** `./dev.sh start` brings up the IRRd container and creates its database, but does **not** seed it with sample data. The `LOCAL-IRR` source will be empty until you run `./dev.sh irrd seed`. This is intentional — most plugin work does not require IRRd content, and automatic seeding would overwrite manual changes.

### Manage IRRd independently

```bash
./dev.sh irrd start    # start only IRRd (without full NetBox bootstrap)
./dev.sh irrd status   # check readiness
./dev.sh irrd logs     # view container logs
./dev.sh irrd seed     # load the deterministic LOCAL-IRR fixture dataset
./dev.sh irrd stop     # stop the container
```

### Default endpoints

| Service | URL |
|---|---|
| HTTP API | `http://127.0.0.1:6080` |
| Status | `http://127.0.0.1:6080/v1/status/` |
| Whois (HTTP) | `http://127.0.0.1:6080/v1/whois/` |
| Whois (TCP) | `127.0.0.1:6043` |

### Seed data

`./dev.sh irrd seed` posts a fixed RPSL fixture into the authoritative `LOCAL-IRR` source. The fixture includes a maintainer, person, aut-num, as-set, route-set, and IPv4/IPv6 route objects. The template lives in `devrun/irrd/fixtures/local-authoritative.rpsl`.

Verify with:

```bash
for q in LOCAL-IRR-MNT LOCAL-IRR-PERSON AS64500 203.0.113.0/24 \
         2001:db8:fbf4::/48 AS64500:RS-LOCAL-EDGE; do
  echo "--- $q ---"
  curl -sS --get --data-urlencode "q=$q" http://127.0.0.1:6080/v1/whois/
  echo
done
```

### Rebuilding after changes

If you modify `devrun/irrd/Dockerfile` or `devrun/irrd/entrypoint.sh`:

```bash
docker compose up -d --build --force-recreate irrd
```

> **Note:** The first IRRd image build is slower than other services because it installs Python build dependencies inside the image.

---

## Optional: Krill

Krill is only needed for hosted-provider sync and write flows. If you are not working on those features, skip this section entirely.

The `devrun` scripts do not install Krill. They auto-detect and use an external workspace at `~/src/krill_for_netbox_rpki/` if it contains:

```text
scripts/start-krill.sh
scripts/stop-krill.sh
etc/krill.conf
cargo-root/bin/krill
```

When detected:

- `./dev.sh start` starts Krill automatically.
- `./dev.sh stop` stops it.

When absent, `devrun` skips Krill and the rest of the environment works normally.

---

## Environment Overrides

The `devrun/` scripts use sensible defaults from `devrun/common.sh`. Override them with environment variables when needed.

### Default paths

| Variable | Default |
|---|---|
| `NETBOX_RELEASE` | `4.5.7` |
| `NETBOX_SRC` | `~/src/netbox-v${NETBOX_RELEASE}` |
| `NETBOX_PROJECT_DIR` | `${NETBOX_SRC}/netbox` |
| `VENV_DIR` | `~/.virtualenvs/netbox-${NETBOX_RELEASE}` |
| `STATE_DIR` | `~/.config/netbox-rpki-dev` |
| `KRILL_ROOT` | `~/src/krill_for_netbox_rpki` |

### Example: target a different NetBox release

```bash
NETBOX_RELEASE=4.5.0 ./dev.sh start
```

### Other general overrides

`NETBOX_RUN_HOST`, `NETBOX_RUN_PORT`, `NETBOX_E2E_BASE_URL`, `NODE_LTS_BIN`

### Test-specific overrides

These let you point tests at a different database or Redis without changing the dev config:

`NETBOX_CONFIGURATION`, `NETBOX_TEST_DB_NAME`, `NETBOX_TEST_DB_USER`, `NETBOX_TEST_DB_PASSWORD`, `NETBOX_TEST_DB_HOST`, `NETBOX_TEST_DB_PORT`, `NETBOX_TEST_DB_TEST_NAME`, `NETBOX_TEST_REDIS_HOST`, `NETBOX_TEST_REDIS_PORT`, `NETBOX_TEST_REDIS_PASSWORD`

### Docker Compose port overrides (via `devrun/.env`)

| Variable | Default |
|---|---|
| `ROUTINATOR_RTR_PORT` | `3323` |
| `ROUTINATOR_HTTP_PORT` | `8323` |
| `ROUTINATOR_METRICS_PORT` | `9556` |
| `IRRD_HTTP_PORT` | `6080` |
| `IRRD_WHOIS_PORT` | `6043` |
| `IRRD_SOURCE` | `LOCAL-IRR` |

---

## Script Reference

### Primary (`./dev.sh` subcommands)

| Command | Purpose |
|---|---|
| `./dev.sh start` | Full bootstrap + start the dev server |
| `./dev.sh stop` | Stop server, worker, Krill, and containers |
| `./dev.sh status` | Show environment and process health |
| `./dev.sh test [lane]` | Run Python tests (`fast`, `contract` (default), `full`, or explicit labels) |
| `./dev.sh e2e` | Run the Playwright browser suite |
| `./dev.sh seed` | Seed reusable sample RPKI data |
| `./dev.sh validator` | Create/update the local Routinator `ValidatorInstance` in NetBox |
| `./dev.sh irrd <cmd>` | Manage the local IRRd lab (`start`, `stop`, `status`, `logs`, `seed`) |

### Secondary (standalone scripts in `devrun/`)

| Script | Purpose |
|---|---|
| `bootstrap-netbox.sh` | Regenerate credentials, config, migrations, collectstatic, and admin user (no server start) |
| `runserver.sh` | Start just the NetBox dev server |
| `worker.sh` | Start just the RQ worker |
| `check-netbox.sh` | Compare baseline vs. plugin-enabled `manage.py check` |
| `status.sh` | Lower-level status report (used by `dev.sh status`) |
| `stop.sh` | Lower-level stop (used by `dev.sh stop`) |

---

## Generated State Reference

After the first successful bootstrap, these generated files are relevant:

| Path | Contents |
|---|---|
| `devrun/.env` | Docker Compose variables (database credentials, port bindings) |
| `~/.config/netbox-rpki-dev/credentials.env` | `NETBOX_DATABASE_PASSWORD`, `NETBOX_ADMIN_PASSWORD`, `NETBOX_SECRET_KEY`, `NETBOX_API_TOKEN_PEPPER`, `IRRD_DATABASE_PASSWORD`, `IRRD_OVERRIDE_PASSWORD` |
| `~/src/netbox-v4.5.7/netbox/netbox/configuration.py` | Generated NetBox config for the local dev instance |
| `~/.config/netbox-rpki-dev/*.log` | Logs from migrations, checks, collectstatic, seeding, and superuser creation |

IRRd state is retained in the `devrun_irrd_state` Docker volume.

None of these files should be committed to version control.

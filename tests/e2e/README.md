# Browser E2E Tests

This suite uses Playwright against a running NetBox development instance with the `netbox_rpki` plugin enabled.

## What it covers

- organization create, edit, and delete
- certificate create, edit, and delete
- ROA create, edit, and delete
- certificate prefix create, edit, and delete
- certificate ASN create, edit, and delete
- ROA prefix create, edit, and delete

The suite drives the real plugin Web UI and uses the plugin's own add, edit, detail, and delete views. It prefers creating plugin objects through the UI. A setup step only prepares the core NetBox prerequisites that are outside the plugin UI surface, such as ASN, prefix, and RIR records.

## Prerequisites

1. Start the local NetBox dev stack:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./dev.sh start
```

2. Prepare the browser test runtime once:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./e2e.sh install
```

This installs npm dependencies, installs Playwright Chromium, and, on minimal WSL images, bootstraps the small set of Linux shared libraries Chromium needs under the user profile.

3. If you prefer the raw npm workflow instead of the wrapper, install Node dependencies manually:

```bash
cd /home/mencken/src/netbox_rpki
npm install
```

4. If you prefer the raw npm workflow instead of the wrapper, install the Playwright browser runtime manually:

```bash
cd /home/mencken/src/netbox_rpki
npm run playwright:install
```

## Run the suite

Recommended from WSL:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./e2e.sh
```

The wrapper also accepts passthrough Playwright args:

```bash
cd /home/mencken/src/netbox_rpki/devrun
./e2e.sh headed
./e2e.sh tests/e2e/netbox-rpki/roas.spec.js --project=chromium
```

Raw npm invocation remains available if your shell already exposes the required Node and library paths:

```bash
cd /home/mencken/src/netbox_rpki
npm run test:e2e
```

For headed execution:

```bash
cd /home/mencken/src/netbox_rpki
npm run test:e2e:headed
```

## Default environment contract

The suite assumes these defaults unless overridden:

- `NETBOX_E2E_BASE_URL=http://127.0.0.1:8000`
- `NETBOX_E2E_USERNAME=admin`
- `NETBOX_E2E_CREDENTIALS_FILE=~/.config/netbox-rpki-dev/credentials.env`
- `NETBOX_E2E_NETBOX_RELEASE=4.5.7`
- `NETBOX_E2E_NETBOX_PROJECT_DIR=~/src/netbox-v4.5.7/netbox`
- `NETBOX_E2E_VENV_DIR=~/.virtualenvs/netbox-4.5.7`

Optional overrides:

- `NETBOX_E2E_PASSWORD` to bypass the credentials file
- `NETBOX_E2E_PYTHON` to point directly at a specific Python executable
- `NODE_LTS_BIN` to override the user-local Node install path consumed by `devrun/e2e.sh`
- `PLAYWRIGHT_LIB_ROOT` or `PLAYWRIGHT_LIB_DIR` to override the local Linux library bundle location consumed by `devrun/e2e.sh`

## Notes

- `dev.sh seed` is optional. The suite does not depend on seeded plugin data.
- `dev.sh e2e` is equivalent to `./e2e.sh` from the `devrun/` directory.
- The setup phase removes prior plugin objects whose comments start with the E2E marker so stale failures do not accumulate across runs.
- The suite runs with a single Playwright worker because it targets a shared live NetBox database.